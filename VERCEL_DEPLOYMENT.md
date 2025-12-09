# Vercel Deployment Guide - Automated Daily Reports

This guide covers setting up automated daily reports using **Vercel Cron Jobs** (requires Pro plan).

## Overview

Your setup will include:
1. **Live Dashboard** - `https://your-project.vercel.app`
2. **Live API** - `https://your-project.vercel.app/api/stats`
3. **Automated Daily Reports** - Runs at 9 AM UTC daily, sends PDF via Slack

---

## Prerequisites

- Vercel Pro account ($20/month)
- GitHub account
- Slack workspace with bot configured

---

## Step 1: Configure Slack Bot

### Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name: "Mobee Stats Bot"
4. Select your workspace

### Add Permissions

Go to "OAuth & Permissions" and add these scopes:
- `channels:history` - Read channel messages
- `chat:write` - Post messages
- `files:write` - Upload PDF files

### Install & Get Token

1. Click "Install to Workspace"
2. Copy the "Bot User OAuth Token" (starts with `xoxb-`)
3. Invite bot to your channels:
   ```
   /invite @Mobee Stats Bot
   ```

### Get Channel IDs

Right-click channel → View channel details → Copy Channel ID

Or use:
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://slack.com/api/conversations.list | jq '.channels[] | {name, id}'
```

---

## Step 2: Deploy to Vercel

### Option A: Deploy via Vercel Dashboard

1. **Push code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/mobee-stats.git
   git push -u origin main
   ```

