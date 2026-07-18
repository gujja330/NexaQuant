# AEGIS Executive Dashboard · Frontend

Self-contained single-page implementation of the UX031 spec. Reads
`reports/*.json` at runtime and renders 7 routes with 20+ widgets.

## Quick start

```
python ux/dashboard/frontend/serve.py
# then open http://127.0.0.1:8765/ux/dashboard/frontend/index.html
```

The serve script is a plain `http.server` with cache disabled so
newly-written `reports/*.json` files are picked up on refresh.

Direct-`file://` also works if your browser allows local fetch of
sibling files (some don't; the server is more reliable).

## Routes

- `/`                — Executive Overview (regime, champion, calibration, top buys, exits, v2.0 lift)
- `/portfolio`       — Portfolio + Holdings table + Position sizing
- `/recommendations` — Top buys, exits, Adaptive v2.0, feature importance
- `/risk`            — Risk budget, sizing, alerts
- `/validation`      — Paper harness state, opportunity cost, rolling edge sparklines
- `/champion`        — Champion strategy, challenger leaderboard, regime champions
- `/knowledge`       — Knowledge graph stats, communities, top influencers, entity/relation breakdown

## Data sources consumed

Every widget declares its source in the top-right of its card:

| Widget | Source file |
|---|---|
| Market Regime | `global_context.json` |
| Champion Strategy | `champion_strategy.json` |
| Calibration ECE | `confidence_calibration.json` |
| Portfolio | `portfolio.json` |
| Top Buys / Exits / Holdings | `recommendations.json` |
| Adaptive Rec v2.0 | `adaptive_rec_v2_signal.json` |
| Feature Importance | `adaptive_rec_v2_feature_importance.json` |
| Risk Budget / Sizing | `risk_capital_v2_latest.json` |
| Validation harness | `validation_v2_latest.json` |
| Knowledge Graph | `graph_statistics.json` / `community_clusters.json` |
| Strategy Leaderboard | `challenger_scoreboard.json` |
| Regime Champions | `regime_comparison.json` |

Widgets gracefully degrade when a source file is missing.

## Design system

Follows the UX031 theme JSON (`reports/dashboard_theme.json`) — same
palette (ink, cream, gold), same typography stack (transitional serif
for display + humanist sans for body + mono for data).

Dark theme is default. `data-theme="light"` toggle via the sidebar
button, persisted to localStorage.

Responsive: sidebar collapses under the header at narrow widths;
grid columns stack.

## Architecture

- **State**: `STATE` object holds every fetched JSON. Loaded once at boot.
- **Router**: hash-based. `/`, `/portfolio`, etc. Rebinds on `hashchange`.
- **Widgets**: pure functions of `STATE`. Each returns a DOM node.
- **Cards**: consistent shell (title + source + body).
- **No frameworks**: vanilla JS, no build step, no external CDN.

## Governance

- Advisory only. No write endpoints.
- No user data leaves the browser.
- No external HTTP requests beyond the local static server.
