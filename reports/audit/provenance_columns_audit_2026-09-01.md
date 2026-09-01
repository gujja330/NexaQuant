# Provenance Columns Audit · 2026-09-01

**Scope**: Which provenance fields are present in each production XLSX sheet.
**Contract** (CEO 2026-09-01): every row must carry `Position ID`, `Runner`,
`Population`, `AsOf`, `Source/Engine`, and lifecycle context. Missing fields
are traceable via Position ID look-up into the Registry + AEGIS History.

## India · `reports/telegram/aegis_history_india.xlsx`

| Sheet | Present | Missing | Verdict |
|---|---|---|---|
| Portfolio | Runner · Lifecycle | Position ID · AsOf · Population · Source · Engine · Country · Run_Type | PARTIAL (no PID linkage on visible view) |
| Exit History (90d) | Runner | Position ID · AsOf · Population · Source · Engine · Country · Lifecycle | PARTIAL (no PID linkage on visible view) |
| Monthly Summary | (aggregate view · no rows have per-position provenance) | N/A | OK by design |
| AEGIS INDIA History | Position ID · Legacy Position ID · Date · Country · Run_Type | AsOf · Population · Source · Engine · Lifecycle | 5/8 present |
| Definitions | N/A (reference sheet) | N/A | OK by design |

## USA · `reports/telegram/aegis_history_usa.xlsx`

Only `AEGIS USA History` sheet is currently emitted (upstream data stale
17d · Portfolio + Exit History + Monthly Summary + Definitions not yet
built for USA). Once rebuilt, expected provenance profile mirrors India.

## Reconciliation strategy while columns missing

The reconciler (`scripts/aegis_final_reconciler.py`) currently cross-checks
Registry ↔ AEGIS History ↔ Portfolio ↔ Exit History via **ticker + runner
+ entry_date**, which is a robust surrogate for Position ID when a row
lacks it. This is C7/C8/C9/C10 today.

## Recommended follow-up (scoped · not executed this session)

1. Add `Position ID` as the LAST column of `Portfolio` + `Exit History (90d)`
   sheets. Small emit-code change · Portfolio row loop already knows the PID
   via Registry lookup. Zero visible impact on operators (last column can
   be hidden via `column_dimensions[last].hidden = True`).
2. Add `AsOf` + `Population` + `Source` columns to `AEGIS History` sheet.
   Source is always `aegis_daily_v2` for these rows · AsOf is the emit
   date · Population is `HISTORICAL_OBSERVATION`.
3. Emit companion `reports/telegram/aegis_history_{market}_provenance.jsonl`
   with the full provenance record for every visible row · immediately
   consumable by reconciler.

## Status

- Documented (this file) · **not implemented**
- Reconciler continues to validate via ticker+runner+entry_date proxy
- Position ID is present + reliable in AEGIS History (the audit sheet)
- Delivery to operator is unaffected

## Provenance-of-provenance

This audit was produced by inspecting today's `aegis_history_india.xlsx`
(672-row AEGIS INDIA History · 28-row Portfolio · 41-row Exit History)
and comparing header rows to the CEO contract issued 2026-09-01.
