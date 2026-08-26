# AEGIS · Production Delivery Layer · HARD LOCK

**Status:** 🔒 **LOCKED**
**Locked date:** 2026-08-26
**Locked by:** CEO signoff · India acceptance run · verdict WARN · 0 BLOCK FAIL
**Locked artefact:** `reports/telegram/aegis_history_india.xlsx` @ 19:30:58 IST
**Canonical source of truth:** `reports/context/portfolio_canonical_india.json` · 30 positions

---

## Final acceptance evidence

| Metric | Result |
|---|---|
| Full pytest | **228/228 passing + 1 skip** |
| XLSX validator verdict | **WARN · PASS=24 · WARN=1 · FAIL=0 · SKIP=0** |
| Zero BLOCK-severity failures | ✅ |
| Registry ↔ Portfolio reconciliation | 48 raw active → 30 INVESTMENT_ACTIVE + 3 risk-mutated-EXIT + 15 quality-filtered · all excluded positions have explicit reasons |
| Only remaining WARN | I13 price drift observation · 12 corp-action-explained + 7 stale-source (all corrected at display time by canonical fallback rule with per-ticker log) · does NOT affect delivered numbers |

## What is HARD LOCKED

| Layer | Enforcement |
|---|---|
| R1 (Runner 1) | Signals + universe + thresholds locked (Constitution v1.1.0 Article 34) |
| R2 (Runner 2) | Signals + universe + thresholds locked |
| Position Registry | Immutable Position IDs · NEW → ACTIVE → EXIT → CLOSED lifecycle · `backend/research/opportunity_registry.py` |
| Canonical INVESTMENT_ACTIVE | Sender emits `reports/context/portfolio_canonical_{market}.json` · SINGLE source of truth. Validator I8 reads it. Registry-active MINUS SHADOW/MOMENTUM/SUGGESTED MINUS risk-mutated-EXIT MINUS quality-filtered = canonical |
| P&L Definitions | Active = (Curr−Entry)/Entry · Today = (Curr−Prev)/Prev · Exit = (Exit−Entry)/Entry · never sum percentages · equal-weight labeled |
| Portfolio contract | Sheet titles, analysis rows, header row, required columns · `backend/delivery/xlsx_contract.py` |
| XLSX validator | 25 invariants I1–I25 · BLOCK/WARN/INFO · fail-before-send · `backend/delivery/xlsx_validator.py` |
| Telegram contract | Delivers only the exact validated per-market XLSX file |
| Lifecycle canonical states | NEW · ACTIVE · ACTIVE+ · EXIT · RE-ENTRY · HOLD (legacy) |
| Forbidden states | PROTECT · REVIEW · TRAIL · TAKE_PROFIT (never as Status) |
| Stop-loss lifecycle mutation | Binding risk signal → Status forced to EXIT + Active P&L transferred to Exit P&L (SUNPHARMA/POWERGRID/ITC pattern) |
| Runner column | R1/R2/SHADOW/MOMENTUM only · country names blocked by I23 |
| Momentum quality-band | Shadow-first lookup with narrow-file fallback · `backend/research/short_term_momentum.py::_quality_band` |
| RE-ENTRY precedence | Prior CLOSED beats same-day NEW · `backend/delivery/telegram/detail_xlsx.py::_opportunity_status` |
| Canonical fallback rules (DOCUMENTED) | (a) Missing stop on same-day NEW/RE-ENTRY → -5% below entry · (b) Missing entry_price on same-day NEW/RE-ENTRY → today's live close · (c) Stale entry >2% from today's live on same-day RE-ENTRY → today's live close · every application logged · `tests/lifecycle/test_canonical_stop_fallback.py` |
| Golden regression fixture | 7 scenarios (A NEW, B loser, C-D closed, E RE-ENTRY, F SHADOW, G MOMENTUM-rejected) · `tests/golden/test_lifecycle_pnl.py` 14/14 |
| Registry↔Portfolio reconciliation | `tests/delivery/test_registry_portfolio_reconciliation.py` |
| Price integrity | 6 checks · corp-action-explained drift = WARN · unexplained still reported · `backend/context/price_integrity_guard.py` |

## Future-change gate

After LOCK, ANY change to a locked layer requires ALL SIX:

1. Documented research evidence with sample size threshold met
2. Filed research ticket in `docs/research/tickets/`
3. Reproducible failing test that isolates the defect
4. Walk-forward validation where applicable (portfolio/decision layers)
5. Full regression suite pass (`pytest tests/`)
6. Explicit CEO approval recorded in the commit message

## Zero-tolerance runtime checks

Every daily CI run must show:

- [ ] Full `pytest tests/` PASS (baseline: 228 tests)
- [ ] India production sender exits 0 OR gracefully-skips (data-quality upstream)
- [ ] USA production sender exits 0 OR gracefully-skips
- [ ] `xlsx_validator` verdict != BLOCK for any BLOCK-severity invariant
- [ ] Registry active count = canonical JSON count = Portfolio Row 2 count = visible investment rows
- [ ] Portfolio Row 2 Realized 90d = Exit History (90d) sheet count exactly
- [ ] Runner column contains only {R1, R2, SHADOW, MOMENTUM}
- [ ] No summed P&L percentages in Row 2/Row 3
- [ ] No CLOSED/EXIT position in ACTIVE section
- [ ] No SUGGESTED/SHADOW/MOMENTUM contaminating P&L population

## Locked deliverable audit trail

| Artifact | Path | Written by |
|---|---|---|
| Canonical INVESTMENT_ACTIVE JSON | `reports/context/portfolio_canonical_{market}.json` | `_split_and_send` (single source of truth) |
| Portfolio XLSX (India) | `reports/telegram/aegis_history_india.xlsx` | `_split_and_send` |
| Portfolio XLSX (USA) | `reports/telegram/aegis_history_usa.xlsx` | `_split_and_send` |
| Validator report | `reports/context/xlsx_validation_{market}.json` | `xlsx_validator.emit` |
| Price integrity report | `reports/context/price_integrity_{market}.json` | `price_integrity_guard.emit` |

## Sprint M scope after LOCK

Sprint M is **research/measurement only**. No production presentation changes.

Analyzed dimensions:
- Runner × Cap × Sector × Investability × Momentum × Risk × Market Regime × Entry Timing
- Metrics: expectancy · win rate · avg winner · avg loser · drawdown · 1D/3D/5D/10D/20D outcomes
- Opportunity capture rate · missed winners · loss attribution

**Findings do not modify R1/R2 until n≥100 closed positions per bucket AND walk-forward validation AND explicit CEO approval.**

---

## Signoff

| Signatory | Role | Date | Basis |
|---|---|---|---|
| CEO | Final approver | 2026-08-26 | "READY FOR LOCK ... goahead plz" |

**Delivery layer HARD LOCKED. No further production presentation changes without the future-change gate above.**
