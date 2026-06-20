# ThreadIntel: Multi-Agent Business System

## Overview

This defines the multi-agent architecture where specialized AI agents handle different parts of the business and hold a structured "team meeting" each day to align on priorities. Each agent has a single job. Together they run the business autonomously — you just review the daily summary and approve key actions.

---

## The Agents

### Agent 1 — Research Agent (`agent_research.py`)
**Job:** Execute research requests and generate reports
**Triggers:** When a subscriber submits a topic
**Tools it uses:** `threadintel/email_brief.py`, `threadintel/research.py` (when built)
**Output:** Gmail draft with completed report + record in Supabase

**Daily task:**
- Check for any pending report requests in Supabase (`status = 'queued'`)
- Generate report for each
- Mark as `delivered` when done
- Flag any that fail

---

### Agent 2 — Sales Agent (`agent_sales.py`)
**Job:** Monitor for new leads, draft outreach, track prospect pipeline
**Triggers:** Daily at 9am
**Tools it uses:** WebSearch, Gmail draft creation, Supabase
**Output:** Draft outreach emails ready for your review + prospect tracking updates

**Daily task:**
- Search Reddit for new threads where people ask about market research tools (search terms from `prospect_list.md`)
- Find 2-3 posts worth replying to — draft replies for your review
- Check if any DMs/emails arrived from prospects — summarize and draft responses
- Update prospect tracker in Supabase

---

### Agent 3 — Customer Success Agent (`agent_cs.py`)
**Job:** Monitor subscriber satisfaction, flag issues, trigger retention actions
**Triggers:** Daily at 8am
**Tools it uses:** Supabase queries, Gmail
**Output:** Daily subscriber health report

**Daily task:**
- Check: which subscribers haven't submitted a request in 14+ days → draft inactivity check-in email
- Check: which subscribers just got their 2nd or 3rd report → draft testimonial request
- Check: any Stripe cancellation events → draft cancellation response
- Check: any renewal events today → draft monthly renewal note
- Surface anything that needs your attention

---

### Agent 4 — Content Agent (`agent_content.py`)
**Job:** Create Twitter/X threads and LinkedIn posts to drive awareness
**Triggers:** Daily at 10am
**Tools it uses:** WebSearch, Groq AI, `threadintel/email_brief.py` for research
**Output:** 3 social posts ready for your review and posting

**Daily task:**
- Pick a trending topic (business, tech, or startup-relevant)
- Run it through the research engine to pull 3-4 real Reddit insights
- Draft a Twitter thread: "I mined Reddit on [topic]. Here's what I found. 🧵"
- Draft a LinkedIn version (single post, more professional)
- Draft a short-form Tweet teaser
- Output all three for your review — you post them manually or approve for scheduling

---

### Agent 5 — Analytics Agent (`agent_analytics.py`)
**Job:** Track business metrics and surface weekly insights
**Triggers:** Every Monday morning
**Tools it uses:** Supabase, Stripe API
**Output:** Weekly business summary

**Weekly report includes:**
- Active subscribers / new this week / churned
- Reports requested and delivered
- MRR and week-over-week change
- Top topics requested (what are subscribers researching?)
- Outreach activity (posts made, DMs sent, replies)
- Recommended priority for the week

---

## The Daily Team Meeting

Every day at 8:30am, a coordinator script runs all agents and produces a single daily briefing:

```
=== ThreadIntel Daily Briefing — [DATE] ===

BUSINESS HEALTH
  Active subscribers: X  |  MRR: $XX  |  Reports in queue: X

ACTION ITEMS FOR YOU TODAY:
  [ ] Agent 2 found 2 Reddit posts worth replying to → review drafts
  [ ] Agent 3 flagged 1 subscriber inactive 16 days → review check-in email
  [ ] Agent 4 prepared 3 social posts → review and post

COMPLETED OVERNIGHT:
  ✓ Report delivered to [Subscriber] on topic "[Topic]"
  ✓ Content drafted: "[Tweet thread title]"

WATCH LIST:
  ! [Subscriber] hasn't opened last 2 reports (no engagement)

METRICS THIS WEEK:
  New signups: X  |  Reports sent: X  |  MRR change: +$X
```

You review this each morning. Everything that needs a human decision is surfaced here. You approve or send — agents do the work.

---

## Implementation Plan

### Phase 1 — Build the coordinator (Week 2)
File: `threadintel/daily_briefing.py`
- Query Supabase for subscriber stats
- Print the daily summary to terminal
- No automation yet — just gives you the data

### Phase 2 — Add Sales + CS agents (Week 3)
- `agent_sales.py` — Reddit search + draft replies
- `agent_cs.py` — subscriber health checks + draft emails

### Phase 3 — Add Content agent (Week 4)
- `agent_content.py` — daily Twitter thread drafts
- Hooks into `email_brief.py` to research topics

### Phase 4 — Automate the coordinator (Month 2)
- Run `daily_briefing.py` on a schedule (Windows Task Scheduler or cron)
- Agents run automatically, briefing lands in your inbox each morning

---

## Agent Communication Protocol

Agents don't talk to each other directly — they communicate through Supabase:
- Each agent reads from and writes to shared tables
- The coordinator reads the state of all tables and assembles the briefing
- This prevents race conditions and keeps everything auditable

```
Agent 2 (Sales) → writes prospect records to Supabase
Agent 3 (CS)    → reads subscriber records, writes follow-up flags
Agent 4 (Content) → writes drafted posts to a `content_queue` table
Coordinator     → reads everything, assembles daily briefing
You             → reviews briefing, approves/sends actions
```

---

## Why This Works

- **Each agent has ONE job.** No agent tries to do too much.
- **You stay in the loop.** Agents draft, you approve. Nothing sends without your review (until you're ready to trust it fully).
- **It scales.** Add more agents as the business grows (e.g., an agent that monitors Stripe for failed payments and drafts recovery emails).
- **It's cheap.** Each agent uses Groq free tier for AI calls. Total daily cost: ~$0.
