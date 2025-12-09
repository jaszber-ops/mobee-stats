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

    # Then upload the PDF using files.uploadV2
    import os
    file_size = os.path.getsize('mobee_stats_report.pdf')

    # Step 1: Get upload URL
    upload_response = requests.post(
        'https://slack.com/api/files.getUploadURLExternal',
        headers={
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'filename': 'mobee_stats_report.pdf',
            'length': file_size
        }
    )

    upload_data = upload_response.json()

    if not upload_data.get('ok'):
        print(f"❌ Error getting upload URL: {upload_data}")
        return

    # Step 2: Upload file to URL
    upload_url = upload_data['upload_url']
    file_id = upload_data['file_id']

    with open('mobee_stats_report.pdf', 'rb') as pdf_file:
        requests.post(upload_url, files={'file': pdf_file})

    # Step 3: Complete the upload
    complete_response = requests.post(
        'https://slack.com/api/files.completeUploadExternal',
        headers={
            'Authorization': f'Bearer {SLACK_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'files': [{'id': file_id, 'title': f'Mobee Stats Report - {stats["total_games"]} Games'}],
            'channel_id': CHANNEL_ID,
            'initial_comment': 'Daily Statistics Report'
        }
    )

    if complete_response.json().get('ok'):
        print('✅ Successfully sent Slack report with PDF attachment')
    else:
        print(f"❌ Error completing upload: {complete_response.json()}")

if __name__ == '__main__':
    send_slack_report()
