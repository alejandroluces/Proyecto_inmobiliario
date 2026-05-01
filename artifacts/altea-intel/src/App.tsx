import { useState, useMemo } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  LayoutDashboard,
  Flame,
  BarChart2,
  Users,
  Settings,
  Gem,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Wifi,
  WifiOff,
  ExternalLink,
  AlertTriangle,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  LineChart,
  Line,
} from "recharts";

import { useProperties } from "@/hooks/useProperties";
import type { Property } from "@/lib/database.types";

const queryClient = new QueryClient();

type Section =
  | "dashboard"
  | "oportunidades"
  | "analisis"
  | "leads"
  | "configuracion";

// ─── Score colour helper ──────────────────────────────────────
function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400 border-emerald-500/30 pulse-glow";
  if (score >= 60) return "text-primary border-primary/30";
  return "text-red-500 border-red-500/30";
}

// ─── Source badge colour ──────────────────────────────────────
function sourceBadgeClass(source: string): string {
  if (source === "Idealista") return "bg-blue-600/60";
  if (source === "Fotocasa") return "bg-purple-600/60";
  return "bg-indigo-600/60"; // Facebook
}

function investmentTagLabel(tag: string): string {
  const labels: Record<string, string> = {
    deep_discount: "Descuento fuerte",
    below_market: "Bajo mercado",
    direct_lead: "Contacto directo",
    price_drop: "Bajada precio",
    needs_zone_review: "Revisar zona",
    needs_manual_review: "Revisar datos",
  };
  return labels[tag] ?? tag.replaceAll("_", " ");
}

// ─── Loading skeleton ─────────────────────────────────────────
function CardSkeleton() {
  return (
    <div className="glassmorphism rounded-xl overflow-hidden animate-pulse">
      <div className="h-48 bg-white/5" />
      <div className="p-5 space-y-3">
        <div className="h-4 bg-white/10 rounded w-3/4" />
        <div className="h-3 bg-white/5 rounded w-1/2" />
        <div className="h-8 bg-white/10 rounded w-1/3 mt-4" />
      </div>
    </div>
  );
}

// ─── Connection status badge ──────────────────────────────────
function ConnectionBadge({ isLive, error }: { isLive: boolean; error: string | null }) {
  if (!isLive) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
        <WifiOff className="h-3 w-3" />
        <span>Modo demo</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
        <AlertTriangle className="h-3 w-3" />
        <span>Error de conexión</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
      <Wifi className="h-3 w-3" />
      <span>En vivo · Supabase</span>
    </div>
  );
}

