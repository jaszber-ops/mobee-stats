#!/usr/bin/env python3
"""
Slack PDF Upload Script

Uploads the generated PDF report to Slack using the Bot Token.
Shows top scorers with their avatars using Slack Block Kit.

Environment variables:
  SLACK_BOT_TOKEN    - Slack bot token (xoxb-...)
  SLACK_CHANNEL_ID   - Channel ID to post to
"""

import os
import sys
import json
import requests
import glob

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '')
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID', '')

# Base URL for avatar images on the live site
AVATAR_BASE_URL = "https://mobee-8.trippplecard.games/assets/avatars_320"

def find_latest_pdf():
    """Find the most recent PDF report file"""
    # Try timestamped file first
    pdfs = glob.glob('mobee8_stats_report_*.pdf')
    if pdfs:
        return sorted(pdfs)[-1]
    # Fall back to generic name
    if os.path.exists('mobee8_stats_report.pdf'):
        return 'mobee8_stats_report.pdf'
    return None

def avatar_coords_to_url(avatar_coords):
    """
    Convert avatarCoords (col,row 0-indexed) to avatar URL.
    Format: "col,row" -> {row+1}-{col+1}.png
    Example: "12,7" -> "8-13.png"
    """
    if not avatar_coords:
        return None
    try:
        parts = avatar_coords.split(',')
        col = int(parts[0])
        row = int(parts[1])
        filename = f"{row+1}-{col+1}.png"
        return f"{AVATAR_BASE_URL}/{filename}"
    except (ValueError, IndexError):
        return None

def load_stats_data():
    """Load stats JSON to extract data for the message"""
    try:
        with open('mobee8_stats.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load stats: {e}")
        return None

def build_slack_blocks(data):
    """Build Slack Block Kit blocks with avatar images for top scorers"""
    if not data:
        return None

    level_1 = data.get('level_1', {})
    level_2 = data.get('level_2', {})

    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "Mobee-8 Hourly Stats Report",
            "emoji": True
        }
    })

    # Summary section
    total_games = level_1.get('total_games', 0) + level_2.get('total_games', 0)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Total Games:* {total_games}\n*Level 1:* {level_1.get('total_games', 0)} games | *Level 2:* {level_2.get('total_games', 0)} games"
        }
    })

    blocks.append({"type": "divider"})

    # Level 1 Top Scorer
    top_1 = level_1.get('top_players_by_score', [{}])[0] if level_1.get('top_players_by_score') else {}
    if top_1.get('score'):
        avatar_url = avatar_coords_to_url(top_1.get('avatarCoords'))
        player_name = top_1.get('name') or top_1.get('playerId', 'Unknown')

        section = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Level 1 Top Scorer*\n:trophy: *{player_name}* - {top_1.get('score')} points"
            }
        }
        if avatar_url:
            section["accessory"] = {
                "type": "image",
                "image_url": avatar_url,
                "alt_text": f"{player_name}'s avatar"
            }
        blocks.append(section)

    # Level 2 Top Scorer
    top_2 = level_2.get('top_players_by_score', [{}])[0] if level_2.get('top_players_by_score') else {}
    if top_2.get('score'):
        avatar_url = avatar_coords_to_url(top_2.get('avatarCoords'))
        player_name = top_2.get('name') or top_2.get('playerId', 'Unknown')

        section = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Level 2 Top Scorer*\n:trophy: *{player_name}* - {top_2.get('score')} points"
            }
        }
        if avatar_url:
            section["accessory"] = {
                "type": "image",
                "image_url": avatar_url,
                "alt_text": f"{player_name}'s avatar"
            }
        blocks.append(section)

    blocks.append({"type": "divider"})

    # Context footer
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Generated at {data.get('generated_at', 'unknown')[:19]} UTC"
            }
        ]
    })

    return blocks

def post_message_with_blocks(blocks):
    """Post a message with Block Kit blocks to Slack"""
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={
            'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'channel': SLACK_CHANNEL_ID,
            'blocks': blocks,
            'text': 'Mobee-8 Hourly Stats Report'  # Fallback text
        }
    )

    result = response.json()
    print(f"chat.postMessage response: ok={result.get('ok')}, error={result.get('error', 'none')}")

    if result.get('ok'):
        return result.get('ts')  # Return thread timestamp for replies
    return None

def upload_to_slack(pdf_path):
    """Upload PDF file to Slack channel with Block Kit message showing avatars"""
    if not SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set")
        return False

    if not SLACK_CHANNEL_ID:
        print("ERROR: SLACK_CHANNEL_ID not set")
        return False

    # Load stats and build blocks message
    stats_data = load_stats_data()
    blocks = build_slack_blocks(stats_data)

    # Post the blocks message first
    thread_ts = None
    if blocks:
        print("Posting Block Kit message with avatars...")
        thread_ts = post_message_with_blocks(blocks)
        if thread_ts:
            print(f"Message posted, thread_ts: {thread_ts}")

    print(f"Uploading {pdf_path} to Slack channel {SLACK_CHANNEL_ID}...")

    file_size = os.path.getsize(pdf_path)
    filename = os.path.basename(pdf_path)

    # Step 1: Get upload URL
    response = requests.post(
        'https://slack.com/api/files.getUploadURLExternal',
        headers={
            'Authorization': f'Bearer {SLACK_BOT_TOKEN}'
        },
        data={
            'filename': filename,
            'length': file_size
        }
    )

    result = response.json()
    print(f"getUploadURLExternal response: ok={result.get('ok')}, error={result.get('error', 'none')}")

    if not result.get('ok'):
        print(f"Failed to get upload URL: {result.get('error')}")
        return False

    upload_url = result.get('upload_url')
    file_id = result.get('file_id')
    print(f"Got upload URL, file_id: {file_id}")

    # Step 2: Upload the file content to the URL
    with open(pdf_path, 'rb') as f:
        file_content = f.read()

    upload_response = requests.post(
        upload_url,
        data=file_content,
        headers={'Content-Type': 'application/octet-stream'}
    )

    print(f"Upload response status: {upload_response.status_code}")
    if upload_response.status_code != 200:
        print(f"Failed to upload file: {upload_response.status_code} {upload_response.text}")
        return False

    # Step 3: Complete the upload and share to channel (as thread reply if we have thread_ts)
    complete_payload = {
        'files': [{'id': file_id, 'title': filename}],
        'channel_id': SLACK_CHANNEL_ID
    }

    # If we posted a blocks message, add PDF as a thread reply
    if thread_ts:
        complete_payload['thread_ts'] = thread_ts
        complete_payload['initial_comment'] = ':page_facing_up: Full PDF report attached'
    else:
        complete_payload['initial_comment'] = ':bar_chart: *Mobee-8 Hourly Stats Report*'

    complete_response = requests.post(
        'https://slack.com/api/files.completeUploadExternal',
        headers={
            'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
            'Content-Type': 'application/json'
        },
        json=complete_payload
    )

    complete_result = complete_response.json()
    print(f"completeUploadExternal response: ok={complete_result.get('ok')}, error={complete_result.get('error', 'none')}")

    if complete_result.get('ok'):
        print("Successfully uploaded to Slack!")
        files = complete_result.get('files', [])
        if files:
            print(f"File URL: {files[0].get('permalink', 'N/A')}")
        return True
    else:
        print(f"Complete upload failed: {complete_result.get('error')}")
        return False

def main():
    pdf_path = find_latest_pdf()
    if not pdf_path:
        print("ERROR: No PDF report found!")
        sys.exit(1)

    print(f"Found PDF: {pdf_path}")

    success = upload_to_slack(pdf_path)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
