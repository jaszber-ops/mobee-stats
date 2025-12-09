#!/bin/bash
# Deploy script for Mobee Stats

echo "🚀 Mobee Stats Deployment Script"
echo "=================================="
echo ""

# Check if REPO_URL is provided
if [ -z "$1" ]; then
    echo "❌ Error: Repository URL required"
    echo ""
    echo "Usage:"
    echo "  1. Create a GitHub repository at: https://github.com/new"
    echo "  2. Copy the repository URL"
    echo "  3. Run: ./deploy-commands.sh YOUR_REPO_URL"
    echo ""
    echo "Example:"
    echo "  ./deploy-commands.sh https://github.com/yourname/mobee-stats.git"
    exit 1
fi

REPO_URL=$1

echo "📦 Initializing Git repository..."
git init

echo "📝 Adding all files..."
git add .

echo "💾 Creating commit..."
git commit -m "Initial commit: Mobee Stats with automated daily reports via Vercel cron"

echo "🔗 Adding remote origin..."
git remote add origin $REPO_URL

echo "📤 Pushing to GitHub..."
git branch -M main
git push -u origin main

echo ""
echo "✅ Code pushed to GitHub successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 NEXT STEPS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  Deploy to Vercel:"
echo "   → Go to: https://vercel.com/new"
echo "   → Click 'Import Git Repository'"
echo "   → Select your repository"
echo "   → Click 'Deploy'"
echo ""
echo "2️⃣  Add Environment Variables in Vercel:"
echo "   → Go to: Settings → Environment Variables"
echo "   → Add:"
echo "      • SLACK_TOKEN = your_slack_token_here"
echo "      • CHANNEL_ID = your_channel_id_here"
echo "      • REPORT_CHANNEL_ID = (optional, channel for daily reports)"
echo "   → Click 'Redeploy' after adding variables"
echo ""
echo "3️⃣  Test your deployment:"
echo "   → Dashboard: https://your-project.vercel.app"
echo "   → Test cron: curl https://your-project.vercel.app/api/daily-report"
echo ""
echo "🎉 Setup complete! Your automated daily reports will start tomorrow at 9 AM UTC"
echo ""
