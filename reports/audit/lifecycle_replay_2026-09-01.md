# R2 Lifecycle Replay · 2026-09-01

Full E2E lifecycle trace for the 3 CEO-flagged R2 positions:
**entry → daily evaluation → engine verdict → Registry → Portfolio sheet → Exit History**

Reconstructed using the SAME rules as production dynamic engine:
- ATR-14 · atr_mult=2.0 · high_vol_scale=1.5 · high_vol_threshold=3.0%
- evaluate_position priority: STOP > T2 > T1 > HORIZON > HOLD
- No hardcoded 5%/6% stop · dynamic engine is authoritative
- Cross-referenced against SHIPPED 3-sheet workbook (Portfolio row · Exit History absence)

## IND-R2-CHAMBLFERT-20260804-893fdf
- ticker: **CHAMBLFERT** (INDIA R2)
- entry: 2026-08-04 @ 452.3500
- days replayed: 19
- Registry: **ACTIVE**
- shipped workbook: `reports\telegram\aegis_india_2026-09-01.xlsx`
- 01_Portfolio row: **R11**
  - shipped snapshot (from XLSX):
    - Entry Date: 2026-08-04
    - Entry Price: 452.35
    - Current Price: 413.55
    - Unrealized P&L %: -8.58
    - Holding Days: 28
    - Dynamic Stop: 400.8
    - Engine Verdict: HOLD (audit-only)
    - Would-Have-Exited-On: —
- 03_Exit_History: ABSENT (correct · position ACTIVE)
- overall: **A · engine HOLD throughout · Registry ACTIVE · Portfolio row present · Exit History absent · CONSISTENT**
- engine verdict was HOLD every day · Registry state consistent · workbook consistent

| Date | Days | Close | Dyn Stop | Stop Type | ATR% | P&L % | Engine |
|---|---|---|---|---|---|---|---|
| 2026-08-04 | 0 | 452.3500 | 435.5929 | atr | 1.85 | 0.0 | HOLD |
| 2026-08-05 | 1 | 454.6000 | 438.3857 | atr | 1.78 | 0.5 | HOLD |
| 2026-08-06 | 2 | 459.5500 | 443.4571 | atr | 1.75 | 1.59 | HOLD |
| 2026-08-07 | 3 | 450.7000 | 434.6214 | atr | 1.78 | -0.36 | HOLD |
| 2026-08-10 | 6 | 451.5500 | 435.7428 | atr | 1.75 | -0.18 | HOLD |
| 2026-08-11 | 7 | 444.3500 | 428.0214 | atr | 1.84 | -1.77 | HOLD |
| 2026-08-12 | 8 | 444.3500 | 428.5000 | atr | 1.78 | -1.77 | HOLD |
| 2026-08-13 | 9 | 442.3000 | 427.2928 | atr | 1.7 | -2.22 | HOLD |
| 2026-08-14 | 10 | 442.7000 | 428.7286 | atr | 1.58 | -2.13 | HOLD |
| 2026-08-17 | 13 | 439.0500 | 424.6286 | atr | 1.64 | -2.94 | HOLD |
| 2026-08-18 | 14 | 434.4000 | 421.1571 | atr | 1.52 | -3.97 | HOLD |
| 2026-08-19 | 15 | 434.8500 | 421.0571 | atr | 1.59 | -3.87 | HOLD |
| 2026-08-20 | 16 | 433.9500 | 421.5286 | atr | 1.43 | -4.07 | HOLD |
| 2026-08-21 | 17 | 431.1500 | 418.3429 | atr | 1.49 | -4.69 | HOLD |
| 2026-08-24 | 20 | 431.6000 | 420.4071 | atr | 1.3 | -4.59 | HOLD |
| 2026-08-25 | 21 | 437.6500 | 424.9357 | atr | 1.45 | -3.25 | HOLD |
| 2026-08-26 | 22 | 427.6000 | 414.6929 | atr | 1.51 | -5.47 | HOLD |
| 2026-08-28 | 24 | 423.2000 | 411.3072 | atr | 1.41 | -6.44 | HOLD |
| 2026-08-31 | 27 | 413.5500 | 400.8000 | atr | 1.54 | -8.58 | HOLD |

## IND-R2-ITC-20260804-e0ebbb
- ticker: **ITC** (INDIA R2)
- entry: 2026-08-04 @ 284.8500
- days replayed: 20
- Registry: **ACTIVE**
- shipped workbook: `reports\telegram\aegis_india_2026-09-01.xlsx`
- 01_Portfolio row: **R12**
  - shipped snapshot (from XLSX):
    - Entry Date: 2026-08-04
    - Entry Price: 284.85
    - Current Price: 264.9
    - Unrealized P&L %: -7
    - Holding Days: 28
    - Dynamic Stop: 258.25
    - Engine Verdict: HOLD (audit-only)
    - Would-Have-Exited-On: —
