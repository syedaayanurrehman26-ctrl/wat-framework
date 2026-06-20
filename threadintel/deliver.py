#!/usr/bin/env python3
"""
ThreadIntel — Report Delivery Worker
Polls Supabase for 'done' reports that haven't been emailed yet, sends them.

Usage:
    python threadintel/deliver.py             # process one batch
    python threadintel/deliver.py --watch     # loop every 60s (foreground worker)
"""

import os, sys, time, logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
)
log = logging.getLogger("threadintel.deliver")

_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_SENTRY_DSN, traces_sample_rate=0.1,
                        environment=os.getenv("ENVIRONMENT", "production"))
    except ImportError:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from email_brief import build_html, _get_gmail_service  # type: ignore


def _supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    from supabase import create_client
    return create_client(url, key)


def _fetch_pending(sb):
    """Return reports that are done but not yet delivered."""
    return (
        sb.table("reports")
        .select("id, topic, subscriber_id, email, report_html, report_num, format, notes")
        .eq("status", "done")
        .eq("delivered", False)
        .execute()
        .data
    )


def _subscriber_email(sb, subscriber_id: str) -> tuple[str, str, str]:
    """Return (email, name, slack_webhook) for a subscriber."""
    rows = (
        sb.table("subscribers")
        .select("email, name, slack_webhook")
        .eq("id", subscriber_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return ("", "Subscriber", "")
    return (
        rows[0].get("email", ""),
        rows[0].get("name", "Subscriber"),
        rows[0].get("slack_webhook", "") or "",
    )


def _send_slack(webhook_url: str, topic: str, fmt: str, report_id: str, notes: str):
    """Post a report-ready notification to a Slack channel."""
    import json, urllib.request
    fmt_labels = {
        "email_brief": "Email Brief", "slides": "Slides",
        "docs": "Google Doc", "sheets": "Google Sheet", "all": "All Formats",
    }
    fmt_label = fmt_labels.get(fmt, fmt)
    import re
    url_match = re.search(r'output:\s*(https://[^\s|]+)', notes or '')
    output_url = url_match.group(1) if url_match else None
    portal_url = "https://threadintel.netlify.app/portal.html"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"*ThreadIntel Report Ready* ✦\n*Topic:* {topic}\n*Format:* {fmt_label}"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Open Portal"},
             "url": portal_url, "style": "primary"},
        ] + ([{"type": "button", "text": {"type": "plain_text", "text": f"Open {fmt_label} ↗"},
               "url": output_url}] if output_url else [])},
    ]
    payload = json.dumps({"blocks": blocks}).encode()
    req = urllib.request.Request(webhook_url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"    ↳ Slack notification sent")
    except Exception as e:
        print(f"    ↳ Slack notify failed: {e}")


def _parse_output_url(notes: str) -> str | None:
    """Extract the cloud output URL from a report's notes field."""
    if not notes:
        return None
    import re
    m = re.search(r'output:\s*(https://[^\s|]+)', notes)
    return m.group(1) if m else None


def _parse_pptx_path(notes: str) -> str | None:
    """Extract a local .pptx path from notes (for attachment)."""
    if not notes:
        return None
    import re
    m = re.search(r'output:\s*([^\s|]+\.pptx)', notes)
    return m.group(1) if m else None


