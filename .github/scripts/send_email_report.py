#!/usr/bin/env python3
"""Send daily report via email using SendGrid"""

import os
import json
import base64
from datetime import datetime

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
except ImportError:
    print("⚠️  SendGrid not installed. Skipping email report.")
    print("   Install with: pip install sendgrid")
    exit(0)

EMAIL_FROM = os.environ.get('EMAIL_FROM')
EMAIL_TO = os.environ.get('EMAIL_TO')
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')

def send_email_report():
    """Send formatted email with PDF attachment"""

    if not all([EMAIL_FROM, EMAIL_TO, SENDGRID_API_KEY]):
        print("⚠️  Email credentials not configured. Skipping email report.")
        return

    # Load the generated stats
    with open('mobee_stats.json', 'r') as f:
        stats = json.load(f)

    # Create HTML email body
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; }}
            .stats {{ padding: 20px; }}
            .stat-box {{ background: #f4f4f4; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .stat-label {{ font-weight: bold; color: #667eea; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #667eea; color: white; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 Mobee Game Statistics</h1>
            <p>Daily Report - {datetime.now().strftime('%B %d, %Y')}</p>
        </div>
        <div class="stats">
            <div class="stat-box">
                <span class="stat-label">Total Games:</span> {stats['total_games']}<br>
                <span class="stat-label">Unique Players:</span> {stats['unique_players']}<br>
                <span class="stat-label">High Score Games:</span> {stats['high_score_games']}
            </div>

            <div class="stat-box">
                <span class="stat-label">Average Score:</span> {stats['avg_score']:.2f}<br>
                <span class="stat-label">Median Score:</span> {stats['median_score']:.2f}<br>
                <span class="stat-label">Highest Score:</span> {stats['max_score']}
            </div>

            <h3>🏆 Top 5 Players by Games Played</h3>
            <table>
                <tr><th>Rank</th><th>Player</th><th>Games</th><th>Avg Score</th></tr>
"""

    for i, (player, scores) in enumerate(stats['top_players_by_games'][:5], 1):
        avg = sum(scores) / len(scores)
        html_content += f"<tr><td>{i}</td><td>{player}</td><td>{len(scores)}</td><td>{avg:.1f}</td></tr>\n"

    html_content += """
            </table>

            <h3>🥇 Top 5 High Scores</h3>
            <table>
                <tr><th>Rank</th><th>Player</th><th>Score</th></tr>
"""

    for i, (player, score) in enumerate(stats['top_players_by_score'][:5], 1):
        html_content += f"<tr><td>{i}</td><td>{player}</td><td>{score}</td></tr>\n"

    html_content += """
            </table>

            <p><strong>📄 Full detailed report is attached as a PDF.</strong></p>
        </div>
    </body>
    </html>
    """

    # Read PDF file
    with open('mobee_stats_report.pdf', 'rb') as f:
        pdf_data = f.read()

    # Create attachment
    encoded_file = base64.b64encode(pdf_data).decode()
    attached_file = Attachment(
        FileContent(encoded_file),
        FileName('mobee_stats_report.pdf'),
        FileType('application/pdf'),
        Disposition('attachment')
    )

    # Create message
    message = Mail(
        from_email=EMAIL_FROM,
        to_emails=EMAIL_TO.split(','),  # Support multiple recipients
        subject=f'📊 Mobee Game Stats - {datetime.now().strftime("%B %d, %Y")}',
        html_content=html_content
    )
    message.attachment = attached_file

    # Send email
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f'✅ Successfully sent email report (status: {response.status_code})')
    except Exception as e:
        print(f'❌ Error sending email: {str(e)}')

if __name__ == '__main__':
    send_email_report()
