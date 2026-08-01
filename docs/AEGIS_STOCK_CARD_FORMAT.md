# AEGIS Stock Card Format · Locked Standard

**Signed into force**: 2026-08-01 (locked per operator directive)
**Scope**: Every stock in every daily report · Runner 1 AND Runner 2 · India + USA
**Delivery**: Compact summary in Telegram message · full detail per stock in attached `.md` companion file
**Governance**: Any change requires operator sign-off · violations are bugs

---

## The Card Template · every stock uses THIS exact structure

```
🟢🟢 TICKER (Company Name)
────────────────────────
Rank          #N
Runner        R1 | R2
Status        NEW BUY | BUY | STRONG BUY | HOLD | ROTATE IN | ROTATE OUT | EXIT
Confidence    XX% (Calibrated | Raw | Historical)
Model Score   XX/100

Holding
Day X / Y
N days remaining

Current
₹price  (or $price for USA)

Recommendation
ACTION
Position Size: X%

Entry
Recommended : DD-MMM-YYYY
Entry Price : ₹price
Buy Zone    : ₹low–₹high

Risk
Stop Loss   : ₹price
Risk         : -X.X%

Reward
Target 1    : ₹price (+X%)
Target 2    : ₹price (+X%)

Performance
Current      : +X.XX%
Max Gain     : +X.XX%
Max DD       : -X.XX%

Lifecycle
State
NEW
↓
ACTIVE
↓
HOLD
↓
EXIT

Exit Trigger
[✓/□] Target Hit
[✓/□] Stop Hit
[✓/□] Time Expired
[✓/□] Rotation
[✓/□] Manual Exit

Top Drivers
✓ Momentum | Quality | Trend | Relative Strength | Earnings Growth | Sector Rotation

Risk Flags
⚠ (only shown when active · e.g. "Earnings in 5 days", "High Beta", "Sector Overweight")

Portfolio
Sector Exposure : X%
Portfolio Weight: X%
Correlation      : Low | Medium | High | —

Expected Alpha
+X%
Confidence Band
+low% → +high%

Historical Similar Setups
Win Rate      XX%
Median Return +X.X%
Average Hold  N days

Last Updated
DD-MMM-YYYY HH:MM IST
```

---

## Confidence % and Model Score · both 0-100 · both mandatory

Operator asked 2026-08-01: *"confidence is out of 100? what is model score?
these all are mandatory right from screenshot"*. Answer:

**Confidence %** · scale **0–100** · answers *"how likely is this to work?"*
- `Calibrated` (default) · post-calibration probability from Runner 2 v3's
  calibration layer · scaled against historical hit rate. A stock with
  Calibrated 55% means: historically, signals this strong turn into
  successful trades 55% of the time in this regime.
- `Raw` · pre-calibration raw model output. Used when the calibrated
  variant isn't available (older payloads). Same 0–100 scale but NOT
  probability-calibrated.
- The `Conf Type` column labels which flavor · never mix without label.

**Model Score** · scale **0–100** · answers *"how strong is the signal?"*
- Ensemble output from Runner 2's 11 models: Momentum · Trend · Value ·
  Growth · Quality · Mean Reversion · News · Macro · Sector · Event-Driven
  · AI-Hybrid.
- Weighted sum per adaptive-weights config · higher = stronger BUY signal.
- Pre-calibration · raw magnitude · NOT a probability.

**Why they diverge (intentional)**:
- A stock can have Model Score 85 (very strong signal) but Confidence 45%
  (only 45% of signals this strong historically played out in this regime).
- Or Model Score 55 (mid signal) with Confidence 70% (high hit-rate on
  weaker but reliable signals for this ticker family).
- The two together = signal magnitude × signal reliability = what the
  operator actually needs to size a position.

**Both are mandatory** · every stock row in the XLSX shows both fields ·
never empty · never faked. Verified 2026-08-01: 41/41 rows populated.

---

## Field-by-field source of truth

