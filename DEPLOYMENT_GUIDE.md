# Mobee Stats - Deployment & Automation Guide

## Overview

This guide covers:
1. Deploying the live dashboard to Vercel
2. Setting up automated daily reports via GitHub Actions
3. Configuring Slack and email notifications

---

## 1. Deploy to Vercel (Live Dashboard)

### Prerequisites
- GitHub account
- Vercel account (free tier works)

### Steps

1. **Push your code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/mobee-stats.git
   git push -u origin main
   ```

2. **Deploy to Vercel:**
   - Go to [vercel.com](https://vercel.com)
   - Click "Add New Project"
   - Import your GitHub repository
   - Vercel will auto-detect the configuration
   - Click "Deploy"

3. **Add Environment Variables (Optional but Recommended):**
   - In Vercel dashboard, go to: Settings → Environment Variables
   - Add:
     - `SLACK_TOKEN`: Your Slack bot token
     - `CHANNEL_ID`: Your Slack channel ID

4. **Update `api/stats.py`** to use environment variables:
   ```python
   import os
   SLACK_TOKEN = os.environ.get('SLACK_TOKEN', 'fallback-token')
   CHANNEL_ID = os.environ.get('CHANNEL_ID', 'fallback-channel')
   ```

5. **Your dashboard is now live at:**
   - `https://your-project-name.vercel.app`
   - API endpoint: `https://your-project-name.vercel.app/api/stats`

---

## 2. Set Up Automated Daily Reports

### Option A: GitHub Actions (Recommended - Free)

GitHub Actions will:
- Run daily at a specified time
- Generate the PDF report
- Send it via Slack and/or email
- Store the PDF as an artifact

#### Setup Steps

1. **Configure GitHub Secrets:**
   - Go to your GitHub repository
   - Navigate to: Settings → Secrets and variables → Actions
   - Add the following secrets:

   **For Slack:**
   - `SLACK_TOKEN`: Your Slack bot token (starts with `xoxb-`)
   - `CHANNEL_ID`: The Slack channel ID to post reports
   - `SLACK_WEBHOOK_URL`: (Optional) Incoming webhook URL

   **For Email (using SendGrid):**
   - `EMAIL_FROM`: Sender email address
   - `EMAIL_TO`: Recipient email(s) (comma-separated for multiple)
   - `SENDGRID_API_KEY`: Your SendGrid API key

2. **Install SendGrid (for email support):**
   Add to `requirements.txt`:
   ```
   sendgrid==6.11.0
   ```

3. **Adjust the schedule:**
   Edit `.github/workflows/daily-report.yml`:
   ```yaml
   schedule:
     # Run every day at 9:00 AM UTC
     - cron: '0 9 * * *'
   ```

   Common cron schedules:
   - `0 9 * * *` - 9:00 AM UTC daily
   - `0 0 * * *` - Midnight UTC daily
   - `0 12 * * 1-5` - Noon UTC, Monday-Friday only

4. **Test the workflow manually:**
   - Go to: Actions tab in GitHub
   - Select "Daily Mobee Stats Report"
   - Click "Run workflow"

5. **View generated PDFs:**
   - Each run stores the PDF as an artifact
   - Available in the Actions tab for 30 days

---

## 3. Slack Setup

### Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name it "Mobee Stats Bot"
4. Select your workspace

### Configure Permissions

1. Go to "OAuth & Permissions"
2. Add these Bot Token Scopes:
   - `channels:history` - Read messages
   - `chat:write` - Post messages
   - `files:write` - Upload files

3. Install the app to your workspace
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### Get Channel ID

1. Open Slack
2. Right-click on your channel → "View channel details"
3. Scroll down to find the Channel ID
4. Or use Slack's API:
   ```bash
   curl -H "Authorization: Bearer YOUR_SLACK_TOKEN" \
        https://slack.com/api/conversations.list
   ```

---

## 4. Email Setup (SendGrid)

### Create SendGrid Account

