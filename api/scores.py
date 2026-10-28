"""Global boards. Scores are client-reported; iOS/web games must carry tap telemetry that replays to the claimed score and looks human."""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import hashlib
import re
import json
import os
import time
import unicodedata
import urllib.request
import uuid

PREFIX = "mobee:solo:tvos:v1"
RULES = "tvos-easy-60-v1"
BOARDS = {"tvos": (PREFIX, RULES),
          "ios": ("mobee:solo:ios:easy:v1", "ios-easy-60-v1"),
          "ios-standard": ("mobee:solo:ios:standard:v1", "ios-standard-60-v1"),
          "twin": ("mobee:solo:twin:green:v1", "twin-green-120-v1")}
RULE_PREFIXES = {rules: prefix for prefix, rules in BOARDS.values()}
# Per game: clock length, cards in the deck, and whether a round is won by naming two shared symbols (Møbee Twin).
RULE_SPECS = {"tvos-easy-60-v1": {"seconds": 60, "deck": 8, "pair": False},
              "ios-easy-60-v1": {"seconds": 60, "deck": 8, "pair": False},
              "ios-standard-60-v1": {"seconds": 60, "deck": 10, "pair": False},
              "twin-green-120-v1": {"seconds": 120, "deck": 12, "pair": True}}
MAX_BODY = 32768  # score + per-tap telemetry
GAME_MS = 60000
MIN_TAP_GAP_MS = 100      # two taps closer than this are not fingers
MIN_REACTION_MS = 150     # deal -> correct tap; faster than any human on a fresh set of cards
MIN_MEDIAN_REACTION_MS = 400
MIN_REACTION_SPREAD = 0.12  # std/mean of reaction times over 8+ rounds; a bot is metronomic

NAME_MAX = 16  # same limit as the app's name field

# Names nobody should see on a public board. Kept identical to www/scores.js in mobee-ios.
# ANYWHERE: blocked wherever they appear, even inside a longer name or spelled out ("f.u.u.c.k", "sh1t").
# WORDS: blocked only as a whole word, because they also occur inside ordinary names (Szarvas, Hancock).
BLOCKED_ANYWHERE = ["fuck", "fck", "cunt", "nigger", "nigga", "faggot", "bitch", "whore", "asshole", "dickhead",
                    "motherf", "hitler", "porn", "rapist", "kurva", "geci", "fasz", "picsa", "bazmeg", "baszd",
                    "kocsog", "ribanc", "csicska", "ficken", "fotze", "wichser", "hurensohn", "schlampe"]
BLOCKED_WORDS = ["ass", "arse", "shit", "dick", "cock", "tits", "sex", "anal", "cum", "piss", "penis", "slut",
                 "rape", "retard", "nazi", "szar", "segg", "pina", "buzi", "basz", "arsch", "hure", "kacke",
                 "scheisse", "scheise", "titten", "nutte"]
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s",
                      "!": "i", "\u00f8": "o", "\u00df": "ss"})

def _letters_pattern(word):
    """f+u+c+k+ : each letter may be repeated ("fuuuck"), but no letter may be dropped ("niger" stays allowed)."""
    return "".join(re.escape(c) + "+" for c in word)

BLOCKED_ANYWHERE_RE = re.compile("|".join(_letters_pattern(w) for w in BLOCKED_ANYWHERE))
BLOCKED_WORDS_RE = re.compile("^(?:" + "|".join(_letters_pattern(w) for w in BLOCKED_WORDS) + ")$")

def name_blocked(name):
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(ch))
    plain = plain.translate(LEET)
    joined = re.sub(r"[^a-z]", "", plain)
    if BLOCKED_ANYWHERE_RE.search(joined):
        return True
    return any(BLOCKED_WORDS_RE.match(w) for w in re.split(r"[^a-z]+", plain) + [joined] if w)

def clean_name(raw):
    """Player name as the app sends it: ("set", name), ("clear", "") for an emptied name, or None to
    leave the stored name alone. A name we can't accept is ignored, never a reason to refuse the score:
    the app keeps re-sending anything answered with 400, so a bad name must not block its queue."""
    if raw is None or not isinstance(raw, str):
        return None
    text = "".join(ch for ch in unicodedata.normalize("NFKC", raw) if not unicodedata.category(ch).startswith("C"))
    name = " ".join(text.split())[:NAME_MAX].strip()
    if not name:
        return ("clear", "")
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)).lower()
    if "mobee" in plain or "m\u00f8bee" in plain:  # "Møbee" names are reserved, as in the app
        return None
    if name_blocked(name):  # shown as the default "Player", as if no name were set; the score still counts
        return ("clear", "")
    return ("set", name)

BOARD_LABELS = {"ios": "Easy", "ios-standard": "Hard", "tvos": "Apple TV", "twin": "Twin"}
SLACK_TIMEOUT = 3  # seconds; a slow Slack must never hold up a score

