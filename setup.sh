#!/bin/bash
# Quick setup script for Mobee Stats automation

echo "🚀 Mobee Stats - Setup Script"
echo "=============================="
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "📦 Initializing Git repository..."
    git init
    git add .
    git commit -m "Initial commit: Mobee Stats with automated reporting"
    echo "✅ Git repository initialized"
else
    echo "✅ Git repository already exists"
fi

echo ""
echo "📋 Next Steps:"
echo ""
echo "1️⃣  Create a GitHub repository:"
echo "   - Go to https://github.com/new"
echo "   - Create a new repository (e.g., 'mobee-stats')"
echo "   - Don't initialize with README (we already have files)"
echo ""

echo "2️⃣  Push your code to GitHub:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/mobee-stats.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""

echo "3️⃣  Configure GitHub Secrets:"
echo "   - Go to: Settings → Secrets and variables → Actions"
echo "   - Add the following secrets:"
echo "     • SLACK_TOKEN (required)"
echo "     • CHANNEL_ID (required)"
echo "     • EMAIL_FROM (optional)"
echo "     • EMAIL_TO (optional)"
echo "     • SENDGRID_API_KEY (optional)"
echo ""

echo "4️⃣  Deploy to Vercel:"
echo "   - Go to https://vercel.com"
echo "   - Import your GitHub repository"
echo "   - Click Deploy"
echo "   - (Optional) Add SLACK_TOKEN and CHANNEL_ID as environment variables"
echo ""

echo "5️⃣  Test the automation:"
echo "   - Go to GitHub Actions tab"
echo "   - Select 'Daily Mobee Stats Report'"
echo "   - Click 'Run workflow'"
echo ""

echo "📖 For detailed instructions, see: DEPLOYMENT_GUIDE.md"
echo ""
echo "🎉 Setup complete! Follow the steps above to deploy."