// ─── Property card ────────────────────────────────────────────
function PropertyCard({ property }: { property: Property }) {
  const color = scoreColor(property.opportunityScore);
  const imgSrc =
    property.imageUrl ||
    "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=800&q=80";

  return (
    <div
      data-testid={`card-${property.id}`}
      className="glassmorphism rounded-xl overflow-hidden group hover:-translate-y-1 transition-all duration-300"
    >
      <div className="relative h-48 w-full overflow-hidden">
        <img
          src={imgSrc}
          alt={property.title}
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          onError={(e) => {
            (e.target as HTMLImageElement).src =
              "https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=800&q=80";
          }}
        />
        <div className="absolute top-3 left-3 flex gap-2 flex-wrap">
          {property.zone && (
            <span className="px-2 py-1 text-xs font-semibold bg-black/60 backdrop-blur-md rounded border border-white/10 text-white">
              {property.zone}
            </span>
          )}
          <span
            className={`px-2 py-1 text-xs font-semibold rounded border border-white/10 text-white backdrop-blur-md ${sourceBadgeClass(property.source)}`}
          >
            {property.source}
          </span>
          {property.isFacebookExclusive && (
            <span className="px-2 py-1 text-xs font-bold rounded border border-amber-500/40 text-amber-300 bg-amber-500/20 backdrop-blur-md">
              🔥 Trato directo
            </span>
          )}
        </div>
        <div className="absolute -bottom-6 right-4">
          <div
            className={`h-14 w-14 rounded-full bg-card border-2 flex items-center justify-center shadow-lg ${color}`}
          >
            <span className="font-display font-bold text-lg">
              {property.opportunityScore}
            </span>
          </div>
        </div>
      </div>

      <div className="p-5 pt-6 space-y-4">
        <div>
          <h3 className="font-display font-semibold text-lg line-clamp-1 group-hover:text-primary transition-colors">
            {property.title}
          </h3>
          <div className="flex items-center text-xs text-muted-foreground mt-1 space-x-3">
            {property.sqm && <span>{property.sqm} m²</span>}
            {property.url && (
              <>
                <span>•</span>
                <a
                  href={property.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 hover:text-primary transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  Ver anuncio <ExternalLink className="h-3 w-3" />
                </a>
              </>
            )}
          </div>
          {property.opportunityReason && (
            <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
              {property.opportunityReason}
            </p>
          )}
          {property.investmentTags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {property.investmentTags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded border border-white/10 bg-white/5 text-[11px] text-muted-foreground"
                >
                  {investmentTagLabel(tag)}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end justify-between border-t border-border pt-4">
          <div>
            {property.price !== null ? (
              <>
                <p className="font-display text-2xl font-bold">
                  €{property.price.toLocaleString("es-ES")}
                </p>
                {property.pricePerSqm && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    €{Math.round(property.pricePerSqm).toLocaleString("es-ES")} / m²
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground italic">Precio a consultar</p>
            )}
          </div>

          <div className="text-right">
            {property.deviationVsAvg !== null && (
              <p
                className={`text-sm font-medium flex items-center justify-end ${
                  property.deviationVsAvg < 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {property.deviationVsAvg < 0 ? "" : "+"}
                {property.deviationVsAvg.toFixed(1)}% vs media
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main layout ──────────────────────────────────────────────
function AppLayout() {
  const [currentSection, setCurrentSection] = useState<Section>("dashboard");
  const [zoneFilter, setZoneFilter] = useState<string>("All");

  const { properties, zoneData, kpis, loading, error, isLive } = useProperties();

  const zones = [
    "All",
    "Altea Hills",
    "Casco Antiguo",
    "Mascarat/Campomanes",
    "Altea la Vella",
    "Playa/Centro",
  ];

  const filteredProperties = useMemo(() => {
    if (zoneFilter === "All") return properties;
    return properties.filter((p) => p.zone === zoneFilter);
  }, [properties, zoneFilter]);

  const facebookLeads = useMemo(
    () => properties.filter((p) => p.source === "Facebook"),
    [properties]
  );

  const facebookExclusives = useMemo(
    () => properties.filter((p) => p.isFacebookExclusive),
    [properties]
  );

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "oportunidades", label: "Oportunidades", icon: Flame },
    { id: "analisis", label: "Análisis por Zona", icon: BarChart2 },
    { id: "leads", label: "Leads Facebook", icon: Users },
    { id: "configuracion", label: "Configuración", icon: Settings },
  ] as const;

  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-sidebar flex flex-col justify-between">
        <div>
          <div className="h-16 flex items-center px-6 border-b border-border">
            <Gem className="h-5 w-5 text-primary mr-2" />
            <h1 className="font-display font-bold tracking-widest text-lg text-foreground">
              ALTEA INTEL
            </h1>
          </div>
          <nav className="p-4 space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                data-testid={`nav-${item.id}`}
                onClick={() => setCurrentSection(item.id)}
                className={`w-full flex items-center space-x-3 px-4 py-3 rounded-md transition-colors ${
                  currentSection === item.id
                    ? "bg-primary/10 text-primary font-medium"
                    : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                }`}
              >
                <item.icon className="h-5 w-5" />
                <span>{item.label}</span>
                {item.id === "leads" && facebookExclusives.length > 0 && (
                  <span className="ml-auto text-xs bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded-full font-bold">
                    {facebookExclusives.length}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>
        <div className="p-6 border-t border-border space-y-3">
          <ConnectionBadge isLive={isLive} error={error} />
          <div className="bg-white/5 border border-white/10 rounded-md p-3 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Tracking activo</span>
            <div className="flex items-center">
              <span className="h-2 w-2 rounded-full bg-emerald-500 mr-2 animate-pulse" />
              <span className="text-xs font-bold">{kpis.totalTracked} prop.</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-background/50">
        <div className="p-8 max-w-7xl mx-auto space-y-8">

          {/* ── DASHBOARD ─────────────────────────────────────── */}
          {currentSection === "dashboard" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">
                  Dashboard Market Intel
                </h2>
                <p className="text-muted-foreground mt-1">
                  Resumen de indicadores clave para Altea.
                </p>
              </header>

              {/* KPIs */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-precio">
                  <p className="text-sm font-medium text-muted-foreground">
                    Precio Medio m²
                  </p>
                  <div className="mt-2 flex items-baseline space-x-2">
                    <p className="text-3xl font-display font-semibold">
                      €{kpis.avgPricePerSqm.toLocaleString("es-ES")}
                    </p>
                    <span className="text-sm text-emerald-500 flex items-center font-medium">
                      <ArrowUpRight className="h-4 w-4 mr-1" />
                      {kpis.avgPricePerSqmTrend}%
                    </span>
                  </div>
                </div>
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-nuevas">
                  <p className="text-sm font-medium text-muted-foreground">
                    Nuevas Propiedades (24h)
                  </p>
                  <div className="mt-2 flex items-baseline space-x-2">
                    <p className="text-3xl font-display font-semibold">
                      {kpis.newPropertiesLast24h}
                    </p>
                    <Activity className="h-5 w-5 text-primary animate-pulse" />
                  </div>
                </div>
                <div
                  className="glassmorphism rounded-xl p-5"
                  data-testid="kpi-oportunidad"
                >
                  <p className="text-sm font-medium text-muted-foreground">
                    Mejor Oportunidad
                  </p>
                  <div className="mt-2 flex items-baseline justify-between">
                    <p className="text-3xl font-display font-semibold text-primary">
                      {kpis.bestOpportunityScore}
                    </p>
                    <span className="text-sm text-muted-foreground truncate max-w-[120px]">
                      {kpis.bestOpportunityTitle}
                    </span>
                  </div>
                </div>
                <div
                  className="glassmorphism rounded-xl p-5"
                  data-testid="kpi-tracking"
                >
                  <p className="text-sm font-medium text-muted-foreground">
                    Total en Tracking
                  </p>
                  <div className="mt-2 flex items-baseline">
                    <p className="text-3xl font-display font-semibold">
                      {kpis.totalTracked}
                    </p>
                    <span className="ml-2 text-sm text-muted-foreground">
                      propiedades
                    </span>
                  </div>
                </div>
              </div>

              {/* Chart & Top Opportunities */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 glassmorphism rounded-xl p-6">
                  <h3 className="font-display text-lg font-semibold mb-6">
                    Comparativa Precio m² por Zona
                  </h3>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={zoneData}
                        margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="#333"
                          vertical={false}
                        />
                        <XAxis
                          dataKey="zone"
                          stroke="#888"
                          fontSize={12}
                          tickLine={false}
                          axisLine={false}
                        />
                        <YAxis
                          stroke="#888"
                          fontSize={12}
                          tickLine={false}
                          axisLine={false}
                          tickFormatter={(val) => `€${val}`}
                        />
                        <Tooltip
                          cursor={{ fill: "rgba(255,255,255,0.05)" }}
                          contentStyle={{
                            backgroundColor: "#111",
                            border: "1px solid #333",
                            borderRadius: "8px",
                          }}
                          itemStyle={{ color: "#f59e0b" }}
                        />
                        <Bar
                          dataKey="avgPricePerSqm"
                          fill="hsl(var(--primary))"
                          radius={[4, 4, 0, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glassmorphism rounded-xl p-6 overflow-hidden flex flex-col">
                  <h3 className="font-display text-lg font-semibold mb-6">
                    Top Oportunidades
                  </h3>
                  <div className="space-y-4 overflow-y-auto pr-2 flex-1">
                    {loading
                      ? Array.from({ length: 4 }).map((_, i) => (
                          <div
                            key={i}
                            className="h-14 bg-white/5 rounded-lg animate-pulse"
                          />
                        ))
                      : properties
                          .filter((p) => p.opportunityScore >= 80)
                          .slice(0, 4)
                          .map((p) => (
                            <div
                              key={p.id}
                              className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors cursor-pointer border border-transparent hover:border-white/10"
                              data-testid={`top-opp-${p.id}`}
                            >
                              <div>
                                <p className="font-medium text-sm truncate max-w-[140px]">
                                  {p.title}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {p.zone ?? "Zona desconocida"}
                                </p>
                              </div>
                              <div className="flex flex-col items-end">
                                <span className="text-xs font-bold px-2 py-1 rounded-full bg-primary/20 text-primary">
                                  {p.opportunityScore}
                                </span>
                                {p.deviationVsAvg !== null && (
                                  <span className="text-xs text-emerald-500 mt-1">
                                    {p.deviationVsAvg.toFixed(1)}%
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                  </div>
                </div>
              </div>

              {/* Detailed Table */}
              <div className="glassmorphism rounded-xl p-6 overflow-hidden">
                <h3 className="font-display text-lg font-semibold mb-6">
                  Últimas Actualizaciones
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-muted-foreground border-b border-border">
                      <tr>
                        <th className="pb-3 font-medium">Título</th>
                        <th className="pb-3 font-medium">Zona</th>
                        <th className="pb-3 font-medium">Precio</th>
                        <th className="pb-3 font-medium">Desviación vs Media</th>
                        <th className="pb-3 font-medium">Historial</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {loading
                        ? Array.from({ length: 5 }).map((_, i) => (
                            <tr key={i}>
                              <td colSpan={5} className="py-4">
                                <div className="h-4 bg-white/5 rounded animate-pulse" />
                              </td>
                            </tr>
                          ))
                        : properties.slice(0, 5).map((p) => {
                            const hist = p.priceHistory;
                            const isDeclining =
                              hist.length > 1 && hist[0] > hist[hist.length - 1];
                            return (
                              <tr
                                key={p.id}
                                className="hover:bg-white/5 transition-colors"
                              >
                                <td className="py-4 font-medium max-w-[200px] truncate pr-4">
                                  {p.title}
                                </td>
                                <td className="py-4 text-muted-foreground">
                                  {p.zone ?? "—"}
                                </td>
                                <td className="py-4 font-display">
                                  {p.price !== null
                                    ? `€${p.price.toLocaleString("es-ES")}`
                                    : "—"}
                                </td>
                                <td className="py-4">
                                  {p.deviationVsAvg !== null ? (
                                    <span
                                      className={`inline-flex items-center ${
                                        p.deviationVsAvg < 0
                                          ? "text-emerald-500"
                                          : "text-red-500"
                                      }`}
                                    >
                                      {p.deviationVsAvg < 0 ? (
                                        <ArrowDownRight className="h-3 w-3 mr-1" />
                                      ) : (
                                        <ArrowUpRight className="h-3 w-3 mr-1" />
                                      )}
                                      {Math.abs(p.deviationVsAvg).toFixed(1)}%
                                    </span>
                                  ) : (
                                    <span className="text-muted-foreground">—</span>
                                  )}
                                </td>
                                <td className="py-4">
                                  {hist.length > 1 ? (
                                    <div className="h-[30px] w-[50px]">
                                      <ResponsiveContainer width="100%" height="100%">
                                        <LineChart
                                          data={hist.map((val, i) => ({ val, i }))}
                                        >
                                          <Line
                                            type="monotone"
                                            dataKey="val"
                                            stroke={isDeclining ? "#10b981" : "#ef4444"}
                                            strokeWidth={2}
                                            dot={false}
                                            isAnimationActive={false}
                                          />
                                        </LineChart>
                                      </ResponsiveContainer>
                                    </div>
                                  ) : (
                                    <span className="text-muted-foreground text-xs">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── OPORTUNIDADES ──────────────────────────────────── */}
          {currentSection === "oportunidades" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                  <h2 className="font-display text-3xl font-bold text-foreground">
                    Oportunidades de Inversión
                  </h2>
                  <p className="text-muted-foreground mt-1">
                    Propiedades con desviación de mercado positiva.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {zones.map((zone) => (
                    <button
                      key={zone}
                      data-testid={`filter-${zone.replace(/\s+/g, "-").toLowerCase()}`}
                      onClick={() => setZoneFilter(zone)}
                      className={`px-4 py-1.5 text-sm rounded-full transition-colors border ${
                        zoneFilter === zone
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-transparent text-muted-foreground border-border hover:border-muted-foreground"
                      }`}
                    >
                      {zone}
                    </button>
                  ))}
                </div>
              </header>

              {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <CardSkeleton key={i} />
                  ))}
                </div>
              ) : filteredProperties.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] text-muted-foreground">
                  <p className="text-lg">No hay propiedades en esta zona.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                  {filteredProperties.map((property) => (
                    <PropertyCard key={property.id} property={property} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── ANÁLISIS POR ZONA ──────────────────────────────── */}
          {currentSection === "analisis" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">
                  Análisis por Zona
                </h2>
                <p className="text-muted-foreground mt-1">
                  Desglose comparativo de precios y volumen de mercado.
                </p>
              </header>

              <div className="glassmorphism rounded-xl p-8">
                <h3 className="font-display text-xl font-semibold mb-8">
                  Precio Medio m² (Macro)
                </h3>
                <div className="h-[400px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={zoneData}
                      margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#222"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="zone"
                        stroke="#888"
                        fontSize={13}
                        tickLine={false}
                        axisLine={false}
                        dy={10}
                      />
                      <YAxis
                        stroke="#888"
                        fontSize={13}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(val) => `€${val}`}
                        dx={-10}
                      />
                      <Tooltip
                        cursor={{ fill: "rgba(255,255,255,0.02)" }}
                        contentStyle={{
                          backgroundColor: "#111",
                          border: "1px solid #333",
                          borderRadius: "8px",
                        }}
                        itemStyle={{ color: "#f59e0b" }}
                      />
                      <Bar
                        dataKey="avgPricePerSqm"
                        fill="hsl(var(--primary))"
                        radius={[6, 6, 0, 0]}
                        maxBarSize={60}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Zone stats table */}
              <div className="glassmorphism rounded-xl p-6">
                <h3 className="font-display text-lg font-semibold mb-4">
                  Resumen por Zona
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-muted-foreground border-b border-border">
                      <tr>
                        <th className="pb-3 font-medium">Zona</th>
                        <th className="pb-3 font-medium">Precio medio m²</th>
                        <th className="pb-3 font-medium">Propiedades</th>
                        <th className="pb-3 font-medium">Chollos (score ≥80)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {zoneData.map((z) => {
                        const zoneProps = properties.filter((p) => p.zone === z.zone);
                        const chollos = zoneProps.filter(
                          (p) => p.opportunityScore >= 80
                        ).length;
                        return (
                          <tr key={z.zone} className="hover:bg-white/5 transition-colors">
                            <td className="py-3 font-medium">{z.zone}</td>
                            <td className="py-3 font-display">
                              €{z.avgPricePerSqm.toLocaleString("es-ES")}
                            </td>
                            <td className="py-3 text-muted-foreground">
                              {z.properties || zoneProps.length}
                            </td>
                            <td className="py-3">
                              {chollos > 0 ? (
                                <span className="text-emerald-400 font-bold">
                                  {chollos} 🔥
                                </span>
                              ) : (
                                <span className="text-muted-foreground">0</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ── LEADS FACEBOOK ─────────────────────────────────── */}
          {currentSection === "leads" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">
                  Leads Facebook
                </h2>
                <p className="text-muted-foreground mt-1">
                  Propiedades detectadas en grupos de Facebook. Las marcadas como
                  "Trato directo" no aparecen en Idealista ni Fotocasa.
                </p>
              </header>

              {facebookExclusives.length > 0 && (
                <div className="glassmorphism rounded-xl p-5 border border-amber-500/20 bg-amber-500/5">
                  <div className="flex items-center gap-3 mb-4">
                    <AlertTriangle className="h-5 w-5 text-amber-400" />
                    <h3 className="font-display font-semibold text-amber-300">
                      {facebookExclusives.length} Tratos Directos Detectados
                    </h3>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Estas propiedades aparecen únicamente en grupos de Facebook —
                    posible venta directa con el propietario sin intermediarios.
                  </p>
                </div>
              )}

              {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <CardSkeleton key={i} />
                  ))}
                </div>
              ) : facebookLeads.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-[40vh] space-y-4">
                  <div className="h-20 w-20 rounded-full bg-indigo-500/10 flex items-center justify-center text-indigo-400 mb-4">
                    <Users className="h-10 w-10" />
                  </div>
                  <h3 className="font-display text-xl font-bold">
                    Sin datos de Facebook aún
                  </h3>
                  <p className="text-muted-foreground max-w-md text-center">
                    Ejecuta el scraper de Facebook para ver propiedades de los grupos
                    de Altea Real Estate y Venta Altea.
                  </p>
                  <code className="mt-4 px-4 py-2 bg-white/5 border border-border rounded text-xs text-muted-foreground">
                    python main.py --source facebook
                  </code>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                  {facebookLeads.map((property) => (
                    <PropertyCard key={property.id} property={property} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── CONFIGURACIÓN ──────────────────────────────────── */}
          {currentSection === "configuracion" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">
                  Configuración
                </h2>
                <p className="text-muted-foreground mt-1">
                  Ajustes de conexión, alertas y umbrales de oportunidad.
                </p>
              </header>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Supabase status */}
                <div className="glassmorphism rounded-xl p-6 space-y-4">
                  <h3 className="font-display font-semibold text-lg">
                    Conexión Supabase
                  </h3>
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center justify-between py-2 border-b border-border">
                      <span className="text-muted-foreground">Estado</span>
                      <ConnectionBadge isLive={isLive} error={error} />
                    </div>
                    <div className="flex items-center justify-between py-2 border-b border-border">
                      <span className="text-muted-foreground">Propiedades en DB</span>
                      <span className="font-display font-semibold">
                        {kpis.totalTracked}
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-2">
                      <span className="text-muted-foreground">Realtime</span>
                      <span
                        className={isLive ? "text-emerald-400" : "text-muted-foreground"}
                      >
                        {isLive ? "Activo" : "Inactivo"}
                      </span>
                    </div>
                  </div>
                  {!isLive && (
                    <div className="mt-4 p-3 bg-white/5 rounded-lg text-xs text-muted-foreground space-y-1">
                      <p className="font-medium text-foreground">
                        Para activar Supabase:
                      </p>
                      <p>
                        1. Crea un archivo{" "}
                        <code className="bg-white/10 px-1 rounded">
                          artifacts/altea-intel/.env
                        </code>
                      </p>
                      <p>
                        2. Añade{" "}
                        <code className="bg-white/10 px-1 rounded">
                          VITE_SUPABASE_URL
                        </code>{" "}
                        y{" "}
                        <code className="bg-white/10 px-1 rounded">
                          VITE_SUPABASE_ANON_KEY
                        </code>
                      </p>
                      <p>3. Reinicia el servidor de desarrollo</p>
                    </div>
                  )}
                </div>

                {/* Scraper info */}
                <div className="glassmorphism rounded-xl p-6 space-y-4">
                  <h3 className="font-display font-semibold text-lg">
                    Scrapers Configurados
                  </h3>
                  <div className="space-y-3 text-sm">
                    {[
                      {
                        name: "Idealista",
                        url: "idealista.com/venta-viviendas/altea-alicante/",
                        color: "bg-blue-500",
                      },
                      {
                        name: "Fotocasa",
                        url: "fotocasa.es/es/comprar/viviendas/altea/",
                        color: "bg-purple-500",
                      },
                      {
                        name: "FB: Altea Real Estate",
                        url: "facebook.com/groups/806383410011342",
                        color: "bg-indigo-500",
                      },
                      {
                        name: "FB: Venta Altea",
                        url: "facebook.com/groups/358112831484535",
                        color: "bg-indigo-500",
                      },
                    ].map((s) => (
                      <div
                        key={s.name}
                        className="flex items-center gap-3 py-2 border-b border-border last:border-0"
                      >
                        <span
                          className={`h-2 w-2 rounded-full ${s.color} flex-shrink-0`}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium">{s.name}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {s.url}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 p-3 bg-white/5 rounded-lg text-xs text-muted-foreground">
                    <p className="font-medium text-foreground mb-1">
                      Ejecutar scrapers:
                    </p>
                    <code className="block">cd services/scrapers</code>
                    <code className="block">python main.py</code>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/" component={AppLayout} />
      <Route>
        <div className="flex items-center justify-center h-screen bg-background text-foreground">
          <p>404 - Not Found</p>
        </div>
      </Route>
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
