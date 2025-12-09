#!/usr/bin/env python3
"""Send daily report to Slack with PDF attachment and text summary"""

import os
import json
import requests

SLACK_TOKEN = os.environ.get('SLACK_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')  # Channel to send report to

def send_slack_report():
    """Send formatted message and PDF to Slack"""

    # Load the generated stats
    with open('mobee_stats.json', 'r') as f:
        stats = json.load(f)

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

    # First, post the message
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'channel': CHANNEL_ID,
            'text': summary,
            'unfurl_links': False,
            'unfurl_media': False
        }
    )

    if not response.json().get('ok'):
        print(f"Error posting message: {response.json()}")
        return

    # Then upload the PDF
    with open('mobee_stats_report.pdf', 'rb') as pdf_file:
        response = requests.post(
            'https://slack.com/api/files.upload',
            headers={
                'Authorization': f'Bearer {SLACK_TOKEN}'
            },
            files={
                'file': ('mobee_stats_report.pdf', pdf_file, 'application/pdf')
            },
            data={
                'channels': CHANNEL_ID,
                'title': f'Mobee Stats Report - {stats["total_games"]} Games',
                'initial_comment': 'Daily Statistics Report'
            }
        )

    if response.json().get('ok'):
        print('✅ Successfully sent Slack report with PDF attachment')
    else:
        print(f"❌ Error uploading PDF: {response.json()}")

if __name__ == '__main__':
    send_slack_report()
