# ThreadIntel: Tomorrow's Action List

Priority order. Do these in sequence — each one unlocks the next.

---

## Block 1 — Foundation (Morning, ~2 hours)

### 1. Get a Domain
- Go to **porkbun.com** (cheapest) or **namecheap.com**
- Search: `threadintel.com` → if taken, try `threadintel.io` or `getthreadintel.com`
- Register it (~$10-12/year)
- Point it to Netlify after website is deployed

### 2. Deploy the Website on Netlify
- Go to netlify.com → sign up with GitHub (or Google)
- Drag and drop the `website/` folder onto the dashboard
- Site goes live instantly at a `*.netlify.app` URL
- Then: Site Settings → Domain Management → Add your new domain
- SSL (HTTPS) is automatic

### 3. Set Up Formspree (5 minutes)
- Go to formspree.io → sign up free
- Create new form → name it "ThreadIntel Waitlist"
- Copy your Form ID (e.g., `xpzgkrqb`)
- Open `website/index.html` line ~1261
- Replace `YOUR_FORM_ID` with your real ID
- Redeploy to Netlify (just drag the folder again)
- Test: submit the form → check your email

### 4. Set Up Stripe
- Go to stripe.com → create account
- Products → Add Product:
  - Name: "ThreadIntel — Founding Member"
  - Price: $9.99/month recurring
- Copy the **Payment Link URL**
- Paste it into `workflows/customer_onboarding.md` (the launch invite template)
- Add your bank account for payouts

---

## Block 2 — Brand (Afternoon, ~1.5 hours)

### 5. Logo
Options (pick one):
- **Option A — AI-generated (free, fast):** Go to looka.com or brandmark.io, type "ThreadIntel", describe: "dark, intelligence, data, threads, premium" → download SVG
- **Option B — Canva (free):** Search "tech logo" templates, customize with ThreadIntel name and purple/teal color scheme from the website
- **Option C — Ask me:** Tell me the style you want (minimal wordmark, icon + text, etc.) and I'll design it as SVG code directly in the HTML

Target: A wordmark logo in the same purple-to-teal gradient already on the website. "Thread" in white, "Intel" in gradient.

### 6. Color Scheme (Already Done — But Finalize It)
The website already has a strong, consistent palette:
```
Background:   #020818 (deep navy-black)
Primary:      #7C6FFF (purple)
Accent:       #00D9B8 (teal)
Gold (badge): #FFE566
Text:         #E2E8F0
Muted text:   #94A3B8
```
Use these EVERYWHERE — logo, social posts, email headers, reports. Consistency = brand recognition.

---

## Block 3 — Social Presence (Afternoon, ~1 hour)

### 7. Create Twitter / X Account
- Go to x.com → Sign up
- Username: `@ThreadIntel` (or `@ThreadIntelHQ` if taken)
- Display name: `ThreadIntel`
- Bio: `Reddit-powered market intelligence reports. 24 hours. $9.99/month. For founders, PMMs, and growth teams.`
- Profile photo: your logo
- Header image: a screenshot or banner version of the website hero
- Link in bio: your new domain
- Pin a first tweet:
  ```
  I just launched ThreadIntel.

  You submit a topic. We mine Reddit, forums, and the web.
  You get a structured intelligence report in 24 hours.

  $9.99/month. Unlimited reports. 50 founding spots.

  If you've ever needed market research but couldn't afford it:
  [link]
  ```

### 8. Post Your First Reddit Thread
In r/SideProject:
```
Title: I built ThreadIntel — Reddit-powered market research reports for $9.99/month [feedback welcome]

[use the Post Type B template from lead_generation.md]
```

---

## Block 4 — Backend Setup (Evening, ~1 hour)

### 9. Set Up Supabase
- Go to supabase.com → sign up free
- Create new project: "threadintel"
- Go to SQL Editor → run the schema from `workflows/technical_architecture.md`
- Save your Supabase URL and anon key to `.env`:
  ```
  SUPABASE_URL=https://xxxxx.supabase.co
  SUPABASE_KEY=your_anon_key_here
  ```

### 10. Register for Reddit API (PRAW)
- Go to reddit.com → sign up or use existing account
- Go to reddit.com/prefs/apps → Create App
  - Type: "script"
  - Name: "ThreadIntel Research"
  - Redirect: `http://localhost:8080`
- Copy client_id and client_secret to `.env`:
  ```
  REDDIT_CLIENT_ID=your_client_id
  REDDIT_SECRET=your_secret
  REDDIT_USER_AGENT=ThreadIntel/1.0 by u/yourusername
  ```

---

## Block 5 — First Revenue Action (Evening, 30 min)

### 11. Send 5 Personal DMs
To people in your existing network who run businesses, do marketing, or do research.
Use the Week 1 DM template from `workflows/lead_generation.md`.

Offer them a free sample report. Get your first conversation started.

### 12. Update the Announce Bar
Once your site is live at a real domain, update `website/index.html`:
- Change the announce bar link from `#order` to the actual Stripe payment link
- Update the footer email if needed

---

## Summary: What Tomorrow Unlocks

| Task | Unlocks |
|------|---------|
| Domain + Netlify deploy | Real URL to share everywhere |
| Formspree | Waitlist form actually works |
| Stripe | Ability to take payment |
| Logo | Professional presence |
| Twitter account | Distribution channel + credibility |
| Reddit post | First organic leads |
| Supabase | Database for subscriber tracking |
| Reddit API | Future: automated research pipeline |
| 5 DMs | First actual conversations with potential customers |

**End of tomorrow: ThreadIntel is a real, live business with a real URL, real payment processing, and real conversations in your inbox.**
