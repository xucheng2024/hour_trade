# GitHub Setup Guide

## Repository Information
- **GitHub URL**: https://github.com/xucheng2024/hour_trade
- **Repository Name**: hour_trade
- **Owner**: xucheng2024

## Quick Setup (First Time)

```bash
# 1. Initialize git repository (if not already done)
cd /Users/mac/Downloads/stocks/hour_trade
git init

# 2. Add all files (excluding those in .gitignore)
git add .

# 3. Create initial commit
git commit -m "Initial commit: OKX Cryptocurrency Trading System"

# 4. Add remote repository
git remote add origin https://github.com/xucheng2024/hour_trade.git

# 5. Push to GitHub
git branch -M main
git push -u origin main
```

## Subsequent Updates

```bash
# Check status
git status

# Add modified files
git add .

# Commit changes
git commit -m "Your commit message here"

# Push to GitHub
git push
```

## Important Security Notes

### ⚠️ Files That Are Automatically Excluded (.gitignore)

The following files are **automatically excluded** from git commits for security:

1. **`.env`** - Contains API keys and database credentials (NEVER COMMIT!)
2. **`*.log`** - Log files
3. **`*.db`** - SQLite database files
4. **`__pycache__/`** - Python cache
5. **`node_modules/`** - Node.js dependencies
6. **`data/*.npz`** - Large data files

### ✅ Safe to Commit

- `.env.example` - Template file (no real credentials)
- Source code (`.py` files)
- Configuration templates
- Documentation files
- `requirements.txt`

## Environment Setup for New Users

When someone clones your repository, they need to:

```bash
# 1. Clone repository
git clone https://github.com/xucheng2024/hour_trade.git
cd hour_trade

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env with real credentials
nano .env  # or use any editor

# 4. Install dependencies
pip install -r requirements.txt

# 5. Initialize database
python init_database.py

# 6. Run the system
python websocket_limit_trading.py
```

## Branch Strategy (Optional)

For better workflow:

```bash
# Create development branch
git checkout -b develop

# Make changes and commit
git add .
git commit -m "Add new feature"

# Push development branch
git push -u origin develop

# When ready, merge to main
git checkout main
git merge develop
git push
```

## Verifying Before Commit

Always check what will be committed:

```bash
# See what files will be committed
git status

# See actual changes
git diff

# If you see .env file, STOP and add it to .gitignore!
```

## Common Git Commands

```bash
# View commit history
git log --oneline

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo all changes to a file
git checkout -- filename

# View remote URL
git remote -v

# Pull latest changes
git pull
```

## Troubleshooting

### Problem: Accidentally committed .env file

```bash
# Remove from git (keep local file)
git rm --cached .env

# Commit the removal
git commit -m "Remove .env from git tracking"

# Push changes
git push
```

### Problem: Remote already exists error

```bash
# Remove existing remote
git remote remove origin

# Add correct remote
git remote add origin https://github.com/xucheng2024/hour_trade.git
```

### Problem: Merge conflicts

```bash
# Pull with rebase
git pull --rebase

# Or force push (careful!)
git push --force
```

## GitHub Repository Settings

After pushing, configure on GitHub:

1. **Settings → Branches**
   - Set `main` as default branch
   - Optional: Add branch protection rules

3. **About** (top right)
   - Add description: "OKX Cryptocurrency Trading System with WebSocket"
   - Add topics: `cryptocurrency`, `trading`, `okx`, `websocket`, `python`

---

**Last Updated**: 2026-01-14
**Repository**: https://github.com/xucheng2024/hour_trade
