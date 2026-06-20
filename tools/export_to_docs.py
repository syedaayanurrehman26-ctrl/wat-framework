#!/usr/bin/env python3
"""
ThreadIntel — Export research report to Google Docs.

Creates a properly formatted Google Doc with the full ThreadIntel report:
executive summary, key findings by source, sentiment overview, and links.
The format can be customized by the caller.

Usage:
    python tools/export_to_docs.py "SaaS pricing strategies"
    python tools/export_to_docs.py "Notion vs Linear" --share user@example.com
    python tools/export_to_docs.py "AI tools 2026" --format brief
    python tools/export_to_docs.py "AI tools 2026" --format detailed

Formats:
    brief    — executive summary + top 10 findings (default)
    detailed — full findings by source with all metadata
    bullets  — just titled bullet points, no metadata (good for sharing)

Output:
    Prints the Doc URL so the subscriber can open it.
"""

import os, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "threadintel"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Google Auth ───────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_FILE = ROOT / "token_docs.json"
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
                raise FileNotFoundError("credentials.json not found.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def _docs_service():
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=_get_creds())


def _drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_creds())


# ── Doc content builder ───────────────────────────────────────────────────────

def _build_requests(topic: str, findings: list, report_data: dict, fmt: str) -> list:
    """Build Google Docs API batchUpdate requests to populate the document."""
    reqs = []
    cursor = 1  # current insert index

    def _insert(text, style=None):
        nonlocal cursor
        req = {
            "insertText": {
                "location": {"index": cursor},
                "text": text,
            }
        }
        reqs.append(req)
        if style:
            reqs.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": cursor, "endIndex": cursor + len(text)},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            })
        cursor += len(text)

    n = datetime.now()
    date_str = f"{n.strftime('%B')} {n.day}, {n.year}"

    # Title
    title_text = f"ThreadIntel Research Report\n"
    _insert(title_text, "TITLE")

    # Subtitle / topic
    _insert(f"{topic}\n", "SUBTITLE")

    # Date + metadata
    sources = sorted(set(f.get("source", "") for f in findings))
    n_pos = sum(1 for f in findings if f.get("sentiment") == "positive")
    n_neg = sum(1 for f in findings if f.get("sentiment") == "negative")

    _insert(
        f"Generated: {date_str}  ·  "
        f"{len(findings)} findings  ·  "
        f"Sources: {', '.join(sources)}\n\n",
        "NORMAL_TEXT",
    )

    # Executive Summary
    _insert("Executive Summary\n", "HEADING_1")
    summary = report_data.get("summary", "")
    if not summary and findings:
        summary = f"Analysis of {len(findings)} data points across {len(sources)} sources on the topic of {topic}."
    _insert(f"{summary}\n\n", "NORMAL_TEXT")

    # Sentiment
    pct_pos = round(n_pos / max(len(findings), 1) * 100)
    pct_neg = round(n_neg / max(len(findings), 1) * 100)
    pct_neu = 100 - pct_pos - pct_neg
    _insert("Sentiment Overview\n", "HEADING_1")
    _insert(
        f"• Positive: {pct_pos}%\n"
        f"• Negative: {pct_neg}%\n"
        f"• Neutral:  {pct_neu}%\n\n",
        "NORMAL_TEXT",
    )

    # Key Takeaways (from report_data bullets)
    bullets = report_data.get("bullets", []) or report_data.get("tldr", [])
    if bullets:
        _insert("Key Takeaways\n", "HEADING_1")
        for b in bullets[:8]:
            _insert(f"• {b}\n", "NORMAL_TEXT")
        _insert("\n", "NORMAL_TEXT")

    # Findings
    if fmt == "brief":
        _insert("Top Findings\n", "HEADING_1")
        for f in findings[:12]:
            src = f.get("source", "")
            title = f.get("title", "")[:120]
            text  = f.get("text", "")[:200].strip()
            url   = f.get("url", "")
            _insert(f"{title}\n", "HEADING_3")
            _insert(f"Source: {src}", "NORMAL_TEXT")
            if f.get("date"):
                _insert(f"  ·  {f['date']}", "NORMAL_TEXT")
            _insert(f"\n{text}\n", "NORMAL_TEXT")
            if url:
                _insert(f"{url}\n\n", "NORMAL_TEXT")

    elif fmt == "bullets":
        _insert("All Findings\n", "HEADING_1")
        for f in findings:
            title = f.get("title", "")[:120]
            src   = f.get("source", "")
            _insert(f"• [{src}] {title}\n", "NORMAL_TEXT")
        _insert("\n", "NORMAL_TEXT")

    else:  # detailed
        by_source: dict = {}
        for f in findings:
            s = f.get("source", "Other")
            by_source.setdefault(s, []).append(f)

        for src, items in by_source.items():
            _insert(f"{src}\n", "HEADING_1")
            for f in items:
                title   = f.get("title", "")[:120]
                text    = f.get("text", "")[:400].strip()
                url     = f.get("url", "")
                score   = f.get("score", "")
                date    = f.get("date", "")
                sent    = f.get("sentiment", "")
                _insert(f"{title}\n", "HEADING_3")
                meta = []
                if date:    meta.append(date)
                if score:   meta.append(f"Score: {score}")
                if sent:    meta.append(f"Sentiment: {sent}")
                if meta:
                    _insert("  ".join(meta) + "\n", "NORMAL_TEXT")
                _insert(f"{text}\n", "NORMAL_TEXT")
                if url:
                    _insert(f"{url}\n\n", "NORMAL_TEXT")

    # Footer
    _insert("\n─────────────────────────────────────────\n", "NORMAL_TEXT")
    _insert(
        f"Generated by ThreadIntel · threadintel.io · $9.99/month unlimited reports\n"
        f"AI research from Reddit, Hacker News, Google News, and the open web.\n",
        "NORMAL_TEXT",
    )

    return reqs


