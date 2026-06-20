#!/usr/bin/env python3
"""
ThreadIntel — Daily Briefing Coordinator
Runs all 5 agent functions and prints a morning status brief.

Usage:
    python threadintel/daily_briefing.py           # terminal only
    python threadintel/daily_briefing.py --email   # also email to inbox
"""

import os, sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Supabase connection ───────────────────────────────────────────────────────

def _supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception:
        return None

# ── Agent 1: Research ─────────────────────────────────────────────────────────

def agent_research(sb) -> dict:
    """Report queue depth and status breakdown."""
    result = {"queued": 0, "in_progress": 0, "done": 0, "failed": 0}
    if sb is None:
        return result
    try:
        rows = sb.table("reports").select("status").execute().data
        for r in rows:
            s = r.get("status", "unknown")
            if s in result:
                result[s] += 1
    except Exception as e:
        result["_error"] = str(e)
    return result

# ── Agent 2: Sales ────────────────────────────────────────────────────────────

def agent_sales(sb) -> dict:
    """Waitlist growth and active subscriber count."""
    result = {"waitlist_total": 0, "new_today": 0, "subscribers": 0}
    if sb is None:
        return result
    try:
        today = datetime.utcnow().date().isoformat()
        waitlist = sb.table("waitlist").select("id, created_at").execute().data
        result["waitlist_total"] = len(waitlist)
        result["new_today"] = sum(
            1 for w in waitlist if (w.get("created_at") or "").startswith(today)
        )
        subs = sb.table("subscribers").select("id").eq("active", True).execute().data
        result["subscribers"] = len(subs)
    except Exception as e:
        result["_error"] = str(e)
    return result

# ── Agent 3: Customer Success ─────────────────────────────────────────────────

def agent_cs(sb) -> dict:
    """Reports stuck for >24 hours that need manual attention."""
    result = {"stuck": []}
    if sb is None:
        return result
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        stuck = (
            sb.table("reports")
            .select("id, topic, status, created_at")
            .in_("status", ["queued", "in_progress"])
            .lt("created_at", cutoff)
            .execute()
            .data
        )
        result["stuck"] = stuck
    except Exception as e:
        result["_error"] = str(e)
    return result

# ── Agent 4: Content ──────────────────────────────────────────────────────────

def agent_content(sb) -> dict:
    """Top topics from recent reports + today's suggested post."""
    result = {"trending_topics": [], "post_suggestion": ""}
    if sb is None:
        result["post_suggestion"] = (
            "No data yet — post a launch announcement on X today. "
            "Tag #buildinpublic #indiehacker"
        )
        return result
    try:
        rows = (
            sb.table("reports")
            .select("topic")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data
        )
        topics = [r["topic"] for r in rows if r.get("topic")]
        result["trending_topics"] = topics[:5]
        if topics:
            result["post_suggestion"] = (
                f'People on ThreadIntel are researching "{topics[0]}" right now. '
                f"Thread idea for X/Twitter."
            )
        else:
            result["post_suggestion"] = (
                "No reports yet — share the landing page in r/SideProject today."
            )
    except Exception as e:
        result["_error"] = str(e)
    return result

# ── Agent 5: Analytics ────────────────────────────────────────────────────────

def agent_analytics(sb) -> dict:
    """MRR, weekly report volume, avg usage per subscriber."""
    result = {"mrr": 0.0, "reports_this_week": 0, "avg_per_sub": 0.0}
    if sb is None:
        return result
    try:
        subs = sb.table("subscribers").select("id").eq("active", True).execute().data
        n = len(subs)
        result["mrr"] = round(n * 9.99, 2)

        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        reports = (
            sb.table("reports")
            .select("id")
            .gte("created_at", week_ago)
            .execute()
            .data
        )
        result["reports_this_week"] = len(reports)
        result["avg_per_sub"] = round(len(reports) / n, 1) if n else 0.0
    except Exception as e:
        result["_error"] = str(e)
    return result

# ── Renderer ──────────────────────────────────────────────────────────────────

B  = "\033[1m"
GR = "\033[32m"
YL = "\033[33m"
RD = "\033[31m"
CY = "\033[36m"
RS = "\033[0m"

