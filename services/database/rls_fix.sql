-- ─────────────────────────────────────────────────────────────────────────────
-- rls_fix.sql  — Run this in Supabase SQL Editor to fix RLS 401 errors
-- ─────────────────────────────────────────────────────────────────────────────
-- 
-- PROBLEM: The scraper uses the anon key (not service_role key), so RLS blocks writes.
-- SOLUTION: Disable RLS on all tables (safe for a personal/private project).
--
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- Disable RLS on all tables (simplest fix for personal projects)
ALTER TABLE properties    DISABLE ROW LEVEL SECURITY;
ALTER TABLE price_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE scraper_runs  DISABLE ROW LEVEL SECURITY;
ALTER TABLE zone_averages DISABLE ROW LEVEL SECURITY;

-- Drop any existing policies that might conflict
DROP POLICY IF EXISTS "service_role can insert properties"    ON properties;
DROP POLICY IF EXISTS "service_role can update properties"    ON properties;
DROP POLICY IF EXISTS "service_role can insert price_history" ON price_history;
DROP POLICY IF EXISTS "public can read properties"            ON properties;
DROP POLICY IF EXISTS "public can read price_history"         ON price_history;

-- Verify RLS is disabled (should return 'f' for all tables)
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename IN ('properties', 'price_history', 'scraper_runs', 'zone_averages');
