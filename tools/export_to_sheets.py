#!/usr/bin/env python3
"""
ThreadIntel — Export research findings to Google Sheets.

Creates a new Google Sheet (or writes to an existing one) with the research
findings from a given topic. Each row is one finding: source, title, snippet,
URL, score, sentiment, date.

Usage:
    python tools/export_to_sheets.py "SaaS pricing strategies"
    python tools/export_to_sheets.py "Notion vs Linear" --share user@example.com
    python tools/export_to_sheets.py "AI tools" --sheet-id <existing_sheet_id>

Output:
    Prints the Sheet URL so the subscriber can open it immediately.
"""

import os, sys, json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "threadintel"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Google Auth ───────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

TOKEN_FILE = ROOT / "token_sheets.json"
CREDS_FILE = ROOT / "credentials.json"


def _get_creds():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    "credentials.json not found. Download it from Google Cloud Console "
                    "(APIs & Services → Credentials → OAuth 2.0 Client IDs → Download JSON)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def _sheets_service():
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=_get_creds())


def _drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_creds())


# ── Sheet builder ─────────────────────────────────────────────────────────────

def _header_row(report_type: str) -> list:
    base = ["Source", "Title", "Snippet", "URL", "Score", "Comments", "Sentiment", "Date", "Subreddit"]
    if report_type == "comparison":
        return ["Topic/Side"] + base
    return base


def _finding_to_row(f: dict, report_type: str) -> list:
    row = [
        f.get("source", ""),
        f.get("title", ""),
        f.get("text", "")[:300],
        f.get("url", ""),
        str(f.get("score", "")),
        str(f.get("comments", "")),
        f.get("sentiment", ""),
        f.get("date", ""),
        f.get("subreddit", ""),
    ]
    if report_type == "comparison":
        return [f.get("_topic", "")] + row
    return row


def export_to_sheets(
    topic: str,
    findings: list = None,
    sources: list = None,
    sheet_id: str = None,
    share_with: str = None,
) -> str:
    """
    Run research + export to Google Sheets.
    Returns the Sheet URL.
    """
    from research import smart_research
    from email_brief import detect_report_type

    if findings is None:
        print(f"Researching: {topic}")
        findings = smart_research(topic, sources=sources)

    # Flatten dict → list for row building
    if isinstance(findings, dict):
        flat = []
        for key in ("reddit", "hackernews", "news", "web", "stackoverflow", "producthunt", "newsapi", "indiehackers", "github_issues"):
            flat.extend(findings.get(key, []))
        findings = flat
    findings = [f for f in findings if isinstance(f, dict)]
    report_type = detect_report_type(topic)
    n = datetime.now()
    sheet_title = f"ThreadIntel — {topic[:60]} ({n.strftime(f'%b {n.day}')})"

    svc = _sheets_service()

    # Create new sheet or use existing
    if sheet_id:
        # Clear and reuse
        svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="Sheet1",
        ).execute()
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        print(f"  Writing to existing sheet: {url}")
    else:
        body = {"properties": {"title": sheet_title}}
        ss = svc.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        sheet_id = ss["spreadsheetId"]
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        print(f"  Created new sheet: {url}")

    # Build rows
    header = _header_row(report_type)
    rows = [header]
    for f in findings:
        rows.append(_finding_to_row(f, report_type))

    # Add summary row at bottom
    n_pos = sum(1 for f in findings if f.get("sentiment") == "positive")
    n_neg = sum(1 for f in findings if f.get("sentiment") == "negative")
    n_neu = sum(1 for f in findings if f.get("sentiment") == "neutral")
    rows.append([])
    rows.append([
        "SUMMARY",
        f"Total: {len(findings)} results",
        f"Sentiment: {round(n_pos/max(len(findings),1)*100)}% pos · "
        f"{round(n_neg/max(len(findings),1)*100)}% neg · "
        f"{round(n_neu/max(len(findings),1)*100)}% neu",
        "", "", "", "", "", "",
    ])
    rows.append([])
    rows.append(["Generated by ThreadIntel · threadintel.io · $9.99/month unlimited reports"])

    # Write to sheet
    body = {"values": rows}
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()

    # Format header row (bold + background)
    fmt_reqs = [
        {
            "repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.2},
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(header)}
            }
        },
    ]
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": fmt_reqs},
    ).execute()

    # Share if requested
    if share_with:
        drive = _drive_service()
        drive.permissions().create(
            fileId=sheet_id,
            body={"type": "user", "role": "writer", "emailAddress": share_with},
            sendNotificationEmail=False,
        ).execute()
        print(f"  Shared with {share_with}")

    print(f"\n  Sheets export complete.")
    print(f"  {len(findings)} findings written.")
    print(f"  Open: {url}\n")
    return url


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export ThreadIntel research to Google Sheets")
    parser.add_argument("topic", nargs="?", help="Research topic")
    parser.add_argument("--share", metavar="EMAIL", help="Share sheet with this email")
    parser.add_argument("--sheet-id", metavar="ID", help="Write to existing sheet instead of creating new")
    args = parser.parse_args()

    if not args.topic:
        args.topic = input("Topic: ").strip()

    export_to_sheets(
        topic=args.topic,
        share_with=args.share,
        sheet_id=args.sheet_id,
    )
