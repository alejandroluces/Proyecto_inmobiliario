-- ============================================================
-- ALTEA INTEL — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- ─── Extensions ─────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ─── Enums ──────────────────────────────────────────────────
do $$ begin
  create type property_source as enum (
    'Idealista',
    'Fotocasa',
    'Facebook'
  );
exception
  when duplicate_object then null;
end $$;

-- ─── Table: properties ──────────────────────────────────────
create table if not exists public.properties (
  id                uuid primary key default uuid_generate_v4(),
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  -- Source tracking
  source            property_source not null,
  external_id       text not null,                    -- ID from the source portal
  url               text,

  -- Core listing data
  title             text not null,
  description       text,
  price             numeric(12, 2),                   -- NULL when "Precio a consultar"
  m2                numeric(8, 2),
  price_per_m2      numeric(10, 2) generated always as (
                      case when m2 > 0 then price / m2 else null end
                    ) stored,

  -- Location
  zone              text,                             -- e.g. "Altea Hills", "Casco Antiguo"

  -- Media
  images            text[] default '{}',

  -- Intelligence
  opportunity_score integer default 0 check (opportunity_score between 0 and 100),
  deviation_vs_avg  numeric(6, 2),                   -- % deviation from zone average
  investment_tags    text[] default '{}',             -- explainable signals: below_market, direct_lead, etc.
  opportunity_reason text,                            -- human-readable reason for the score

  -- Facebook-specific flag
  is_facebook_exclusive boolean default false,        -- true when not found in Idealista/Fotocasa

  -- Unique constraint per source
  constraint uq_source_external unique (source, external_id)
);

-- Safe upgrades for existing databases created before the investment fields.
alter table public.properties
  add column if not exists investment_tags text[] default '{}';

alter table public.properties
  add column if not exists opportunity_reason text;

-- ─── Table: price_history ───────────────────────────────────
create table if not exists public.price_history (
  id          uuid primary key default uuid_generate_v4(),
  property_id uuid not null references public.properties(id) on delete cascade,
  price       numeric(12, 2) not null,
  recorded_at timestamptz not null default now()
);

create index if not exists idx_price_history_property_id
  on public.price_history(property_id);

create index if not exists idx_price_history_recorded_at
  on public.price_history(recorded_at desc);

-- ─── Table: zone_averages ───────────────────────────────────
-- Cached zone statistics updated by the scraper after each run
create table if not exists public.zone_averages (
  id              uuid primary key default uuid_generate_v4(),
  zone            text not null unique,
  avg_price_per_m2 numeric(10, 2),
  property_count  integer default 0,
  updated_at      timestamptz not null default now()
);

-- Seed with known Altea zone averages (will be updated by scraper)
insert into public.zone_averages (zone, avg_price_per_m2, property_count)
values
  ('Altea Hills',          2750, 0),
  ('Casco Antiguo',        2820, 0),
  ('Mascarat/Campomanes',  3100, 0),
  ('Altea la Vella',       1480, 0),
  ('Playa/Centro',         2780, 0)
on conflict (zone) do nothing;

-- ─── Table: scraper_runs ────────────────────────────────────
-- Audit log for each scraper execution
create table if not exists public.scraper_runs (
  id              uuid primary key default uuid_generate_v4(),
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  source          property_source not null,
  properties_found    integer default 0,
  properties_new      integer default 0,
  properties_updated  integer default 0,
  errors          text[] default '{}',
  status          text default 'running'   -- 'running' | 'success' | 'error'
);

-- ─── Trigger: auto-update updated_at ────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_properties_updated_at on public.properties;
create trigger trg_properties_updated_at
  before update on public.properties
  for each row execute function public.set_updated_at();

-- ─── Trigger: auto-insert price_history on price change ─────
create or replace function public.record_price_change()
returns trigger language plpgsql as $$
begin
  -- Only record when price actually changes (or on first insert)
  if (TG_OP = 'INSERT' and new.price is not null) or
     (TG_OP = 'UPDATE' and new.price is distinct from old.price and new.price is not null) then
    insert into public.price_history(property_id, price)
    values (new.id, new.price);
  end if;
  return new;
end;
$$;

drop trigger if exists trg_record_price_change on public.properties;
create trigger trg_record_price_change
  after insert or update on public.properties
  for each row execute function public.record_price_change();

-- ─── Row Level Security ──────────────────────────────────────
-- Enable RLS (adjust policies to your auth setup)
alter table public.properties    enable row level security;
alter table public.price_history enable row level security;
alter table public.zone_averages enable row level security;
alter table public.scraper_runs  enable row level security;

-- Public read access (dashboard is read-only for anonymous users)
create policy "Public read properties"
  on public.properties for select using (true);

create policy "Public read price_history"
  on public.price_history for select using (true);

create policy "Public read zone_averages"
  on public.zone_averages for select using (true);

-- Service role has full access (used by the Python scraper via service key)
-- No additional policy needed — service_role bypasses RLS by default.

-- ─── Realtime ───────────────────────────────────────────────
-- Enable Realtime on properties so the React dashboard auto-updates
-- Go to: Supabase Dashboard → Database → Replication → Tables
-- and toggle ON the "properties" table.
--
-- Or run the following (requires superuser / Supabase support):
-- alter publication supabase_realtime add table public.properties;

-- ─── Useful Views ───────────────────────────────────────────
-- Drop first so existing databases can add/reorder view columns safely.
drop view if exists public.v_opportunities;

create or replace view public.v_opportunities as
select
  p.id,
  p.created_at,
  p.source,
  p.title,
  p.price,
  p.m2,
  p.price_per_m2,
  p.zone,
  p.url,
  p.images,
  p.opportunity_score,
  p.deviation_vs_avg,
  p.investment_tags,
  p.opportunity_reason,
  p.is_facebook_exclusive,
  za.avg_price_per_m2 as zone_avg_price_per_m2,
  (
    select ph.price
    from public.price_history ph
    where ph.property_id = p.id
    order by ph.recorded_at asc
    limit 1
  ) as initial_price,
  (
    select array_agg(ph.price order by ph.recorded_at asc)
    from public.price_history ph
    where ph.property_id = p.id
  ) as price_history
from public.properties p
left join public.zone_averages za on za.zone = p.zone
where p.price is not null
order by p.opportunity_score desc;
