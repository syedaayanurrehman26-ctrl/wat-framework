-- ThreadIntel — Supabase migrations v2
-- Run these in: Supabase → SQL Editor → New Query → Paste → Run

-- ─────────────────────────────────────────────────────────────────
-- 1. Core reports table columns
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE reports ADD COLUMN IF NOT EXISTS format text DEFAULT 'email_brief';
ALTER TABLE reports ADD COLUMN IF NOT EXISTS sources text[];
ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_html text;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_num integer;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS delivered boolean DEFAULT false;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS notes text;

-- Self-service auth columns
ALTER TABLE reports ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS user_id uuid;

-- Clarifying context (audience, goal, specific angle from portal)
ALTER TABLE reports ADD COLUMN IF NOT EXISTS angles text;

-- Portal v2 enhancements
ALTER TABLE reports ADD COLUMN IF NOT EXISTS source_filter text;      -- comma-separated sources, NULL = all
ALTER TABLE reports ADD COLUMN IF NOT EXISTS date_range text DEFAULT '30d'; -- '7d'|'30d'|'6m'|'all'
ALTER TABLE reports ADD COLUMN IF NOT EXISTS rating integer;           -- 1-5 star rating from user
ALTER TABLE reports ADD COLUMN IF NOT EXISTS rerun_of uuid;            -- original report id if this is a re-run
ALTER TABLE reports ADD COLUMN IF NOT EXISTS delivered_at timestamptz; -- when the email was sent

-- ─────────────────────────────────────────────────────────────────
-- 2. Subscribers table (legacy)
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS slack_webhook text;
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS name text;

-- ─────────────────────────────────────────────────────────────────
-- 3. User settings table (per-user integrations + preferences)
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
  user_id            uuid PRIMARY KEY,
  google_share_email text,        -- share Sheets/Docs/Slides with this Google email
  slack_webhook      text,        -- Slack incoming webhook URL
  notify_email       boolean DEFAULT true,
  notify_slack       boolean DEFAULT false,
  created_at         timestamptz DEFAULT now(),
  updated_at         timestamptz DEFAULT now()
);

ALTER TABLE user_settings DISABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────
-- 4. RLS — keep disabled (portal filters by email/user_id in JS)
-- Re-enable when worker uses service-role key separately.
-- ─────────────────────────────────────────────────────────────────
ALTER TABLE reports DISABLE ROW LEVEL SECURITY;

-- ─────────────────────────────────────────────────────────────────
-- 5. Verify schema
-- ─────────────────────────────────────────────────────────────────
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'reports'
ORDER BY ordinal_position;
