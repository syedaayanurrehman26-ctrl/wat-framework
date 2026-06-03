# -*- coding: utf-8 -*-
"""
WAT Tool: Newsletter Generator + Gmail Draft Creator
Workflow: workflows/email_newsletter_generator.md

What this does:
  1. Asks you for a topic
  2. Uses Groq AI (Llama 3.3-70b) to research and write all content
  3. Auto-generates an eye-catching subject line
  4. Creates a Gmail draft with everything pre-filled
  5. Opens the draft in Chrome — you just add recipients and hit Send

Run: python tools/newsletter.py
"""

import os, sys, json, base64, webbrowser, subprocess, re
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

HAS_COLORTHIEF = False
try:
    import importlib
    if importlib.util.find_spec("colorthief"):
        from colorthief import ColorThief  # type: ignore
        from io import BytesIO
        HAS_COLORTHIEF = True
except Exception:
    pass

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import requests
from dotenv import load_dotenv

ROOT       = Path(__file__).parent.parent
TOKEN_FILE = ROOT / "token.json"
CREDS_FILE = ROOT / "credentials.json"
SCOPES     = ["https://www.googleapis.com/auth/gmail.compose"]

load_dotenv(ROOT / ".env")

# ─────────────────────────────────────────────
# COLOR UTILITIES
# ─────────────────────────────────────────────

def hex_to_hsl(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c*2 for c in h)
    r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
    mx, mn = max(r,g,b), min(r,g,b)
    lv = (mx+mn)/2
    if mx == mn: return 0, 0, lv*100
    d = mx-mn
    s = d/(2-mx-mn) if lv > 0.5 else d/(mx+mn)
    if mx==r: hue = (g-b)/d + (6 if g<b else 0)
    elif mx==g: hue = (b-r)/d + 2
    else: hue = (r-g)/d + 4
    return hue/6*360, s*100, lv*100

def hsl_to_hex(h, s, l):
    h, s, l = h/360, s/100, l/100
    if s == 0:
        v = int(l*255)
        return f"#{v:02x}{v:02x}{v:02x}"
    def hue2rgb(p, q, t):
        if t<0: t+=1
        if t>1: t-=1
        if t<1/6: return p+(q-p)*6*t
        if t<1/2: return q
        if t<2/3: return p+(q-p)*(2/3-t)*6
        return p
    q = l*(1+s) if l<0.5 else l+s-l*s
    p = 2*l-q
    r,g,b = hue2rgb(p,q,h+1/3), hue2rgb(p,q,h), hue2rgb(p,q,h-1/3)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def wcag_contrast(c1, c2):
    """WCAG 2.1 contrast ratio between two hex colors."""
    def lum(hx):
        hx = hx.lstrip('#')
        if len(hx) == 3: hx = ''.join(c*2 for c in hx)
        vals = [int(hx[i:i+2],16)/255 for i in (0,2,4)]
        lin  = [v/12.92 if v<=0.03928 else ((v+0.055)/1.055)**2.4 for v in vals]
        return 0.2126*lin[0] + 0.7152*lin[1] + 0.0722*lin[2]
    try:
        l1, l2 = lum(c1), lum(c2)
        hi, lo = max(l1,l2), min(l1,l2)
        return (hi+0.05)/(lo+0.05)
    except Exception:
        return 1.0

def ensure_readable(text_hex, bg_hex, min_ratio=4.5):
    """Return text_hex if contrast passes; auto-fix by surface tone — never changes hue family."""
    try:
        if wcag_contrast(text_hex, bg_hex) >= min_ratio:
            return text_hex
        def lum(hx):
            hx = hx.lstrip('#')
            if len(hx)==3: hx=''.join(c*2 for c in hx)
            v=[int(hx[i:i+2],16)/255 for i in(0,2,4)]
            lin=[x/12.92 if x<=0.03928 else((x+0.055)/1.055)**2.4 for x in v]
            return 0.2126*lin[0]+0.7152*lin[1]+0.0722*lin[2]
        if lum(bg_hex) > 0.18:  # light surface — need dark text
            for c in ["#1A202C","#0A1F3D","#2D3748","#4A5568"]:
                if wcag_contrast(c, bg_hex) >= min_ratio: return c
            return "#1A202C"
        else:                    # dark surface — need light text
            for c in ["#EDEFF2","#F4C842","#F4A261","#ffffff"]:
                if wcag_contrast(c, bg_hex) >= min_ratio: return c
            return "#EDEFF2"
    except Exception:
        return "#1A202C"

