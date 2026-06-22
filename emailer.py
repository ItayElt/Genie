"""
Email sender with an inline HTML template.
Supports Gmail SMTP (default) or SendGrid.
No external images — pure CSS/text layout for reliable Gmail rendering.
"""

import logging
import re
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

from config import (
    SENDGRID_API_KEY, SENDER_EMAIL, SENDER_NAME,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
)

logger = logging.getLogger(__name__)

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


# ── Component builders ────────────────────────────────────────────────────────

def _badge(rank: str) -> str:
    colors = {"P0": "#CC0000", "P1": "#C05621"}
    color = colors.get(rank, "#666666")
    return (
        f'<span style="display:inline-block;background:{color};color:#FFFFFF;'
        f'font-size:10px;font-weight:700;letter-spacing:1px;padding:2px 7px;'
        f'border-radius:3px;font-family:monospace;vertical-align:middle">{rank}</span>'
    )


def _story_card(story: Dict[str, Any]) -> str:
    rank = story.get("rank", "P1")
    left_color = {"P0": "#CC0000", "P1": "#DD6B20"}.get(rank, "#999999")

    details_html = "".join(
        f'<li style="margin-bottom:7px;font-size:15px;color:#333333;line-height:1.65;'
        f'font-family:{_FONT}">{d}</li>'
        for d in story.get("details", [])
    )
    sources_html = " &nbsp;·&nbsp; ".join(
        f'<a href="{s["url"]}" style="color:#2563EB;text-decoration:none;font-size:12px;'
        f'font-family:{_FONT}">{s["title"]}'
        + (f' ({s["date"]})' if s.get("date") else "")
        + "</a>"
        for s in story.get("sources", []) if s.get("url")
    )

    return f"""
<div style="border:1px solid #E8E8E8;border-left:3px solid {left_color};
            border-radius:4px;padding:20px 22px;margin-bottom:14px;background:#FFFFFF">

  <div style="margin-bottom:8px">
    <span style="font-size:10px;font-weight:700;letter-spacing:1.2px;color:#AAAAAA;
                 text-transform:uppercase;margin-right:10px;font-family:{_FONT}">{story.get('category','')}</span>
    {_badge(rank)}
  </div>

  <h2 style="margin:0 0 12px;font-size:17px;font-weight:700;color:#111111;line-height:1.35;
             font-family:{_FONT}">
    {story.get('headline','')}
  </h2>

  <p style="margin:0 0 13px;color:#333333;font-size:15px;line-height:1.7;font-family:{_FONT}">
    {story.get('brief','')}
  </p>

  <ul style="margin:0 0 14px;padding-left:20px">
    {details_html}
  </ul>

  <div style="background:#F0F7FF;border-left:3px solid #2563EB;padding:11px 15px;
              border-radius:0 4px 4px 0;margin-bottom:12px">
    <div style="font-size:10px;font-weight:700;color:#1D4ED8;letter-spacing:1px;
                text-transform:uppercase;margin-bottom:5px;font-family:{_FONT}">Why it matters for Genie Code</div>
    <p style="margin:0;color:#1E3A5F;font-size:15px;line-height:1.65;font-family:{_FONT}">
      {story.get('why_it_matters','')}
    </p>
  </div>

  {"<div style='font-size:12px;color:#AAAAAA;font-family:" + _FONT + "'>Source: " + sources_html + "</div>" if sources_html else ""}
</div>
"""


def _competitor_item(item: Dict[str, Any]) -> str:
    url = item.get("url", "")
    link = (
        f' <a href="{url}" style="color:#7C3AED;font-size:12px;text-decoration:none;'
        f'font-family:{_FONT}">→</a>'
        if url else ""
    )
    return f"""
<div style="border-left:3px solid #7C3AED;padding:11px 15px;margin-bottom:12px;
            background:#FAF5FF;border-radius:0 4px 4px 0">
  <div style="font-weight:700;color:#5B21B6;font-size:14px;margin-bottom:4px;
              font-family:{_FONT}">
    {item.get('company','')}{link}
  </div>
  <p style="margin:0 0 4px;color:#333333;font-size:15px;line-height:1.6;font-family:{_FONT}">
    {item.get('what_happened','')}
  </p>
  <p style="margin:0;color:#555555;font-size:14px;line-height:1.6;font-family:{_FONT}">
    {item.get('why_it_matters','')}
  </p>
</div>
"""


