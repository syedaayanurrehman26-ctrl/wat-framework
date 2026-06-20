#!/usr/bin/env python3
"""
ThreadIntel — Report Queue Worker
The heart of the automation. Picks up queued reports from Supabase,
runs the full research + generation pipeline, stores the HTML, marks done.

deliver.py then emails completed reports to subscribers.

Usage:
    python threadintel/worker.py              # process one batch
    python threadintel/worker.py --watch      # loop every 30s (production)
    python threadintel/worker.py --once "topic"  # process a single topic (test)
"""

import os, sys, time, json, base64, logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).parent))


def _startup_check():
    """Validate critical environment variables before the worker loop starts."""
    required = {
        "SUPABASE_URL":  "Supabase project URL",
        "SUPABASE_KEY":  "Supabase anon/service key",
        "GROQ_API_KEY":  "Groq API key (free at console.groq.com)",
    }
    optional = {
        "REDDIT_CLIENT_ID":  "Reddit API — reports will skip Reddit without this",
        "REDDIT_SECRET":     "Reddit API secret",
        "SENTRY_DSN":        "Sentry error tracking (optional)",
    }
    missing_required = []
    for key, desc in required.items():
        val = os.getenv(key, "").strip()
        if not val or val.startswith("your_"):
            missing_required.append(f"  ✗ {key} — {desc}")
    if missing_required:
        print("\n  ── STARTUP FAILED: missing required config ──")
        for m in missing_required:
            print(m)
        print("\n  Add these to your .env file and restart.\n")
        sys.exit(1)

    warnings = []
    for key, desc in optional.items():
        val = os.getenv(key, "").strip()
        if not val or val.startswith("your_"):
            warnings.append(f"  ⚠  {key} not set — {desc}")
    if warnings:
        print("\n  ── Optional config missing (non-fatal) ──")
        for w in warnings:
            print(w)
        print()

# ── Structured logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
)
log = logging.getLogger("threadintel.worker")

# ── Sentry (optional — set SENTRY_DSN in .env to enable) ─────────────────────
_SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.2,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        log.info("Sentry initialised")
    except ImportError:
        log.warning("sentry-sdk not installed — run: pip install sentry-sdk")

# ── Imports ───────────────────────────────────────────────────────────────────

def _import_pipeline():
    """Lazy import so the worker starts fast even if deps are missing."""
    from research import smart_research
    from email_brief import generate_content, build_html
    return smart_research, generate_content, build_html

# ── Supabase ──────────────────────────────────────────────────────────────────

def _supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    from supabase import create_client
    return create_client(url, key)

# ── Queue ─────────────────────────────────────────────────────────────────────

def _fetch_queued(sb) -> list:
    return (
        sb.table("reports")
        .select("id, topic, sources, format, subscriber_id, email, user_id, report_num, angles, source_filter, date_range")
        .eq("status", "queued")
        .order("created_at")
        .limit(5)
        .execute()
        .data
    )


def _get_user_settings(sb, user_id: str) -> dict:
    """Return user_settings row for a given auth user_id, or {}."""
    if not user_id:
        return {}
    try:
        rows = sb.table("user_settings").select("*").eq("user_id", user_id).limit(1).execute().data
        return rows[0] if rows else {}
    except Exception:
        return {}

def _mark(sb, report_id, status, **extra):
    sb.table("reports").update({"status": status, **extra}).eq("id", report_id).execute()


def _send_slack_notification(webhook_url: str, topic: str, subject: str, report_url: str = None):
    """Post a completion notification to a user's Slack webhook. Fails silently."""
    if not webhook_url:
        return
    try:
        blocks = [
            {"type": "section", "text": {
                "type": "mrkdwn",
                "text": f":bar_chart: *ThreadIntel Report Ready*\n*Topic:* {topic}\n*{subject}*"
            }}
        ]
        if report_url:
            blocks.append({"type": "section", "text": {
                "type": "mrkdwn",
                "text": f"<{report_url}|View Report>"
            }})
        requests.post(webhook_url, json={"blocks": blocks}, timeout=8)
    except Exception:
        pass