def slack_post(text):
    """Post one message to Slack, via SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN + SLACK_CHANNEL_ID.
    Returns False (and does nothing) when neither is configured or Slack fails."""
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    token, channel = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_CHANNEL_ID")
    if webhook:
        url, body, headers = webhook, {"text": text}, {}
    elif token and channel:
        url, body = "https://slack.com/api/chat.postMessage", {"channel": channel, "text": text, "unfurl_links": False}
        headers = {"Authorization": "Bearer " + token}
    else:
        return False
    try:
        request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json; charset=utf-8", **headers})
        with urllib.request.urlopen(request, timeout=SLACK_TIMEOUT) as response:
            return response.status == 200
    except Exception:
        return False

def player_label(entry):
    return entry.get("name") or entry.get("displayName") or "Player"

def where(entry):
    loc = entry.get("location") or {}
    place = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
    app = ((entry.get("telemetry") or {}).get("client") or {}).get("app")
    return " · ".join(x for x in (place, app) if x)

def announce_top_ten(entry, prefix):
    """After a new game is stored: if it set the player's best and that best is in the board's top 10,
    ping Slack ("New #1 on Easy" / "#4 on Hard"). Never raises."""
    try:
        board = next(b for b, (p, _) in BOARDS.items() if p == prefix)
        stored = redis_cmd("HGET", prefix + ":players", entry["playerId"])
        if not stored or json.loads(stored).get("id") != entry["id"]:
            return False  # not a new personal best
        rank = int(redis_cmd("ZCOUNT", prefix + ":best", "(" + str(entry["score"]), "+inf")) + 1
        if rank > 10:
            return False
        players = int(redis_cmd("ZCARD", prefix + ":best"))
        head = f":trophy: *New #1 on {BOARD_LABELS[board]}*" if rank == 1 else f":star: *#{rank} on {BOARD_LABELS[board]}*"
        detail = f"{player_label(entry)} — {entry['score']} points"
        tail = " · ".join(x for x in (where(entry), f"{players} players on the board") if x)
        return slack_post(f"{head}: {detail}\n{tail}")
    except Exception:
        return False

class Suspicious(ValueError):
    """Submission is well-formed but the telemetry does not support the score; answered with 422."""

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
    spec = RULE_SPECS[data["rules"]]
    if type(score) is not int or not 0 <= score <= 2 * spec["seconds"]:
        raise ValueError("Invalid score")
    if data.get("durationSeconds") != spec["seconds"]:
        raise ValueError(f"Only completed {spec['seconds']}-second games qualify")
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
    name = clean_name(data.get("name"))
    if name:
        entry["nameUpdate"] = name[0]
        if name[0] == "set":
            entry["name"] = name[1]
    if telemetry:
        entry["telemetry"] = telemetry
    if data["rules"].startswith(("ios-", "twin-")) or "taps" in telemetry:
        verify_telemetry(entry)
    return entry

