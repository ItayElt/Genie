"""
Multi-source signal collector.
Strategy:
  1. Parse RSS feeds from Tier 0–3 sources (free, reliable, no rate limits).
  2. Run targeted Tavily searches for Tier 2–8 sources and community signals.
  3. Deduplicate by URL.
  4. Filter out URLs already featured in recent briefs (via state.py).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import feedparser

from config import TAVILY_API_KEY, LOOKBACK_HOURS

logger = logging.getLogger(__name__)

# Current month/year for dynamic queries — updated each run
_NOW = datetime.now()
_MONTH_YEAR = _NOW.strftime("%B %Y")      # e.g. "June 2026"


# ── RSS FEEDS  (Tier 0–3, always scraped) ───────────────────────────────────

RSS_FEEDS: Dict[str, str] = {
    # Tier 0 – Databricks
    "Databricks Blog":          "https://www.databricks.com/feed",
    "Databricks Engineering":   "https://www.databricks.com/blog/engineering/feed",

    # Tier 1 – Direct data platform competitors
    "Snowflake Blog":           "https://www.snowflake.com/blog/feed/",
    "Microsoft AI Blog":        "https://blogs.microsoft.com/ai/feed/",
    "Microsoft Fabric":         "https://community.fabric.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=FabricUpdates",
    "ClickHouse Blog":          "https://clickhouse.com/blog/rss.xml",
    "MongoDB Blog":             "https://www.mongodb.com/developer/feed.xml",
    "Trino Blog":               "https://trino.io/feed.xml",

    # Tier 2 – AI coding agents
    "GitHub Blog":              "https://github.blog/feed/",
    "GitHub Changelog":         "https://github.blog/changelog/feed/",
    "Anthropic Blog":           "https://www.anthropic.com/rss.xml",
    "OpenAI Blog":              "https://openai.com/news/rss.xml",
    "Cursor Blog":              "https://cursor.com/blog/rss.xml",

    # Tier 3 – Foundation models
    "Google DeepMind":          "https://deepmind.google/discover/blog/rss.xml",
    "Meta AI Blog":             "https://ai.meta.com/blog/rss/",
    "NVIDIA Blog":              "https://blogs.nvidia.com/feed/",

    # Tier 4 – Agent frameworks
    "LangChain Blog":           "https://blog.langchain.dev/rss/",

    # Tier 5 – Infrastructure
    "AWS ML Blog":              "https://aws.amazon.com/blogs/machine-learning/feed/",
    "AWS Big Data Blog":        "https://aws.amazon.com/blogs/big-data/feed/",
    "Google Cloud AI":          "https://cloud.google.com/feeds/gcp-blog-topics-ai-machine-learning.xml",
    "Google Cloud Blog":        "https://cloud.google.com/feeds/gcp-blog-topics-databases.xml",
    "Vercel Blog":              "https://vercel.com/atom",

    # Tier 7 – Community (high-signal, filtered by Claude)
    "Hacker News Front Page":   "https://hnrss.org/frontpage",
    "Hacker News Best":         "https://hnrss.org/best",
}

# ── TAVILY QUERIES  (dynamic dates, Tier 2–8) ───────────────────────────────

def _tavily_queries() -> List[str]:
    """Build queries with the current month/year so they never go stale."""
    my = _MONTH_YEAR  # "June 2026"
    # BUDGET MODE: 8 queries/day to preserve remaining free-tier credits.
    # Switch back to full 29-query list next month when quota resets.
    return [
        # Top competitors (highest value per credit)
        f"Snowflake Cortex AI data platform announcement {my}",
        f"Microsoft Fabric AI data agent update {my}",
        f"AWS SageMaker Redshift Glue data platform AI update {my}",
        f"Google BigQuery Vertex AI update {my}",
        f"Palantir AIP Foundry enterprise AI {my}",

        # AI coding agents
        f"Cursor Claude Code GitHub Copilot agent update {my}",
        f"OpenAI Anthropic model release announcement {my}",

        # Data ecosystem
        f"Apache Spark Iceberg dbt data engineering release {my}",
    ]


# Domains blocked from appearing as signals — low-quality, user-generated, or irrelevant
_BLOCKED_DOMAINS = {
    # Content farms / regional blogs
    "techafricanews.com", "analyticsvidhya.com", "towardsdatascience.com",
    "kdnuggets.com", "dataversity.net", "aimagazine.com", "aibusiness.com",
    "tfir.io", "siliconangle.com", "itprotoday.com", "infoworld.com",
    # Personal / community platforms
    "medium.com", "substack.com", "dev.to", "hashnode.com", "beehiiv.com",
    "ghost.io", "blogspot.com", "wordpress.com",
    # Social / forums
    "reddit.com", "news.ycombinator.com", "twitter.com", "x.com",
    "linkedin.com", "facebook.com", "quora.com",
    # Video (description scrapes)
    "youtube.com", "youtu.be",
    # Generic "strategy" / SEO content sites
    "strategy.com", "simplilearn.com", "coursera.org", "udemy.com",
    "oreilly.com", "dzone.com", "intellipaat.com",
}


def _is_blocked(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return domain in _BLOCKED_DOMAINS or any(domain.endswith("." + b) for b in _BLOCKED_DOMAINS)
    except Exception:
        return False


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def _source_tier(name: str) -> int:
    tiers = [
        (0, ["Databricks"]),
        (1, ["Snowflake", "Microsoft Fabric", "Microsoft AI",
             "Palantir", "Cloudera", "Dremio", "Starburst", "ClickHouse",
             "Teradata", "Oracle", "IBM", "SAP", "MongoDB", "Hex", "Deepnote",
             "Trino", "Presto", "Redshift", "BigQuery", "Vertex AI",
             "SageMaker", "Glue", "Synapse", "Apache Flink", "Apache Spark"]),
        (2, ["GitHub", "Cursor", "Anthropic", "OpenAI", "Claude", "Windsurf", "Gemini", "Kiro", "Codex"]),
        (3, ["DeepMind", "Meta AI", "NVIDIA", "Llama"]),
        (4, ["LangChain", "LangGraph", "LlamaIndex", "CrewAI", "AutoGen"]),
        (5, ["AWS", "Google Cloud", "Vercel", "Cloudflare"]),
    ]
    for tier, keywords in tiers:
        if any(k in name for k in keywords):
            return tier
    return 7


# ── RSS fetcher ───────────────────────────────────────────────────────────────

def fetch_rss_signals() -> List[Dict[str, Any]]:
    cutoff = _cutoff()
    signals: List[Dict[str, Any]] = []
    seen: set = set()

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                url = getattr(entry, "link", "")
                if not url or url in seen:
                    continue
                pub_date = _parse_date(entry)
                if pub_date < cutoff:
                    continue
                seen.add(url)
                signals.append({
                    "source":    source_name,
                    "title":     getattr(entry, "title", ""),
                    "url":       url,
                    "summary":   getattr(entry, "summary", "")[:600],
                    "published": pub_date.isoformat(),
                    "tier":      _source_tier(source_name),
                })
        except Exception as e:
            logger.warning(f"RSS fetch failed for {source_name}: {e}")

    logger.info(f"RSS: {len(signals)} signals from {len(RSS_FEEDS)} feeds")
    return signals


# ── Tavily search ─────────────────────────────────────────────────────────────

def fetch_tavily_signals() -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set — skipping web search")
        return []

    try:
        from tavily import TavilyClient
    except ImportError:
        logger.error("tavily-python not installed — run: pip install tavily-python")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    signals: List[Dict[str, Any]] = []
    seen: set = set()

    for query in _tavily_queries():
        try:
            result = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                days=2,           # only results from the past 2 days
                include_answer=False,
            )
            for r in result.get("results", []):
                url = r.get("url", "")
                if not url or url in seen or _is_blocked(url):
                    continue
                seen.add(url)
                signals.append({
                    "source":    f"Web: {r.get('source', r.get('url','')[:40])}",
                    "title":     r.get("title", ""),
                    "url":       url,
                    "summary":   r.get("content", "")[:600],
                    "published": r.get("published_date") or datetime.now(timezone.utc).isoformat(),
                    "tier":      _source_tier(r.get("url", "")),
                    "query":     query,
                })
        except Exception as e:
            logger.warning(f"Tavily failed for '{query[:50]}': {e}")

    logger.info(f"Tavily: {len(signals)} signals from {len(_tavily_queries())} queries")
    return signals


# ── Public API ────────────────────────────────────────────────────────────────

def collect_all_signals() -> List[Dict[str, Any]]:
    """
    Collect, deduplicate, filter previously-seen stories,
    and return up to 120 fresh signals sorted by tier then recency.
    Only signals from the past 48 hours are included.
    """
    rss = fetch_rss_signals()
    web = fetch_tavily_signals()

    # Hard 48-hour freshness cutoff — drop anything older regardless of source
    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    fresh_rss_web = []
    dropped = 0
    for s in rss + web:
        pub = s.get("published", "")
        try:
            from datetime import datetime as _dt
            pub_dt = _dt.fromisoformat(pub.replace("Z", "+00:00"))
            if pub_dt < cutoff_48h:
                dropped += 1
                continue
        except Exception:
            pass  # if date unparseable, keep the signal
        fresh_rss_web.append(s)
    if dropped:
        logger.info(f"Dropped {dropped} signals older than 48h")

    # Deduplicate by URL within this run
    seen_urls: set = set()
    unique: List[Dict[str, Any]] = []
    for s in fresh_rss_web:
        url = s.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(s)

    # Filter out stories already featured in past briefs
    try:
        from state import filter_fresh
        unique = filter_fresh(unique)
    except Exception as e:
        logger.warning(f"State filter skipped: {e}")

    # Sort: tier ASC (0 = most important), then published DESC
    unique.sort(key=lambda s: (s.get("tier", 9), ""), reverse=False)
    unique.sort(key=lambda s: s.get("published", ""), reverse=True)

    logger.info(f"Total fresh signals: {len(unique)}")
    return unique[:120]