# ── Core pipeline ─────────────────────────────────────────────────────────────

def _build_output(topic, findings, data, report_format, subscriber_name, report_num, share_with=None):
    """
    Dispatch to the right output builder based on format.
    Returns (html, extra_url). share_with is a Google email to auto-share exports with.
    """
    from email_brief import build_html

    fmt = (report_format or "email_brief").lower()
    extra_url = None

    html = build_html(data, subscriber_name=subscriber_name, report_num=report_num)

    if fmt in ("sheets", "google_sheets"):
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from export_to_sheets import export_to_sheets
            extra_url = export_to_sheets(topic, findings=findings, share_with=share_with)
            print(f"    → Sheets: {extra_url}")
        except Exception as e:
            print(f"    Sheets export failed: {e}")

    elif fmt in ("docs", "google_docs"):
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from export_to_docs import export_to_docs
            extra_url = export_to_docs(topic, findings=findings, share_with=share_with)
            print(f"    → Docs: {extra_url}")
        except Exception as e:
            print(f"    Docs export failed: {e}")

    elif fmt in ("slides", "pptx", "powerpoint", "google_slides"):
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from export_to_slides import export_to_google_slides, export_to_pptx
            # Prefer Google Slides (shareable URL); fall back to local .pptx
            try:
                extra_url = export_to_google_slides(topic, findings=findings, share_with=share_with)
            except Exception:
                extra_url = export_to_pptx(topic, findings=findings)
            print(f"    → Slides: {extra_url}")
        except Exception as e:
            print(f"    Slides export failed: {e}")

    elif fmt == "all":
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            from export_to_sheets import export_to_sheets
            from export_to_docs   import export_to_docs
            from export_to_slides import export_to_pptx
            sheets_url = export_to_sheets(topic, findings=findings, share_with=share_with)
            docs_url   = export_to_docs(topic, findings=findings, share_with=share_with)
            pptx_path  = export_to_pptx(topic, findings=findings, share_with=share_with)
            extra_url = f"Sheets: {sheets_url} | Docs: {docs_url} | PPTX: {pptx_path}"
        except Exception as e:
            print(f"    All-format export partial failure: {e}")

    return html, extra_url


def process_report(sb, report: dict) -> bool:
    """
    Run the full pipeline for one report.
    Returns True on success, False on failure.
    """
    report_id     = report["id"]
    topic         = report["topic"]
    sources       = report.get("sources") or None
    report_num    = report.get("report_num")
    sub_id        = report.get("subscriber_id")
    user_id       = report.get("user_id")
    report_format = report.get("format") or "email_brief"
    angles        = report.get("angles") or ""
    source_filter = report.get("source_filter") or None
    date_range    = report.get("date_range") or "30d"

    # Source filter from portal overrides the legacy sources field
    if source_filter:
        sources = [s.strip() for s in source_filter.split(",") if s.strip()]

    # Convert portal date_range → research engine params
    _range_map = {
        "7d":  ("week",  7),
        "30d": ("month", 30),
        "6m":  ("year",  180),
        "all": ("all",   None),
    }
    time_filter, days_ago = _range_map.get(date_range, ("all", None))

    print(f"\n  [{_ts()}] Processing: '{topic}' (id={report_id[:8]}..., fmt={report_format}, range={date_range})")
    _mark(sb, report_id, "in_progress")

    # Resolve email + name for delivery
    if sub_id:
        sub_email, sub_first = _get_subscriber_email(sb, sub_id)
    elif report.get("email"):
        sub_email = report["email"]
        sub_first = report["email"].split("@")[0].replace(".", " ").title()
    else:
        sub_email, sub_first = "", "there"

    # Look up user settings (Google share email, Slack webhook, notification prefs)
    settings = _get_user_settings(sb, user_id)
    google_share_email = settings.get("google_share_email") or None
    slack_webhook      = settings.get("slack_webhook") or None
    notify_slack       = settings.get("notify_slack", False)

    if sub_email:
        _send_queued_confirmation(sub_email, sub_first, topic, report_format)

    try:
        smart_research, generate_content, build_html = _import_pipeline()

        # Step 1: Research — pass time filters from user's portal selection
        print(f"  Step 1/3  Researching '{topic}'...")
        findings = smart_research(topic, sources=sources, time_filter=time_filter, days_ago=days_ago)

        # Step 2: Generate report content via Groq (pass angles separately for richer context)
        print(f"  Step 2/3  Generating report with Groq...")
        data = generate_content(topic, findings=findings, angles=angles)
        subject = data.get("subject_line", f"ThreadIntel: {topic}")

        # Step 3: Get subscriber name for watermark
        subscriber_name = sub_first if sub_id else None

        # Build output — auto-share Google exports with user's linked email
        html, extra_url = _build_output(topic, findings, data, report_format,
                                        subscriber_name, report_num,
                                        share_with=google_share_email)

        notes = f"subject: {subject}"
        if extra_url:
            notes += f" | output: {extra_url}"

        # Store in Supabase
        _mark(sb, report_id, "done",
              report_html=html,
              report_num=report_num,
              notes=notes)

        # Slack notification if user configured a webhook
        if notify_slack and slack_webhook:
            _send_slack_notification(slack_webhook, topic, subject, report_url=extra_url)

        print(f"  [{_ts()}] Done: '{topic}' — ready for delivery")
        return True

    except Exception as e:
        err = str(e)[:500]
        log.error("Report failed: topic=%r report_id=%s error=%s", topic, report_id, err)
        # Capture to Sentry if configured
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("report_id", report_id)
                scope.set_tag("topic", topic[:100])
                sentry_sdk.capture_exception(e)
        except Exception:
            pass
        _mark(sb, report_id, "failed", notes=f"error: {err}")
        _send_admin_alert(topic, err, report_id)
        return False


