"""
Vercel Cron Job Handler for Daily Mobee Stats Report
Generates stats and sends to Slack
"""

from http.server import BaseHTTPRequestHandler
import requests
import re
from collections import defaultdict, Counter
from datetime import datetime
import json
import os

# Slack credentials
SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
REPORT_CHANNEL_ID = os.environ.get('REPORT_CHANNEL_ID', CHANNEL_ID)
CRON_SECRET = os.environ.get('CRON_SECRET', '')

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
        params = {"channel": channel_id, "limit": 1000}
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

def parse_game_notification(text, timestamp=None):
    """Parse a game notification message"""
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

    return {
        "is_high_score": is_high_score,
        "score": score,
        "city": city,
        "country": country,
        "platform": platform,
        "user_code": user_code,
        "timestamp": timestamp
    }

def analyze_games(games):
    """Analyze game data"""
    if not games:
        return None

    total_games = len(games)
    unique_players = len(set(g["user_code"] for g in games))
    high_score_games = sum(1 for g in games if g["is_high_score"])

    scores = [g["score"] for g in games]
    avg_score = sum(scores) / len(scores)
    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores)//2] if len(sorted_scores) % 2 == 1 else (sorted_scores[len(sorted_scores)//2-1] + sorted_scores[len(sorted_scores)//2]) / 2
    max_score = max(scores)

    platform_counts = Counter(g["platform"] for g in games)
    country_counts = Counter(g["country"] for g in games)

    player_games = defaultdict(list)
    player_high_scores = defaultdict(int)

    for game in games:
        player_games[game["user_code"]].append(game["score"])
        if game["score"] > player_high_scores[game["user_code"]]:
            player_high_scores[game["user_code"]] = game["score"]

    top_players_by_games = sorted(player_games.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    top_players_by_score = sorted(player_high_scores.items(), key=lambda x: x[1], reverse=True)[:10]

    # Engagement
    one_time_players = sum(1 for scores in player_games.values() if len(scores) == 1)
    returning_players = sum(1 for scores in player_games.values() if len(scores) > 1)

    # Daily stats
    daily_stats = defaultdict(lambda: {"games": 0, "players": set()})
    for game in games:
        if game.get("timestamp"):
            date = datetime.fromtimestamp(game["timestamp"]).strftime("%Y-%m-%d")
            daily_stats[date]["games"] += 1
            daily_stats[date]["players"].add(game["user_code"])

    recent_days = sorted(daily_stats.items(), reverse=True)[:7]

    return {
        "total_games": total_games,
        "unique_players": unique_players,
        "high_score_games": high_score_games,
        "avg_score": avg_score,
        "median_score": median_score,
        "max_score": max_score,
        "top_players_by_games": top_players_by_games,
        "top_players_by_score": top_players_by_score,
        "platform_counts": dict(platform_counts),
        "country_counts": dict(country_counts),
        "one_time_players": one_time_players,
        "returning_players": returning_players,
        "recent_days": recent_days
    }

def send_slack_report(stats):
    """Send formatted report to Slack"""

    # Create rich Slack blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Mobee Game Statistics - {datetime.now().strftime('%B %d, %Y')}",
                "emoji": True
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Total Games:*\n{stats['total_games']:,}"},
                {"type": "mrkdwn", "text": f"*Unique Players:*\n{stats['unique_players']:,}"},
                {"type": "mrkdwn", "text": f"*High Score Games:*\n{stats['high_score_games']:,}"},
                {"type": "mrkdwn", "text": f"*Avg Score:*\n{stats['avg_score']:.2f}"}
            ]
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Median Score:*\n{stats['median_score']:.2f}"},
                {"type": "mrkdwn", "text": f"*Highest Score:*\n{stats['max_score']}"},
                {"type": "mrkdwn", "text": f"*New Players:*\n{stats['one_time_players']}"},
                {"type": "mrkdwn", "text": f"*Returning:*\n{stats['returning_players']}"}
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*🏆 Top 5 Players by Games Played:*"}
        }
    ]

    # Add top players
    top_players_text = ""
    for i, (player, scores) in enumerate(stats['top_players_by_games'][:5], 1):
        avg = sum(scores) / len(scores)
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
        top_players_text += f"{medal} `{player}` - {len(scores)} games (avg: {avg:.1f})\n"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": top_players_text}
    })

    # Add top scores
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*🎯 Top 5 High Scores:*"}
    })

    top_scores_text = ""
    for i, (player, score) in enumerate(stats['top_players_by_score'][:5], 1):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
        top_scores_text += f"{medal} `{player}` - {score} points\n"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": top_scores_text}
    })

    # Add recent activity
    if stats['recent_days']:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📈 Last 7 Days Activity:*"}
        })

        activity_text = ""
        for date, data in stats['recent_days']:
            activity_text += f"• {date}: {data['games']} games, {len(data['players'])} players\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": activity_text}
        })

    # Add footer
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"📄 Full dashboard: https://your-project.vercel.app | Generated at {datetime.now().strftime('%I:%M %p UTC')}"
            }
        ]
    })

    # Send to Slack
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'channel': REPORT_CHANNEL_ID,
            'blocks': blocks,
            'text': f'Daily Mobee Stats - {stats["total_games"]} games',
            'unfurl_links': False,
            'unfurl_media': False
        }
    )

    return response.json()

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle cron job trigger"""
        try:
            # Verify authorization
            if CRON_SECRET:
                auth_header = self.headers.get('Authorization', '')
                if auth_header != f'Bearer {CRON_SECRET}':
                    self.send_response(401)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                    return

            # Fetch and analyze data
            messages = fetch_slack_messages(CHANNEL_ID, SLACK_TOKEN)

            games = []
            for msg in messages:
                text = msg.get("text", "")
                if "Score:" in text or "HIGH SCORE:" in text:
                    timestamp = float(msg.get("ts", 0))
                    parsed = parse_game_notification(text, timestamp)
                    if parsed and parsed["score"] <= 30:
                        games.append(parsed)

            stats = analyze_games(games)

            if not stats:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'No game data found'}).encode())
                return

            # Send to Slack
            slack_result = send_slack_report(stats)

            # Return success
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'success': True,
                'stats_summary': {
                    'total_games': stats['total_games'],
                    'unique_players': stats['unique_players'],
                    'avg_score': round(stats['avg_score'], 2)
                },
                'slack_ok': slack_result.get('ok'),
                'timestamp': datetime.now().isoformat()
            }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
