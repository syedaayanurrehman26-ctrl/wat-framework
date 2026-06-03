# Skill: Email Newsletter Generator

## What This Skill Does
Takes any topic — a geopolitical event, market report, industry briefing, company update —
and produces a professional, visually rich HTML newsletter that can be copy-pasted directly
into Gmail with all formatting preserved.

## Skill Name
`email_newsletter_generator`

## When To Use This Skill
Use this whenever the user says any of:
- "Make me a newsletter on [topic]"
- "Create an email brief about [topic]"
- "Generate a client update on [topic]"
- "Write a newsletter for [topic]"

## Required Inputs (ask the user for these)
1. **Topic** — what is the newsletter about? (e.g. "US-Iran conflict", "AI market 2025", "Tesla Q2 earnings")
2. **Audience** — who is reading it? (clients, investors, general public, internal team)
3. **Tone** — intelligence brief / corporate / casual / urgent
4. **Key stats** — any specific numbers or data points to highlight (optional — agent can research)
5. **Sections** — any specific sections the user wants (optional — agent decides by default)

## What the Agent Does (Step by Step)

### Step 1 — Research & Structure Data
- If user provides data: use it directly
- If user provides URLs: run `tools/scrape_website.py` (when available) to pull content
- If user provides a topic only: use agent knowledge to populate STATS, TIMELINE, and SECTIONS
- Organise data into: summary paragraphs, key statistics (number + label + note), timeline events, tables

### Step 2 — Choose Visual Theme
Default themes (pick based on tone):
- **Dark navy/red** — geopolitical, conflict, urgent briefings (used in US-Iran)
- **Dark navy/gold** — financial, market, investment reports
- **Dark green/white** — sustainability, ESG, tech growth
- **Deep purple/cyan** — AI, technology, innovation topics
- **Corporate grey/blue** — internal reports, neutral briefings

### Step 3 — Run the Newsletter Tool
```
python tools/generate_newsletter.py --topic "TOPIC" --theme "THEME"
```
Or for topic-specific tools already built:
```
python tools/generate_us_iran_newsletter.py
```

### Step 4 — Verify Output
- Open the HTML file in Chrome
- Check: header renders, stat cards show, tables are visible, colours load
- Confirm no broken layout or missing sections

### Step 5 — Deliver Instructions to User
Always tell the user:
1. Open `[filename].html` in Chrome
2. Ctrl+A → Ctrl+C
3. Open Gmail Compose
4. Ctrl+V to paste
5. Gmail preserves all inline styles and table formatting

## Gmail Compatibility Rules (NEVER break these)
These rules MUST be followed every time a newsletter is built:

| Rule | Why |
|------|-----|
| All styles must be inline (style="...") | Gmail strips <style> blocks |
| Use `<table>` for all layout | Gmail ignores flexbox and grid |
| No JavaScript | Gmail strips all script tags |
| No CSS animations or @keyframes | Gmail strips them |
| No :hover, :focus, :active | Gmail ignores pseudo-classes |
| No external fonts (use Arial, Georgia, Calibri) | Gmail blocks external font imports |
| No position: fixed/absolute/sticky | Gmail ignores positioning |
| Max width 680px | Standard email client width |
| All images need width/height attributes | Prevents layout collapse |

## Newsletter Structure (Default)
Every newsletter built with this skill should include:

1. **Header** — Title, subtitle, metadata (period, sources, type)
2. **Executive Summary** — 2-3 paragraphs of essential context
3. **By The Numbers** — 9-12 stat cards in a 3-column grid
4. **Alert Banner** — (optional) red warning box for critical information
5. **Main Content** — timeline / events / data (topic-specific)
6. **Supporting Tables** — 1-2 data tables (groups, metrics, breakdowns)
7. **Outlook / Analysis** — 3-4 forward-looking paragraphs with coloured left borders
8. **Footer** — Sources, generated-by attribution

## Tools Built So Far
| Tool | Topic | Status |
|------|-------|--------|
| `tools/generate_us_iran_newsletter.py` | US-Iran Conflict | Done |
| `tools/generate_newsletter.py` | Generic (any topic) | To be built |

## How To Add A New Newsletter Topic
1. Copy `tools/generate_us_iran_newsletter.py`
2. Rename to `tools/generate_[topic]_newsletter.py`
3. Replace the DATA section at the top (STATS, TIMELINE, tables)
4. Keep all the `build_*` functions — only the data changes
5. Run and verify

## Output Files
- `[topic]_newsletter.html` — saved in project root
- Open in Chrome → Copy → Paste into Gmail

## Improvement Log
- v1 (Jun 2026): First version built for US-Iran conflict
- Gmail compatibility rewrite: removed all <style> blocks, converted to 100% inline styles + tables
- Next: build generic parameterized tool so any topic works without copying the file
