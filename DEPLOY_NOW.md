# 🚀 Deploy Now - Quick Start

You have Vercel Pro! Let's get this deployed in 5 minutes.

## Step 1: Push to GitHub (2 min)

```bash
# Initialize git if not already done
git init
git add .
git commit -m "Add Vercel cron job for automated daily reports"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/mobee-stats.git
git branch -M main
git push -u origin main
```

## Step 2: Deploy to Vercel (1 min)

### Option A: Via Dashboard (Easiest)
1. Go to [vercel.com/new](https://vercel.com/new)
2. Click "Import Git Repository"
3. Select your `mobee-stats` repo
4. Click "Deploy" (Vercel auto-detects everything!)

### Option B: Via CLI
```bash
npm install -g vercel
vercel login
vercel --prod
```

Your dashboard will be live at: `https://mobee-stats.vercel.app`

## Step 3: Add Environment Variables (2 min)

In Vercel Dashboard:
1. Go to your project
2. Settings → Environment Variables
3. Add these:

| Variable | Value | Where to get it |
|----------|-------|----------------|
| `SLACK_TOKEN` | `xoxb-...` | Slack App OAuth page |
| `CHANNEL_ID` | `C0A2VA0T0E4` | Your game data channel |
| `REPORT_CHANNEL_ID` | `C...` | Channel for daily reports (optional, defaults to CHANNEL_ID) |
| `CRON_SECRET` | Random string | Generate with: `openssl rand -base64 32` |

**Important:** After adding variables, click "Redeploy" to apply them!

## Step 4: Test It! (30 sec)

### Test the dashboard:
Visit: `https://your-project.vercel.app`

### Test the cron endpoint manually:
```bash
# If you set CRON_SECRET
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://your-project.vercel.app/api/daily-report

# Without CRON_SECRET
curl https://your-project.vercel.app/api/daily-report
```

Check Slack - you should see a beautiful report! 🎉

## Step 5: Verify Cron Schedule

In Vercel Dashboard:
1. Go to: Settings → Crons
2. You should see:
   - Path: `/api/daily-report`
   - Schedule: `0 9 * * *` (9 AM UTC daily)
   - Status: Active ✅

### Adjust Schedule (Optional)

Edit `vercel.json`:
```json
{
  "crons": [{
    "path": "/api/daily-report",
    "schedule": "0 14 * * *"  // 2 PM UTC / 9 AM EST
  }]
}
```

Common schedules:
- `0 9 * * *` - 9 AM UTC
- `0 14 * * *` - 2 PM UTC (9 AM EST)
- `0 17 * * *` - 5 PM UTC (9 AM PST)
- `0 0 * * *` - Midnight UTC
- `0 9 * * 1-5` - 9 AM UTC, weekdays only

Then redeploy: `vercel --prod`

## What You Get

✅ Live dashboard at `https://your-project.vercel.app`
✅ API endpoint at `https://your-project.vercel.app/api/stats`
✅ Automated daily reports sent to Slack at 9 AM UTC
✅ Beautiful formatted Slack messages with stats
✅ Last 7 days activity tracker
✅ Top players and high scores

## Your Report Includes:

📊 **Overview Stats**
- Total games, players, high scores
- Average and median scores

🏆 **Leaderboards**
- Top 5 players by games played
- Top 5 high scores

📈 **Recent Activity**
- Last 7 days breakdown
- Daily game counts and player counts

## Monitoring

### View Cron Logs
1. Vercel Dashboard → Your Project
2. Deployments → Latest deployment
3. Functions tab → `/api/daily-report`
4. Click to view execution logs

### Check Next Run Time
Settings → Crons → Shows "Next Scheduled"

### Manual Trigger
Just hit the endpoint:
```bash
curl https://your-project.vercel.app/api/daily-report
```

## Troubleshooting

### Report not sending?

**Check:**
1. Environment variables are set correctly
2. Bot is invited to Slack channel: `/invite @Mobee Stats Bot`
3. Bot has permissions: `channels:history`, `chat:write`
4. View function logs in Vercel

### Wrong timezone?

The cron runs on UTC. Calculate your local time:
- EST: UTC - 5 hours → Use `0 14 * * *` for 9 AM EST
- PST: UTC - 8 hours → Use `0 17 * * *` for 9 AM PST
- CET: UTC + 1 hour → Use `0 8 * * *` for 9 AM CET

### Want to change report format?

Edit `api/daily-report.py` and redeploy!

## Next Steps (Optional)

### Add Email Reports
- Set up SendGrid (free 100 emails/day)
- Add email function to `api/daily-report.py`
- Add env vars: `SENDGRID_API_KEY`, `EMAIL_TO`

### Multiple Report Channels
Add to environment variables:
```
REPORT_CHANNEL_ID=C123456,C789012,C345678
```

Update code to loop through channels.

### Weekly Summary
Add another cron job:
```json
{
  "path": "/api/weekly-summary",
  "schedule": "0 9 * * 1"  // Monday 9 AM
}
```

## You're Done! 🎉

Your automated daily reports are now live!

**First automated run:** Tomorrow at 9 AM UTC
**Dashboard:** https://your-project.vercel.app
**Cost:** $20/month (Vercel Pro)

Need help? Check the function logs in Vercel Dashboard.
