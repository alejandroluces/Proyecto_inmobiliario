/**
 * supabase.ts — Supabase client singleton
 *
 * Set these two environment variables in a .env file at the root of
 * artifacts/altea-intel/ (never commit the real values):
 *
 *   VITE_SUPABASE_URL=https://your-project-id.supabase.co
 *   VITE_SUPABASE_ANON_KEY=your-anon-public-key
 */
import { createClient } from "@supabase/supabase-js";
import type { Database } from "./database.types";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn(
    "[Altea Intel] Supabase env vars not set. " +
      "Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to your .env file. " +
      "Falling back to mock data."
  );
}

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient<Database>(supabaseUrl, supabaseAnonKey, {
        realtime: { params: { eventsPerSecond: 10 } },
      })
    : null;

export const isSupabaseConfigured = !!supabase;
