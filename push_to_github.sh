#!/bin/bash
# Script to push project to GitHub
# Repository: https://github.com/xucheng2024/hour_trade

set -e  # Exit on error

echo "🚀 Pushing to GitHub: xucheng2024/hour_trade"
echo "================================================"

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "📝 Initializing git repository..."
    git init
    echo "✅ Git initialized"
fi

# Check if .env exists (should not be committed)
if [ -f ".env" ]; then
    echo "⚠️  .env file detected - will be excluded by .gitignore"
fi

# Add all files
echo "📦 Adding files to git..."
git add .

# Show what will be committed
echo ""
echo "📋 Files to be committed:"
git status --short

# Ask for confirmation
echo ""
read -p "⚠️  VERIFY: Check files above. No .env or API keys? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted by user"
    exit 1
fi

# Commit
echo "💾 Creating commit..."
git commit -m "Initial commit: OKX Cryptocurrency Trading System

- WebSocket real-time trading system
- 36 crypto pairs with optimized entry points
- Automated limit buy and market sell orders
- Neon PostgreSQL database integration
- Web dashboard for trade monitoring
- Vercel API deployment support"

# Check if remote exists
if git remote | grep -q "origin"; then
    echo "📡 Remote 'origin' already exists"
else
    echo "📡 Adding remote repository..."
    git remote add origin https://github.com/xucheng2024/hour_trade.git
fi

# Set branch to main
git branch -M main

# Push to GitHub
echo "⬆️  Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ SUCCESS! Project pushed to GitHub"
echo "🔗 View at: https://github.com/xucheng2024/hour_trade"
echo ""
echo "📝 Next steps:"
echo "1. Visit GitHub repository settings"
echo "2. Add secrets for GitHub Actions (if needed):"
echo "   - DATABASE_URL"
echo "   - OKX_API_KEY"
echo "   - OKX_SECRET"
echo "   - OKX_PASSPHRASE"
echo ""
echo "3. Configure repository description and topics"
