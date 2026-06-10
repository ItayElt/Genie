#!/usr/bin/env python3
"""
CLI for managing the Genie Code PM Morning Brief.

Commands:
  python3 manage.py list                    — list all active recipients
  python3 manage.py add email@example.com   — add a recipient
  python3 manage.py remove email@example.com — remove a recipient
  python3 manage.py check                   — validate config and API keys
  python3 manage.py test                    — send a test email (uses last generated HTML)
  python3 manage.py run                     — generate and send today's brief right now
  python3 manage.py dry-run                 — generate brief, save HTML, no email
  python3 manage.py state                   — show deduplication stats
  python3 manage.py reset-state             — clear seen-stories state (re-run stories)
"""

import sys
import os
import smtplib
import ssl
from pathlib import Path
from datetime import datetime

# ── Bootstrap path ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

RECIPIENTS_FILE = ROOT / "recipients.txt"
LOGS_DIR = ROOT / "logs"


# ── Recipients helpers ───────────────────────────────────────────────────────

def _read_lines() -> list[str]:
    if not RECIPIENTS_FILE.exists():
        return []
    return RECIPIENTS_FILE.read_text().splitlines()


def _write_lines(lines: list[str]) -> None:
    RECIPIENTS_FILE.write_text("\n".join(lines) + "\n")


def get_active_recipients() -> list[str]:
    """Return all non-commented, non-paused email addresses."""
    emails = []
    for line in _read_lines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            emails.append(stripped)
    return emails


def cmd_list() -> None:
    active = get_active_recipients()
    all_lines = _read_lines()
    paused = [
        l.strip().lstrip("-")
        for l in all_lines
        if l.strip().startswith("-")
    ]
    print(f"\n{'─'*44}")
    print(f"  Genie Code PM Brief — Recipients")
    print(f"{'─'*44}")
    if active:
        print(f"\n  Active ({len(active)}):")
        for e in active:
            print(f"    ✓ {e}")
    else:
        print("\n  No active recipients.")
    if paused:
        print(f"\n  Paused ({len(paused)}):")
        for e in paused:
            print(f"    ⏸ {e}")
    print(f"\n  File: {RECIPIENTS_FILE}\n")


def cmd_add(email: str) -> None:
    email = email.strip().lower()
    lines = _read_lines()
    active = get_active_recipients()

    if email in active:
        print(f"  ✓ {email} is already a recipient.")
        return

    # Re-activate if paused
    new_lines = []
    reactivated = False
    for line in lines:
        if line.strip() == f"-{email}":
            new_lines.append(email)
            reactivated = True
        else:
            new_lines.append(line)

    if not reactivated:
        new_lines.append(email)

    _write_lines(new_lines)
    action = "Re-activated" if reactivated else "Added"
    print(f"  ✓ {action}: {email}")
    print(f"  Total active: {len(get_active_recipients())}")


def cmd_remove(email: str) -> None:
    email = email.strip().lower()
    lines = _read_lines()
    new_lines = []
    found = False
    for line in lines:
        if line.strip() == email:
            new_lines.append(f"-{email}  # paused {datetime.now().strftime('%Y-%m-%d')}")
            found = True
        else:
            new_lines.append(line)
    if found:
        _write_lines(new_lines)
        print(f"  ✓ Paused (not deleted): {email}")
        print("    To permanently remove, edit recipients.txt manually.")
    else:
        print(f"  ✗ Not found: {email}")


# ── System check ─────────────────────────────────────────────────────────────

def cmd_check() -> None:
    print(f"\n{'─'*44}")
    print("  Genie Code PM Brief — System Check")
    print(f"{'─'*44}\n")

    ok = True

    def check(label: str, value: str | None, hint: str = "") -> None:
        nonlocal ok
        if value:
            print(f"  ✓ {label}")
        else:
            print(f"  ✗ {label} — NOT SET{f' ({hint})' if hint else ''}")
            ok = False

    # API keys
    check("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"), "required — get at console.anthropic.com")
    check("TAVILY_API_KEY",    os.getenv("TAVILY_API_KEY"),    "required — get at app.tavily.com (free tier available)")

    # Email transport
    sg   = os.getenv("SENDGRID_API_KEY")
    smtp = os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD")
    if sg:
        check("SENDGRID_API_KEY", sg)
    elif smtp:
        check("SMTP_USER",     os.getenv("SMTP_USER"))
        check("SMTP_PASSWORD", os.getenv("SMTP_PASSWORD"), "Gmail App Password — see README")
    else:
        print("  ✗ No email transport — set SENDGRID_API_KEY or SMTP_USER+SMTP_PASSWORD")
        ok = False

    # Optional
    unsplash = os.getenv("UNSPLASH_ACCESS_KEY")
    print(f"  {'✓' if unsplash else '○'} UNSPLASH_ACCESS_KEY {'(hero image)' if unsplash else '— optional, hero will use fallback image'}")

    # Recipients
    recipients = get_active_recipients()
    if recipients:
        print(f"  ✓ Recipients ({len(recipients)}): {', '.join(recipients)}")
    else:
        print("  ✗ No recipients — run: python3 manage.py add your@email.com")
        ok = False

    # State
    try:
        from state import get_stats
        stats = get_stats()
        print(f"  ✓ Dedup state: {stats['total_seen']} seen URLs tracked")
    except Exception as e:
        print(f"  ○ Dedup state: not yet initialized ({e})")

    print(f"\n  {'✅ All good — ready to send!' if ok else '⚠️  Fix the issues above before running.'}\n")
    return ok


