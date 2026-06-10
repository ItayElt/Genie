#!/usr/bin/env python3
"""Genie Code PM Morning Brief — daily AI newsletter for Databricks PMs."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytz

from config import get_recipients
from searcher import collect_all_signals
from generator import generate_newsletter, extract_featured_urls
from emailer import send_newsletter, build_html
from state import mark_as_seen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def save_debug_artifacts(newsletter: dict) -> None:
    tz = pytz.timezone("America/Los_Angeles")
    stamp = datetime.now(tz).strftime("%Y-%m-%d")

    json_path = LOGS_DIR / f"brief_{stamp}.json"
    json_path.write_text(json.dumps(newsletter, indent=2))
    logger.info(f"JSON → {json_path}")

    html_path = LOGS_DIR / f"brief_{stamp}.html"
    html_path.write_text(build_html(newsletter))
    logger.info(f"HTML → {html_path}")


def main(dry_run: bool = False) -> None:
    logger.info("=== Genie Code PM Morning Brief ===")

    # Load recipients
    recipients = get_recipients()
    if not recipients and not dry_run:
        logger.error("No recipients configured. Run: python3 manage.py add email@example.com")
        sys.exit(1)
    logger.info(f"Recipients: {recipients if recipients else '(dry-run, no email)'}")

    # 1. Collect fresh signals (already-seen URLs filtered out by state.py)
    logger.info("Collecting signals...")
    signals = collect_all_signals()
    logger.info(f"Fresh signals: {len(signals)}")

    if not signals:
        logger.warning("No fresh signals — all recent news already seen, or check API keys.")
        sys.exit(1)

    # 2. Generate newsletter
    logger.info("Generating newsletter via Claude...")
    newsletter = generate_newsletter(signals)

    # 3. Save HTML + JSON to logs/
    save_debug_artifacts(newsletter)

    if dry_run:
        logger.info("Dry-run: saved to logs/, no email sent.")
        return

    # 4. Send email
    success = send_newsletter(newsletter, recipients)

    if success:
        # 5. Only mark stories as seen AFTER confirmed delivery
        featured_urls = extract_featured_urls(newsletter)
        mark_as_seen(featured_urls)
        logger.info(f"Delivered. {len(featured_urls)} URLs marked as seen.")
    else:
        logger.error("Delivery failed — URLs NOT marked as seen (will retry tomorrow).")
        sys.exit(1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
