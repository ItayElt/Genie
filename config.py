import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
# Hardcoded to Sonnet to keep cost ~$3.50/month (never change to Opus — that exceeds $5/month)
CLAUDE_MODEL        = "claude-sonnet-4-6"
TAVILY_API_KEY      = os.getenv("TAVILY_API_KEY")
SENDGRID_API_KEY    = os.getenv("SENDGRID_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

SENDER_EMAIL = os.getenv("SENDER_EMAIL", os.getenv("SMTP_USER", ""))
SENDER_NAME  = os.getenv("SENDER_NAME", "Genie Code PM Brief")

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "36"))


def get_recipients() -> list[str]:
    """
    Load active recipients from recipients.txt.
    Falls back to RECIPIENT_EMAILS env var for backwards compatibility.
    """
    recipients_file = Path(__file__).parent / "recipients.txt"
    if recipients_file.exists():
        emails = []
        for line in recipients_file.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                emails.append(stripped)
        if emails:
            return emails

    # Fallback: env var
    env_val = os.getenv("RECIPIENT_EMAILS", "")
    return [e.strip() for e in env_val.split(",") if e.strip()]