def _send_report(service, to_email: str, subscriber_name: str, report: dict):
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    topic      = report.get("topic", "Your research")
    report_num = report.get("report_num")
    fmt        = (report.get("format") or "email_brief").lower()
    notes      = report.get("notes") or ""

    html_body = report.get("report_html") or build_html(
        {"topic": topic, "sections": []}, subscriber_name=subscriber_name, report_num=report_num
    )

    # Inject output link into email body for non-email formats
    output_url  = _parse_output_url(notes)
    pptx_path   = _parse_pptx_path(notes)

    fmt_labels = {
        "slides": "PowerPoint Slides", "pptx": "PowerPoint Slides",
        "docs": "Google Doc", "google_docs": "Google Doc",
        "sheets": "Google Sheet", "google_sheets": "Google Sheet",
        "all": "All Formats",
    }
    fmt_label = fmt_labels.get(fmt, "")

    if output_url and fmt_label:
        link_block = f"""
        <div style="font-family:Arial,sans-serif;background:rgba(124,111,255,.1);border:1px solid rgba(124,111,255,.3);
                    border-radius:12px;padding:20px 24px;margin:24px 0;text-align:center;">
          <div style="font-size:13px;color:#94A3B8;margin-bottom:8px;">Your {fmt_label} is ready</div>
          <a href="{output_url}"
             style="display:inline-block;background:linear-gradient(135deg,#7C6FFF,#5A4FE0);
                    color:#fff;font-weight:800;font-size:15px;padding:14px 32px;
                    border-radius:10px;text-decoration:none;">
            Open {fmt_label} ↗
          </a>
        </div>"""
        html_body = html_body.replace("</body>", link_block + "</body>")

    # Use AI-generated subject_line from Groq when available (stored in notes)
    import re as _re
    ai_subject_match = _re.search(r'subject:\s*(.+?)(?:\s*\||$)', notes)
    ai_subject = ai_subject_match.group(1).strip() if ai_subject_match else ""

    if ai_subject and len(ai_subject) > 10:
        subject = ai_subject
    elif fmt_label:
        subject = f"ThreadIntel: Your {fmt_label} on '{topic[:40]}' is ready"
    else:
        subject = f"ThreadIntel: Your report on '{topic[:50]}' is ready"

    msg = MIMEMultipart("mixed")
    msg["to"]      = to_email
    msg["from"]    = "me"
    msg["subject"] = subject

    # HTML body
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    # Attach .pptx if it exists locally
    if pptx_path:
        try:
            pptx_file = Path(pptx_path)
            if pptx_file.exists():
                with open(pptx_file, "rb") as f:
                    part = MIMEApplication(f.read(),
                        Name=f"ThreadIntel_{topic[:40].replace(' ','_')}.pptx")
                part["Content-Disposition"] = f'attachment; filename="{part.get_param("Name")}"'
                msg.attach(part)
                print(f"    ↳ Attached PPTX: {pptx_file.name}")
        except Exception as e:
            print(f"    ↳ PPTX attach failed: {e}")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  ✓ Delivered '{topic[:40]}' ({fmt}) to {to_email}")


def process_batch():
    sb = _supabase()
    service = _get_gmail_service()
    pending = _fetch_pending(sb)

    if not pending:
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] No pending deliveries.")
        return 0

    print(f"  [{datetime.now().strftime('%H:%M:%S')}] Found {len(pending)} report(s) to deliver.")

    delivered = 0
    for report in pending:
        try:
            # Support both old subscriber model and new self-service auth model
            if report.get("subscriber_id"):
                email, name, slack_webhook = _subscriber_email(sb, report["subscriber_id"])
            elif report.get("email"):
                email = report["email"]
                name = email.split("@")[0].replace(".", " ").title()
                slack_webhook = ""
            else:
                email, name, slack_webhook = "", "Subscriber", ""

            if not email:
                print(f"  ⚠  No email for report {report['id']} — skipping.")
                continue

            _send_report(service, email, name, report)

            # Slack notification if subscriber has a webhook configured
            if slack_webhook:
                _send_slack(slack_webhook, report.get("topic",""), report.get("format",""),
                            report["id"], report.get("notes",""))

            # Mark delivered — try with timestamp, fall back without
            try:
                sb.table("reports").update({
                    "delivered": True,
                    "delivered_at": datetime.utcnow().isoformat(),
                }).eq("id", report["id"]).execute()
            except Exception:
                sb.table("reports").update({"delivered": True}).eq("id", report["id"]).execute()

            delivered += 1
            log.info("Delivered report %s to %s", report.get("id"), email)
        except Exception as e:
            log.error("Delivery failed report=%s error=%s", report.get("id"), e)
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
            except Exception:
                pass
            sb.table("reports").update({"status": "failed"}).eq("id", report["id"]).execute()

    return delivered


def main():
    watch = "--watch" in sys.argv
    interval = 60  # seconds

    if watch:
        print(f"\n  ThreadIntel Delivery Worker — polling every {interval}s. Ctrl+C to stop.\n")
        while True:
            try:
                process_batch()
            except Exception as e:
                print(f"  Batch error: {e}")
            time.sleep(interval)
    else:
        try:
            n = process_batch()
            print(f"  Done — {n} report(s) delivered.\n")
        except RuntimeError as e:
            print(f"\n  Setup required: {e}\n")


if __name__ == "__main__":
    main()