- 03_Exit_History: ABSENT (correct · position ACTIVE)
- overall: **A · engine HOLD throughout · Registry ACTIVE · Portfolio row present · Exit History absent · CONSISTENT**
- engine verdict was HOLD every day · Registry state consistent · workbook consistent

| Date | Days | Close | Dyn Stop | Stop Type | ATR% | P&L % | Engine |
|---|---|---|---|---|---|---|---|
| 2026-08-04 | 0 | 284.8500 | 276.1000 | atr | 1.54 | 0.0 | HOLD |
| 2026-08-05 | 1 | 289.0000 | 280.4000 | atr | 1.49 | 1.46 | HOLD |
| 2026-08-06 | 2 | 285.8000 | 277.1214 | atr | 1.52 | 0.33 | HOLD |
| 2026-08-07 | 3 | 286.1000 | 277.7786 | atr | 1.45 | 0.44 | HOLD |
| 2026-08-10 | 6 | 282.6500 | 274.3929 | atr | 1.46 | -0.77 | HOLD |
| 2026-08-11 | 7 | 279.0000 | 270.2929 | atr | 1.56 | -2.05 | HOLD |
| 2026-08-12 | 8 | 279.0000 | 270.5429 | atr | 1.52 | -2.05 | HOLD |
| 2026-08-13 | 9 | 276.1500 | 267.5786 | atr | 1.55 | -3.05 | HOLD |
| 2026-08-14 | 10 | 278.2000 | 270.2786 | atr | 1.42 | -2.33 | HOLD |
| 2026-08-17 | 13 | 273.0500 | 265.1928 | atr | 1.44 | -4.14 | HOLD |
| 2026-08-18 | 14 | 270.0000 | 262.2000 | atr | 1.44 | -5.21 | HOLD |
| 2026-08-19 | 15 | 267.0500 | 258.6786 | atr | 1.57 | -6.25 | HOLD |
| 2026-08-20 | 16 | 271.6500 | 262.8357 | atr | 1.62 | -4.63 | HOLD |
| 2026-08-21 | 17 | 269.4000 | 261.5857 | atr | 1.45 | -5.42 | HOLD |
| 2026-08-24 | 20 | 270.6000 | 263.6429 | atr | 1.29 | -5.0 | HOLD |
| 2026-08-25 | 21 | 268.0000 | 261.1071 | atr | 1.29 | -5.92 | HOLD |
| 2026-08-26 | 22 | 271.4000 | 264.4928 | atr | 1.27 | -4.72 | HOLD |
| 2026-08-27 | 23 | 269.0000 | 261.8500 | atr | 1.33 | -5.56 | HOLD |
| 2026-08-28 | 24 | 268.1500 | 261.4143 | atr | 1.26 | -5.86 | HOLD |
| 2026-08-31 | 27 | 264.9000 | 258.2500 | atr | 1.26 | -7.0 | HOLD |

## USA-R2-IT-20260810-b5fd37
- ticker: **IT** (USA R2)
- entry: 2026-08-10 @ 193.1700
- days replayed: 3
- Registry: **ACTIVE**
- shipped workbook: `reports\telegram\aegis_usa_2026-09-01.xlsx`
- 01_Portfolio row: **R7**
  - shipped snapshot (from XLSX):
    - Entry Date: 2026-08-10
    - Entry Price: 193.17
    - Current Price: 179.46
    - Unrealized P&L %: -7.1
    - Holding Days: 22
    - Dynamic Stop: 161.7654
    - Engine Verdict: HOLD (audit-only)
    - Would-Have-Exited-On: —
- 03_Exit_History: ABSENT (correct · position ACTIVE)
- overall: **A · engine HOLD throughout · Registry ACTIVE · Portfolio row present · Exit History absent · CONSISTENT**
- engine verdict was HOLD every day · Registry state consistent · workbook consistent

| Date | Days | Close | Dyn Stop | Stop Type | ATR% | P&L % | Engine |
|---|---|---|---|---|---|---|---|
| 2026-08-10 | 0 | 193.1700 | 176.0389 | vol_scaled | 5.91 | 0.0 | HOLD |
| 2026-08-11 | 1 | 187.2700 | 169.9118 | vol_scaled | 6.18 | -3.05 | HOLD |
| 2026-08-12 | 2 | 179.4600 | 161.7654 | vol_scaled | 6.57 | -7.1 | HOLD |