1. Sign up at [sendgrid.com](https://sendgrid.com) (free tier: 100 emails/day)
2. Verify your sender email address
3. Create an API key:
   - Settings → API Keys → Create API Key
   - Give it "Full Access"
   - Copy the key (you won't see it again!)

### Configure Sender Authentication

1. Go to Settings → Sender Authentication
2. Verify a Single Sender (easiest) or Domain Authentication

---

## 5. Alternative: Vercel Cron Jobs

If you have a Vercel Pro account ($20/month), you can use Vercel's built-in cron jobs:

### Create `/api/cron/daily-report.py`:

```python
from http.server import BaseHTTPRequestHandler
import subprocess
import os

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Verify cron secret
        auth = self.headers.get('Authorization')
        if auth != f"Bearer {os.environ.get('CRON_SECRET')}":
            self.send_response(401)
            self.end_headers()
            return

        # Run the report generation
        subprocess.run(['python3', 'mobee_stats.py'])
        subprocess.run(['python3', '.github/scripts/send_slack_report.py'])

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Report generated and sent')
```

### Update `vercel.json`:

```json
{
  "crons": [{
    "path": "/api/cron/daily-report",
    "schedule": "0 9 * * *"
  }]
}
```

---

## 6. Testing Your Setup

### Test Locally

```bash
# Generate report
python3 mobee_stats.py

# Test Slack notification
export SLACK_TOKEN="your-token"
export CHANNEL_ID="your-channel-id"
python3 .github/scripts/send_slack_report.py

# Test email notification
export EMAIL_FROM="your-email@domain.com"
export EMAIL_TO="recipient@domain.com"
export SENDGRID_API_KEY="your-api-key"
python3 .github/scripts/send_email_report.py
```

### Test GitHub Action

1. Push your code to GitHub
2. Go to Actions tab
3. Click "Daily Mobee Stats Report"
4. Click "Run workflow" → "Run workflow"
5. Watch the execution logs

---

## 7. Monitoring & Troubleshooting

### Check GitHub Actions Logs
- Go to Actions tab
- Click on a workflow run
- Expand each step to see logs

### Common Issues

**Slack API Errors:**
- Verify bot is invited to the channel
- Check token has correct scopes
- Ensure channel ID is correct

**Email Failures:**
- Verify SendGrid API key
- Check sender is verified
- Review SendGrid activity logs

**PDF Generation Fails:**
- Check Python dependencies are installed
- Verify Slack API is accessible
- Review error messages in logs

---

## 8. Customization

### Change Report Format

Edit `.github/scripts/send_slack_report.py` to modify the Slack message format.

### Add More Recipients

For email:
```
EMAIL_TO="person1@example.com,person2@example.com,person3@example.com"
```

For Slack, post to multiple channels:
```python
channels = ['CHANNEL_ID_1', 'CHANNEL_ID_2']
for channel in channels:
    # post message
```

### Change Frequency

Modify the cron schedule in `.github/workflows/daily-report.yml`:
- Hourly: `0 * * * *`
- Every 6 hours: `0 */6 * * *`
- Weekly (Monday 9am): `0 9 * * 1`

---

## 9. Cost Breakdown

| Service | Free Tier | Cost |
|---------|-----------|------|
| Vercel | Yes | $0 (dashboard only) |
| GitHub Actions | 2,000 min/month | $0 (plenty for daily reports) |
| SendGrid | 100 emails/day | $0 |
| Slack | Unlimited API calls | $0 |

**Total Cost: $0** for basic setup!

---

## 10. Security Best Practices

1. **Never commit secrets to Git:**
   - Use GitHub Secrets for tokens
   - Use environment variables in Vercel
   - Add `.env` to `.gitignore`

2. **Rotate tokens periodically**

3. **Use least-privilege permissions:**
   - Only grant necessary Slack scopes
   - Restrict API keys to required features

4. **Monitor usage:**
   - Check GitHub Actions usage
   - Review Slack API rate limits
   - Monitor SendGrid quota

---

## Need Help?

- Vercel Docs: https://vercel.com/docs
- GitHub Actions: https://docs.github.com/actions
- Slack API: https://api.slack.com/docs
- SendGrid: https://docs.sendgrid.com

---

## Quick Start Checklist

- [ ] Push code to GitHub
- [ ] Deploy to Vercel
- [ ] Create Slack app and get token
- [ ] Get Slack channel ID
- [ ] (Optional) Set up SendGrid
- [ ] Add secrets to GitHub
- [ ] Test workflow manually
- [ ] Verify first automated run

**You're all set! 🎉**
