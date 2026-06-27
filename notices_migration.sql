-- ══════════════════════════════════════════════════════════════════
-- CampusMind — Agentic Notice Notification Tables
-- Run this in your Supabase SQL editor
-- ══════════════════════════════════════════════════════════════════

-- 1. Notices table — admin-created notices (from PDF or text)
CREATE TABLE IF NOT EXISTS public.notices (
  id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title        TEXT NOT NULL,
  content      TEXT NOT NULL,
  notice_type  TEXT NOT NULL DEFAULT 'general',  -- 'holiday' | 'exam_notice' | 'fee_notice' | 'student_notice' | 'scholarship' | 'internship' | 'general'
  source_type  TEXT NOT NULL DEFAULT 'pdf',       -- 'pdf' | 'text'
  source_file  TEXT,                              -- original filename if source_type = 'pdf'
  scholar_ids  TEXT[] DEFAULT '{}',               -- scholar IDs extracted by agent (empty = broadcast)
  is_broadcast BOOLEAN DEFAULT FALSE,             -- TRUE if notice is for all students (holiday etc.)
  notified_count INT DEFAULT 0,                   -- how many students were notified
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- 2. Per-user notification delivery table
CREATE TABLE IF NOT EXISTS public.user_notifications (
  id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  notice_id            UUID REFERENCES public.notices(id) ON DELETE CASCADE,
  user_id              UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  scholar_id           VARCHAR(7),
  notification_title   TEXT NOT NULL,
  notification_message TEXT NOT NULL,
  is_read              BOOLEAN DEFAULT FALSE,
  created_at           TIMESTAMPTZ DEFAULT now()
);

-- ── Row Level Security ─────────────────────────────────────────────

ALTER TABLE public.notices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_notifications ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to allow re-running
DROP POLICY IF EXISTS "Service role full access on notices" ON public.notices;
DROP POLICY IF EXISTS "Service role full access on user_notifications" ON public.user_notifications;
DROP POLICY IF EXISTS "Users can view their own notifications" ON public.user_notifications;
DROP POLICY IF EXISTS "Users can update their own notifications" ON public.user_notifications;

-- Backend service role: full access to both tables
CREATE POLICY "Service role full access on notices" ON public.notices
  USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on user_notifications" ON public.user_notifications
  USING (true) WITH CHECK (true);

-- Students: can only read their own notifications
CREATE POLICY "Users can view their own notifications" ON public.user_notifications
  FOR SELECT USING (auth.uid() = user_id);

-- Students: can mark their own notifications as read
CREATE POLICY "Users can update their own notifications" ON public.user_notifications
  FOR UPDATE USING (auth.uid() = user_id);

-- ── Indexes for fast lookup ────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_user_notifications_user_id ON public.user_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notifications_is_read ON public.user_notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notices_created_at ON public.notices(created_at DESC);
