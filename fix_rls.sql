-- ============================================================
-- Run this in Supabase SQL Editor to fix the RLS insert error
-- (Do NOT run the full supabase_setup.sql — it drops the table)
-- ============================================================

-- Enable RLS on documents (may already be enabled)
alter table documents enable row level security;

-- Drop old conflicting policies if any
drop policy if exists "Service role full access on documents" on documents;
drop policy if exists "Allow public read on documents" on documents;

-- Allow the backend service role to insert/update/delete chunks freely
create policy "Service role full access on documents" on documents
  using (true)
  with check (true);
