from http.server import BaseHTTPRequestHandler
import requests
import re
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import json
import os
import io
import base64

# Import for PDF generation
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.style.use('seaborn-v0_8-darkgrid')
except ImportError as e:
    print(f"Missing dependency: {e}")

# Slack credentials from environment variables
SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
REPORT_CHANNEL_ID = os.environ.get('REPORT_CHANNEL_ID', CHANNEL_ID)  # Channel to send daily reports

# Import the functions from the main script
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

def send_slack_report(stats, pdf_bytes):
    """Send formatted report to Slack with PDF attachment"""

    # Create summary text
    summary = f"""📊 *Daily Mobee Game Statistics Report*

*Overall Stats:*
• Total Games: {stats['total_games']}
• Unique Players: {stats['unique_players']}
• High Score Games: {stats['high_score_games']}

*Score Stats:*
• Average Score: {stats['avg_score']:.2f}
• Median Score: {stats['median_score']:.2f}
• Highest Score: {stats['max_score']}

*Top 3 Players by Games:*
"""

    for i, (player, scores) in enumerate(stats['top_players_by_games'][:3], 1):
        avg = sum(scores) / len(scores)
        summary += f"{i}. `{player}` - {len(scores)} games (avg: {avg:.1f})\n"

    summary += f"\n*Top 3 High Scores:*\n"
    for i, (player, score) in enumerate(stats['top_players_by_score'][:3], 1):
        summary += f"{i}. `{player}` - {score} points\n"

    summary += "\n📄 Full PDF report attached below."

    # Post the message
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'channel': REPORT_CHANNEL_ID,
            'text': summary,
            'unfurl_links': False,
            'unfurl_media': False
        }
    )

    if not response.json().get('ok'):
        return {'success': False, 'error': f"Error posting message: {response.json()}"}

    # Upload the PDF
    response = requests.post(
        'https://slack.com/api/files.upload',
        headers={'Authorization': f'Bearer {SLACK_TOKEN}'},
        files={'file': ('mobee_stats_report.pdf', pdf_bytes, 'application/pdf')},
        data={
            'channels': REPORT_CHANNEL_ID,
            'title': f'Mobee Stats Report - {stats["total_games"]} Games',
            'initial_comment': 'Daily Statistics Report'
        }
    )

    if response.json().get('ok'):
        return {'success': True}
    else:
        return {'success': False, 'error': f"Error uploading PDF: {response.json()}"}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle cron job trigger"""
        try:
            # Verify authorization (Vercel sets this header for cron jobs)
            auth_header = self.headers.get('Authorization')
            cron_secret = os.environ.get('CRON_SECRET', '')

            if cron_secret and auth_header != f'Bearer {cron_secret}':
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())
                return

            # Fetch messages and generate stats
            messages = fetch_slack_messages(CHANNEL_ID, SLACK_TOKEN)

            games = []
            for msg in messages:
                text = msg.get("text", "")
                if "Score:" in text or "HIGH SCORE:" in text:
                    parsed = parse_game_notification(text)
                    if parsed and parsed["score"] <= 30:
                        # Add timestamp
                        if "ts" in msg:
                            parsed["timestamp"] = float(msg["ts"])
                        games.append(parsed)

            # Note: For Vercel, we'll create a simplified stats analysis
            # Full analyze_games function would be imported or recreated here
            stats = {
                'total_games': len(games),
                'unique_players': len(set(g["user_code"] for g in games)),
                'high_score_games': sum(1 for g in games if g["is_high_score"]),
                'avg_score': sum(g["score"] for g in games) / len(games) if games else 0,
                'median_score': sorted([g["score"] for g in games])[len(games)//2] if games else 0,
                'max_score': max(g["score"] for g in games) if games else 0,
                'top_players_by_games': [],
                'top_players_by_score': []
            }

            # For now, return success without PDF generation
            # Full PDF generation would require matplotlib in Vercel environment
            result = {
                'success': True,
                'stats': stats,
                'message': 'Report generated successfully',
                'timestamp': datetime.now().isoformat()
            }

            # Send to Slack (without PDF for now - add PDF generation if needed)
            # slack_result = send_slack_report(stats, pdf_bytes)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