def _quick_hit(item: Dict[str, Any]) -> str:
    url = item.get("url", "#")
    text = item.get("text", "")
    return (
        f'<li style="margin-bottom:9px;font-size:15px;color:#333333;line-height:1.55;'
        f'font-family:{_FONT}">'
        f'<a href="{url}" style="color:#333333;text-decoration:none">{text}</a>'
        f"</li>"
    )


# ── HTML assembler ────────────────────────────────────────────────────────────

def build_html(newsletter: Dict[str, Any]) -> str:
    date_str = newsletter.get("date", datetime.now().strftime("%B %-d, %Y"))

    # TOC — strip any [Category Tag] — prefixes Claude may have included
    _tag_re = re.compile(r'^\[[^\]]+\]\s*[—\-]\s*')
    toc_items = "".join(
        f'<li style="margin-bottom:8px;font-size:15px;color:#222222;line-height:1.45;'
        f'font-family:{_FONT}">'
        f'• &nbsp;{_tag_re.sub("", item)}</li>'
        for item in newsletter.get("toc", [])
    )

    # Stories
    p0_html = "".join(_story_card(s) for s in newsletter.get("p0_stories", []))
    p1_html = "".join(_story_card(s) for s in newsletter.get("p1_stories", []))

    # Competitor watch
    comp_items = newsletter.get("competitor_watch", [])
    comp_html = ""
    if comp_items:
        cards = "".join(_competitor_item(c) for c in comp_items)
        comp_html = f"""
<div style="margin:32px 0 0">
  <div style="font-size:11px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
              color:#111111;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #7C3AED;
              font-family:{_FONT}">Competitor Watch</div>
  {cards}
</div>"""

    # Quick hits
    qh_html = ""
    hits = newsletter.get("quick_hits", [])
    if hits:
        items = "".join(_quick_hit(h) for h in hits)
        qh_html = f"""
<div style="margin:32px 0 0">
  <div style="font-size:11px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
              color:#111111;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #DDDDDD;
              font-family:{_FONT}">Quick Hits</div>
  <ul style="margin:0;padding-left:0;list-style:none">{items}</ul>
</div>"""

    # Observations
    obs_html = ""
    obs = newsletter.get("observations", [])
    if obs:
        items = "".join(
            f'<li style="margin-bottom:10px;font-size:15px;color:#333333;'
            f'line-height:1.65;font-family:{_FONT}">{o}</li>'
            for o in obs
        )
        obs_html = f"""
<div style="margin:32px 0 0">
  <div style="font-size:11px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
              color:#111111;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #DDDDDD;
              font-family:{_FONT}">What PMs Should Be Talking About</div>
  <ul style="margin:0;padding-left:18px">{items}</ul>
</div>"""

    # Community Sentiment (Fridays only)
    cs_html = ""
    cs_items = newsletter.get("community_sentiment", [])
    if cs_items:
        def _cs_card(item: Dict[str, Any]) -> str:
            url = item.get("url", "")
            platform = item.get("platform", "")
            engagement = item.get("engagement", "")
            summary = item.get("summary", "")
            header_line = f"{platform}"
            if engagement:
                header_line += f" &nbsp;·&nbsp; {engagement}"
            link_html = (
                f' <a href="{url}" style="color:#065F46;font-size:12px;text-decoration:none;'
                f'font-family:{_FONT}">→</a>'
                if url else ""
            )
            return f"""
<div style="border-left:3px solid #059669;padding:11px 15px;margin-bottom:12px;
            background:#ECFDF5;border-radius:0 4px 4px 0">
  <div style="font-weight:700;color:#065F46;font-size:13px;margin-bottom:4px;
              font-family:{_FONT}">{header_line}{link_html}</div>
  <p style="margin:0;color:#333333;font-size:15px;line-height:1.6;font-family:{_FONT}">{summary}</p>
</div>"""

        cards = "".join(_cs_card(c) for c in cs_items)
        cs_html = f"""
<div style="margin:32px 0 0">
  <div style="font-size:11px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;
              color:#111111;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #059669;
              font-family:{_FONT}">Community Sentiment</div>
  {cards}
</div>"""

    # Good morning — bold only the opening phrase (first sentence), rest normal
    gm_raw = newsletter.get("good_morning", "").strip()
    first_dot = gm_raw.find(". ")
    if first_dot > 0:
        gm_html = (
            f'<p style="margin:0;color:#111111;font-size:16px;line-height:1.75;font-family:{_FONT}">'
            f'<strong>{gm_raw[:first_dot+1]}</strong> {gm_raw[first_dot+2:]}</p>'
        )
    else:
        gm_html = (
            f'<p style="margin:0;color:#111111;font-size:16px;line-height:1.75;font-family:{_FONT}">'
            f'{gm_raw}</p>'
        )

    def section_header(label: str) -> str:
        return (
            f'<div style="font-size:11px;font-weight:700;letter-spacing:1.8px;'
            f'text-transform:uppercase;color:#111111;margin:32px 0 18px;'
            f'padding-bottom:8px;border-bottom:2px solid #FF3621;font-family:{_FONT}">{label}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Genie Code PM Morning Brief — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#F2F2F2;font-family:{_FONT}">

<div style="max-width:640px;margin:24px auto;padding:0 12px">

  <!-- ── HERO: pure CSS, no external images ── -->
  <div style="background:#000000;border-radius:8px 8px 0 0;padding:38px 32px 34px;text-align:center">
    <div style="color:#FFFFFF;font-size:30px;font-weight:800;letter-spacing:-0.5px;
                line-height:1.15;font-family:{_FONT}">
      Genie Code
    </div>
    <div style="color:#FF3621;font-size:13px;font-weight:700;letter-spacing:2.5px;
                text-transform:uppercase;margin-top:6px;font-family:{_FONT}">
      PM Morning Brief
    </div>
    <div style="color:#666666;font-size:12px;margin-top:10px;font-family:{_FONT}">
      {date_str}
    </div>
  </div>

  <!-- ── MAIN CONTENT ── -->
  <div style="background:#FFFFFF;border:1px solid #E0E0E0;border-top:none;
              border-radius:0 0 8px 8px;overflow:hidden">

    <!-- Good Morning -->
    <div style="padding:28px 32px 26px;border-bottom:1px solid #EEEEEE">
      {gm_html}
    </div>

    <!-- TOC -->
    <div style="padding:22px 32px 24px;border-bottom:1px solid #EEEEEE;background:#FAFAFA">
      <div style="font-size:15px;font-weight:700;color:#111111;margin-bottom:14px;
                  font-family:{_FONT}">
        In today's brief:
      </div>
      <ul style="margin:0;padding-left:0;list-style:none">{toc_items}</ul>
    </div>

    <!-- Stories -->
    <div style="padding:10px 32px 36px">
      {section_header("Top Developments")}
      {p0_html}
      {p1_html}
      {comp_html}
      {qh_html}
      {obs_html}
      {cs_html}
    </div>

  </div>

  <!-- ── FOOTER ── -->
  <div style="text-align:center;padding:20px 0 30px">
    <p style="margin:0;font-size:11px;color:#AAAAAA;line-height:1.8;font-family:{_FONT}">
      Genie Code PM Morning Brief &nbsp;·&nbsp; {date_str}<br>
      Built for PMs on Genie Code at Databricks.<br>
      <a href="mailto:itayeltahan1@gmail.com?subject=Unsubscribe"
         style="color:#AAAAAA;text-decoration:underline">Unsubscribe</a>
    </p>
  </div>

</div>
</body>
</html>"""


# ── Senders ───────────────────────────────────────────────────────────────────

def _send_sendgrid(subject: str, html: str, recipients: List[str]) -> bool:
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        msg = Mail(
            from_email=(SENDER_EMAIL, SENDER_NAME),
            to_emails=recipients,
            subject=subject,
            html_content=html,
        )
        r = sg.send(msg)
        logger.info(f"SendGrid: {r.status_code}")
        return r.status_code in (200, 202)
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False


def _send_smtp(subject: str, html: str, recipients: List[str]) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{SENDER_NAME} <{SMTP_USER}>"
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html, "html"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
        logger.info(f"SMTP: delivered to {recipients}")
        return True
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False


def send_newsletter(newsletter: Dict[str, Any], recipients: List[str]) -> bool:
    if not recipients:
        logger.error("No recipients — add emails via: python3 manage.py add email@example.com")
        return False

    date_str = newsletter.get("date", datetime.now().strftime("%B %-d, %Y"))
    subject  = f"Genie Code PM Brief — {date_str}"
    html     = build_html(newsletter)

    if SENDGRID_API_KEY:
        return _send_sendgrid(subject, html, recipients)
    elif SMTP_USER and SMTP_PASSWORD:
        return _send_smtp(subject, html, recipients)
    else:
        logger.error("No email transport. Set SENDGRID_API_KEY or SMTP_USER+SMTP_PASSWORD in .env")
        return False
