# UX031 — Executive Dashboard

**Sprint 16 · UX track.** Primary web dashboard for institutional
investors. Presents the complete AEGIS investment lifecycle in one place.

> Advisory-only per ARCH001A Article V clause 5.1. Deterministic,
> tenant-generic, responsive, dark-first, keyboard-navigable.

---

## What it is (and isn't)

This module produces the **design spec + configuration data** for the
Executive Dashboard — a set of five JSON files the frontend consumes to
render the UI:

- Widget catalog (what components exist and where they get data)
- Route + filter map (URL structure + applicable filters per route)
- Grid layouts (12-col responsive grid, per-route section arrangements)
- Theme (institutional dark-first design system)
- Runtime config (brand, quality gates, performance budgets, shortcuts)

It does **not** ship an actual frontend implementation (React / Next.js
components). Those consume these JSONs and can be built in any framework.

## Outputs (5)

Written to `reports/`:

- **`dashboard_widgets.json`** — 23 widget definitions with data sources,
  metrics, visual patterns, refresh cadences, and grid sizes.
- **`dashboard_routes.json`** — 10 URL routes + 10 filter definitions.
- **`dashboard_layout.json`** — 10 per-route 12-column grid arrangements
  with sections + row/col spans.
- **`dashboard_theme.json`** — institutional dark theme with colors,
  typography scale, spacing units, breakpoints, motion, elevation.
- **`dashboard_config.json`** — brand, runtime, data sources, quality
  gates, auth mode, performance budgets, feature flags, keyboard shortcuts.

## Routes (10)

| Path | Name | Purpose |
|---|---|---|
| `/`             | Executive Overview      | Daily snapshot: regime + grade + opportunities + actions |
| `/market`       | Market Overview         | Sector/industry heatmaps, regime + heatmap |
| `/portfolio`    | Portfolio               | Composition, holdings, dependency graph |
| `/recommendations` | Recommendations      | Buys, exits, timeline |
| `/risk`         | Risk                    | Alerts, radar, drawdown |
| `/performance`  | Performance             | Equity curve, win rate, drawdown, heatmap, scoreboard |
| `/champion`     | Champion Strategy       | Champion card + scoreboard + regime champions + drift |
| `/knowledge`    | Knowledge Graph         | Interactive force-directed graph explorer |
| `/historical`   | Historical Performance  | Timelines and trends |
| `/health`       | Portfolio Health        | Scores + alerts + drift |

## Widgets (23)

Every widget declares `data_source` (which `reports/*.json` or `.parquet`
files it reads) and `refresh` cadence. Widgets consuming DEV031
(Knowledge Graph): `knowledge_graph`, `top_influencers`,
`portfolio_dependency_graph`.

Notable widgets:

- **`market_regime`** — badge from DEV017 + DEV030 classifications
- **`champion_strategy`** — headline card from DEV030
- **`confidence_gauge`** — DEV029 ECE dial
- **`sector_allocation`** / **`industry_allocation`** — treemaps from DEV022
- **`top_opportunities`** / **`todays_actions`** — DEV023 recommendations
- **`equity_curve`** / **`drawdown_curve`** — DEV021 backtest
- **`challenger_scoreboard`** / **`drift_panel`** — DEV030 leaderboard + drift
- **`risk_alerts`** / **`risk_radar`** — DEV024 monitoring
- **`knowledge_graph`** / **`top_influencers`** — DEV031 relationships

## Theme

Dark-first institutional palette; light-mode overrides included.

- **Brand:** `#0F172A` (slate-900 base) · `#38BDF8` (sky-400 accent)
  · `#FBBF24` (amber-400 highlight — champion badges, star ratings)
- **Status:** buy `#22C55E` · hold `#EAB308` · exit `#EF4444`
- **Regime:** Risk-On (green) · Neutral (yellow) · Risk-Off (red)
- **Typography:** Inter body / JetBrains Mono for tickers + strategy names
- **Motion:** 120ms/200ms/320ms fast/base/slow; respects `prefers-reduced-motion`

## Filters (10)

`portfolio · sector · industry · market_regime · date · confidence ·
recommendation · strategy · entity_type · relation_type`

Each filter declares its source (path into a `reports/` file) or a fixed
option list, so the frontend can populate dropdowns without hardcoding
tickers/sectors.

## Governance

- **Advisory only** — the dashboard reads `reports/` and never writes back.
- **Tenant generic** — every ticker/sector/industry is data-driven; no
  hardcoded values in widget or filter definitions.
- **Deterministic rendering** — same `reports/*` inputs produce the same UI.
- **Performance budgets** — enforced client-side (initial render <=1.5s,
  widget data <=600ms, route transition <=220ms).
- **Accessibility** — WCAG AA color contrast, keyboard shortcuts, focus states.

## Layout

```
ux/dashboard/
  lib/
    theme.py       — colors, typography, spacing, breakpoints, motion
    widgets.py     — 23 widget definitions
    routes.py      — 10 routes + 10 filters
    layouts.py     — 10 per-route grid layouts
    config.py      — runtime + brand + quality gates
  publish/
    bundle.py      — emit the 5 JSON configs
  tests/
    test_smoke.py  — consistency checks (widget refs, layout grid, etc.)
  run.py           — CLI
```

## Run

```
python ux/dashboard/run.py
python ux/dashboard/tests/test_smoke.py
```

## Future extensions (design already accommodates)

- **UX032 · AI Investment Copilot** — a route `/copilot` consuming DEV026
  Research Assistant outputs
- **UX033 · Portfolio Workspace** — collaborative annotations
- Server-side rendering / edge caching of `dashboard_*.json`
- Per-user layout customisation (widget reordering)
