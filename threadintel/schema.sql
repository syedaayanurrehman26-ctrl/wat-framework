-- ThreadIntel — Supabase Database Schema
-- Paste this entire file into:
-- Supabase Dashboard → SQL Editor → New Query → Run

-- ── Extensions ────────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ── Subscribers ───────────────────────────────────────────────────────────────
create table if not exists subscribers (
  id                  uuid primary key default gen_random_uuid(),
  email               text unique not null,
  name                text,
  company             text,
  stripe_customer_id  text,
  stripe_sub_id       text,
  plan                text default 'founding',   -- 'founding' | 'standard'
  active              boolean default false,
  monthly_price       numeric default 9.99,
  reports_sent        integer default 0,
  last_report_at      timestamptz,
  notes               text,
  created_at          timestamptz default now()
);

-- ── Reports ───────────────────────────────────────────────────────────────────
create table if not exists reports (
  id              uuid primary key default gen_random_uuid(),
  subscriber_id   uuid references subscribers(id) on delete cascade,
  topic           text not null,
  sources         text[] default array['reddit','hackernews','news','web'],
  format          text default 'email_brief',  -- 'email_brief' | 'pdf' | 'all'
  status          text default 'queued',       -- 'queued' | 'in_progress' | 'done' | 'failed'
  report_html     text,
  report_num      integer,
  delivered       boolean default false,
  delivered_at    timestamptz,
  notes           text,
  created_at      timestamptz default now()
);

-- ── Waitlist ──────────────────────────────────────────────────────────────────
create table if not exists waitlist (
  id              uuid primary key default gen_random_uuid(),
  email           text unique not null,
  name            text,
  company         text,
  first_topic     text,
  format_pref     text,
  referral_source text,
  converted       boolean default false,
  created_at      timestamptz default now()
);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Subscribers can only see their own rows
alter table subscribers enable row level security;
alter table reports enable row level security;
alter table waitlist enable row level security;

-- Service role (your Python scripts) bypasses RLS automatically.
-- Portal users (magic link auth) see only their own reports:
drop policy if exists "subscribers: self only" on subscribers;
create policy "subscribers: self only"
  on subscribers for select
  using (auth.uid()::text = id::text);

drop policy if exists "reports: owner only" on reports;
create policy "reports: owner only"
  on reports for all
  using (
    subscriber_id in (
      select id from subscribers where auth.uid()::text = id::text
    )
  );

-- Waitlist: anyone can insert (signup form), nobody can read via client
drop policy if exists "waitlist: insert only" on waitlist;
create policy "waitlist: insert only"
  on waitlist for insert
  with check (true);

-- ── Indexes ───────────────────────────────────────────────────────────────────
create index if not exists reports_status_idx on reports(status);
create index if not exists reports_sub_idx on reports(subscriber_id);
create index if not exists reports_created_idx on reports(created_at desc);
create index if not exists subscribers_email_idx on subscribers(email);
create index if not exists waitlist_created_idx on waitlist(created_at desc);

-- ── Schedules (recurring reports) ────────────────────────────────────────────
-- Subscribers can schedule a topic to be researched weekly/bi-weekly/monthly.
-- scheduler.py reads this table and queues new reports when due.
create table if not exists schedules (
  id              uuid primary key default gen_random_uuid(),
  subscriber_id   uuid references subscribers(id) on delete cascade,
  topic           text not null,
  sources         text[] default array['reddit','hackernews','news','web'],
  frequency       text default 'weekly',    -- 'weekly' | 'biweekly' | 'monthly'
  active          boolean default true,
  last_run_at     timestamptz,
  next_run_at     timestamptz default now(),
  total_runs      integer default 0,
  created_at      timestamptz default now()
);

alter table schedules enable row level security;

drop policy if exists "schedules: owner only" on schedules;
create policy "schedules: owner only"
  on schedules for all
  using (
    subscriber_id in (
      select id from subscribers where auth.uid()::text = id::text
    )
  );

create index if not exists schedules_next_run_idx on schedules(next_run_at) where active = true;

-- ── Done ──────────────────────────────────────────────────────────────────────
-- After running this:
-- 1. Go to Settings → API → copy URL and anon key into .env
-- 2. Add SUPABASE_URL and SUPABASE_KEY to .env
-- 3. Run: python threadintel/daily_briefing.py  (should show live zeros)
