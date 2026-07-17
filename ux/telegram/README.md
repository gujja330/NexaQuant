# UX030 — Institutional Telegram Intelligence Platform

**Sprint 15 · User Experience track.** Transforms Telegram from a
notification channel into the primary client interface for AEGIS.

> Advisory-only delivery layer. No state mutation. Deterministic. Mobile-first.
> Tenant-generic — no hardcoded tickers, sectors, or companies.

---

## What it does

Reads DEV017-DEV030 outputs from `reports/` and produces:

1. **Reference configs** describing the design system (templates, layouts,
   commands, notification rules, UI config).
2. **Rendered examples** for every message type using live context.
3. **A Python renderer + command dispatcher** the runtime delivery layer
   can import and call directly.

Users get 15-30 second daily consumption of a fully-scored portfolio +
opportunity list + risk view + strategy update — without opening any web app.

## Message Types (9)

| # | Type | Priority | Sends |
|---|---|---|---|
| 1 | Morning Brief         | MEDIUM   | daily digest |
| 2 | Daily Executive Summary| MEDIUM  | daily digest |
| 3 | New Buys Summary      | MEDIUM   | daily digest |
| 4 | Buy Alert             | HIGH     | 30-min coalesce |
| 5 | Exit Alert            | CRITICAL | immediate |
| 6 | Portfolio Health      | MEDIUM   | daily digest |
| 7 | Risk Alert            | CRITICAL | immediate |
| 8 | Champion Update       | HIGH     | 30-min coalesce |
| 9 | Weekly Review         | MEDIUM   | weekly digest |

## Interactive Commands (17)

`/help /summary /portfolio /buy /exits /health /risk /champion /challengers
/regime /performance /confidence /why <ticker> /doctor <ticker>
/history <ticker> /compare <a> <b> /sector <name>`

Every command is **deterministic** and evidence-based. No LLM.
See `lib/commands.py::COMMANDS`.

## Visual Elements

- **Status icons:** 🟢 buy · 🟡 hold · 🔴 exit · 🚨 alert · ⚠ warn · ✅ success
- **Grade badges:** 🟢 A/A+/A- · 🟡 B/B+/B- · 🟠 C/C+/C- · 🔴 D/F
- **Regime badges:** 🟢 Risk-On · 🟡 Neutral · 🔴 Risk-Off
- **Confidence stars:** ★★★★★ 95+ · ★★★★☆ 85-94 · ★★★☆☆ 75-84 · ★★☆☆☆ 65-74 · ★☆☆☆☆ <65
- **Progress bars:** `██████░░░░` 10-cell fill
- **Sector icons:** 💻 IT · 🏦 Financials · ⚕ Health · 🛒 Consumer · ⚡ Energy · 🏗 Materials · 🏭 Industrials · 💡 Utilities · 📡 Comms · 🏠 Real Estate

Central registry in `lib/icons.py` — retheme in one place.

## Notification Rules (5 tiers)

| Tier | Send | Coalesce |
|---|---|---|
| CRITICAL | immediate | none |
| HIGH     | immediate | 30-min window |
| MEDIUM   | batched   | daily summary |
| LOW      | batched   | weekly review |
| SILENT   | never     | log only |

See `lib/notification_rules.py::PRIORITY_MAP` for the full event→tier map.

## Outputs (6)

Written to `reports/`:

- `telegram_templates.json`           — message-type registry + styling principles
- `telegram_layouts.json`             — per-message section layouts + visual element registry
- `telegram_commands.json`            — command catalog (name / args / description)
- `telegram_notification_rules.json`  — priority map + grouping rules
- `telegram_ui_config.json`           — brand, style, iconography, thresholds
- `telegram_examples.md`              — live rendered examples using current context

## Layout

```
ux/telegram/
  lib/
    icons.py               — central visual registry
    aggregator.py          — reads DEV017-DEV030 outputs into a Context
    renderer.py            — 9 render_* functions producing Markdown
    commands.py            — 17 command handlers + dispatcher
    notification_rules.py  — 5-tier priority + grouping
  publish/
    bundle.py              — emit the 6 outputs
  tests/
    test_smoke.py          — 40+ assertions
  run.py                   — CLI
```

## Run

```
python ux/telegram/run.py
python ux/telegram/tests/test_smoke.py
```

## Design Principles

1. **Mobile-first** — every message fits a phone screen.
2. **30-second consumption** — hierarchical information density.
3. **Tenant-generic** — reads sectors/tickers/companies from context, never hardcoded.
4. **Deterministic** — same context in, same output out. No LLM calls.
5. **Advisory-only** — the delivery layer never mutates recommendations or portfolios.
6. **Composable** — 9 render functions and 17 commands, each independent.
7. **Themable** — every emoji and icon in `lib/icons.py`. Change once, change everywhere.

## Future extensions

- **UX031** — Web dashboard (same context; different presentation)
- **UX032** — Mobile app
- **UX033** — Voice assistant
- **/history <ticker>** — needs per-ticker rec history file (deferred to a future sprint)
