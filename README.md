# IntelliVest — Persistent 24/7 AI Engine

Runs autonomously on GitHub's free servers. No VPS, no hosting cost, no leaving your computer on.

---

## How it works

```
GitHub Actions (free cron, 7×/day on trading days)
    ↓ runs ai_engine.py on GitHub's servers
Fetches live prices (Finnhub) + news (RSS)
    ↓
Runs Claude AI analysis for all 7 strategies
    ↓
Saves results to data/*.json in this repository
    ↓
GitHub Pages serves index.html + data files
    ↓
Your browser reads live AI results whenever you open the URL
```

**Cost: ~£2/month** (Claude Haiku API only — everything else is free)

---

## Setup — takes about 10 minutes

### Step 1: Create a GitHub account
Go to [github.com](https://github.com) and sign up (free).

### Step 2: Create a new repository
1. Click the **+** button → **New repository**
2. Name it: `intellivest` (or anything you like)
3. Set to **Public** (required for free GitHub Pages)
4. Click **Create repository**

### Step 3: Upload the files
Upload all files from this folder to your repository:
- Drag and drop the entire folder contents onto the GitHub repository page
- Or use GitHub Desktop (easier for non-developers)

The structure should be:
```
your-repo/
├── index.html
├── .github/
│   └── workflows/
│       └── ai-engine.yml
├── scripts/
│   └── ai_engine.py
└── data/
    ├── state.json
    ├── config.json
    ├── prices.json
    ├── daily_insight.json
    └── strategy_results.json
```

### Step 4: Add your API keys as GitHub Secrets
This keeps your keys secure — they are never visible in the code.

1. In your repository, go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these two secrets:

| Secret name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Claude API key (starts with `sk-ant-`) |
| `FINNHUB_API_KEY` | Your Finnhub API key |

### Step 5: Enable GitHub Pages
1. Go to **Settings** → **Pages**
2. Under **Source**, select **Deploy from a branch**
3. Select **main** branch, **/ (root)** folder
4. Click **Save**

GitHub will give you a URL like: `https://yourusername.github.io/intellivest`

That is your permanent dashboard URL. Bookmark it.

### Step 6: Enable GitHub Actions
1. Go to the **Actions** tab in your repository
2. If prompted, click **Enable Actions**
3. Click on **IntelliVest AI Engine** workflow
4. Click **Run workflow** → **Run workflow** to test it manually

Watch it run. It should take 2-3 minutes and update the data/ files.

### Step 7: Open your dashboard
Go to your GitHub Pages URL. The dashboard will load and automatically read the AI results.

---

## Schedule

The engine runs automatically at these times (all weekdays, Mon-Fri):

| Time EST | Time UTC | What runs |
|----------|----------|-----------|
| 08:00 | 13:00 | Pre-market: Master + Momentum only |
| 09:35 | 14:35 | All 7 strategies |
| 10:30 | 15:30 | All 7 strategies |
| 12:00 | 17:00 | All 7 strategies |
| 13:30 | 18:30 | All 7 strategies |
| 15:00 | 20:00 | All 7 strategies |
| 15:45 | 20:45 | All 7 strategies |

Weekends: nothing runs (market closed, no point burning API calls).

---

## Updating your config

To change AI thresholds (min opportunity score, stop loss, etc.):
1. Edit `data/config.json` in your repository
2. The next engine run picks up the new settings automatically

---

## Cost breakdown

| Service | Cost |
|---------|------|
| GitHub (hosting + Actions) | **Free** |
| GitHub Pages (dashboard URL) | **Free** |
| Finnhub (market data) | **Free** |
| Claude Haiku API (AI engine) | **~£2/month** |
| **Total** | **~£2/month** |

GitHub Actions free tier: 2,000 minutes/month.
Our usage: ~7 runs/day × 2 min × 22 trading days = ~308 min/month. Well within limit.

---

## Troubleshooting

**Actions not running:** Check Settings → Actions → General → Allow all actions is enabled.

**No data showing in dashboard:** Check the Actions tab for failed runs. Most common cause: API key not set in Secrets.

**"Permission denied" when pushing data:** In your workflow settings, ensure Actions has write permission: Settings → Actions → General → Workflow permissions → Read and write.

**EDGAR insider data not loading:** This uses a proxy and occasionally rate-limits. It will retry on next refresh.
