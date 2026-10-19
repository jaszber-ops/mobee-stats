"""Global boards. tvOS submissions are client-reported, not cheat-proof."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import hashlib
import json
import os
import time
import urllib.request
import uuid

PREFIX = "mobee:solo:tvos:v1"
RULES = "tvos-easy-60-v1"
BOARDS = {"tvos": (PREFIX, RULES),
          "ios": ("mobee:solo:ios:easy:v1", "ios-easy-60-v1"),
          "ios-standard": ("mobee:solo:ios:standard:v1", "ios-standard-60-v1")}
RULE_PREFIXES = {rules: prefix for prefix, rules in BOARDS.values()}
MAX_BODY = 32768  # score + per-tap telemetry

def redis_cmd(*args):
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("UPSTASH_REDIS_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("UPSTASH_REDIS_TOKEN")
    if not url or not token:
        raise RuntimeError("Redis configuration missing")
    request = urllib.request.Request(url, data=json.dumps(args).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    if data.get("error"):
        raise RuntimeError("Redis operation failed")
    return data.get("result")

def valid_uuid(value):
    if not isinstance(value, str):
        raise ValueError("Invalid identifier")
    return str(uuid.UUID(value))

def location_from_headers(headers):
    """Coarse player location (city, country) from Vercel's edge geo headers; never the raw address."""
    city = unquote(headers.get("x-vercel-ip-city", "") or "").strip()[:40]
    country = (headers.get("x-vercel-ip-country", "") or "").strip().upper()[:2]
    if not country.isalpha():
        return None
    return {"city": city, "country": country}

def validate_submission(data):
    if not isinstance(data, dict) or data.get("rules") not in RULE_PREFIXES:
        raise ValueError("Unsupported rules")
    identifier = valid_uuid(data.get("id"))
    player = valid_uuid(data.get("playerId"))
    score = data.get("score")
    if type(score) is not int or not 0 <= score <= 120:
        raise ValueError("Invalid score")
    if data.get("durationSeconds") != 60:
        raise ValueError("Only completed 60-second games qualify")
    avatar = data.get("avatar")
    if avatar not in {f"{r}-{c}" for r in range(1, 11) for c in range(1, 14)}:
        raise ValueError("Invalid avatar")
    completed = data.get("completedAt")
    if type(completed) not in (int, float) or not 0 < completed <= time.time() + 300:
        raise ValueError("Invalid completion time")
    entry = {"id": identifier, "playerId": player, "avatar": avatar, "score": score,
             "completedAt": completed, "receivedAt": time.time(), "rules": data["rules"],
             "displayName": "Player " + player[:6].upper()}
    # Optional gameplay telemetry (every tap and every deal); kept with the game record only.
    telemetry = {}
    for key, limit in (("taps", 400), ("rounds", 200)):
        items = data.get(key)
        if isinstance(items, list) and len(items) <= limit and all(isinstance(i, dict) for i in items):
            telemetry[key] = items
    if isinstance(data.get("client"), dict):
        telemetry["client"] = {k: str(v)[:64] for k, v in list(data["client"].items())[:8]}
    if telemetry:
        entry["telemetry"] = telemetry
    return entry

# Idempotent game receipt and best-per-player update in one atomic transaction.
# Sorting metadata uses server receipt time to avoid trusting client time for ties.
# KEYS: games, best, players, avatars. ARGV: game id, player id, full record, score, board record, avatar.
SAVE = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[3])
redis.call('HSET', KEYS[4], ARGV[2], ARGV[6])
local old = redis.call('ZSCORE', KEYS[2], ARGV[2])
if not old or tonumber(ARGV[4]) > tonumber(old) then
  redis.call('ZADD', KEYS[2], ARGV[4], ARGV[2])
  redis.call('HSET', KEYS[3], ARGV[2], ARGV[5])
end
return 1
"""
RATE = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], 600) end
return n
"""

def save_score(data, address, location=None):
    entry = validate_submission(data)
    if location:
        entry["location"] = location
    prefix = RULE_PREFIXES[entry["rules"]]
    # Vercel supplies the client address. Store only a short hash, with a 10-minute TTL.
    digest = hashlib.sha256(address.encode()).hexdigest()[:24]
    if int(redis_cmd("EVAL", RATE, 1, prefix + ":rate:" + digest)) > 120:
        return 429, {"error": "Too many submissions; try again later"}
    board_entry = {k: v for k, v in entry.items() if k != "telemetry"}
    fresh = redis_cmd("EVAL", SAVE, 4, prefix + ":games", prefix + ":best",
                      prefix + ":players", prefix + ":avatars", entry["id"], entry["playerId"],
                      json.dumps(entry), entry["score"], json.dumps(board_entry), entry["avatar"])
    return 200, {"accepted": True, "duplicate": not bool(fresh), "id": entry["id"]}

def tv_board(board="tvos"):
    prefix = BOARDS[board][0]
    # Include every player tied at the top-10 cutoff, then apply deterministic tie order.
    top = redis_cmd("ZREVRANGE", prefix + ":best", 0, 9) or []
    if not top:
        return []
    cutoff = redis_cmd("ZSCORE", prefix + ":best", top[-1])
    players = redis_cmd("ZREVRANGEBYSCORE", prefix + ":best", "+inf", cutoff) or []
    raw = redis_cmd("HMGET", prefix + ":players", *players) if players else []
    entries = [json.loads(item) for item in raw if item]
    # Show each player's current avatar, not the one worn when the best score was set.
    current = redis_cmd("HMGET", prefix + ":avatars", *[e["playerId"] for e in entries]) if entries else []
    for e, avatar in zip(entries, current):
        if avatar:
            e["avatar"] = avatar
    return sorted(entries, key=lambda e: (-e["score"], e["receivedAt"], e["id"]))[:10]

def legacy_board():
    raw = json.loads((Path(__file__).resolve().parent.parent / "mobee_games_raw.json").read_text())
    best = {}
    for game in raw:
        player = game.get("user_code")
        score = game.get("score")
        if not player or type(score) is not int or score < 0:
            continue
        entry = {"id": "legacy:" + player, "playerId": player, "avatar": "",
                 "displayName": player, "score": score, "rules": "legacy",
                 "completedAt": float(game.get("timestamp", 0))}
        previous = best.get(player)
        if previous is None or score > previous["score"]:
            best[player] = entry
    return sorted(best.values(), key=lambda e: (-e["score"], e["completedAt"], e["id"]))[:10]

class handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        board = parse_qs(urlparse(self.path).query).get("board", ["tvos"])[0]
        if board not in (*BOARDS, "legacy"):
            return self.reply(400, {"error": "Unknown leaderboard"})
        try:
            entries = legacy_board() if board == "legacy" else tv_board(board)
            self.reply(200, {"board": board, "entries": entries,
                            "source": "legacy_snapshot" if board == "legacy" else "global",
                            "validation": "historical" if board == "legacy" else "client_reported"})
        except Exception:
            self.reply(503, {"error": "Leaderboard temporarily unavailable"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                return self.reply(413, {"error": "Invalid request size"})
            data = json.loads(self.rfile.read(length))
            address = self.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()
            status, response = save_score(data, address, location_from_headers(self.headers))
            self.reply(status, response)
        except (ValueError, TypeError, AttributeError):
            self.reply(400, {"error": "Invalid score submission"})
        except Exception:
            self.reply(503, {"error": "Score service unavailable; retry later"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
