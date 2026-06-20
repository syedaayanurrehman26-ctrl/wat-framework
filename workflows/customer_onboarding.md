# ThreadIntel: Customer Onboarding Playbook

## Overview
This is the complete end-to-end playbook for every customer — from the moment they join the waitlist to ongoing retention. Follow this exactly for every subscriber. Never hand over code, tools, or any technical asset. The value lives entirely in the service you deliver.

---

## Phase 1: Waitlist → Activation

### Step 1.1 — Waitlist Signup Notification
When someone joins the waitlist via the website form, Formspree sends you an email instantly. You'll see their name, email, research type, and referral source.

**Do immediately:**
- Reply to their submission email within 24 hours (see email template below)
- Add them to a simple spreadsheet: `Name | Email | Signup Date | Status | Notes`
- Update `FOUNDING_SPOTS_TAKEN` in `website/index.html` by 1

**Template — Waitlist Welcome (send within 24 hours):**
```
Subject: Welcome to ThreadIntel — Your founding spot is saved 🔒

Hi [First Name],

Thanks for joining the ThreadIntel waitlist. You're one of our founding members — which means $9.99/month locked in forever, even after the public price goes to $24.99.

We're launching within the next 1–2 weeks. When we go live, I'll send you a personal invite with:
- Your Stripe payment link ($9.99/month, cancel anytime)
- Your dedicated research request email
- Instructions for submitting your first report

In the meantime — what's the first topic you'd like us to research? Even just a rough idea helps me make sure your first report is exactly what you need.

Talk soon,
Aayan
ThreadIntel
```

---

### Step 1.2 — Launch Invite (when ready to go live)
Send this to everyone on your waitlist in signup order. Founding members go first.

**Template — Launch Invite:**
```
Subject: ThreadIntel is live — your founding spot is waiting

Hi [First Name],

We're officially live. Your founding member spot is ready.

👉 Subscribe here: [STRIPE PAYMENT LINK]

Once you complete payment, reply to this email with your first research request and I'll get your report started immediately — delivered within 24 hours.

What to include in your request:
- Topic (be as specific or broad as you like)
- Output format: PDF / PowerPoint / Email Brief (or all three)
- Any specific angles you want covered
- Any competitors or comparisons you want included

Your $9.99/month is locked forever from the moment you subscribe.

See you inside,
Aayan
ThreadIntel
```

---

## Phase 2: First Subscriber — Payment & Setup

### Step 2.1 — Stripe Setup (one-time, do this before launch)
1. Create account at stripe.com
2. Go to Products → Create Product
   - Name: "ThreadIntel Founding Member"
   - Price: $9.99/month recurring
   - Billing: Monthly
3. Copy the Payment Link URL
4. Add to your launch invite email template above
5. In Stripe Settings → Notifications: enable email alerts for new subscriptions and cancellations
6. Optional: set up a webhook to ping you on Slack/email on any subscription event

**What Stripe handles automatically:**
- Monthly billing on the same date each month
- Failed payment retries (3 automatic attempts)
- Email receipts to customers
- Cancellation processing
- Subscription status tracking

**What you need to track manually:**
- Who has an active subscription vs. lapsed
- When a subscriber's access should stop (Stripe tells you when they cancel/fail)

---

### Step 2.2 — Welcome Email (send immediately after payment confirmed)
```
Subject: You're in — here's how ThreadIntel works

Hi [First Name],

Payment confirmed — welcome to ThreadIntel. You're a founding member at $9.99/month, locked in forever.

HOW TO REQUEST RESEARCH
Just reply to this email with:

1. Your topic — can be a question, a company name, a market, a competitor, anything
2. Your preferred format — PDF, PowerPoint, or Email Brief (default is Email Brief)
3. Any specific focus areas — optional, but helps us go deeper on what matters to you

Example request:
"Research topic: What are SaaS founders on Reddit saying about Notion vs Linear? 
Format: Email Brief
Focus: Feature complaints, switching reasons, pricing sentiment"

WHAT HAPPENS NEXT
- I'll confirm your request within a few hours
- Your report will be in your inbox within 24 hours
- If anything isn't right, just reply and I'll redo it free

IMPORTANT
Everything is handled on my end. You never need to install anything, run any code, or deal with any technical setup. Just email me your topic.

Ready when you are,
Aayan
ThreadIntel
```

---

## Phase 3: Research Request → Report Delivery

### Step 3.1 — Receiving a Request
When a subscriber emails a research request:

1. **Reply within 4 hours** confirming you received it:
   ```
   Got it — researching [Topic] now. Your report will be in your inbox by [DATE, 24h from now].
   Format: [their format]
   ```

