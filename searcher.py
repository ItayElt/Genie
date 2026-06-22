"""
Multi-source signal collector.
Strategy:
  1. Parse RSS feeds from Tier 1 sources (conversational analytics competitors).
  2. Run targeted Tavily searches for broader coverage and NL-to-SQL benchmarks.
  3. On Fridays: scan HN/Reddit for high-engagement community discussion.
  4. Deduplicate by URL.
  5. Filter out URLs already featured in recent briefs (via state.py).
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import feedparser

from config import TAVILY_API_KEY, LOOKBACK_HOURS

logger = logging.getLogger(__name__)

_NOW = datetime.now()
_MONTH_YEAR = _NOW.strftime("%B %Y")      # e.g. "June 2026"
_IS_FRIDAY = _NOW.weekday() == 4


# -- RSS FEEDS  (Tier 1 = conversational analytics competitors, always scraped) ----

RSS_FEEDS: Dict[str, str] = {
    # Tier 1 -- Direct NL-to-SQL / conversational analytics competitors
    "Snowflake Blog":           "https://www.snowflake.com/blog/feed/",
    "Microsoft AI Blog":        "https://blogs.microsoft.com/ai/feed/",
    "Microsoft Fabric":         "https://community.fabric.microsoft.com/t5/s/gxcuf89792/rss/board?board.id=FabricUpdates",
    "Google Cloud AI":          "https://cloud.google.com/feeds/gcp-blog-topics-ai-machine-learning.xml",
    "Google Cloud Blog":        "https://cloud.google.com/feeds/gcp-blog-topics-databases.xml",
    "ThoughtSpot Blog":         "https://www.thoughtspot.com/blog/rss.xml",
    "Hex Blog":                 "https://hex.tech/blog/rss.xml",
    "AWS ML Blog":              "https://aws.amazon.com/blogs/machine-learning/feed/",
    "AWS Big Data Blog":        "https://aws.amazon.com/blogs/big-data/feed/",

    # Tier 1 -- Databricks (context only, never standalone Genie Code)
    "Databricks Blog":          "https://www.databricks.com/feed",
    "Databricks Engineering":   "https://www.databricks.com/blog/engineering/feed",

    # Tier 2 -- AI coding agents (data-context only)
    "GitHub Blog":              "https://github.blog/feed/",
    "GitHub Changelog":         "https://github.blog/changelog/feed/",
    "Anthropic Blog":           "https://www.anthropic.com/rss.xml",
    "OpenAI Blog":              "https://openai.com/news/rss.xml",
    "Cursor Blog":              "https://cursor.com/blog/rss.xml",

    # Tier 3 -- Foundation models (quick hits only)
    "Google DeepMind":          "https://deepmind.google/discover/blog/rss.xml",
    "Meta AI Blog":             "https://ai.meta.com/blog/rss/",
    "NVIDIA Blog":              "https://blogs.nvidia.com/feed/",

    # Agent frameworks (data workflow context)
    "LangChain Blog":           "https://blog.langchain.dev/rss/",

    # Data ecosystem
    "ClickHouse Blog":          "https://clickhouse.com/blog/rss.xml",
    "MongoDB Blog":             "https://www.mongodb.com/developer/feed.xml",
    "Trino Blog":               "https://trino.io/feed.xml",
    "Vercel Blog":              "https://vercel.com/atom",

    # Community (high-engagement signals only -- Claude filters by pillar relevance)
    "Hacker News Front Page":   "https://hnrss.org/frontpage",
    "Hacker News Best":         "https://hnrss.org/best",
}


# -- TAVILY QUERIES  (full list -- budget mode: set TAVILY_BUDGET=1 in .env to use 8) ----

def _tavily_queries() -> List[str]:
    """
    Full 29-query list (30 credits/day, 870/month -- fits free tier of 1,000).
    In budget mode (8 queries) comment block is active to cut to top-value queries only.
    """
    my = _MONTH_YEAR  # "June 2026"

    # BUDGET MODE: uncomment this block and comment out the full list below
    # return [
    #     f"Snowflake Cortex Analyst NL-to-SQL conversational analytics {my}",
    #     f"Microsoft Fabric Copilot Power BI AI data agent {my}",
    #     f"Google BigQuery Gemini data agent NL-to-SQL {my}",
    #     f"ThoughtSpot Sigma Omni Looker conversational BI update {my}",
    #     f"AWS QuickSight Q Bedrock agents data analytics {my}",
    #     f"Hex Magic AI notebook data agent {my}",
    #     f"NL-to-SQL text-to-SQL benchmark BIRD Spider arXiv {my}",
    #     f"Tableau Salesforce Agentforce analytics AI agent {my}",
    # ]

    return [
        # Tier 1 -- Conversational analytics / NL-to-SQL direct competitors
        f"Snowflake Cortex Analyst Intelligence NL-to-SQL conversational analytics {my}",
        f"Microsoft Fabric Copilot Power BI natural language data agent {my}",
        f"Google BigQuery Gemini data agent NL-to-SQL conversational {my}",
        f"ThoughtSpot Sage AI natural language analytics update {my}",
        f"Sigma Computing AI analytics agent update {my}",
        f"Omni Analytics AI conversational BI update {my}",
        f"Looker conversational analytics natural language update {my}",
        f"Tableau Next Salesforce Agentforce analytics AI agent {my}",
        f"Hex Magic AI notebook data agent update {my}",
        f"AWS Q QuickSight Bedrock data analytics agent {my}",

        # Tier 1 -- Other data platforms with NL/agent features
        f"Palantir AIP Foundry data agent NL query {my}",
        f"Databricks Delta Lake Unity Catalog MLflow platform update {my}",
        f"Databricks partnership acquisition pricing enterprise announcement {my}",
        f"ClickHouse Starburst Dremio data lakehouse AI query {my}",
        f"dbt Labs semantic layer natural language data transformation {my}",

        # Tier 2 -- AI coding agents (data context only)
        f"GitHub Copilot SQL data agent update {my}",
        f"Cursor AI SQL data workflow update {my}",
        f"Claude Code Anthropic data SQL agent update {my}",
        f"OpenAI Codex Windsurf Devin data agent SQL {my}",

        # Tier 3 -- Foundation models (only if text-to-SQL relevant)
        f"OpenAI model SQL code generation benchmark {my}",
        f"Anthropic Claude model SQL code latency pricing {my}",
        f"Google Gemini model SQL code generation update {my}",
        f"Meta Llama model SQL code generation release {my}",

        # Benchmarks and research (mandatory scan)
        f"NL-to-SQL text-to-SQL BIRD Spider 2.0 benchmark leaderboard {my}",
        f"NL-to-SQL agentic data analysis arXiv research {my}",
        f"LLM SQL code generation benchmark arXiv {my}",

        # Agent frameworks
        f"LangGraph LangChain CrewAI LlamaIndex data workflow agent {my}",

        # Data ecosystem
        f"Apache Iceberg Delta Lake open table format release {my}",
        f"Fivetran Airbyte data integration pipeline announcement {my}",
    ]


def _friday_community_queries() -> List[str]:
    """Friday-only: scan for high-engagement community discussion."""
    my = _MONTH_YEAR
    return [
        f"Genie Code Cortex Analyst Fabric Copilot conversational BI community discussion {my}",
        f"natural language SQL data analyst AI tool Hacker News Reddit discussion {my}",
    ]


# Domains blocked from appearing as signals
_BLOCKED_DOMAINS = {
    # Content farms / regional blogs
    "techafricanews.com", "analyticsvidhya.com", "towardsdatascience.com",
    "kdnuggets.com", "dataversity.net", "aimagazine.com", "aibusiness.com",
    "tfir.io", "siliconangle.com", "itprotoday.com", "infoworld.com",
    # Personal / community platforms
    "medium.com", "substack.com", "dev.to", "hashnode.com", "beehiiv.com",
    "ghost.io", "blogspot.com", "wordpress.com",
    # Social / forums (HN/Reddit allowed only via RSS with engagement filter in Claude)
    "twitter.com", "x.com", "linkedin.com", "facebook.com", "quora.com",
    # Video (description scrapes)
    "youtube.com", "youtu.be",
    # Generic SEO content sites
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


# -- Helpers -------------------------------------------------------------------

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
        (1, ["Snowflake", "Microsoft Fabric", "Microsoft AI", "ThoughtSpot", "Sigma",
             "Omni", "Looker", "Tableau", "Salesforce", "Hex", "QuickSight",
             "BigQuery", "Vertex AI", "Gemini", "Palantir", "Bedrock",
             "Fabric", "Power BI"]),
        (0, ["Databricks"]),  # tier 0 for sorting but treated as context-only in prompt
        (2, ["GitHub", "Cursor", "Anthropic", "OpenAI", "Claude", "Windsurf",
             "Devin", "Codex"]),
        (3, ["DeepMind", "Meta AI", "NVIDIA", "Llama"]),
        (4, ["LangChain", "LangGraph", "LlamaIndex", "CrewAI", "AutoGen"]),
        (5, ["AWS", "Google Cloud", "Vercel", "ClickHouse", "MongoDB", "Trino",
             "dbt", "Fivetran", "Airbyte", "Iceberg", "Cloudera", "Dremio",
             "Starburst", "SageMaker", "Glue", "Redshift",
             "Apache Flink", "Apache Spark"]),
    ]
    for tier, keywords in tiers:
        if any(k in name for k in keywords):
            return tier
    return 7


# -- RSS fetcher ---------------------------------------------------------------

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


# -- Tavily search -------------------------------------------------------------

def fetch_tavily_signals(extra_queries: List[str] | None = None) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY not set -- skipping web search")
        return []

    try:
        from tavily import TavilyClient
    except ImportError:
        logger.error("tavily-python not installed -- run: pip install tavily-python")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    signals: List[Dict[str, Any]] = []
    seen: set = set()

    all_queries = _tavily_queries() + (extra_queries or [])

    for query in all_queries:
        try:
            result = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                days=2,
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

    logger.info(f"Tavily: {len(signals)} signals from {len(all_queries)} queries")
    return signals


# -- Public API ----------------------------------------------------------------

def collect_all_signals() -> List[Dict[str, Any]]:
    """
    Collect, deduplicate, filter previously-seen stories,
    and return up to 120 fresh signals sorted by tier then recency.
    Only signals from the past 48 hours are included.
    On Fridays, adds community sentiment queries.
    """
    rss = fetch_rss_signals()

    # On Fridays, add community-sentiment queries to the Tavily call
    friday_extras = _friday_community_queries() if _IS_FRIDAY else []
    web = fetch_tavily_signals(extra_queries=friday_extras)

    # Hard 48-hour freshness cutoff
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

    # Sort: tier ASC (1 = most important for our purposes), then published DESC
    unique.sort(key=lambda s: (s.get("tier", 9), ""), reverse=False)
    unique.sort(key=lambda s: s.get("published", ""), reverse=True)

    logger.info(f"Total fresh signals: {len(unique)} (Friday community scan: {_IS_FRIDAY})")
    return unique[:120]
