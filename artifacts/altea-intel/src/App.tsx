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
  Activity
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line } from "recharts";

import { mockProperties, zonePriceData, marketKPIs, Property } from "@/data/mockData";

const queryClient = new QueryClient();

type Section = "dashboard" | "oportunidades" | "analisis" | "leads" | "configuracion";

function AppLayout() {
  const [currentSection, setCurrentSection] = useState<Section>("dashboard");
  const [zoneFilter, setZoneFilter] = useState<string>("All");

  const filteredProperties = useMemo(() => {
    if (zoneFilter === "All") return mockProperties;
    return mockProperties.filter(p => p.zone === zoneFilter);
  }, [zoneFilter]);

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "oportunidades", label: "Oportunidades", icon: Flame },
    { id: "analisis", label: "Análisis por Zona", icon: BarChart2 },
    { id: "leads", label: "Leads Facebook", icon: Users },
    { id: "configuracion", label: "Configuración", icon: Settings },
  ] as const;

  const zones = ["All", "Altea Hills", "Casco Antiguo", "Mascarat/Campomanes", "Altea la Vella", "Playa/Centro"];

  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-sidebar flex flex-col justify-between">
        <div>
          <div className="h-16 flex items-center px-6 border-b border-border">
            <Gem className="h-5 w-5 text-primary mr-2" />
            <h1 className="font-display font-bold tracking-widest text-lg text-foreground">ALTEA INTEL</h1>
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
              </button>
            ))}
          </nav>
        </div>
        <div className="p-6 border-t border-border">
          <div className="bg-white/5 border border-white/10 rounded-md p-3 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Tracking activo</span>
            <div className="flex items-center">
              <span className="h-2 w-2 rounded-full bg-emerald-500 mr-2 animate-pulse"></span>
              <span className="text-xs font-bold">{marketKPIs.totalTracked} prop.</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-background/50">
        <div className="p-8 max-w-7xl mx-auto space-y-8">
          
          {currentSection === "dashboard" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">Dashboard Market Intel</h2>
                <p className="text-muted-foreground mt-1">Resumen de indicadores clave para Altea.</p>
              </header>

              {/* KPIs */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-precio">
                  <p className="text-sm font-medium text-muted-foreground">Precio Medio m²</p>
                  <div className="mt-2 flex items-baseline space-x-2">
                    <p className="text-3xl font-display font-semibold">€{marketKPIs.avgPricePerSqm.toLocaleString()}</p>
                    <span className="text-sm text-emerald-500 flex items-center font-medium">
                      <ArrowUpRight className="h-4 w-4 mr-1" />
                      {marketKPIs.avgPricePerSqmTrend}%
                    </span>
                  </div>
                </div>
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-nuevas">
                  <p className="text-sm font-medium text-muted-foreground">Nuevas Propiedades (24h)</p>
                  <div className="mt-2 flex items-baseline space-x-2">
                    <p className="text-3xl font-display font-semibold">{marketKPIs.newPropertiesLast24h}</p>
                    <Activity className="h-5 w-5 text-primary animate-pulse" />
                  </div>
                </div>
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-oportunidad">
                  <p className="text-sm font-medium text-muted-foreground">Mejor Oportunidad</p>
                  <div className="mt-2 flex items-baseline justify-between">
                    <p className="text-3xl font-display font-semibold text-primary">{marketKPIs.bestOpportunityScore}</p>
                    <span className="text-sm text-muted-foreground truncate max-w-[120px]">{marketKPIs.bestOpportunityTitle}</span>
                  </div>
                </div>
                <div className="glassmorphism rounded-xl p-5" data-testid="kpi-tracking">
                  <p className="text-sm font-medium text-muted-foreground">Total en Tracking</p>
                  <div className="mt-2 flex items-baseline">
                    <p className="text-3xl font-display font-semibold">{marketKPIs.totalTracked}</p>
                    <span className="ml-2 text-sm text-muted-foreground">propiedades</span>
                  </div>
                </div>
              </div>

              {/* Chart & Table Row */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2 glassmorphism rounded-xl p-6">
                  <h3 className="font-display text-lg font-semibold mb-6">Comparativa Precio m² por Zona</h3>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={zonePriceData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                        <XAxis dataKey="zone" stroke="#888" fontSize={12} tickLine={false} axisLine={false} />
                        <YAxis stroke="#888" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `€${val}`} />
                        <Tooltip 
                          cursor={{ fill: 'rgba(255,255,255,0.05)' }} 
                          contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '8px' }}
                          itemStyle={{ color: '#f59e0b' }}
                        />
                        <Bar dataKey="avgPricePerSqm" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="glassmorphism rounded-xl p-6 overflow-hidden flex flex-col">
                  <h3 className="font-display text-lg font-semibold mb-6">Top Oportunidades</h3>
                  <div className="space-y-4 overflow-y-auto pr-2 flex-1">
                    {mockProperties.filter(p => p.opportunityScore >= 80).slice(0, 4).map(p => (
                      <div key={p.id} className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors cursor-pointer border border-transparent hover:border-white/10" data-testid={`top-opp-${p.id}`}>
                        <div>
                          <p className="font-medium text-sm truncate max-w-[140px]">{p.title}</p>
                          <p className="text-xs text-muted-foreground">{p.zone}</p>
                        </div>
                        <div className="flex flex-col items-end">
                          <span className={`text-xs font-bold px-2 py-1 rounded-full ${p.opportunityScore >= 80 ? 'bg-primary/20 text-primary' : 'bg-white/10 text-white'}`}>
                            {p.opportunityScore}
                          </span>
                          <span className="text-xs text-emerald-500 mt-1">{p.deviationVsAvg}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              
              {/* Detailed Table */}
              <div className="glassmorphism rounded-xl p-6 overflow-hidden">
                <h3 className="font-display text-lg font-semibold mb-6">Últimas Actualizaciones</h3>
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
                      {mockProperties.slice(0, 5).map(p => {
                        const isDeclining = p.priceHistory[0] > p.priceHistory[p.priceHistory.length - 1];
                        return (
                          <tr key={p.id} className="hover:bg-white/5 transition-colors">
                            <td className="py-4 font-medium max-w-[200px] truncate pr-4">{p.title}</td>
                            <td className="py-4 text-muted-foreground">{p.zone}</td>
                            <td className="py-4 font-display">€{p.price.toLocaleString()}</td>
                            <td className="py-4">
                              <span className={`inline-flex items-center ${p.deviationVsAvg < 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                {p.deviationVsAvg < 0 ? <ArrowDownRight className="h-3 w-3 mr-1" /> : <ArrowUpRight className="h-3 w-3 mr-1" />}
                                {Math.abs(p.deviationVsAvg)}%
                              </span>
                            </td>
                            <td className="py-4">
                              <div className="h-[30px] w-[50px]">
                                <ResponsiveContainer width="100%" height="100%">
                                  <LineChart data={p.priceHistory.map((val, i) => ({ val, i }))}>
                                    <Line 
                                      type="monotone" 
                                      dataKey="val" 
                                      stroke={isDeclining ? '#10b981' : '#ef4444'} 
                                      strokeWidth={2} 
                                      dot={false} 
                                      isAnimationActive={false}
                                    />
                                  </LineChart>
                                </ResponsiveContainer>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {currentSection === "oportunidades" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                  <h2 className="font-display text-3xl font-bold text-foreground">Oportunidades de Inversión</h2>
                  <p className="text-muted-foreground mt-1">Explora propiedades con desviación de mercado positiva.</p>
                </div>
                
                {/* Zone Filter Bar */}
                <div className="flex flex-wrap gap-2">
                  {zones.map(zone => (
                    <button
                      key={zone}
                      data-testid={`filter-${zone.replace(/\s+/g, '-').toLowerCase()}`}
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

              {/* Property Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {filteredProperties.map(property => {
                  let scoreColor = "text-red-500 border-red-500/30";
                  if (property.opportunityScore >= 80) scoreColor = "text-emerald-400 border-emerald-500/30 pulse-glow";
                  else if (property.opportunityScore >= 60) scoreColor = "text-primary border-primary/30";

                  return (
                    <div key={property.id} data-testid={`card-${property.id}`} className="glassmorphism rounded-xl overflow-hidden group hover:-translate-y-1 transition-all duration-300">
                      <div className="relative h-48 w-full overflow-hidden">
                        <img 
                          src={property.imageUrl} 
                          alt={property.title} 
                          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                        />
                        <div className="absolute top-3 left-3 flex gap-2">
                          <span className="px-2 py-1 text-xs font-semibold bg-black/60 backdrop-blur-md rounded border border-white/10 text-white">
                            {property.zone}
                          </span>
                          <span className={`px-2 py-1 text-xs font-semibold rounded border border-white/10 text-white backdrop-blur-md ${property.source === 'Idealista' ? 'bg-blue-600/60' : 'bg-indigo-600/60'}`}>
                            {property.source}
                          </span>
                        </div>
                        <div className="absolute -bottom-6 right-4">
                          <div className={`h-14 w-14 rounded-full bg-card border-2 flex items-center justify-center shadow-lg ${scoreColor}`}>
                            <span className="font-display font-bold text-lg">{property.opportunityScore}</span>
                          </div>
                        </div>
                      </div>
                      
                      <div className="p-5 pt-6 space-y-4">
                        <div>
                          <h3 className="font-display font-semibold text-lg line-clamp-1 group-hover:text-primary transition-colors">{property.title}</h3>
                          <div className="flex items-center text-xs text-muted-foreground mt-1 space-x-3">
                            <span>{property.bedrooms} hab</span>
                            <span>•</span>
                            <span>{property.bathrooms} ba</span>
                            <span>•</span>
                            <span>{property.sqm} m²</span>
                          </div>
                        </div>
                        
                        <div className="flex items-end justify-between border-t border-border pt-4">
                          <div>
                            <p className="font-display text-2xl font-bold">€{property.price.toLocaleString()}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">€{property.pricePerSqm.toLocaleString()} / m²</p>
                          </div>
                          
                          <div className="text-right">
                            {property.deviationVsAvg < 0 ? (
                              <p className="text-sm font-medium text-emerald-400 flex items-center justify-end">
                                {property.deviationVsAvg}% vs media
                              </p>
                            ) : (
                              <p className="text-sm font-medium text-red-400 flex items-center justify-end">
                                +{property.deviationVsAvg}% vs media
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {currentSection === "analisis" && (
            <div className="space-y-6 animate-in fade-in duration-500">
              <header>
                <h2 className="font-display text-3xl font-bold text-foreground">Análisis por Zona</h2>
                <p className="text-muted-foreground mt-1">Desglose comparativo de precios y volumen de mercado.</p>
              </header>
              
              <div className="glassmorphism rounded-xl p-8">
                  <h3 className="font-display text-xl font-semibold mb-8">Precio Medio m² (Macro)</h3>
                  <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={zonePriceData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                        <XAxis dataKey="zone" stroke="#888" fontSize={13} tickLine={false} axisLine={false} dy={10} />
                        <YAxis stroke="#888" fontSize={13} tickLine={false} axisLine={false} tickFormatter={(val) => `€${val}`} dx={-10} />
                        <Tooltip 
                          cursor={{ fill: 'rgba(255,255,255,0.02)' }} 
                          contentStyle={{ backgroundColor: '#111', border: '1px solid #333', borderRadius: '8px' }}
                          itemStyle={{ color: '#f59e0b' }}
                        />
                        <Bar dataKey="avgPricePerSqm" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} maxBarSize={60} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
              </div>
            </div>
          )}

          {currentSection === "leads" && (
            <div className="flex flex-col items-center justify-center h-[60vh] space-y-4 animate-in fade-in duration-500">
              <div className="h-20 w-20 rounded-full bg-indigo-500/10 flex items-center justify-center text-indigo-400 mb-4">
                <Users className="h-10 w-10" />
              </div>
              <h2 className="font-display text-2xl font-bold">Integración de Leads Facebook</h2>
              <p className="text-muted-foreground max-w-md text-center">
                Conecta tus campañas de Facebook Ads para recibir y clasificar leads de alto valor directamente en este panel.
              </p>
              <div className="mt-8 px-4 py-2 border border-border rounded-full bg-white/5 text-sm text-muted-foreground flex items-center">
                <span className="h-2 w-2 rounded-full bg-primary animate-pulse mr-2"></span>
                Funcionalidad próximamente disponible
              </div>
            </div>
          )}

          {currentSection === "configuracion" && (
            <div className="flex flex-col items-center justify-center h-[60vh] space-y-4 animate-in fade-in duration-500">
              <div className="h-20 w-20 rounded-full bg-white/5 flex items-center justify-center text-muted-foreground mb-4">
                <Settings className="h-10 w-10" />
              </div>
              <h2 className="font-display text-2xl font-bold">Configuración</h2>
              <p className="text-muted-foreground text-center">Ajustes de alertas, umbrales de oportunidad y fuentes de datos.</p>
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
