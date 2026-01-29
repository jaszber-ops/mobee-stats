import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

REDIS_URL = os.environ.get("UPSTASH_REDIS_URL", "")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_TOKEN", "")

def redis_cmd(cmd):
    """Execute a Redis command via Upstash REST API"""
    url = f"{REDIS_URL}/{cmd}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {REDIS_TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["result"]

def get_leaderboard_data():
    """Fetch and parse all game data from Redis"""
    # Get all Level 1 and Level 2 games
    l1_raw = redis_cmd("lrange/mobee8:events:7/0/-1")
    l2_raw = redis_cmd("lrange/mobee8:events:12/0/-1")

    # Parse games - track avatar with timestamp for most recent
    games = []
    player_avatar_times = {}  # {code: (timestamp, avatar)}

    for raw in l1_raw + l2_raw:
        g = json.loads(raw)
        level = 1 if g.get("symbolsPerCard") == 7 else 2
        ts = g["startedAt"] / 1000

        for code, score in g.get("scores", {}).items():
            games.append({
                "user_code": code,
                "score": score,
                "level": level,
                "timestamp": ts,
                "city": g.get("locations", {}).get(code, {}).get("city", ""),
                "room": g.get("roomId", "")
            })

            # Only update avatar if this game is more recent
            if code in g.get("avatars", {}):
                avatar = g["avatars"][code]
                if code not in player_avatar_times or ts > player_avatar_times[code][0]:
                    player_avatar_times[code] = (ts, avatar)

    # Extract just avatars (most recent per player)
    player_avatars = {code: av for code, (_, av) in player_avatar_times.items()}

    return {
        "recent_games": games,
        "player_avatars": player_avatars,
        "legacy_summary": {},
        "symbols": [],
        "meta": {
            "l1_count": len(l1_raw),
            "l2_count": len(l2_raw),
            "total_games": len(games),
            "players": len(player_avatars)
        }
    }

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not REDIS_URL or not REDIS_TOKEN:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Redis credentials not configured"}).encode())
                return

            data = get_leaderboard_data()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "s-maxage=60, stale-while-revalidate=30")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
