# Mobee Game Statistics Dashboard

A live statistics dashboard for Mobee game data, featuring real-time analytics, player leaderboards, and performance metrics.

## Features

- 📊 Real-time statistics dashboard
- 🏆 Player leaderboards
- 📱 Platform analytics
- 🌍 Geographic distribution
- 📈 Score distribution analysis
- 📄 PDF report generation

## Local Development

### Generate Statistics Locally

```bash
python3 mobee_stats.py
```

This will:
- Fetch latest data from Slack
- Generate statistics
- Save JSON data files
- Create a PDF report

### View Dashboard Locally

Open `index.html` in your browser. It will use the local `mobee_stats.json` file.

## Deploy to Vercel

### Prerequisites

1. Install Vercel CLI:
```bash
npm install -g vercel
```

2. Create a Vercel account at https://vercel.com

### Deployment Steps

1. Initialize a Git repository (if not already done):
```bash
git init
git add .
git commit -m "Initial commit"
```

2. Deploy to Vercel:
```bash
vercel
```

Follow the prompts:
- Link to existing project or create new? → **Create new**
- What's the name of your project? → **mobee-stats** (or your choice)
- Which directory is your code located? → **./** (current directory)

3. For production deployment:
```bash
vercel --prod
```

### Environment Variables (Optional)

If you want to add environment variables for the Slack token:

1. Go to your Vercel dashboard
2. Select your project
3. Go to Settings → Environment Variables
4. Add:
   - `SLACK_TOKEN`: Your Slack bot token
   - `CHANNEL_ID`: Your Slack channel ID

Then update `api/stats.py` to read from environment variables:
```python
import os
SLACK_TOKEN = os.environ.get('SLACK_TOKEN', 'fallback-token')
CHANNEL_ID = os.environ.get('CHANNEL_ID', 'fallback-channel')
```

## How It Works

### Static Website
- `index.html`: Beautiful, responsive dashboard
- Auto-refreshes every 5 minutes
- Mobile-friendly design

### Serverless API
- `/api/stats`: Fetches live data from Slack and returns statistics
- Automatically deployed as a serverless function on Vercel
- No server management required

### Local Script
- `mobee_stats.py`: Python script for local analysis and PDF generation
- Can be run via cron job for regular updates

## File Structure

```
mobee_stats/
├── index.html              # Dashboard frontend
├── api/
│   └── stats.py           # Serverless API endpoint
├── mobee_stats.py         # Local statistics generator
├── generate_pdf_report.py # Standalone PDF generator
├── vercel.json            # Vercel configuration
├── requirements.txt       # Python dependencies
├── mobee_stats.json       # Generated statistics (static fallback)
├── mobee_games_raw.json   # Raw game data
└── README.md              # This file
```

## URLs After Deployment

- Dashboard: `https://your-project.vercel.app`
- API: `https://your-project.vercel.app/api/stats`

## Auto-Updates

The dashboard automatically:
- Fetches fresh data from the API every 5 minutes
- Updates all statistics in real-time
- No manual refresh needed

## Customization

### Change Refresh Interval

In `index.html`, modify the interval (currently 5 minutes):
```javascript
setInterval(loadStats, 5 * 60 * 1000); // 5 minutes in milliseconds
```

### Modify Styling

Edit the `<style>` section in `index.html` to customize colors, fonts, and layout.

### Add More Statistics

1. Update the analysis in `api/stats.py`
2. Add new sections to `index.html`
3. Update the `displayStats()` function

## Support

For issues or questions, check the Vercel deployment logs:
```bash
vercel logs
```