# ── Main export function ──────────────────────────────────────────────────────

def export_to_docs(
    topic: str,
    findings: list = None,
    sources: list = None,
    fmt: str = "brief",
    share_with: str = None,
) -> str:
    """
    Run research + export to Google Docs. Returns the Doc URL.
    fmt: 'brief' | 'detailed' | 'bullets'
    """
    from research import smart_research
    from email_brief import generate_content

    if findings is None:
        print(f"Researching: {topic}")
        findings = smart_research(topic, sources=sources)

    # generate_content needs the raw structured dict
    print(f"  Generating report content...")
    report_data = generate_content(topic, findings=findings)

    # Flatten for per-finding iteration
    if isinstance(findings, dict):
        flat = []
        for key in ("reddit", "hackernews", "news", "web", "stackoverflow", "producthunt", "newsapi", "indiehackers", "github_issues"):
            flat.extend(findings.get(key, []))
        findings = flat
    findings = [f for f in findings if isinstance(f, dict)]

    svc = _docs_service()

    n = datetime.now()
    doc_title = f"ThreadIntel — {topic[:60]} ({n.strftime(f'%b {n.day}')})"

    # Create the doc
    doc = svc.documents().create(body={"title": doc_title}).execute()
    doc_id = doc["documentId"]
    url = f"https://docs.google.com/document/d/{doc_id}"
    print(f"  Created doc: {url}")

    # Populate with content
    requests_list = _build_requests(topic, findings, report_data, fmt)
    if requests_list:
        svc.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests_list},
        ).execute()

    # Share if requested
    if share_with:
        drive = _drive_service()
        drive.permissions().create(
            fileId=doc_id,
            body={"type": "user", "role": "writer", "emailAddress": share_with},
            sendNotificationEmail=False,
        ).execute()
        print(f"  Shared with {share_with}")

    print(f"\n  Docs export complete ({len(findings)} findings, format: {fmt})")
    print(f"  Open: {url}\n")
    return url


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export ThreadIntel research to Google Docs")
    parser.add_argument("topic", nargs="?", help="Research topic")
    parser.add_argument("--share", metavar="EMAIL", help="Share doc with this email")
    parser.add_argument("--format", choices=["brief", "detailed", "bullets"], default="brief")
    args = parser.parse_args()

    if not args.topic:
        args.topic = input("Topic: ").strip()

    export_to_docs(
        topic=args.topic,
        fmt=args.format,
        share_with=args.share,
    )