def darken_to_readable(hex_color, bg_hex="#FFFFFF", min_ratio=4.5):
    """
    Darken hex_color within its own hue until it passes contrast on bg_hex.
    NEVER substitutes a different hue — preserves the brand color identity.
    """
    try:
        if wcag_contrast(hex_color, bg_hex) >= min_ratio:
            return hex_color
        h, s, l = hex_to_hsl(hex_color)
        for target_l in range(int(l)-5, 4, -5):
            candidate = hsl_to_hex(h, s, max(target_l, 5))
            if wcag_contrast(candidate, bg_hex) >= min_ratio:
                return candidate
        return hsl_to_hex(h, s, 15)   # darkest fallback, still in-hue
    except Exception:
        return "#1A202C"

def guess_brand_url(topic):
    """
    Guess the official URL from a topic with zero API calls.
    Tries multiple domain patterns and extensions.
    """
    skip = {
        "the","a","an","of","in","on","at","for","and","with","by","to","vs",
        "q1","q2","q3","q4","h1","h2","fy","earnings","report","update","news",
        "latest","2024","2025","2026","analysis","review","breakdown","results",
        "quarter","annual","weekly","monthly","daily","global","world","market",
        "how","why","what","when","where","who","war","conflict","crisis","deal"
    }
    raw = topic.lower().strip()

    # Preserve hyphens for compound brands (coca-cola, t-mobile)
    first_word_raw = raw.split()[0] if raw.split() else ""
    hyphen_brand = re.sub(r'[^a-z-]', '', first_word_raw)

    # Clean words for normal matching
    words = [w for w in re.sub(r'[^a-z ]', ' ', raw).split()
             if w not in skip and len(w) > 2]

    candidates = []
    if hyphen_brand and '-' in hyphen_brand:
        candidates.append(f"https://www.{hyphen_brand}.com")
        candidates.append(f"https://www.{hyphen_brand.replace('-','')}.com")
    if words:
        w0 = words[0]
        candidates += [
            f"https://www.{w0}.com",
            f"https://www.{w0}.org",
            f"https://www.{w0}.io",
            f"https://{w0}.com",
        ]
    if len(words) >= 2:
        merged = words[0] + words[1]
        candidates.append(f"https://www.{merged}.com")

    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = requests.head(url, timeout=5, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code < 400:
                return url
        except Exception:
            continue
    return None

def build_brand_palette(primary_hex):
    """
    Build a LIGHT-BASE palette from one extracted brand color.
    RULE: the MOST VIVID color always becomes the accent (primary).
    Dark extracted colors → header bg only, never text/accents.
    """
    try:
        h, s, l = hex_to_hsl(primary_hex)
        s = max(25, min(90, s))

        if l < 35:
            # Dark brand color (e.g. FIFA navy).
            # Derive the MOST VIVID complement as the accent — never use the dark color as accent.
            vivid_h   = (h + 175) % 360     # near-complementary hue (navy → gold/amber range)
            vivid_raw = hsl_to_hex(vivid_h, max(s, 78), 58)
            # Use large-text (3:1) threshold — keeps accent vivid, not muddy
            accent    = darken_to_readable(vivid_raw, "#FFFFFF", min_ratio=3.0)
            accent_hdr = ensure_readable(vivid_raw, primary_hex)  # readable on dark header
            return {
                "header_bg":  primary_hex,
                "body_bg":    "#FAF7F0",
                "card_bg":    "#FFFFFF",
                "primary":    accent,         # vivid — stat numbers, borders, section labels
                "secondary":  primary_hex,    # dark — table headers, date chips bg
                "accent":     accent_hdr,     # vivid on dark header
                "text_main":  "#1A202C",
                "text_muted": "#4A5568",
            }
        else:
            # Vivid/bright brand color — use directly as accent.
            dark_hdr = hsl_to_hex(h, s*0.9, 10)
            accent   = darken_to_readable(primary_hex, "#FFFFFF", min_ratio=3.0)
            return {
                "header_bg":  dark_hdr,
                "body_bg":    "#FAF7F0",
                "card_bg":    "#FFFFFF",
                "primary":    accent,
                "secondary":  dark_hdr,
                "accent":     ensure_readable(primary_hex, dark_hdr),
                "text_main":  "#1A202C",
                "text_muted": "#4A5568",
            }
    except Exception:
        return None

def fetch_brand_colors(topic):
    """
    Return a full palette dict for the topic.
    Uses zero Groq tokens — URL guessed via heuristic, colors extracted from the page.
    Falls back gracefully to None (Groq generates colors instead).
    """
    site_url = guess_brand_url(topic)
    if not site_url:
        return None
    print(f"  Fetching brand colors from {site_url}...")

    # Step 2: fetch the page
    try:
        page = requests.get(site_url, timeout=8, allow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        html = page.text
    except Exception:
        return None

    def valid_hex(c):
        c = c.strip()
        if re.match(r'^#[0-9a-fA-F]{3}$', c):
            c = '#' + ''.join(x*2 for x in c[1:])
        return c if re.match(r'^#[0-9a-fA-F]{6}$', c) else None

    # Step 3a: meta theme-color (highest priority — explicitly set by brand)
    for pat in [
        r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']theme-color["\']',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            color = valid_hex(m.group(1))
            if color:
                print(f"  Brand color (theme-color meta): {color}")
                return build_brand_palette(color)

    # Step 3b: mask-icon color (Safari pinned tab — often the brand's key color)
    m = re.search(r'<link[^>]+rel=["\']mask-icon["\'][^>]+color=["\']([^"\']+)["\']', html, re.I)
    if m:
        color = valid_hex(m.group(1))
        if color:
            print(f"  Brand color (mask-icon): {color}")
            return build_brand_palette(color)

    # Step 3c: msapplication-TileColor
    m = re.search(r'<meta[^>]+name=["\']msapplication-TileColor["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']msapplication-TileColor["\']', html, re.I)
    if m:
        color = valid_hex(m.group(1))
        if color:
            print(f"  Brand color (msapplication): {color}")
            return build_brand_palette(color)

    # Step 3d: CSS custom properties
    for prop in ['--color-primary','--primary-color','--primary','--brand-color',
                 '--color-brand','--color-accent','--accent','--color-highlight']:
        m = re.search(rf'{re.escape(prop)}\s*:\s*(#[0-9a-fA-F]{{3,6}})', html)
        if m:
            color = valid_hex(m.group(1))
            if color:
                print(f"  Brand color (CSS var {prop}): {color}")
                return build_brand_palette(color)

    # Step 3c: colorthief on hero image (if available)
    if HAS_COLORTHIEF:
        img_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if img_m:
            try:
                img_url = img_m.group(1)
                img_resp = requests.get(img_url, timeout=6)
                ct = ColorThief(BytesIO(img_resp.content))
                rgb = ct.get_color(quality=1)
                color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                print(f"  Brand color (image extraction): {color}")
                return build_brand_palette(color)
            except Exception:
                pass

    return None

# ─────────────────────────────────────────────
# GMAIL AUTH
# ─────────────────────────────────────────────

def get_gmail_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ─────────────────────────────────────────────
# CONTENT GENERATION (Claude API)
# ─────────────────────────────────────────────

def generate_content(topic):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        print("ERROR: GROQ_API_KEY not set in .env — get a free key at console.groq.com")
        sys.exit(1)

    # Try to fetch real brand colors before generating content
    brand_pal = fetch_brand_colors(topic)

    print(f"  Researching: {topic}...")

    prompt = f"""You are a senior research journalist creating a professional intelligence newsletter.
Generate comprehensive, factual newsletter content for this topic: "{topic}"

CRITICAL ACCURACY RULES — NEVER BREAK THESE:
- Today's date is June 1, 2026. Never invent events that have not yet happened.
- If the topic is a FUTURE event, only cover confirmed facts, preparations, history, schedule, venue.
  Do NOT fabricate match results, scores, winners, or outcomes that have not occurred.
- If the topic is a PAST event, only include verified historical facts.
- VERIFY OR OMIT: if you are not certain of a specific number or structural fact, DO NOT include it.
  It is better to omit a stat entirely than to guess or estimate. Never round up or substitute a
  "typical" or "traditional" figure when the real one may differ (e.g. do not assume a tournament
  has 32 teams just because older editions did — check if the format has changed).
- Every stat must be a number you are genuinely confident is correct. If unsure, leave it out.
- Label predictions clearly as "Projected" or "Expected" — never state them as facts.

IMPORTANT — Color Palette Rule:
Research the primary colors authentically associated with this topic (brand colors, event colors, national colors, etc).
Build a dark, premium color palette from those. Ensure all text is readable. Examples:
- FIFA World Cup 2026 → deep navy (#0A1F3D), gold (#C9A227), red (#C8102E)
- McDonald's → red (#DA291C), yellow (#FFC72C), dark bg (#1A0A00)
- Apple → silver (#A8A8A8), white (#F5F5F5), dark bg (#0D0D0D)
Always use dark backgrounds. Always ensure text contrast is strong.

STATUS PILL RULES — apply these to every timeline event's "status" field:
- CONFIRMED  = already happened, verified fact
- HISTORICAL = happened before 2020, well-established record
- PROJECTED  = has NOT happened yet, or is a forecast/prediction (MUST use this for future events)
- RISK       = a threat, danger or downside scenario

Return ONLY valid JSON — no markdown, no explanation, just raw JSON:
{{
  "title": "Short powerful title (4-6 words max)",
  "subtitle": "One compelling subtitle sentence",
  "tldr": [
    "One-line bullet summarising the most important fact",
    "One-line bullet on the key number or scale",
    "One-line bullet on what happens next or why it matters"
  ],
  "colors": {{
    "header_bg": "#hex — dark brand color for the header band only (e.g. navy, dark red)",
    "primary":   "#hex — the most VIVID brand color — used for numbers, borders, accents on WHITE",
    "secondary": "#hex — second brand color (for table headers, chips)",
    "accent":    "#hex — vivid color readable ON the dark header (often same as primary)"
  }},
  "summary": [
    "First paragraph — essential context and background (3-4 sentences)",
    "Second paragraph — key recent developments with specific facts (3-4 sentences)",
    "Third paragraph — current status and what it means (3-4 sentences)"
  ],
  "pull_quote": "The single most striking insight from this topic — one punchy sentence in the author's voice.",
  "stats": [
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}},
    {{"number": "X", "label": "Short label", "note": "Source or brief context"}}
  ],
  "timeline": [
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}},
    {{"date": "Mon YYYY", "headline": "What happened", "detail": "Why it matters — 1-2 sentences", "status": "CONFIRMED|HISTORICAL|PROJECTED|RISK"}}
  ],
  "table_title": "Descriptive title for the data table",
  "table_headers": ["Column 1", "Column 2", "Column 3"],
  "table_rows": [
    ["value", "value", "value"],
    ["value", "value", "value"],
    ["value", "value", "value"],
    ["value", "value", "value"],
    ["value", "value", "value"]
  ],
  "outlook": [
    {{"label": "Short Term", "text": "2-3 sentence near-term outlook"}},
    {{"label": "Key Risk",   "text": "2-3 sentence biggest risk to watch"}},
    {{"label": "Watch For",  "text": "2-3 sentence indicators to monitor"}}
  ],
  "comparison_title": "Metric name WITH units and timeframe (e.g. 'Operating margin by automaker, Q1 2025 (%)')",
  "comparison": [
    {{"label": "Entity A", "value": 75, "max": 100}},
    {{"label": "Entity B", "value": 45, "max": 100}},
    {{"label": "Entity C", "value": 90, "max": 100}},
    {{"label": "Entity D", "value": 30, "max": 100}}
  ],
  "sources": "Reuters | AP | [2-4 other credible sources for this topic]",
  "subject_line": "Eye-catching email subject under 55 chars — short, urgent, makes someone NEED to open it"
}}

STATS: Return AT LEAST 10 stats (exactly 10 is ideal). Never return fewer than 7.
Only include stats you are genuinely confident are correct — omit any you are unsure of.

COMPARISON RULES:
- comparison_title MUST name the metric clearly with units AND timeframe (e.g. "EV market share, 2025 (%)").
- The metric must be decision-useful — something that genuinely helps the reader judge or compare.
- All values must share the same unit and the same max scale.
- If no meaningful, real, comparable metric exists for this topic, return comparison_title as "" and comparison as [].
  Never output arbitrary numbers with no context.

DATA FRESHNESS — CRITICAL:
- It is June 2026. Do NOT present figures from 2022 or 2023 as current.
- If you do not reliably know a CURRENT figure, either omit it or label it clearly with its year (e.g. "FY2024").
- Never invent precise financials (revenue, net income, EPS, market cap). If unsure of the exact figure, omit
  the stat or table row entirely rather than fabricate.

Use real facts and specific numbers. Be authoritative. Today's date is June 2026."""

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    # Try models in order — each has its own separate quota on Groq free tier
    MODELS = [
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "mixtral-8x7b-32768",
        "llama3-8b-8192",
    ]

    import time
    resp = None
    for model in MODELS:
        payload["model"] = model
        for attempt in range(2):
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 429:
                if attempt == 0:
                    print(f"  {model} rate limited — trying next model...")
                break
            resp.raise_for_status()
            break
        if resp and resp.status_code == 200:
            break
    else:
        print("ERROR: All Groq models rate limited. Daily quota likely exhausted — try again tomorrow.")
        sys.exit(1)

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]

    data = json.loads(raw.strip())

    # Override colors with real brand palette if fetched successfully
    if brand_pal:
        data["colors"] = brand_pal

    return data

# ─────────────────────────────────────────────
# HTML BUILDER (Gmail-compatible: inline styles + tables only)
# ─────────────────────────────────────────────

def build_html(d):
    title    = d["title"]
    subtitle = d["subtitle"]

    # ── COLOR SYSTEM ─────────────────────────────────────────────────────
    # Page/card backgrounds are ALWAYS hardcoded light — never from Groq or extraction.
    # Only accent/header colors come from the brand palette.
    c    = d.get("colors", {})
    BG   = "#FAF7F0"    # warm cream — hardcoded, never overridden
    CARD = "#FFFFFF"    # white cards — hardcoded, never overridden
    CAR2 = "#F5F2EB"    # alt row
    BDR  = "#E2E8F0"    # light border
    DARK = "#1A202C"    # body text — always near-black on light bg
    MUTE = "#4A5568"    # muted text — always dark

    # Header — brand dark color (safe default if extraction fails)
    HDR  = c.get("header_bg", "#0c1219")

    # Accent — brand vivid color, readable on white (3:1 large-text threshold)
    RED  = darken_to_readable(c.get("primary", "#B8860B"), CARD, min_ratio=3.0)

    # Header accent — brand vivid readable on dark header
    ORG  = ensure_readable(c.get("accent", "#F4A261"), HDR)

    # Secondary — dark tint for table headers, date chips
    BLU  = c.get("secondary", "#1B4F8A")

    # Fixed: header always uses light text
    HWHT = "#EDEFF2"   # light text on dark header
    HGRY = "#8a94a0"   # muted text on dark header

    summary     = d.get("summary", [])
    stats       = d.get("stats", [])
    timeline    = d.get("timeline", [])
    t_title     = d.get("table_title", "Data Breakdown")
    t_heads     = d.get("table_headers", [])
    t_rows      = d.get("table_rows", [])
    outlook     = d.get("outlook", [])
    sources     = d.get("sources", "")
    pull_quote  = d.get("pull_quote", "")
    tldr        = d.get("tldr", [])
    comparison       = d.get("comparison", [])
    comparison_title = d.get("comparison_title", "")

    # ── hero stat (stats[0] full-width) ──
    hero_html  = ""
    grid_stats = list(stats)
    if stats:
        h = stats[0]
        grid_stats = list(stats[1:])
        # Hard trim to lower multiple of 3 — never emit incomplete rows or spacers
        n = len(grid_stats)
        if n % 3 != 0:
            grid_stats = grid_stats[:n - (n % 3)]
        hero_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{CARD};border:1px solid {BDR};border-radius:10px;
              border-left:5px solid {RED};overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
  <tr>
    <td style="padding:28px 32px;width:40%;vertical-align:middle;border-right:1px solid {BDR};height:110px;">
      <span style="font-family:Arial,sans-serif;font-size:56px;font-weight:800;color:{RED};
                   display:block;line-height:1;">{h['number']}</span>
    </td>
    <td style="padding:28px 32px;vertical-align:middle;height:110px;">
      <span style="font-family:Arial,sans-serif;font-size:17px;font-weight:700;color:{DARK};
                   display:block;margin-bottom:8px;">{h['label']}</span>
      <span style="font-family:Arial,sans-serif;font-size:13px;color:{MUTE};
                   line-height:1.6;display:block;">{h['note']}</span>
    </td>
  </tr>
</table>"""

    # ── remaining stat cards (3 per row, padded to full rows) ──
    stat_rows = ""
    for i in range(0, len(grid_stats), 3):
        chunk = grid_stats[i:i+3]
        stat_rows += "<tr>"
        for s in chunk:
            stat_rows += f"""
      <td width="33%" style="padding:6px;vertical-align:top;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background:{CARD};border:1px solid {BDR};border-radius:8px;
                      border-top:3px solid {RED};box-shadow:0 1px 3px rgba(0,0,0,0.05);">
          <tr><td align="center" style="padding:22px 12px 18px;height:150px;vertical-align:middle;">
            <span style="font-family:Arial,sans-serif;font-size:34px;font-weight:800;color:{RED};
                         display:block;line-height:1.1;">{s['number']}</span>
            <span style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;color:{DARK};
                         display:block;margin:7px 0 5px;">{s['label']}</span>
            <span style="font-family:Arial,sans-serif;font-size:11px;color:{MUTE};
                         display:block;line-height:1.5;">{s['note']}</span>
          </td></tr>
        </table>
      </td>"""
        stat_rows += "</tr>"

    # ── pull quote (dark block for drama) ──
    pull_html = ""
    if pull_quote:
        pull_html = f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{HDR};border-radius:10px;overflow:hidden;">
  <tr>
    <td style="padding:32px 36px;border-left:5px solid {ORG};">
      <span style="font-family:Georgia,serif;font-size:56px;font-weight:700;color:{ORG};
                   display:block;line-height:0.6;margin-bottom:14px;">&ldquo;</span>
      <span style="font-family:Georgia,serif;font-size:20px;color:{HWHT};
                   line-height:1.6;display:block;font-style:italic;">{pull_quote}</span>
    </td>
  </tr>
</table>"""

    # ── timeline rows — spine + chips + event numbers (no status pills) ──
    tl_rows = ""
    for i, ev in enumerate(timeline):
        bg  = CARD if i % 2 == 0 else CAR2
        num = str(i + 1).zfill(2)
        # Date chip uses header dark bg with warm accent text — always readable
        tl_rows += f"""
      <tr>
        <td style="background:{RED};width:6px;padding:0;"></td>
        <td style="background:{bg};padding:16px 14px;width:120px;vertical-align:top;
                   border-bottom:1px solid {BDR};">
          <span style="display:inline-block;background:{HDR};color:{ORG};
                       font-family:Arial,sans-serif;font-size:10px;font-weight:700;
                       padding:3px 10px;border-radius:12px;letter-spacing:0.5px;
                       white-space:nowrap;">{ev['date']}</span>
        </td>
        <td style="background:{bg};padding:16px 18px;border-bottom:1px solid {BDR};vertical-align:top;">
          <span style="font-family:Arial,sans-serif;font-size:13px;font-weight:700;
                       color:{DARK};display:block;margin-bottom:5px;">{ev['headline']}</span>
          <span style="font-family:Arial,sans-serif;font-size:12px;color:{MUTE};
                       line-height:1.6;display:block;">{ev['detail']}</span>
        </td>
        <td style="background:{bg};padding:16px 10px;border-bottom:1px solid {BDR};
                   vertical-align:middle;width:32px;text-align:right;">
          <span style="font-family:Arial,sans-serif;font-size:26px;font-weight:800;
                       color:{BDR};">{num}</span>
        </td>
      </tr>"""

    # ── data table headers ──
    th_html = "".join(
        f'<th style="padding:12px 14px;font-family:Arial,sans-serif;font-size:11px;'
        f'font-weight:700;color:{HWHT};text-align:left;letter-spacing:1px;'
        f'text-transform:uppercase;border-bottom:2px solid {ORG};">{h}</th>'
        for h in t_heads)

    # ── data table rows ──
    dt_rows = ""
    for i, row in enumerate(t_rows):
        bg    = CARD if i % 2 == 0 else CAR2
        cells = "".join(
            f'<td style="background:{bg};padding:12px 14px;font-family:Arial,sans-serif;'
            f'font-size:12px;color:{DARK if j==0 else MUTE};border-bottom:1px solid {BDR};'
            f'font-weight:{"700" if j==0 else "400"};">{v}</td>'
            for j, v in enumerate(row))
        dt_rows += f"<tr>{cells}</tr>"

    # ── summary paragraphs ──
    sum_html = "".join(
        f'<p style="font-family:Arial,sans-serif;font-size:14px;color:{MUTE};'
        f'line-height:1.85;margin:0 0 14px 0;">{p}</p>'
        for p in summary)

    # ── bar chart rows ──
    bar_rows = ""
    for item in comparison:
        try:
            val      = float(item.get("value", 0))
            mx       = float(item.get("max", 100)) or 100
            pct      = min(100, max(0, round(val / mx * 100)))
            lbl      = item.get("label", "")
            disp     = str(item.get("value", ""))
            filled_w = max(1, pct)
            empty_w  = max(1, 100 - pct)
            bar_rows += f"""
      <tr>
        <td style="padding:8px 0 4px;">
          <span style="font-family:Arial,sans-serif;font-size:12px;font-weight:600;color:{DARK};">{lbl}</span>
          <span style="font-family:Arial,sans-serif;font-size:12px;color:{MUTE};float:right;">{disp}</span>
        </td>
      </tr>
      <tr>
        <td style="padding:0 0 12px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="border-radius:4px;overflow:hidden;">
            <tr>
              <td width="{filled_w}%" style="background:{RED};height:10px;border-radius:4px 0 0 4px;"></td>
              <td width="{empty_w}%" style="background:{BDR};height:10px;border-radius:0 4px 4px 0;"></td>
            </tr>
          </table>
        </td>
      </tr>"""
        except Exception:
            continue

    # ── outlook blocks ──
    outlook_html = ""
    for i, o in enumerate(outlook, 1):
        bar_color = RED if i == 1 else ORG if i == 2 else BLU
        outlook_html += f"""
      <tr>
        <td style="width:4px;background:{bar_color};padding:0;"></td>
        <td style="background:{CARD};padding:20px 22px;border-bottom:1px solid {BDR};">
          <span style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;
                       color:{RED};text-transform:uppercase;letter-spacing:1px;
                       display:block;margin-bottom:7px;">{o['label']}</span>
          <span style="font-family:Arial,sans-serif;font-size:13px;color:{MUTE};
                       line-height:1.8;display:block;">{o['text']}</span>
        </td>
      </tr>"""

    # ── section label helper ──
    def sec_label(text):
        return (f'<span style="font-family:Arial,sans-serif;font-size:11px;font-weight:700;'
                f'color:{RED};letter-spacing:3px;text-transform:uppercase;display:block;'
                f'margin-bottom:16px;padding-left:10px;border-left:3px solid {RED};">{text}</span>')

    # ── CTA button text on ORG (warm accent on dark footer) ──
    cta_txt = ensure_readable("#1A202C", ORG)  # dark text on warm accent button

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
</head>
<body style="margin:0;padding:0;background:{BG};">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{BG};">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" border="0"
       style="border:1px solid {BDR};box-shadow:0 2px 12px rgba(0,0,0,0.08);">

<!-- HEADER (dark band — brand color) -->
<tr><td style="background:{HDR};padding:52px 36px 44px;text-align:center;">
  <span style="display:inline-block;background:{ORG};color:{ensure_readable('#1A202C', ORG)};
               font-family:Arial,sans-serif;font-size:11px;font-weight:700;letter-spacing:3px;
               text-transform:uppercase;padding:5px 16px;border-radius:3px;margin-bottom:20px;">
    Intelligence Brief
  </span><br>
  <span style="font-family:Georgia,serif;font-size:44px;font-weight:700;color:{HWHT};
               line-height:1.15;display:block;margin-bottom:12px;">{title}</span>
  <span style="font-family:Georgia,serif;font-size:20px;font-weight:400;color:{ORG};
               display:block;margin-bottom:16px;">{subtitle}</span>
  <span style="font-family:Arial,sans-serif;font-size:11px;color:{HGRY};letter-spacing:2px;
               text-transform:uppercase;display:block;margin-bottom:14px;">
    ISSUE 001 &nbsp;&middot;&nbsp; JUNE 2026 &nbsp;&middot;&nbsp; 5 MIN READ &nbsp;&middot;&nbsp; INTELLIGENCE BRIEF
  </span>
  <span style="font-family:Arial,sans-serif;font-size:11px;color:{HGRY};">
    Sources: <strong style="color:{ORG};">{sources}</strong>
  </span>
</td></tr>

<!-- AT A GLANCE STRIP -->
{f"""<tr><td style="background:{CARD};border-top:3px solid {RED};border-bottom:1px solid {BDR};padding:16px 36px;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="width:80px;vertical-align:top;padding-top:2px;">
      <span style="display:inline-block;background:{RED};color:{HWHT};font-family:Arial,sans-serif;
                   font-size:10px;font-weight:800;letter-spacing:1px;padding:3px 10px;border-radius:4px;">
        AT A GLANCE
      </span>
    </td>
    <td style="vertical-align:top;padding-left:12px;">
      {"".join(f'<span style="font-family:Arial,sans-serif;font-size:13px;color:{DARK};display:block;line-height:1.75;padding:1px 0;">&#8250;&nbsp; {b}</span>' for b in tldr)}
    </td>
  </tr></table>
</td></tr>""" if tldr else ""}

<!-- SUMMARY -->
<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label("Executive Summary")}
  <table width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr><td style="background:{CARD};border-left:4px solid {RED};border-radius:8px;
                   padding:24px 26px;border:1px solid {BDR};">
      {sum_html}
    </td></tr>
  </table>
</td></tr>

<!-- PULL QUOTE -->
{f'<tr><td style="background:{BG};padding:46px 36px 0;">{pull_html}</td></tr>' if pull_quote else ""}

<!-- STATS -->
<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label("By The Numbers")}
  {hero_html}
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;">
    {stat_rows}
  </table>
</td></tr>

<!-- TIMELINE -->
<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label("Timeline of Key Events")}
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid {BDR};border-radius:8px;overflow:hidden;">
    {tl_rows}
  </table>
