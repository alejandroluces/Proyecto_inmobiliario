/**
 * database.types.ts — TypeScript types auto-derived from the Supabase schema.
 * Keep in sync with services/database/schema.sql
 *
 * To regenerate automatically after schema changes:
 *   npx supabase gen types typescript --project-id YOUR_PROJECT_ID > src/lib/database.types.ts
 */

export type PropertySource = "Idealista" | "Fotocasa" | "Facebook";

export type Zone =
  | "Altea Hills"
  | "Casco Antiguo"
  | "Mascarat/Campomanes"
  | "Altea la Vella"
  | "Playa/Centro";

// ─── Raw DB row types ────────────────────────────────────────

export interface DbProperty {
  id: string;
  created_at: string;
  updated_at: string;
  source: PropertySource;
  external_id: string;
  url: string | null;
  title: string;
  description: string | null;
  price: number | null;
  m2: number | null;
  price_per_m2: number | null;   // generated column
  zone: string | null;
  images: string[];
  opportunity_score: number;
  deviation_vs_avg: number | null;
  investment_tags: string[];
  opportunity_reason: string | null;
  is_facebook_exclusive: boolean;
}

export interface DbPriceHistory {
  id: string;
  property_id: string;
  price: number;
  recorded_at: string;
}

export interface DbZoneAverage {
  id: string;
  zone: string;
  avg_price_per_m2: number | null;
  property_count: number;
  updated_at: string;
}

export interface DbScraperRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  source: PropertySource;
  properties_found: number;
  properties_new: number;
  properties_updated: number;
  errors: string[];
  status: "running" | "success" | "error";
}

// ─── View: v_opportunities ───────────────────────────────────

export interface DbOpportunity extends DbProperty {
  zone_avg_price_per_m2: number | null;
  initial_price: number | null;
  price_history: number[] | null;
}

// ─── Supabase Database type (for createClient<Database>) ─────

export interface Database {
  public: {
    Tables: {
      properties: {
        Row: DbProperty;
        Insert: Omit<DbProperty, "id" | "created_at" | "updated_at" | "price_per_m2">;
        Update: Partial<Omit<DbProperty, "id" | "created_at" | "price_per_m2">>;
      };
      price_history: {
        Row: DbPriceHistory;
        Insert: Omit<DbPriceHistory, "id" | "recorded_at">;
        Update: never;
      };
      zone_averages: {
        Row: DbZoneAverage;
        Insert: Omit<DbZoneAverage, "id">;
        Update: Partial<Omit<DbZoneAverage, "id">>;
      };
      scraper_runs: {
        Row: DbScraperRun;
        Insert: Omit<DbScraperRun, "id" | "started_at">;
        Update: Partial<Omit<DbScraperRun, "id" | "started_at">>;
      };
    };
    Views: {
      v_opportunities: {
        Row: DbOpportunity;
      };
    };
    Functions: Record<string, never>;
    Enums: {
      property_source: PropertySource;
    };
  };
}

// ─── App-level Property type (used by UI components) ─────────

export interface Property {
  id: string;
  title: string;
  zone: string | null;
  price: number | null;
  sqm: number | null;
  pricePerSqm: number | null;
  source: PropertySource;
  opportunityScore: number;
  deviationVsAvg: number | null;
  investmentTags: string[];
  opportunityReason: string | null;
  description: string | null;
  priceHistory: number[];
  imageUrl: string | null;
  url: string | null;
  listedAt: string;
  isFacebookExclusive: boolean;
}

// ─── Mapper: DB row → App Property ───────────────────────────

export function mapDbPropertyToApp(row: DbOpportunity): Property {
  return {
    id: row.id,
    title: row.title,
    zone: row.zone,
    price: row.price,
    sqm: row.m2,
    pricePerSqm: row.price_per_m2,
    source: row.source,
    opportunityScore: row.opportunity_score,
    deviationVsAvg: row.deviation_vs_avg,
    investmentTags: row.investment_tags ?? [],
    opportunityReason: row.opportunity_reason,
    description: row.description,
    priceHistory: row.price_history ?? (row.price ? [row.price] : []),
    imageUrl: row.images?.[0] ?? null,
    url: row.url,
    listedAt: row.created_at,
    isFacebookExclusive: row.is_facebook_exclusive,
  };
}
