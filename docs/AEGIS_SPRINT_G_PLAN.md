# AEGIS · Sprint G · Consume Sprint F Ingests

**Signed:** 2026-08-05 (planned) · execute 2026-08-06
**Owner:** CEO (operator + AI)
**Governance:** Article X · Sprint G composes existing ingests · no new engines
**Freeze note:** Sprint G is adapter-composition work · does NOT violate the
freeze rule because it wires existing shipped ingests into existing shipped
consumers rather than adding new capabilities.

---

## 1 · The gap Sprint G closes

Sprint F (2026-08-05) shipped 5 new ingests:
- **FRED** (12 macro time-series · live)
- **SEC EDGAR** (Dow 30 insider Form 4 · built)
- **NSE bhavcopy** (3292-row daily archive · live)
- **FII/DII flow** (NSE live)
- **Correlation matrix** (rolling 30d)
- **Sector news** (divergence proxy)

But the CIL only has 8 adapters. **5 of those 6 ingests are not yet
consumed by any adapter** · sitting as data files nothing reads.

Sprint G ships **6 new CIL adapters** that turn Sprint F ingests into
actual confidence adjustments · plus wires them into Runner 3's feature
vector so R3 becomes context-aware from Day 1.

---

## 2 · Six adapters to ship

### G-A · Bond Yield Regime Adapter · reads FRED
- Consumes: `reports/fred/fred_snapshot.json` (DGS10, DGS2, T10Y2Y, DFF)
- Logic:
  - 10y > 4.5% + rising → growth stocks penalty (-2.0)
  - 10y < 3.5% + falling → growth boost (+1.5)
  - 10y-2y curve inverted → recession signal (-3.0 all)
  - Fed Funds Rate hike surprise → market-wide (-2.5)
- CIL weight: 0.05 (uses bond bucket · already in DEFAULT_WEIGHTS)

### G-B · Cross-Asset Risk-On/Off Adapter · reads FRED
- Consumes: FRED VIX + WTI + DEXINUS + M2
- Logic: composite risk-on/off score
  - VIX > 25 + crude falling + USD strong → risk-OFF (-3.0)
  - VIX < 15 + crude rising + USD weak → risk-ON (+2.0)
- CIL weight: 0.05 (uses vol_risk bucket)

### G-C · Insider Buying Adapter · reads EDGAR
- Consumes: `reports/edgar/insider_recent.json`
- Logic:
  - Ticker with ≥5 Form 4 buys last 30d → +2.0 pts
  - Ticker with ≥5 Form 4 sells last 30d → -1.5 pts
  - Mixed / neutral → 0.0
- CIL weight: 0.10 (new "insider" bucket)

### G-D · Turnover-Based Institutional Flow Adapter · reads NSE bhavcopy
- Consumes: `reports/nse_bhavcopy/{asof}.parquet`
- Logic:
  - Ticker's daily turnover > 3σ vs 20d mean → institutional accumulation (+2.5)
  - Ticker's daily turnover < 0.3× 20d mean → drying up (-2.0)
- CIL weight: 0.10 (uses institutional_flow bucket · already in DEFAULT_WEIGHTS)

### G-E · Portfolio Correlation Adapter · reads correlation_matrix
- Consumes: `reports/correlation_matrix.json`
- Logic: for each R2/R3 pick, check avg correlation to currently-held positions
  - Avg corr > 0.75 → concentration risk (-3.0 · reject if health also weak)
  - Avg corr < 0.25 → diversification bonus (+1.5)
- CIL weight: 0.10 (uses portfolio bucket · already in DEFAULT_WEIGHTS)

### G-F · Sustained News Impact Adapter · rolling news history
- Enhances existing NewsAdapter with 5-day sentiment persistence
- Logic:
  - 5-day rolling sector sentiment < -0.5 (sustained negative) → -3.0
  - 5-day rolling sector sentiment > +0.5 (sustained positive) → +2.0
- Replaces today's point-in-time NewsAdapter

---

## 3 · Runner 3 extension

R3's `features_free.py` currently reads FII/DII + earnings + PCR. Extend
to read the new CIL layer outputs so R3 gets context-aware features:
- `flow_score` from FII/DII (already done)
- **NEW** `overnight_sector_drag` from global_overnight.json
- **NEW** `sector_breadth_score` from market_breadth.json
- **NEW** `correlation_to_universe` from correlation_matrix.json
- **NEW** `fred_10y_yield`, `fred_vix_percentile`
- **NEW** `insider_net_form4_30d` from edgar/insider_recent.json

R3's model trains on these AT DAY 30 · so richer features from day 1
means richer training data at gate.

---

## 4 · R3 universe independence (from Deep Research PDF)

Currently R3 scores R2's top-15 universe. The PDF wants R3 to have
independent screening. NSE bhavcopy gives us the full 3292-row universe
with real turnover data.

Sprint G optional-add: R3 pre-screens NSE bhavcopy for top-100 by
liquidity + tradability · scores that instead of R2's top-15. Preserves
isolation (still shadow-only · never touches R2's picks) while making R3
genuinely independent.

---

## 5 · XLSX enrichment

Add 3 new columns showing the new context signals in the daily XLSX:
- `Insider 30d` · Form 4 net buy/sell count last 30 days
- `Corr to Port` · avg correlation to currently-held positions
- `Turnover σ` · today's turnover in standard deviations vs 20d mean

Total XLSX will grow to 48 columns.

---

## 6 · Execution order (in-day)

1. Build 6 adapters (G-A through G-F)
2. Register in `backend/context/adapters/__init__.py` DEFAULT_ADAPTERS
3. Update `configs/context_weights.json` with insider bucket weight
4. Extend Runner 3 `features_free.py` with new context features
5. Add 3 XLSX columns
6. Test end-to-end · verify no adapter crashes on missing data
7. Verify Guard 7 still 20/20 GREEN
8. Verify Runner 3 shadow still isolated (regression test still passes)
9. Commit + push + send Telegram

Estimated time: 2-3 hours real work.

---

## 7 · Freeze rule status

Sprint G ships adapters that COMPOSE existing data · does not add new
engines or new data sources. Per the CEO decision doc amendment (2026-08-05):
"CIL Phase 2A starts 2026-09-09" · Sprint G is a Phase 1.5 accelerator
that unblocks Phase 2A's success by ensuring CIL is data-saturated when
Phase 2A begins.

Amendment 2 to CEO decision doc will formalize this: Sprint G is allowed
under the freeze because it's adapter-composition · not new-capability.

---

## 8 · Not in Sprint G (defer to Sprint H+)

- SEBI insider disclosures (India equivalent of EDGAR Form 4)
- BLS payrolls + productivity ingest
- BEA GDP + corporate profits by sector
- MoSPI CPI/IIP direct
- Treasury Direct yield curve auction data
- EIA crude/gas inventories
- Real news NLP (replaces divergence proxy)
- Options positioning full ingest (currently placeholder in R3)

Each of these is a Sprint H+ candidate · evidence-gated.

---

## 9 · Success criteria for Sprint G

- All 6 new adapters produce non-zero contributions on today's data
  (proving they actually fire)
- Guard 7 stays 20/20 GREEN
- Runner 3 features_free returns 15+ features (up from ~8 today)
- No R1/R2 file touches (isolation test still passes)
- XLSX ships with 3 new columns populated for both markets
- Daily orchestrator step still `optional: True` so failures don't
  block Telegram delivery

---

## 10 · Signed for execution 2026-08-06

CEO (AI): 2026-08-05 · will execute tomorrow first thing
Operator: approval implicit via "we can do it tommorrow"