2. **Run the research** using `tools/newsletter.py` for Email Brief format:
   ```
   python tools/newsletter.py
   Topic: [their topic]
   ```
   For PDF/PowerPoint — use the output as content, format manually or build dedicated tools.

3. **Quality check before sending:**
   - All stats have sources or are clearly labeled
   - No fabricated numbers
   - All sections present: summary, stats, timeline, table, comparison, outlook
   - Report reads well, not like raw AI output
   - Add customer's name to the footer watermark (see below)

### Step 3.2 — Watermarking Reports
Every report must include this in the footer before delivery:

```
Prepared exclusively for [Customer First Name] [Customer Last Name]
ThreadIntel Research Service · syed.aayan.rehman@gmail.com
For internal use only. Redistribution prohibited.
Report generated: [DATE]
```

This protects your IP. If someone screenshots or shares the report, it's tied to them.

### Step 3.3 — Delivery Email
```
Subject: Your ThreadIntel Report: [Topic Name]

Hi [First Name],

Your report is ready. Find it [attached as PDF / in the brief below / attached as PPTX].

REPORT: [Topic Name]
Generated: [Date]
Sources: [2-3 main sources used]

[PASTE FULL EMAIL BRIEF HERE, or attach PDF/PPTX]

---
Not quite what you needed? Just reply and tell me what to adjust — I'll redo it free within 24 hours.

Ready for your next report? Just reply with a new topic.

Aayan
ThreadIntel
```

---

## Phase 4: Retention & Growth

### Step 4.1 — Inactivity Check (if no request in 14 days)
```
Subject: Any research topics on your mind?

Hi [First Name],

Just checking in — haven't heard from you in a couple of weeks. 

Anything you've been wanting to dig into? A market, a competitor, a question you keep putting off researching?

Even a rough topic works — just reply and I'll take care of the rest.

Aayan
ThreadIntel
```

### Step 4.2 — After 2nd or 3rd Report — Ask for Testimonial
```
Subject: Quick question

Hi [First Name],

You've now received [X] reports — I'd love to know how they've been landing for you.

If you've found them useful, would you be willing to write 1-2 sentences I could use as a testimonial on the ThreadIntel site? No pressure at all — just helps other people understand what they're getting.

If anything's been off or could be better, I'd love to hear that too.

Thanks,
Aayan
```

### Step 4.3 — Monthly Renewal Moment
When Stripe processes a monthly renewal, send a personal note:

```
Subject: Month [X] — What should we research?

Hi [First Name],

Month [X] just renewed — thanks for being a founding member.

What's on your research list this month? Reply with a topic and I'll get started.

Aayan
```

### Step 4.4 — Cancellation Response
If Stripe notifies you of a cancellation:

```
Subject: Your ThreadIntel subscription

Hi [First Name],

I saw your subscription was cancelled — totally fine, no hard feelings.

Out of curiosity: was there something specific that wasn't working, or was it just timing? Your feedback would genuinely help me make this better.

You'll keep all the reports you've received. If you ever want to come back, just reply to this email — though note that the $9.99 founding rate won't be available again once the price rises.

Thanks for being a founding member,
Aayan
```

---

## Security & IP Protection

### What customers NEVER receive:
- Source code of any kind
- Access to your tools, scripts, or API keys
- Login credentials to any system you use
- The methodology beyond "we use AI + human curation"

### How the service is protected:
1. **Watermarked reports** — every report tied to the subscriber's name
2. **Email-only delivery** — no platform to clone, no app to reverse-engineer
3. **Terms of service** — include in welcome email footer: "Reports are for subscriber's internal business use only. Redistribution, resale, or public sharing is prohibited under the ThreadIntel Terms of Service."
4. **Stripe controls access** — when they cancel, they stop receiving reports. They can't prepay for 6 months and use forever.
5. **You own the output format** — the specific structure, sections, and visual design of your reports is your trade dress
6. **No client-side processing** — everything runs on your machine, not theirs

### If someone tries to cancel then re-subscribe repeatedly:
Stripe tracks this. After 2 cancellations, you can manually add a note to their account and consider not re-offering the founding rate.

---

## Subscriber Tracking Spreadsheet

Maintain this manually in Google Sheets:

| # | Name | Email | Signup Date | Subscribed Date | Plan | Status | Reports Sent | Last Report Date | Notes |
|---|------|-------|-------------|-----------------|------|--------|-------------|-----------------|-------|
| 1 | | | | | Founding $9.99 | Active | 0 | | |

Update after every report sent and every status change.
