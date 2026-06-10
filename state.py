"""
Tracks which URLs and story topics have already appeared in past briefs,
so the newsletter never repeats the same news two days in a row.

State is persisted to state/seen_stories.json.
Entries older than PRUNE_DAYS are automatically removed.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "state" / "seen_stories.json"
PRUNE_DAYS = 14  # forget a story after 14 days so it can resurface if still relevant


def _load() -> Dict[str, str]:
    """Return {url: iso_date_added}."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save(state: Dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _prune(state: Dict[str, str]) -> Dict[str, str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)).isoformat()
    return {url: d for url, d in state.items() if d >= cutoff}


def get_seen_urls() -> Set[str]:
    """Return the set of URLs already featured in recent briefs."""
    return set(_prune(_load()).keys())


def mark_as_seen(urls: List[str]) -> None:
    """Record that these URLs were featured in today's brief."""
    state = _prune(_load())
    now = datetime.now(timezone.utc).isoformat()
    for url in urls:
        if url:
            state[url] = now
    _save(state)
    logger.info(f"Marked {len(urls)} URLs as seen (state total: {len(state)})")


def filter_fresh(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove signals whose URLs have already been featured."""
    seen = get_seen_urls()
    fresh = [s for s in signals if s.get("url", "") not in seen]
    skipped = len(signals) - len(fresh)
    if skipped:
        logger.info(f"Filtered {skipped} already-seen signals → {len(fresh)} fresh")
    return fresh


def get_stats() -> Dict[str, Any]:
    state = _prune(_load())
    return {
        "total_seen": len(state),
        "oldest": min(state.values()) if state else None,
        "newest": max(state.values()) if state else None,
    }
