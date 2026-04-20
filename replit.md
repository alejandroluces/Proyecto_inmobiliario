# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Artifacts

### Altea Intel — Luxury Real Estate Dashboard (`artifacts/altea-intel`)
- **Type**: React + Vite (frontend-only, no backend)
- **Preview path**: `/`
- **Stack**: React, Tailwind CSS, Recharts, Lucide React, Wouter
- **Theme**: Dark mode (Slate-900 bg, Amber-500 gold accents, Emerald green for gains)
- **Features**:
  - Sidebar navigation (Dashboard, Oportunidades, Análisis por Zona, Leads FB, Config)
  - KPI cards: Avg price/m², New properties 24h, Best opportunity score, Total tracked
  - Zone filter bar for 5 Altea zones
  - Property opportunity grid with photo, score badge, source badge (Idealista/Facebook)
  - Zone comparison bar chart (Recharts)
  - Detailed table with sparkline price history (Recharts LineChart)
  - Glassmorphism card design, Space Grotesk/Inter fonts
- **Mock data**: `src/data/mockData.ts` — 10 realistic Altea properties with opportunity scores
- **Supabase-ready**: TypeScript interfaces defined in mockData.ts for easy backend swap

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.