# ── Test email ───────────────────────────────────────────────────────────────

def cmd_test() -> None:
    """Send a test email using the most recently generated HTML, or a simple ping."""
    recipients = get_active_recipients()
    if not recipients:
        print("  ✗ No recipients configured. Run: python3 manage.py add your@email.com")
        return

    # Find most recent HTML
    html_files = sorted(LOGS_DIR.glob("brief_*.html"), reverse=True)
    if html_files:
        html = html_files[0].read_text()
        subject = f"[TEST] Genie Code PM Brief — {html_files[0].stem.replace('brief_', '')}"
        print(f"  Using: {html_files[0].name}")
    else:
        html = "<h1>Test email from Genie Code PM Brief</h1><p>Setup is working correctly.</p>"
        subject = "[TEST] Genie Code PM Brief — ping"

    from emailer import send_newsletter
    # Wrap as minimal newsletter dict for the sender
    success = _send_raw(subject, html, recipients)
    if success:
        print(f"  ✓ Test email sent to: {', '.join(recipients)}")
    else:
        print("  ✗ Send failed — run: python3 manage.py check")


def _send_raw(subject: str, html: str, recipients: list[str]) -> bool:
    import os
    sg = os.getenv("SENDGRID_API_KEY")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SENDER_EMAIL") or smtp_user or "brief@example.com"

    if sg:
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            client = sendgrid.SendGridAPIClient(api_key=sg)
            msg = Mail(
                from_email=(sender, "Genie Code PM Brief"),
                to_emails=recipients,
                subject=subject,
                html_content=html,
            )
            r = client.send(msg)
            return r.status_code in (200, 202)
        except Exception as e:
            print(f"  SendGrid error: {e}")
            return False
    elif smtp_user and smtp_pass:
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Genie Code PM Brief <{smtp_user}>"
            msg["To"] = ", ".join(recipients)
            msg.attach(MIMEText(html, "html"))
            ctx = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls(context=ctx)
                s.login(smtp_user, smtp_pass)
                s.sendmail(smtp_user, recipients, msg.as_string())
            return True
        except Exception as e:
            print(f"  SMTP error: {e}")
            return False
    return False


# ── State management ─────────────────────────────────────────────────────────

def cmd_state() -> None:
    from state import get_stats
    stats = get_stats()
    print(f"\n  Dedup state: {stats['total_seen']} URLs tracked")
    if stats["oldest"]:
        print(f"  Oldest entry: {stats['oldest'][:10]}")
        print(f"  Newest entry: {stats['newest'][:10]}")
    print()


def cmd_reset_state() -> None:
    state_file = ROOT / "state" / "seen_stories.json"
    if state_file.exists():
        state_file.unlink()
        print("  ✓ State cleared. All stories are now eligible to appear again.")
    else:
        print("  ○ State file doesn't exist yet — nothing to clear.")


# ── Run ───────────────────────────────────────────────────────────────────────

def cmd_run(dry: bool = False) -> None:
    import main as m
    m.main(dry_run=dry)


# ── Entry point ───────────────────────────────────────────────────────────────

HELP = __doc__

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(HELP)
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "add" and len(args) == 2:
        cmd_add(args[1])
    elif args[0] == "remove" and len(args) == 2:
        cmd_remove(args[1])
    elif args[0] == "check":
        cmd_check()
    elif args[0] == "test":
        cmd_test()
    elif args[0] == "run":
        cmd_run(dry=False)
    elif args[0] == "dry-run":
        cmd_run(dry=True)
    elif args[0] == "state":
        cmd_state()
    elif args[0] == "reset-state":
        cmd_reset_state()
    else:
        print(f"  Unknown command: {' '.join(args)}")
        print(HELP)
        sys.exit(1)