def _get_subscriber_name(sb, subscriber_id) -> str:
    if not subscriber_id:
        return None
    try:
        rows = sb.table("subscribers").select("name").eq("id", subscriber_id).limit(1).execute().data
        return (rows[0].get("name") or "").split()[0] if rows else None
    except Exception:
        return None


def _get_subscriber_email(sb, subscriber_id) -> tuple[str, str]:
    """Return (email, first_name) for a subscriber."""
    if not subscriber_id:
        return "", "Subscriber"
    try:
        rows = sb.table("subscribers").select("email, name").eq("id", subscriber_id).limit(1).execute().data
        if not rows:
            return "", "Subscriber"
        email = rows[0].get("email", "")
        name  = (rows[0].get("name") or "Subscriber").split()[0]
        return email, name
    except Exception:
        return "", "Subscriber"


def _send_transactional(to_email: str, subject: str, html_body: str):
    """Send a transactional email via Gmail API. Fails silently."""
    try:
        from email_brief import _get_gmail_service
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        service = _get_gmail_service()
        msg = MIMEMultipart("alternative")
        msg["to"]      = to_email
        msg["from"]    = "me"
        msg["subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as e:
        print(f"  [email] Failed to send '{subject}' to {to_email}: {e}")


def _send_queued_confirmation(to_email: str, name: str, topic: str, fmt: str):
    """Tell the subscriber their report is being processed."""
    fmt_labels = {
        "email_brief": "Email Brief",
        "slides": "PowerPoint Slides",
        "docs": "Google Docs",
        "sheets": "Google Sheets",
        "all": "All Formats",
    }
    fmt_display = fmt_labels.get(fmt, fmt)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#020818;
                color:#E2E8F0;padding:40px 32px;border-radius:16px;">
      <div style="font-size:22px;font-weight:800;margin-bottom:4px;">
        Thread<em style="color:#7C6FFF;">Intel</em>
      </div>
      <div style="height:2px;background:linear-gradient(90deg,#7C6FFF,#00D9B8);margin:16px 0 32px;border-radius:2px;"></div>
      <p style="font-size:16px;margin-bottom:8px;">Hi {name},</p>
      <p style="color:#94A3B8;line-height:1.7;margin-bottom:24px;">
        We received your research request and the pipeline is running now.
        You'll have your report in your inbox within 30 minutes.
      </p>
      <div style="background:rgba(124,111,255,.1);border:1px solid rgba(124,111,255,.3);
                  border-radius:12px;padding:20px 24px;margin-bottom:32px;">
        <div style="font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
                    color:#7C6FFF;margin-bottom:8px;">Your Request</div>
        <div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:4px;">{topic}</div>
        <div style="font-size:13px;color:#94A3B8;">Format: {fmt_display}</div>
      </div>
      <p style="font-size:13px;color:#4A5568;line-height:1.6;">
        You don't need to do anything — we'll email you when it's ready.<br>
        Questions? Reply to this email.
      </p>
      <div style="margin-top:32px;padding-top:20px;border-top:1px solid rgba(255,255,255,.06);
                  font-size:11px;color:#4A5568;">
        ThreadIntel · <a href="https://threadintel.io/portal.html" style="color:#7C6FFF;">Open Portal</a>
      </div>
    </div>"""
    _send_transactional(to_email, f"ThreadIntel: Processing your report on '{topic[:50]}'", html)


def _send_admin_alert(topic: str, error: str, report_id: str):
    """Email the admin when a report fails."""
    admin_email = os.getenv("ADMIN_EMAIL", "syed.aayan.rehman@gmail.com")
    html = f"""
    <div style="font-family:monospace;background:#1a0000;color:#ff9999;padding:24px;border-radius:8px;">
      <strong style="font-size:16px;">⚠ ThreadIntel Report Failed</strong><br><br>
      <b>Report ID:</b> {report_id}<br>
      <b>Topic:</b> {topic}<br>
      <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br><br>
      <b>Error:</b><br>
      <pre style="white-space:pre-wrap;color:#ffcccc;">{error}</pre>
    </div>"""
    _send_transactional(admin_email, f"[ThreadIntel] FAILED: '{topic[:50]}'", html)

# ── Batch runner ──────────────────────────────────────────────────────────────

def process_batch() -> tuple[int, int]:
    """Returns (success_count, failure_count)."""
    sb = _supabase()
    queued = _fetch_queued(sb)

    if not queued:
        print(f"  [{_ts()}] Queue empty — nothing to process.")
        return 0, 0

    print(f"  [{_ts()}] {len(queued)} report(s) in queue.")
    ok = fail = 0
    for report in queued:
        if process_report(sb, report):
            ok += 1
        else:
            fail += 1

    return ok, fail

# ── Single-topic test mode ────────────────────────────────────────────────────

def process_once(topic: str):
    """Process a single topic without Supabase — useful for local testing."""
    print(f"\n[Worker test mode] Topic: {topic}\n")
    smart_research, generate_content, build_html = _import_pipeline()

    print("Step 1/3  Researching...")
    findings = smart_research(topic)

    print("\nStep 2/3  Generating report...")
    data = generate_content(topic, findings=findings)

    print("\nStep 3/3  Building HTML...")
    html = build_html(data)

    out = ROOT / ".tmp" / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\n  Saved to: {out}")
    print(f"  Open in browser: file:///{out}")
    return html

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts():
    return datetime.now().strftime("%H:%M:%S")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # Test mode skips startup check (uses no Supabase)
    if args and args[0] == "--once":
        topic = " ".join(args[1:]) or input("Topic: ").strip()
        process_once(topic)
        return

    _startup_check()

    watch   = "--watch" in args
    interval = 30  # seconds

    if watch:
        print(f"\n  ThreadIntel Worker — watching queue every {interval}s. Ctrl+C to stop.\n")
        while True:
            try:
                ok, fail = process_batch()
                if ok or fail:
                    print(f"  Batch done: {ok} succeeded, {fail} failed.")
            except RuntimeError as e:
                print(f"  Setup required: {e}")
                break
            except Exception as e:
                print(f"  Unexpected error: {e}")
            time.sleep(interval)
    else:
        try:
            ok, fail = process_batch()
            print(f"\n  Done — {ok} succeeded, {fail} failed.\n")
        except RuntimeError as e:
            print(f"\n  Setup required: {e}\n")

if __name__ == "__main__":
    main()
