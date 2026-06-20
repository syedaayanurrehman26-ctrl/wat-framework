# ThreadIntel: Technical Architecture

## Overview
This document defines the full tech stack, data flow, and integration plan for ThreadIntel as a working subscription business. Everything here is chosen for zero cost to start, minimal code, and the ability to grow.

---

## Stack Decision

| Layer | Tool | Why | Cost |
|-------|------|-----|------|
| Database | **Supabase** | PostgreSQL + auth + storage + API in one. Free tier: 500MB DB, 50K users | Free |
| Auth | **Supabase Auth** | Built in. Email magic links or password — no extra setup | Free |
| Payments | **Stripe** | Industry standard. Handles subscriptions, retries, cancellations automatically | 2.9% + $0.30/txn |
| Waitlist form | **Formspree** | One line of HTML. Emails you every signup. No backend | Free (50/mo) |
| Website hosting | **Netlify** (or Vercel) | Drag and drop deploy. Custom domain. SSL auto | Free |
| Research engine | **Python + PRAW** | Reddit API wrapper. Free for non-commercial, throttled at 60 req/min | Free |
| AI generation | **Groq API** | Already in use. Llama 3.3-70b. Fast and free tier | Free |
| Email delivery | **Gmail (OAuth)** | Already integrated in email_brief.py | Free |
| Domain | **Namecheap or Porkbun** | ~$10/year for .com | ~$10/yr |

**Total monthly cost at launch: ~$0 + Stripe transaction fees**

---

## Database Schema (Supabase)

### Table: `subscribers`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
email           text UNIQUE NOT NULL
name            text
first_name      text
last_name       text
company         text
stripe_customer_id  text
stripe_sub_id   text
plan            text DEFAULT 'founding'    -- 'founding' | 'standard'
active          boolean DEFAULT false
status          text DEFAULT 'waitlist'    -- 'waitlist' | 'active' | 'cancelled' | 'paused'
monthly_price   numeric DEFAULT 9.99
reports_sent    integer DEFAULT 0
last_report_at  timestamptz
slack_webhook   text                       -- Slack Incoming Webhook URL for team delivery
notes           text
created_at      timestamptz DEFAULT now()

-- ADD THIS COLUMN if not present:
-- ALTER TABLE subscribers ADD COLUMN slack_webhook text;
```

### Table: `reports`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
subscriber_id   uuid REFERENCES subscribers(id)
topic           text NOT NULL
format          text DEFAULT 'email_brief'   -- 'email_brief' | 'pdf' | 'pptx' | 'all'
status          text DEFAULT 'queued'        -- 'queued' | 'processing' | 'delivered' | 'failed'
requested_at    timestamptz DEFAULT now()
delivered_at    timestamptz
notes           text
```

### Table: `waitlist`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
email           text UNIQUE NOT NULL
first_name      text
company         text
first_topic     text
format_pref     text
referral_source text
created_at      timestamptz DEFAULT now()
converted       boolean DEFAULT false
```

---

## How a Customer Accesses the Service

### Phase 1 (Now — Manual): Email-Based
```
Customer fills form on website
    ↓
Formspree sends you an email with their details
    ↓
You reply within 24h with Stripe payment link
    ↓
Customer pays → Stripe sends you a confirmation email
    ↓
You manually add them to Supabase subscribers table
    ↓
You send welcome email (from customer_onboarding.md template)
    ↓
Customer replies with research topic
    ↓
You run: python threadintel/email_brief.py
    ↓
Report lands in their inbox as Gmail draft → you send it
```

### Phase 2 (Week 3-4 — Semi-automated): Stripe Webhook
```
Customer pays Stripe
    ↓
Stripe webhook fires → Python script auto-inserts into Supabase
    ↓
Auto-sends welcome email via Gmail API
    ↓
Everything else still manual (report generation + delivery)
```

### Phase 3 (Month 2 — Automated): Full Pipeline
```
Customer pays Stripe
    ↓
Webhook auto-creates subscriber in Supabase
    ↓
Customer submits topic via email or simple web form
    ↓
research.py mines Reddit → email_brief.py generates report
    ↓
deliver.py sends directly to subscriber
    ↓
Supabase report record updated automatically
```

---

## Stripe Setup (Step-by-step)

1. Go to stripe.com → Create account
2. Products → Add Product
   - Name: "ThreadIntel — Founding Member"
   - Price: $9.99 recurring / monthly
3. Copy the **Payment Link URL** → paste into `customer_onboarding.md` launch invite email
4. Settings → Webhooks → Add endpoint (when ready for Phase 2)
5. Settings → Customer emails → Enable payment receipts
6. Dashboard → Balances tab → add bank account for payouts

**Revenue lands in your bank account automatically every 2 days (Stripe standard payout).**

---

## Formspree Setup (5 minutes)

1. Go to formspree.io → Sign up free
2. Create new form → name it "ThreadIntel Waitlist"
3. Copy the Form ID (looks like: `xpzgkrqb`)
4. In `website/index.html` line 1261, replace `YOUR_FORM_ID` with your real ID:
   ```html
   <form action="https://formspree.io/f/xpzgkrqb" method="POST" id="order-form">
   ```
5. Every form submission emails you instantly at syed.aayan.rehman@gmail.com

---

## Netlify Deploy (10 minutes)

1. Go to netlify.com → Sign up with GitHub
2. Drag and drop the `website/` folder onto the Netlify dashboard
3. Site is live at a random URL like `threadintel-xyz.netlify.app`
4. Buy domain → Site Settings → Domain Management → Add custom domain
5. Netlify handles SSL (HTTPS) automatically

---

## Reddit API Setup (for research.py)

**Option A — PRAW (free, rate-limited)**
```python
import praw
reddit = praw.Reddit(
    client_id="YOUR_APP_ID",
    client_secret="YOUR_SECRET",
    user_agent="ThreadIntel Research/1.0"
)
# Register at reddit.com/prefs/apps → create app → "script" type
```
- Limit: 60 requests/minute, 100 results per listing
- Good enough for 10-50 subscribers

**Option B — Arctic Shift API (free, historical)**
- URL: `https://arctic-shift.photon-reddit.com/api/`
- No auth required for public endpoints
- Best for pulling historical threads (2020-present)
- Use as fallback when PRAW rate limits

**Recommended approach:** Use PRAW for recent posts (last 30 days), Arctic Shift for historical context.

---

## Security Rules

- API keys live ONLY in `.env` (already gitignored)
- Supabase Row Level Security (RLS) enabled on all tables
- No customer ever sees code, scripts, or credentials
- Stripe handles all payment data (PCI compliant by default)
- Reports watermarked with subscriber name before delivery

---

## Cost Projection

| Subscribers | Monthly Revenue | Monthly Cost | Profit |
|-------------|----------------|--------------|--------|
| 10 | $99.90 | ~$3 (Stripe fees) | ~$97 |
| 50 | $499.50 | ~$15 | ~$485 |
| 100 | $999 | ~$29 + Supabase Pro ($25) | ~$945 |
| 500 | $4,995 | ~$145 + infra ~$50 | ~$4,800 |

Supabase free tier handles up to 50,000 monthly active users — you won't hit paid tier for a very long time.