| Field | Source · payload path | Missing behavior |
|---|---|---|
| Ticker | `recommendations[i].ticker` | required · never missing |
| Company Name | company name lookup (static · in `command_center.py`) | show ticker only |
| Rank | `recommendations[i].rank` | `—` |
| Runner | derived: R1 from `runner1_validation.runner1_orphans` · R2 from main recs | required |
| Status | derived: `investor_action.entry` · `rotation_intelligence.should_rotate` · lifecycle event | required |
| Confidence | `calibrated_confidence` (Cal) OR `confidence` (Raw) OR CSV `Rec Confidence %` (Historical) | `—` |
| Model Score | R2: `ensemble_score` · R1: `Score /100` from CSV | `—` |
| Holding · Day X / Y | R2: `evolution.days_recommended / position_plan.time_horizon_days` · R1: derived from CSV holding | `—` |
| N days remaining | Y − X | `—` |
| Current | `position_plan.entry_zone.current_price` OR position_store's last_seen_price | `—` |
| Recommended date | `evolution.first_seen_date` OR position_store's first_seen_date | `—` |
| Entry Price | position_store's `first_seen_price` | `—` |
| Buy Zone | `position_plan.entry_zone.ideal_buy_low – ideal_buy_high` OR R1 CSV `Buy Range` | `—` |
| Stop Loss | `position_plan.entry_zone.stop_loss` OR R1 CSV-derived (`price × 0.95`) | `—` |
| Risk % | `(stop_loss − entry_price) / entry_price × 100` | `—` |
| Target 1 | `position_plan.entry_zone.target_1` OR R1 CSV `Hist Target` | `—` |
| Target 2 | `position_plan.entry_zone.target_2` OR derived `(current + 1.5 × (T1 − current))` | `—` |
| Target %s | `(target − entry) / entry × 100` | `—` |
| Current Performance | position_store: `(last_seen_price − first_seen_price) / first_seen_price × 100` | `—` |
| Max Gain | position_store: `(high_water_price − first_seen_price) / first_seen_price × 100` | `—` |
| Max DD | position_store: `(low_water_price − first_seen_price) / first_seen_price × 100` | `—` |
| Lifecycle State | R006 portfolio_ledger's last event · NEW/ACTIVE/HOLD/EXITED | `NEW` for un-tracked |
| Exit Trigger checkboxes | R006 portfolio_ledger scan · `EXIT_TARGET → Target Hit` etc. | all `□` for active |
| Top Drivers | `attribution.top_features` OR R1 CSV `Why` heuristic parse | `—` |
| Risk Flags | derived: earnings calendar + beta + portfolio sector exposure | omit section if none |
| Sector Exposure | R006 portfolio state · sum allocated_pct per sector | `—` |
| Portfolio Weight | `position_plan.suggested_allocation_pct` | `—` |
| Correlation | portfolio-level correlation to existing holdings | `—` (deferred · needs corr matrix) |
| Expected Alpha | `rotation_intelligence.expected_alpha_delta_pct` OR `(t1 − entry) / entry × 100` | `—` |
| Confidence Band | derived from historical calibration variance · `[expected − σ, expected + σ]` | `—` (deferred · needs calibration data per-setup) |
| Historical Similar Setups | requires per-setup backtest lookup (Ticket R007 · not yet built) | show `—` explicitly |
| Last Updated | `payload.run_utc` in IST/ET · rendered as `DD-MMM-YYYY HH:MM TZ` | required · from payload |

---

## Delivery: 2-part message

Because the full card (~45 lines) × N stocks (15) far exceeds Telegram's 4096-char single-message cap, the daily report is delivered as:

1. **Compact Telegram message** (existing Command Center · unchanged) · shows CEO Action · Runner Experiment · Runner Comparison · top 3-4 rich cards inline (NEW BUY IDEAS · EXITS) · references the attached file
2. **Attached `.md` file** · full detailed card per every stock in the current portfolio · sent via Telegram's `sendDocument` API alongside the message

File name: `aegis_detail_{market}_{YYYY-MM-DD}.md`
File path: `reports/telegram/aegis_detail_{market}_{asof}.md`

## Never fake data

If a field is missing (Historical Similar Setups · Confidence Band · Correlation · Risk Flags data unavailable) render `—` explicitly · NEVER a plausible-looking made-up number.

If the file attachment fails to upload · the compact Telegram message still sends with a note "detail report unavailable · re-run daily pipeline".

---

## Section order within one card (locked)

```
Header (ticker + emoji + company name)
─────
Rank / Runner / Status / Confidence / Model Score
Holding
Current
Recommendation
Entry
Risk
Reward
Performance
Lifecycle
Exit Trigger
Top Drivers
Risk Flags        (optional · omit if none)
Portfolio
Expected Alpha
Confidence Band
Historical Similar Setups
Last Updated
```

Same order for R1 and R2 · same for BUY / HOLD / EXIT stocks · same for India / USA · **Formula 1 timing screen** rule from `AEGIS_TELEGRAM_FORMAT.md` §Golden-Rule.

---

## Renderer

Function: `_detailed_stock_card(rec, market, position_store, portfolio_ledger)` in `backend/delivery/telegram/detail_report.py`

Batch: `render_daily_detail_report(market, asof)` in same file · produces the full `.md` file with every stock's card.

Send: `scripts/telegram_command_center_send.py` sends compact message + attaches the detail file.

---

**Locked 2026-08-01 · edit only with operator sign-off · violations = bugs**