</td></tr>

<!-- DATA TABLE -->
<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label(t_title)}
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid {BDR};border-radius:8px;overflow:hidden;">
    <tr style="background:{HDR};">{th_html}</tr>
    {dt_rows}
  </table>
</td></tr>

<!-- BAR CHARTS -->
{f"""<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label("Comparison")}
  {f'<p style="font-family:Arial,sans-serif;font-size:12px;color:{MUTE};margin:0 0 14px 0;font-style:italic;">{comparison_title}</p>' if comparison_title else ""}
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:{CARD};border-radius:8px;padding:20px 24px;border:1px solid {BDR};">
    {bar_rows}
  </table>
</td></tr>""" if comparison else ""}

<!-- OUTLOOK -->
<tr><td style="background:{BG};padding:46px 36px 0;">
  {sec_label("Outlook &amp; Analysis")}
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="border:1px solid {BDR};border-radius:8px;overflow:hidden;">
    {outlook_html}
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="background:{HDR};padding:40px 36px 36px;text-align:center;">
  <table cellpadding="0" cellspacing="0" border="0" style="margin:0 auto 24px;">
    <tr>
      <td style="background:{ORG};border-radius:4px;padding:14px 36px;">
        <span style="font-family:Arial,sans-serif;font-size:14px;font-weight:700;
                     color:{cta_txt};letter-spacing:0.5px;">
          Read the full brief &#8594;
        </span>
      </td>
    </tr>
  </table>
  <span style="font-family:Arial,sans-serif;font-size:10px;color:{HGRY};line-height:1.9;display:block;">
    Data compiled from open-source intelligence and credentialed journalistic sources.<br>
    <strong style="color:{HWHT};">Generated by WAT Framework</strong> &nbsp;|&nbsp; tools/newsletter.py
  </span>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html

# ─────────────────────────────────────────────
# GMAIL DRAFT
# ─────────────────────────────────────────────

def create_draft(service, subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()
    return draft["message"]["id"]

def open_in_chrome(message_id):
    url = f"https://mail.google.com/mail/#drafts/{message_id}"
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            subprocess.Popen([path, url])
            return
    webbrowser.open(url)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== WAT Newsletter Generator ===\n")

    topic = input("Topic: ").strip()
    if not topic:
        print("No topic entered. Exiting.")
        sys.exit(0)

    print("\nStep 1/3  Generating content with Groq AI...")
    data = generate_content(topic)
    subject = data["subject_line"]
    print(f"  Subject: {subject}")

    print("Step 2/3  Building Gmail draft...")
    html = build_html(data)
    service = get_gmail_service()
    message_id = create_draft(service, subject, html)
    print(f"  Draft created.")

    print("Step 3/3  Opening in Chrome...")
    open_in_chrome(message_id)

    print(f"""
Done!
  Gmail is opening in Chrome with your newsletter pre-loaded.
  Add recipient emails and hit Send.
""")
