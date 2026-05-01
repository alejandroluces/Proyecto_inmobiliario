# 🏡 ALTEA INTEL — Guía Completa de Uso

Sistema de inteligencia inmobiliaria para el mercado de Altea (Alicante).
Scraping automático de Idealista, Fotocasa y grupos de Facebook → análisis de oportunidades → dashboard en tiempo real.

---

## 📋 Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Configuración inicial (una sola vez)](#2-configuración-inicial-una-sola-vez)
3. [Configurar Supabase](#3-configurar-supabase)
4. [Llenar la base de datos](#4-llenar-la-base-de-datos)
5. [Ver el dashboard](#5-ver-el-dashboard)
6. [Referencia de comandos](#6-referencia-de-comandos)
7. [Solución de problemas](#7-solución-de-problemas)

---

## 1. Requisitos previos

| Herramienta | Versión mínima | Instalación |
|-------------|---------------|-------------|
| Python | 3.11+ | https://python.org |
| Node.js | 18+ | https://nodejs.org |
| pnpm | 8+ | `npm install -g pnpm` |
| Google Chrome | cualquiera | https://google.com/chrome |

---

## 2. Configuración inicial (una sola vez)

### 2.1 Instalar dependencias Python

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"
pip install -r requirements.txt
playwright install chromium
```

### 2.2 Instalar dependencias del frontend

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\artifacts\altea-intel"
pnpm install
```

### 2.3 Configurar variables de entorno del scraper

Edita el archivo `services/scrapers/.env`:

```env
# ── Supabase ──────────────────────────────────────────────────
SUPABASE_URL=https://TU_PROYECTO.supabase.co
SUPABASE_SERVICE_KEY=tu_anon_key_aqui

# ── Telegram (opcional) ───────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

> 💡 La `SUPABASE_SERVICE_KEY` la encuentras en:
> Supabase Dashboard → Settings → API → **anon public** key

### 2.4 Configurar variables de entorno del frontend

Edita el archivo `artifacts/altea-intel/.env`:

```env
VITE_SUPABASE_URL=https://TU_PROYECTO.supabase.co
VITE_SUPABASE_ANON_KEY=tu_anon_key_aqui
```

---

## 3. Configurar Supabase

### 3.1 Crear las tablas (una sola vez)

1. Ve a → **Supabase Dashboard → SQL Editor → New Query**
2. Copia y pega el contenido de `services/database/schema.sql`
3. Haz clic en **Run** (o `Ctrl+Enter`)

### 3.2 Desactivar RLS para permitir escrituras ⚠️ OBLIGATORIO

Sin este paso, el scraper no puede subir datos (error 401).

1. Ve a → **Supabase Dashboard → SQL Editor → New Query**
2. Pega y ejecuta:

```sql
ALTER TABLE properties    DISABLE ROW LEVEL SECURITY;
ALTER TABLE price_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE scraper_runs  DISABLE ROW LEVEL SECURITY;
ALTER TABLE zone_averages DISABLE ROW LEVEL SECURITY;
```

3. Deberías ver: `Success. No rows returned`

> El archivo `services/database/rls_fix.sql` tiene este SQL listo para copiar.

### 3.3 Verificar que funciona

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"
python debug_parse.py
```

Deberías ver al final: `✅ Upsert OK — returned 1 rows`

---

## 4. Llenar la base de datos

### Opción A — Rápida: Solo Fotocasa (recomendado para empezar)

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"

# Paso 1: Descargar HTML de 5 páginas (~150 pisos, ~5-10 min)
python scraper_fotocasa.py --fetch --max-pages 5

# Paso 2: Parsear y subir a Supabase
python main.py --source fotocasa
```

### Opción B — Completa: Fotocasa + Idealista

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\services\scrapers"

# Descargar ambas fuentes
python scraper_fotocasa.py --fetch --max-pages 5
python scraper_idealista.py --fetch --max-pages 5

# Subir todo a Supabase
python main.py --no-facebook
```

### Opción C — Todo incluyendo Facebook

**Primero, hacer login en Facebook (una sola vez):**

```powershell
python scraper_facebook.py --login
```
→ Se abre Chrome → inicia sesión en Facebook → cierra el navegador → sesión guardada.

**Luego ejecutar todo:**

```powershell
python main.py
```

### Opción D — Re-parsear HTML ya descargado (sin navegador, instantáneo)

Si ya tienes HTML descargado y solo quieres re-parsear y subir:

```powershell
python scraper_fotocasa.py --parse
python scraper_idealista.py --parse
python main.py --no-facebook
```

---

## 5. Ver el dashboard

```powershell
cd "c:\Users\aleja\OneDrive\Desktop\Repositorios git\Intelligent-Asset-Tracker\artifacts\altea-intel"
pnpm dev
```

Abre en el navegador: **http://localhost:5173**

### Secciones del dashboard:

| Sección | Descripción |
|---------|-------------|
| 🏠 **Dashboard** | KPIs: precio medio m², nuevas propiedades 24h, mejor oportunidad, total tracking. Gráfico por zona. |
| 🔥 **Oportunidades** | Grid de tarjetas con foto, precio, m², score de oportunidad. Filtros por zona. |
| 📊 **Análisis por Zona** | Comparativa de precios m² por zona + tabla resumen con chollos detectados. |
| 👥 **Leads Facebook** | Propiedades de grupos FB. Las marcadas 🔥 "Trato directo" no están en Idealista/Fotocasa. |
| ⚙️ **Configuración** | Estado de conexión Supabase, scrapers configurados. |

---

## 6. Referencia de comandos

### Scrapers individuales

```powershell
# ── Fotocasa ──────────────────────────────────────────────────
python scraper_fotocasa.py --fetch --max-pages 3      # Descargar 3 páginas (~90 pisos)
python scraper_fotocasa.py --fetch --max-pages 5      # Descargar 5 páginas (~150 pisos)
python scraper_fotocasa.py --parse                    # Re-parsear HTML guardado
python scraper_fotocasa.py --fetch --parse            # Descargar + parsear
python scraper_fotocasa.py --login                    # Resolver CAPTCHA una vez

# ── Idealista ─────────────────────────────────────────────────
python scraper_idealista.py --fetch --max-pages 3
python scraper_idealista.py --fetch --max-pages 5
python scraper_idealista.py --parse
python scraper_idealista.py --fetch --parse
python scraper_idealista.py --login

# ── Facebook ──────────────────────────────────────────────────
python scraper_facebook.py --login                    # Login (una sola vez)
python scraper_facebook.py                            # Scrape grupos
```

### Orquestador principal (main.py)

```powershell
python main.py                          # Todo: Idealista + Fotocasa + Facebook
python main.py --no-facebook            # Solo Idealista + Fotocasa
python main.py --source fotocasa        # Solo Fotocasa
python main.py --source idealista       # Solo Idealista
python main.py --source facebook        # Solo Facebook
```

### Diagnóstico

```powershell
python debug_parse.py                   # Verifica parse + conexión Supabase
```

---

## 7. Solución de problemas

### ❌ Error: `42501 — row-level security policy`
**Causa:** RLS activo en Supabase.  
**Solución:** Ejecuta el SQL del paso 3.2 en el SQL Editor de Supabase.

### ❌ Error: `name 'random' is not defined`
**Causa:** Import faltante (ya corregido en la versión actual).  
**Solución:** Asegúrate de tener la versión más reciente del código.

### ❌ El scraper detecta CAPTCHA en páginas normales
**Causa:** Falso positivo en la detección.  
**Solución:** Ya corregido — la detección ahora verifica si hay listings reales antes de declarar bloqueo.

### ❌ Fotocasa devuelve propiedades con `price=None`
**Causa:** El HTML de las tarjetas no tenía el precio en el selector esperado.  
**Solución:** Ya corregido — ahora usa regex directo sobre el texto completo de la tarjeta.

### ❌ El dashboard muestra "Modo demo" (sin datos reales)
**Causa:** Las variables de entorno del frontend no están configuradas.  
**Solución:** Edita `artifacts/altea-intel/.env` con tu URL y anon key de Supabase.

### ❌ Chrome no se abre / error de Playwright
**Solución:**
```powershell
playwright install chromium
playwright install-deps chromium
```

### ⚠️ CAPTCHA frecuente en Idealista/Fotocasa
**Recomendación:** Usa `--max-pages 3` para sesiones cortas. Ejecuta el scraper en horarios de baja actividad (noche). La sesión persistente reduce los CAPTCHAs con el tiempo.

---

## 📁 Estructura del proyecto

```
Intelligent-Asset-Tracker/
├── artifacts/
│   └── altea-intel/              # Frontend React (dashboard)
│       ├── src/
│       │   ├── App.tsx           # UI principal (5 secciones)
│       │   ├── hooks/
│       │   │   └── useProperties.ts  # Hook Supabase Realtime
│       │   └── lib/
│       │       ├── supabase.ts   # Cliente Supabase
│       │       └── database.types.ts
│       └── .env                  # VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
│
├── services/
│   ├── database/
│   │   ├── schema.sql            # Crear tablas en Supabase
│   │   └── rls_fix.sql           # Desactivar RLS (obligatorio)
│   └── scrapers/
│       ├── main.py               # Orquestador principal
│       ├── scraper_fotocasa.py   # Scraper Fotocasa
│       ├── scraper_idealista.py  # Scraper Idealista
│       ├── scraper_facebook.py   # Scraper grupos Facebook
│       ├── scorer.py             # Lógica de puntuación (Altea Scorer)
│       ├── alerts.py             # Alertas Telegram / consola
│       ├── config.py             # Configuración centralizada
│       ├── utils.py              # Utilidades (parse_price, detect_zone…)
│       ├── debug_parse.py        # Script de diagnóstico
│       ├── requirements.txt      # Dependencias Python
│       ├── .env                  # SUPABASE_URL + SUPABASE_SERVICE_KEY
│       └── html_cache/           # HTML descargado (no subir a git)
│           ├── fotocasa/         # results_page_*.html
│           └── idealista/        # results_page_*.html
```

---

## 🎯 Flujo completo recomendado (primera vez)

```
1. Configurar .env (scrapers + frontend)
2. Ejecutar schema.sql en Supabase
3. Ejecutar rls_fix.sql en Supabase
4. python scraper_fotocasa.py --fetch --max-pages 5
5. python main.py --source fotocasa
6. pnpm dev  →  http://localhost:5173
```

**Tiempo total estimado: ~20 minutos** (incluyendo descarga de ~150 pisos de Fotocasa).
