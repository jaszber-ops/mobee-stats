from http.server import BaseHTTPRequestHandler
import requests
import re
from collections import defaultdict, Counter
import json

# Slack credentials from environment variables
import os
SLACK_TOKEN = os.environ.get('SLACK_TOKEN', '')
CHANNEL_ID = os.environ.get('CHANNEL_ID', '')

def fetch_slack_messages(channel_id, token):
    """Fetch all messages from a Slack channel"""
    messages = []
    cursor = None

    url = "https://slack.com/api/conversations.history"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    while True:
        params = {
            "channel": channel_id,
            "limit": 1000
        }
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        if not data.get("ok"):
            break

        messages.extend(data.get("messages", []))

        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return messages

def parse_game_notification(text):
    """Parse a game notification message to extract data"""

    is_high_score = "🏆 HIGH SCORE:" in text or "HIGH SCORE:" in text or ":trophy: HIGH SCORE:" in text

    score_match = re.search(r'(?:HIGH SCORE|Score):\s*(\d+)', text)
    if not score_match:
        return None

    score = int(score_match.group(1))

    location_match = re.search(r'\|\s*([^|]+),\s*([^|]+)\s*\|', text)
    city = location_match.group(1).strip() if location_match else "Unknown"
    country = location_match.group(2).strip() if location_match else "Unknown"

    platform_match = re.search(r'\|\s*([^|]+)\s*\|\s*[a-zA-Z0-9]+\s*#', text)
    platform = platform_match.group(1).strip() if platform_match else "Unknown"

    user_match = re.search(r'\|\s*([a-zA-Z0-9]+)\s*#\d+', text)
    user_code = user_match.group(1).strip() if user_match else "Unknown"

    game_num_match = re.search(r'#(\d+)', text)
    game_number = int(game_num_match.group(1)) if game_num_match else 0

    game_code_match = re.search(r'Code:\s*(MOBEE-[0-9A-Z-]+)', text)
    game_code = game_code_match.group(1) if game_code_match else "Unknown"

    return {
        "is_high_score": is_high_score,
        "score": score,
        "city": city,
        "country": country,
        "platform": platform,
        "user_code": user_code,
        "game_number": game_number,
        "game_code": game_code
    }

def analyze_games(games):
    """Analyze game data and generate statistics"""

    if not games:
        return None

    total_games = len(games)
    unique_players = len(set(g["user_code"] for g in games))
    high_score_games = sum(1 for g in games if g["is_high_score"])

    scores = [g["score"] for g in games]
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)
    min_score = min(scores)

    city_counts = Counter(g["city"] for g in games)
    country_counts = Counter(g["country"] for g in games)

    platform_counts = Counter(g["platform"] for g in games)
    platform_scores = defaultdict(list)
    for game in games:
        platform_scores[game["platform"]].append(game["score"])

    player_games = defaultdict(list)
    player_high_scores = defaultdict(int)
    player_cities = defaultdict(set)
    player_platforms = defaultdict(set)

    for game in games:
        player_games[game["user_code"]].append(game["score"])
        if game["score"] > player_high_scores[game["user_code"]]:
            player_high_scores[game["user_code"]] = game["score"]
        player_cities[game["user_code"]].add(game["city"])
        player_platforms[game["user_code"]].add(game["platform"])

    one_time_players = sum(1 for scores in player_games.values() if len(scores) == 1)
    returning_players = sum(1 for scores in player_games.values() if len(scores) > 1)
    super_engaged = sum(1 for scores in player_games.values() if len(scores) >= 10)

    location_scores = defaultdict(list)
    for game in games:
        location_scores[game["country"]].append(game["score"])

    top_players_by_games = sorted(
        player_games.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )[:10]

    top_players_by_score = sorted(
        player_high_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]

    score_ranges = {
        "0-5": 0,
        "6-10": 0,
        "11-15": 0,
        "16-20": 0,
        "20+": 0
    }

    for score in scores:
        if score <= 5:
            score_ranges["0-5"] += 1
        elif score <= 10:
            score_ranges["6-10"] += 1
        elif score <= 15:
            score_ranges["11-15"] += 1
        elif score <= 20:
            score_ranges["16-20"] += 1
        else:
            score_ranges["20+"] += 1

    return {
        "total_games": total_games,
        "unique_players": unique_players,
        "high_score_games": high_score_games,
        "avg_score": avg_score,
        "max_score": max_score,
        "min_score": min_score,
        "city_counts": dict(city_counts),
        "country_counts": dict(country_counts),
        "platform_counts": dict(platform_counts),
        "platform_scores": {k: {"count": len(v), "avg": sum(v)/len(v), "max": max(v)} for k, v in platform_scores.items()},
        "location_scores": {k: {"count": len(v), "avg": sum(v)/len(v)} for k, v in location_scores.items()},
        "engagement": {
            "one_time_players": one_time_players,
            "returning_players": returning_players,
            "super_engaged": super_engaged
        },
        "player_cities": {k: len(v) for k, v in player_cities.items()},
        "player_platforms": {k: len(v) for k, v in player_platforms.items()},
        "top_players_by_games": [[p, scores] for p, scores in top_players_by_games],
        "top_players_by_score": [[p, score] for p, score in top_players_by_score],
        "score_distribution": score_ranges
    }

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Fetch and analyze data
            messages = fetch_slack_messages(CHANNEL_ID, SLACK_TOKEN)

            games = []
            for msg in messages:
                text = msg.get("text", "")
                if "Score:" in text or "HIGH SCORE:" in text:
                    parsed = parse_game_notification(text)
                    if parsed and parsed["score"] <= 30:  # Ignore scores over 30
                        games.append(parsed)

            stats = analyze_games(games)

            # Return JSON response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