def _fmt_date():
    n = datetime.now()
    return n.strftime(f"%A, %B {n.day} %Y · %I:%M %p")


def render(research, sales, cs, content, analytics, connected=True) -> str:
    lines = [
        "",
        f"{B}{'─' * 62}{RS}",
        f"{B}  ThreadIntel  ·  Daily Briefing{RS}",
        f"  {_fmt_date()}",
        f"{B}{'─' * 62}{RS}",
    ]

    # Sales
    lines += [
        "",
        f"{B}{CY}[ SALES ]{RS}",
        f"  Waitlist: {sales.get('waitlist_total', 0)} total "
        f"(+{sales.get('new_today', 0)} today)",
        f"  Active subscribers: {sales.get('subscribers', 0)}"
        f"  ←  target: 10",
    ]
    if sales.get("_error"):
        lines.append(f"  {RD}Error: {sales['_error']}{RS}")

    # Analytics
    mrr = analytics.get("mrr", 0)
    lines += [
        "",
        f"{B}{GR}[ ANALYTICS ]{RS}",
        f"  MRR: ${mrr:.2f}  (next milestone: $99.90)",
        f"  Reports this week: {analytics.get('reports_this_week', 0)}",
        f"  Avg per subscriber: {analytics.get('avg_per_sub', 0)}",
    ]

    # Research queue
    q = research
    lines += [
        "",
        f"{B}{YL}[ RESEARCH QUEUE ]{RS}",
        f"  Queued {q.get('queued', 0)}  |  "
        f"In progress {q.get('in_progress', 0)}  |  "
        f"Done {q.get('done', 0)}  |  "
        f"Failed {q.get('failed', 0)}",
    ]

    # CS
    stuck = cs.get("stuck", [])
    if stuck:
        lines += ["", f"{B}{RD}[ CUSTOMER SUCCESS — ACTION NEEDED ]{RS}"]
        for r in stuck:
            lines.append(
                f"  ⚠  Report #{r.get('id', '?')} · \"{r.get('topic', '?')}\" "
                f"stuck as '{r.get('status')}' since "
                f"{(r.get('created_at') or '')[:10]}"
            )
    else:
        lines += ["", f"{B}{GR}[ CUSTOMER SUCCESS ]{RS}", "  All clear — no stuck reports."]

    # Content
    lines += ["", f"{B}{CY}[ CONTENT ]{RS}"]
    if content.get("trending_topics"):
        lines.append(f"  Trending: {', '.join(content['trending_topics'])}")
    lines.append(f"  Today's post idea: {content.get('post_suggestion', '')}")

    if not connected:
        lines += [
            "",
            f"{YL}  ! Supabase not connected — add SUPABASE_URL + SUPABASE_KEY to .env{RS}",
        ]

    lines += ["", f"{B}{'─' * 62}{RS}", ""]
    return "\n".join(lines)

# ── Email delivery ────────────────────────────────────────────────────────────

def _email_briefing(plain_text: str):
    """Send plain-text briefing to owner email via Gmail API."""
    try:
        import base64
        from email.mime.text import MIMEText
        sys.path.insert(0, str(Path(__file__).parent))
        from email_brief import _get_gmail_service  # type: ignore
        service = _get_gmail_service()
        n = datetime.now()
        subject = f"ThreadIntel Daily Brief · {n.strftime(f'%b {n.day}')}"
        msg = MIMEText(plain_text)
        msg["to"] = "syed.aayan.rehman@gmail.com"
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print("  ✓ Briefing emailed to syed.aayan.rehman@gmail.com\n")
    except Exception as e:
        print(f"  Could not email briefing: {e}\n")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    send_email = "--email" in sys.argv
    sb = _supabase()

    briefing = render(
        agent_research(sb),
        agent_sales(sb),
        agent_cs(sb),
        agent_content(sb),
        agent_analytics(sb),
        connected=(sb is not None),
    )
    print(briefing)

    if send_email:
        # strip ANSI codes before emailing
        import re
        plain = re.sub(r"\033\[[0-9;]*m", "", briefing)
        _email_briefing(plain)


if __name__ == "__main__":
    main()