def verify_telemetry(entry):
    """Replay the deal/tap log: it must reproduce the score, respect the game's sequence and clock, and show human timing."""
    telemetry = entry.get("telemetry", {})
    rounds, taps = telemetry.get("rounds"), telemetry.get("taps")
    if not rounds or taps is None:
        raise Suspicious("Telemetry required")
    spec = RULE_SPECS.get(entry["rules"], RULE_SPECS[RULES])
    deck_size, game_ms, pair = spec["deck"], spec["seconds"] * 1000, spec["pair"]
    def answer_of(r):
        """The round's answer: one symbol, or (Twin) the set of the two shared symbols."""
        if not pair:
            return r.get("answer") if isinstance(r.get("answer"), str) else None
        a = r.get("answers")
        return frozenset(a) if isinstance(a, list) and len(a) == 2 and all(isinstance(x, str) for x in a) and len(set(a)) == 2 else None
    for i, r in enumerate(rounds):
        cards = r.get("cards")
        if r.get("r") != i + 1 or type(r.get("t")) is not int or not 0 <= r["t"] <= game_ms \
                or not (isinstance(cards, list) and len(set(map(str, cards))) == 3 and all(type(c) is int and 0 <= c < deck_size for c in cards)) \
                or answer_of(r) is None or (i and r["t"] < rounds[i - 1]["t"]):
            raise Suspicious("Malformed round" if type(r.get("t")) is not int or r.get("t", 0) <= game_ms else "Deals after the game clock")
    score, rnd, last_t, reactions = 0, 1, -MIN_TAP_GAP_MS, []
    for tap in taps:
        t, ok, sym = tap.get("t"), tap.get("ok"), tap.get("s")
        if pair:
            named = frozenset(sym) if isinstance(sym, list) and len(sym) == 2 and all(isinstance(x, str) for x in sym) and len(set(sym)) == 2 else None
        else:
            named = sym if isinstance(sym, str) else None
        if tap.get("r") != rnd or type(t) is not int or type(ok) is not bool or named is None \
                or t < rounds[rnd - 1]["t"] or t - last_t < MIN_TAP_GAP_MS or ok != (named == answer_of(rounds[rnd - 1])):
            raise Suspicious("Malformed tap")
        if t > game_ms:
            raise Suspicious("Taps after the game clock")
        last_t = t
        score = max(0, score + (1 if ok else -1))
        if ok:
            reactions.append(t - rounds[rnd - 1]["t"])
            rnd += 1
            if rnd > len(rounds):
                raise Suspicious("Correct tap without a following deal")
    if rnd != len(rounds) or score != entry["score"]:
        raise Suspicious("Telemetry does not reproduce the score")
    if reactions:
        reactions.sort()
        mean = sum(reactions) / len(reactions)
        spread = (sum((x - mean) ** 2 for x in reactions) / len(reactions)) ** 0.5 / mean
        if reactions[0] < MIN_REACTION_MS or reactions[len(reactions) // 2] < MIN_MEDIAN_REACTION_MS \
                or (len(reactions) >= 8 and spread < MIN_REACTION_SPREAD):
            raise Suspicious("Inhuman reaction times")

# Idempotent game receipt and best-per-player update in one atomic transaction.
# Sorting metadata uses server receipt time to avoid trusting client time for ties.
# KEYS: games, best, players, avatars, names.
# ARGV: game id, player id, full record, score, board record, avatar, name action (keep|set|clear), name.
SAVE = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[3])
redis.call('HSET', KEYS[4], ARGV[2], ARGV[6])
if ARGV[7] == 'set' then redis.call('HSET', KEYS[5], ARGV[2], ARGV[8])
elseif ARGV[7] == 'clear' then redis.call('HDEL', KEYS[5], ARGV[2]) end
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
    try:
        entry = validate_submission(data)
    except Suspicious as reason:
        game_id = data.get("id") if isinstance(data, dict) else None
        if isinstance(game_id, str) and len(game_id) <= 40 and data.get("rules") in RULE_PREFIXES:
            redis_cmd("HSET", RULE_PREFIXES[data["rules"]] + ":rejected", game_id,
                      json.dumps({"reason": str(reason), "receivedAt": time.time(), "submission": data}))
        return 422, {"accepted": False, "error": str(reason)}
    if location:
        entry["location"] = location
    prefix = RULE_PREFIXES[entry["rules"]]
    # Vercel supplies the client address. Store only a short hash, with a 10-minute TTL.
    digest = hashlib.sha256(address.encode()).hexdigest()[:24]
    if int(redis_cmd("EVAL", RATE, 1, prefix + ":rate:" + digest)) > 120:
        return 429, {"error": "Too many submissions; try again later"}
    action = entry.pop("nameUpdate", "keep")
    board_entry = {k: v for k, v in entry.items() if k not in ("telemetry", "name")}
    fresh = redis_cmd("EVAL", SAVE, 5, prefix + ":games", prefix + ":best",
                      prefix + ":players", prefix + ":avatars", prefix + ":names", entry["id"], entry["playerId"],
                      json.dumps(entry), entry["score"], json.dumps(board_entry), entry["avatar"],
                      action, entry.get("name", ""))
    if fresh:
        announce_top_ten(entry, prefix)
    return 200, {"accepted": True, "duplicate": not bool(fresh), "id": entry["id"]}

BOARD_LUA = """
local top = redis.call('ZREVRANGE', KEYS[1], 0, 9)
if #top == 0 then return {} end
local cutoff = redis.call('ZSCORE', KEYS[1], top[#top])
local players = redis.call('ZREVRANGEBYSCORE', KEYS[1], '+inf', cutoff)
return {redis.call('HMGET', KEYS[2], unpack(players)), redis.call('HMGET', KEYS[3], unpack(players)),
        redis.call('HMGET', KEYS[4], unpack(players))}
"""

def tv_board(board="tvos"):
    prefix = BOARDS[board][0]
    # One round trip: top 10 plus everyone tied at the cutoff, their records, current avatars and names.
    result = redis_cmd("EVAL", BOARD_LUA, 4, prefix + ":best", prefix + ":players", prefix + ":avatars",
                       prefix + ":names")
    if not result:
        return []
    raw, avatars, names = result
    entries = []
    for item, avatar, name in zip(raw, avatars, names):
        if not item:
            continue
        e = json.loads(item)
        # Show each player's current avatar, not the one worn when the best score was set.
        if avatar:
            e["avatar"] = avatar
        # Likewise the player's current name; players who never set one keep "Player XXXXXX".
        if name:
            e["name"] = e["displayName"] = name
        entries.append(e)
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
    def reply(self, status, data, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        board = parse_qs(urlparse(self.path).query).get("board", ["tvos"])[0]
        if board not in (*BOARDS, "legacy"):
            return self.reply(400, {"error": "Unknown leaderboard"})
        try:
            entries = legacy_board() if board == "legacy" else tv_board(board)
            # Edge-cached for a few seconds so repeat views skip the function entirely; clients that
            # just posted a score add a cache-busting query parameter to read through.
            self.reply(200, {"board": board, "entries": entries,
                            "source": "legacy_snapshot" if board == "legacy" else "global",
                            "validation": "historical" if board == "legacy" else "telemetry_replayed"},
                       cache="public, max-age=0, s-maxage=5, stale-while-revalidate=60")
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
