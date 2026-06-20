#!/usr/bin/env python3
"""
ThreadIntel — Recurring Report Scheduler
Checks the `schedules` table and queues new reports for topics that are due.

Usage:
    python threadintel/scheduler.py            # process once
    python threadintel/scheduler.py --watch    # loop every 10 minutes

This is the engine behind weekly/bi-weekly recurring research subscriptions.
When a subscriber sets up a recurring topic in the portal, this script
automatically queues a new report at the right time.
"""

import os, sys, time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent.parent / ".env")

FREQUENCY_DAYS = {
    "weekly":   7,
    "biweekly": 14,
    "monthly":  30,
}


def _supabase():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    from supabase import create_client
    return create_client(url, key)


def _due_schedules(sb) -> list:
    """Return active schedules whose next_run_at is now or overdue."""
    now = datetime.utcnow().isoformat()
    return (
        sb.table("schedules")
        .select("id, subscriber_id, topic, sources, frequency, total_runs")
        .eq("active", True)
        .lte("next_run_at", now)
        .execute()
        .data
    )


def _queue_report(sb, schedule: dict) -> str:
    """Insert a new report row for this schedule. Returns new report id."""
    result = sb.table("reports").insert({
        "subscriber_id": schedule["subscriber_id"],
        "topic": schedule["topic"],
        "sources": schedule["sources"],
        "status": "queued",
        "report_num": schedule["total_runs"] + 1,
        "notes": f"Auto-queued by scheduler (run #{schedule['total_runs'] + 1})",
    }).execute()
    return result.data[0]["id"] if result.data else None


def _advance_schedule(sb, schedule: dict):
    """Update next_run_at and increment total_runs."""
    days = FREQUENCY_DAYS.get(schedule["frequency"], 7)
    next_run = (datetime.utcnow() + timedelta(days=days)).isoformat()
    sb.table("schedules").update({
        "last_run_at": datetime.utcnow().isoformat(),
        "next_run_at": next_run,
        "total_runs": schedule["total_runs"] + 1,
    }).eq("id", schedule["id"]).execute()


def process_schedules() -> int:
    sb = _supabase()
    due = _due_schedules(sb)

    if not due:
        print(f"  [{_ts()}] No schedules due.")
        return 0

    print(f"  [{_ts()}] {len(due)} schedule(s) due — queuing reports...")
    queued = 0
    for s in due:
        try:
            report_id = _queue_report(sb, s)
            _advance_schedule(sb, s)
            print(f"  + Queued report for '{s['topic']}' (subscriber {s['subscriber_id'][:8]}...)")
            queued += 1
        except Exception as e:
            print(f"  ! Failed schedule {s['id']}: {e}")

    return queued


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main():
    watch = "--watch" in sys.argv
    interval = 600  # 10 minutes

    if watch:
        print(f"\n  ThreadIntel Scheduler — checking every {interval // 60} min. Ctrl+C to stop.\n")
        while True:
            try:
                process_schedules()
            except RuntimeError as e:
                print(f"  Setup required: {e}")
                break
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(interval)
    else:
        try:
            n = process_schedules()
            print(f"  Done — {n} report(s) queued.\n")
        except RuntimeError as e:
            print(f"\n  Setup required: {e}\n")


if __name__ == "__main__":
    main()