2. **Import to Vercel:**
   - Go to [vercel.com/new](https://vercel.com/new)
   - Import your GitHub repository
   - Vercel auto-detects configuration
   - Click "Deploy"

### Option B: Deploy via Vercel CLI

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel

# Deploy to production
vercel --prod
```

---

## Step 3: Configure Environment Variables

In Vercel dashboard: **Settings → Environment Variables**

Add these variables:

| Variable | Value | Required |
|----------|-------|----------|
| `SLACK_TOKEN` | Your bot token (`xoxb-...`) | ✅ Yes |
| `CHANNEL_ID` | Channel for fetching game data | ✅ Yes |
| `REPORT_CHANNEL_ID` | Channel for daily reports (defaults to CHANNEL_ID) | Optional |
| `CRON_SECRET` | Random string for security (optional but recommended) | Optional |

### Generate CRON_SECRET

```bash
openssl rand -base64 32
```

Add this to environment variables and save it securely.

---

## Step 4: Verify Cron Job Setup

### Check Configuration

Your `vercel.json` should have:

```json
{
  "crons": [
    {
      "path": "/api/generate-report",
      "schedule": "0 9 * * *"
    }
  ]
}
```

### Cron Schedule Options

- `0 9 * * *` - Daily at 9:00 AM UTC
- `0 0 * * *` - Daily at midnight UTC
- `0 */6 * * *` - Every 6 hours
- `0 9 * * 1-5` - Weekdays at 9 AM
- `0 9 * * 1` - Every Monday at 9 AM

**Note:** Vercel uses UTC timezone. Convert to your local time:
- 9 AM UTC = 4 AM EST / 1 AM PST
- Adjust the hour in the cron schedule accordingly

---

## Step 5: Test the Setup

### Test the Dashboard

Visit: `https://your-project.vercel.app`

You should see the live statistics dashboard.

### Test the API

Visit: `https://your-project.vercel.app/api/stats`

You should see JSON statistics.

### Test the Cron Job Manually

```bash
# If you set CRON_SECRET
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://your-project.vercel.app/api/generate-report

# Without CRON_SECRET
curl https://your-project.vercel.app/api/generate-report
```

Check your Slack channel for the report.

---

## Step 6: Monitor Cron Executions

### View Logs

1. Go to Vercel dashboard
2. Select your project
3. Go to "Deployments"
4. Click on a deployment
5. View "Functions" tab
6. Check logs for `/api/generate-report`

### Check Cron Status

Go to: **Settings → Crons**

You'll see:
- Cron schedule
- Last execution time
- Next scheduled execution
- Execution history

---

## Customization

### Change Report Time

Edit `vercel.json`:

```json
{
  "crons": [{
    "path": "/api/generate-report",
    "schedule": "0 6 * * *"  // 6 AM UTC
  }]
}
```

Redeploy after changes:
```bash
vercel --prod
```

### Send to Multiple Channels

Update environment variables:
```
REPORT_CHANNEL_ID=C123456,C789012,C345678
```

Modify `api/generate-report.py` to split and iterate:
```python
channels = REPORT_CHANNEL_ID.split(',')
for channel in channels:
    send_slack_report(stats, pdf_bytes, channel)
```

### Add Email Notifications

1. Install SendGrid:
   ```bash
   pip install sendgrid
   ```

2. Add to `requirements.txt`:
   ```
   sendgrid==6.11.0
   ```

3. Add environment variables:
   - `SENDGRID_API_KEY`
   - `EMAIL_FROM`
   - `EMAIL_TO`

4. Add email function to `api/generate-report.py`

---

## Troubleshooting

### Cron Job Not Running

**Check:**
- ✅ Vercel Pro plan is active
- ✅ Cron is configured in `vercel.json`
- ✅ Latest deployment is production
- ✅ No errors in function logs

**Verify in Vercel:**
Settings → Crons → Check "Last Execution"

### Slack Upload Fails

**Common issues:**
- Bot not invited to channel
- Missing `files:write` permission
- Invalid token
- Channel ID incorrect

**Test permissions:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://slack.com/api/auth.test
```

### Function Timeout

Vercel Pro functions timeout at 60 seconds (Hobby: 10s)

If timing out:
- Optimize data fetching
- Reduce message limit
- Cache results

### Missing Dependencies

If packages fail to import:

1. Add to `requirements.txt`
2. Redeploy to Vercel
3. Check build logs

---

## Cost Breakdown

| Service | Cost |
|---------|------|
| Vercel Pro | $20/month |
| Slack API | Free |
| Total | **$20/month** |

### What You Get:
- Unlimited cron jobs
- 100GB bandwidth
- Faster builds
- Team collaboration
- Priority support

---

## Security Best Practices

### 1. Use CRON_SECRET

Prevent unauthorized cron triggers:

```python
# In api/generate-report.py
cron_secret = os.environ.get('CRON_SECRET', '')
if cron_secret and auth_header != f'Bearer {cron_secret}':
    return 401
```

### 2. Rotate Tokens

Periodically regenerate:
- Slack bot token
- Cron secret
- API keys

### 3. Restrict Permissions

Only grant necessary Slack scopes:
- `channels:history` ✅
- `channels:write` ❌ (not needed)
- `admin` ❌ (never)

### 4. Monitor Usage

- Check Vercel function invocations
- Review Slack API rate limits
- Set up error alerts

---

## Advanced: Multiple Reports

### Different Reports, Different Times

```json
{
  "crons": [
    {
      "path": "/api/daily-report",
      "schedule": "0 9 * * *"
    },
    {
      "path": "/api/weekly-summary",
      "schedule": "0 9 * * 1"
    },
    {
      "path": "/api/monthly-summary",
      "schedule": "0 9 1 * *"
    }
  ]
}
```

Create separate endpoints for each report type.

---

## Need Help?

### Documentation
- Vercel Crons: https://vercel.com/docs/cron-jobs
- Slack API: https://api.slack.com/docs
- Vercel CLI: https://vercel.com/docs/cli

### Common Commands

```bash
# View logs
vercel logs

# Check deployment status
vercel ls

# Redeploy latest
vercel --prod

# Remove deployment
vercel rm PROJECT_NAME
```

---

## Quick Start Checklist

- [ ] Upgrade to Vercel Pro
- [ ] Create Slack bot and get token
- [ ] Get channel IDs
- [ ] Push code to GitHub
- [ ] Deploy to Vercel
- [ ] Add environment variables
- [ ] Test `/api/generate-report` manually
- [ ] Wait for first automated run
- [ ] Check Slack for report

**You're all set! 🚀**

The cron job will now run automatically daily at your specified time.
