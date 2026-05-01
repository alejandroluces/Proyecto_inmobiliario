/**
 * useProperties.ts — Real-time Supabase hook for properties
 *
 * Behaviour:
 *  - If Supabase is configured: fetches live data from v_opportunities view
 *    and subscribes to Realtime INSERT/UPDATE/DELETE events on the properties table.
 *  - If Supabase is NOT configured: falls back to mockProperties so the UI
 *    still works during local development without credentials.
 */
import { useState, useEffect, useCallback } from "react";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import { mapDbPropertyToApp } from "@/lib/database.types";
import type { Property } from "@/lib/database.types";
import type { DbOpportunity, DbZoneAverage } from "@/lib/database.types";
import { mockProperties, zonePriceData, marketKPIs } from "@/data/mockData";

// ─── Zone price data shape ────────────────────────────────────
export interface ZonePricePoint {
  zone: string;
  avgPricePerSqm: number;
  properties: number;
}

// ─── KPI shape ───────────────────────────────────────────────
export interface MarketKPIs {
  avgPricePerSqm: number;
  avgPricePerSqmTrend: number;
  newPropertiesLast24h: number;
  bestOpportunityScore: number;
  bestOpportunityTitle: string;
  totalTracked: number;
}

// ─── Hook return type ─────────────────────────────────────────
export interface UsePropertiesResult {
  properties: Property[];
  zoneData: ZonePricePoint[];
  kpis: MarketKPIs;
  loading: boolean;
  error: string | null;
  isLive: boolean;  // true when connected to Supabase
}

// ─── Helpers ─────────────────────────────────────────────────

function computeKPIs(props: Property[], zoneData: ZonePricePoint[]): MarketKPIs {
  const priced = props.filter((p) => p.price !== null && p.sqm !== null && p.sqm > 0);
  const avgPricePerSqm =
    priced.length > 0
      ? Math.round(
          priced.reduce((sum, p) => sum + (p.pricePerSqm ?? 0), 0) / priced.length
        )
      : 0;

  const now = new Date();
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const newLast24h = props.filter(
    (p) => new Date(p.listedAt) >= yesterday
  ).length;

  const best = props.reduce(
    (top, p) => (p.opportunityScore > top.opportunityScore ? p : top),
    props[0] ?? { opportunityScore: 0, title: "—" }
  );

  return {
    avgPricePerSqm,
    avgPricePerSqmTrend: 3.2, // TODO: calculate from price_history trend
    newPropertiesLast24h: newLast24h,
    bestOpportunityScore: best?.opportunityScore ?? 0,
    bestOpportunityTitle: best?.title?.split(" ").slice(0, 3).join(" ") ?? "—",
    totalTracked: props.length,
  };
}

function buildZoneData(zoneAverages: DbZoneAverage[]): ZonePricePoint[] {
  return zoneAverages
    .filter((z) => z.avg_price_per_m2 !== null)
    .map((z) => ({
      zone: z.zone,
      avgPricePerSqm: Math.round(z.avg_price_per_m2!),
      properties: z.property_count,
    }));
}

// ─── Main hook ───────────────────────────────────────────────

export function useProperties(): UsePropertiesResult {
  const [properties, setProperties] = useState<Property[]>([]);
  const [zoneData, setZoneData] = useState<ZonePricePoint[]>(zonePriceData);
  const [kpis, setKpis] = useState<MarketKPIs>(marketKPIs);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Fallback to mock data when Supabase is not configured ──
  useEffect(() => {
    if (!isSupabaseConfigured) {
      setProperties(
        mockProperties.map((p) => ({
          id: p.id,
          title: p.title,
          zone: p.zone,
          price: p.price,
          sqm: p.sqm,
          pricePerSqm: p.pricePerSqm,
          source: p.source as Property["source"],
          opportunityScore: p.opportunityScore,
          deviationVsAvg: p.deviationVsAvg,
          investmentTags: [],
          opportunityReason: p.deviationVsAvg < 0
            ? `${Math.abs(p.deviationVsAvg).toFixed(1)}% por debajo de la media de zona`
            : "Dato demo sin razon de oportunidad",
          description: p.description,
          priceHistory: p.priceHistory,
          imageUrl: p.imageUrl,
          url: null,
          listedAt: p.listedAt,
          isFacebookExclusive: p.source === "Facebook",
        }))
      );
      setZoneData(zonePriceData);
      setKpis(marketKPIs);
      setLoading(false);
    }
  }, []);

  // ── Fetch from Supabase ────────────────────────────────────
  const fetchData = useCallback(async () => {
    if (!supabase) return;

    try {
      setLoading(true);
      setError(null);

      // Fetch properties from the v_opportunities view (ordered by score desc)
      const { data: propRows, error: propErr } = await supabase
        .from("v_opportunities")
        .select("*")
        .order("opportunity_score", { ascending: false })
        .limit(200);

      if (propErr) throw propErr;

      const mapped = (propRows as DbOpportunity[]).map(mapDbPropertyToApp);
      setProperties(mapped);

      // Fetch zone averages
      const { data: zoneRows, error: zoneErr } = await supabase
        .from("zone_averages")
        .select("*")
        .order("zone");

      if (zoneErr) throw zoneErr;

      const zd = buildZoneData(zoneRows as DbZoneAverage[]);
      if (zd.length > 0) setZoneData(zd);

      setKpis(computeKPIs(mapped, zd.length > 0 ? zd : zonePriceData));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[useProperties] fetch error:", msg);
      setError(msg);
      // Keep showing mock data on error
      if (properties.length === 0) {
        setProperties(
          mockProperties.map((p) => ({
            id: p.id,
            title: p.title,
            zone: p.zone,
            price: p.price,
            sqm: p.sqm,
            pricePerSqm: p.pricePerSqm,
            source: p.source as Property["source"],
            opportunityScore: p.opportunityScore,
            deviationVsAvg: p.deviationVsAvg,
            investmentTags: [],
            opportunityReason: p.deviationVsAvg < 0
              ? `${Math.abs(p.deviationVsAvg).toFixed(1)}% por debajo de la media de zona`
              : "Dato demo sin razon de oportunidad",
            description: p.description,
            priceHistory: p.priceHistory,
            imageUrl: p.imageUrl,
            url: null,
            listedAt: p.listedAt,
            isFacebookExclusive: p.source === "Facebook",
          }))
        );
      }
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Initial fetch ──────────────────────────────────────────
  useEffect(() => {
    if (!isSupabaseConfigured) return;
    fetchData();
  }, [fetchData]);

  // ── Realtime subscription ──────────────────────────────────
  useEffect(() => {
    if (!supabase) return;
    const client = supabase;

    const channel = client
      .channel("properties-realtime")
      .on(
        "postgres_changes",
        {
          event: "*",           // INSERT, UPDATE, DELETE
          schema: "public",
          table: "properties",
        },
        (payload) => {
          console.log("[Realtime] properties change:", payload.eventType);
          // Re-fetch the full view to get computed fields (price_per_m2, etc.)
          fetchData();
        }
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") {
          console.log("[Realtime] Subscribed to properties table ✓");
        }
      });

    return () => {
      client.removeChannel(channel);
    };
  }, [fetchData]);

  return {
    properties,
    zoneData,
    kpis,
    loading,
    error,
    isLive: isSupabaseConfigured,
  };
}
