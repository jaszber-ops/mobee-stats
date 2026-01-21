#!/usr/bin/env python3
"""
Slack PDF Upload Script

Uploads the generated PDF report to Slack using the Bot Token.

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

def load_highlights():
    """Load stats JSON to extract highlights for the message"""
    try:
        with open('mobee8_stats.json', 'r') as f:
            data = json.load(f)

        level_1 = data.get('level_1', {})
        level_2 = data.get('level_2', {})

        top_7 = level_1.get('top_players_by_score', [{}])[0] if level_1.get('top_players_by_score') else {}
        top_12 = level_2.get('top_players_by_score', [{}])[0] if level_2.get('top_players_by_score') else {}

        highlights = []
        highlights.append(f"*Level 1 (7 symbols)*: {level_1.get('total_games', 0)} games, top score: {top_7.get('score', 0)}")
        highlights.append(f"*Level 2 (12 symbols)*: {level_2.get('total_games', 0)} games, top score: {top_12.get('score', 0)}")
        highlights.append(f"*Total*: {level_1.get('total_games', 0) + level_2.get('total_games', 0)} games")

        return '\n'.join(highlights)
    except Exception as e:
        print(f"Warning: Could not load highlights: {e}")
        return "Mobee-8 Stats Report"

def upload_to_slack(pdf_path):
    """Upload PDF file to Slack channel using the new v2 API"""
    if not SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN not set")
        return False

    if not SLACK_CHANNEL_ID:
        print("ERROR: SLACK_CHANNEL_ID not set")
        return False

    highlights = load_highlights()
    initial_comment = f":bar_chart: *Mobee-8 Hourly Stats Report*\n\n{highlights}"

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

    # Step 3: Complete the upload and share to channel
    complete_response = requests.post(
        'https://slack.com/api/files.completeUploadExternal',
        headers={
            'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            'files': [{'id': file_id, 'title': filename}],
            'channel_id': SLACK_CHANNEL_ID,
            'initial_comment': initial_comment
        }
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
