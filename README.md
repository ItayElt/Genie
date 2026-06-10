# Genie Code PM Morning Brief

A daily AI newsletter delivered at 8 AM, curated specifically for Product Managers on Genie Code at Databricks.

Scans 20+ RSS feeds and 25+ targeted web searches across Databricks, Snowflake, Microsoft Fabric, OpenAI, Anthropic, GitHub Copilot, Cursor, LangChain, HackerNews, Reddit, and more — then uses Claude to rank, filter, and write the brief.

---

## Quick Start

### 1. Install dependencies

```bash
cd genie-code-brief
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up environment

```bash
cp .env.example .env
```

Edit `.env` with your keys:

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `TAVILY_API_KEY` | app.tavily.com (free tier available) |
| `SMTP_USER` + `SMTP_PASSWORD` | Gmail → Settings → App Passwords |
| `SENDGRID_API_KEY` | sendgrid.com (alternative to Gmail) |
| `UNSPLASH_ACCESS_KEY` | unsplash.com/developers (optional, for hero image) |

**Gmail App Password** (if using SMTP):
1. Go to myaccount.google.com → Security → 2-Step Verification
2. Scroll down → App passwords → Generate
3. Use the 16-char password as `SMTP_PASSWORD`

### 3. Test (no email sent)

```bash
python3 main.py --dry-run
```

The HTML output lands in `logs/brief_YYYY-MM-DD.html` — open it in a browser.

### 4. Send one now

```bash
python3 main.py
```

### 5. Schedule daily at 8 AM

**Option A: Mac/Linux cron (runs on your machine)**

```bash
bash setup_cron.sh
```

**Option B: GitHub Actions (runs in the cloud — recommended)**

1. Push this repo to GitHub (can be private).
2. Go to Settings → Secrets → New repository secret.
3. Add each key from your `.env` as a GitHub Secret.
4. The workflow in `.github/workflows/daily_brief.yml` fires Mon–Fri at 8 AM PDT.
5. To also send on weekends, change `1-5` to `*` in the cron expression.

---

## Architecture

```
main.py
  └── searcher.py      RSS feeds (20 sources) + Tavily web search (25 queries)
  └── generator.py     Claude claude-opus-4-8 → structured JSON newsletter
  └── emailer.py       HTML builder + Gmail SMTP or SendGrid sender
```

## Source Tiers

| Tier | Sources | Weight |
|------|---------|--------|
| 0 | Databricks Blog, Engineering Blog | 10/10 |
| 1 | Snowflake, Microsoft Fabric | 10/10 |
| 2 | Cursor, Claude Code, GitHub Copilot, OpenAI Codex, Windsurf | 10/10 |
| 3 | OpenAI, Anthropic, Google DeepMind, Meta AI, NVIDIA | 9/10 |
| 4 | LangChain, LangGraph, LlamaIndex, CrewAI | 8/10 |
| 5 | AWS ML, Google Cloud, Vercel | 8/10 |
| 6 | arXiv research (product-relevant only) | 8/10 |
| 7 | Hacker News, Reddit (r/dataengineering, r/LocalLLaMA) | 9/10 |
| 8 | High-signal X accounts | 8/10 |

## Customization

- **Add recipients**: Edit `RECIPIENT_EMAILS` in `.env` (comma-separated)
- **Change time**: Edit the cron expression in `setup_cron.sh` or `.github/workflows/daily_brief.yml`
- **Change model**: Set `CLAUDE_MODEL=claude-sonnet-4-6` in `.env` (cheaper, faster)
- **Adjust lookback**: Set `LOOKBACK_HOURS=48` in `.env` for a longer window
- **Add RSS feeds**: Edit the `RSS_FEEDS` dict in `searcher.py`
- **Add search queries**: Edit `TAVILY_QUERIES` in `searcher.py`
