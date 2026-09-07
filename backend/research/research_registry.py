"""AEGIS Research Registry · SINGLE SOURCE OF TRUTH for R1/R2/R3 items.

CEO 2026-09-04 · fixes the "summary compiled by hand-estimation" class of
error that produced the 46-vs-49 reconciliation gap. Anything that wants
to count · summarise · or dashboard R1/R2/R3 research must read from this
module. Never hand-tallied.

Two levels · ITEMS (declarative registry) and OUTCOMES (computed live from
Coverage Tracker + STP artifacts).

Every item has EXACTLY these fields:
  id           · short stable identifier
  runner       · R1 | R2 | R3 | COMPOSITE | STANDALONE | FUNDAMENTALS | DOMAIN
  category     · P0..P5 | II.x | F0x | Dxx | Other
  name         · human-readable
  approach     · one-line method summary
  tier         · Tier 1 | Tier 2 | Tier 3 | N/A
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class ResearchItem:
    id: str
    runner: str
    category: str
    name: str
    approach: str
    tier: str = "N/A"
    # Remediation scheduling (CEO 2026-09-04 · queue lowest-effort first)
    remediation_priority: int = 99   # 1 = highest · 99 = not scheduled
    upstream_substrate: tuple = ()   # tuple of item ids this depends on being Tested
    next_stp_action: str = ""        # concrete action needed to leave WORKED_LEGACY


# ── Data-quality tracks (CEO 2026-09-07) ────────────────────────────────────
DATA_QUALITY_ITEMS: list = []

# ── R1 ──────────────────────────────────────────────────────────────────────
R1_ITEMS: list[ResearchItem] = [
    ResearchItem("R1.1", "R1", "Self-analysis", "R1 engine self-analysis · 3 candidate models",
                  "Code trace · verify baseline HGB + LR + heuristic still running · Precision@10 selector",
                  remediation_priority=20, next_stp_action="STP T1+T2 only · self-analysis is diagnostic not predictive"),
    ResearchItem("R1.2", "R1", "Perf-analysis", "R1 real 25-trade performance analysis",
                  "Query registry · exclude admin exits · sector + filter-strategy hypotheticals",
                  remediation_priority=15, next_stp_action="Re-run when n_R1_closed ≥ 50 (currently 25)"),
    ResearchItem("R1.5.3", "R1", "KG-filter", "KG-community rolling group filter",
                  "Replace static GICS with 57 KG communities · rolling top-N acceptance",
                  upstream_substrate=("D13-KG",), remediation_priority=10,
                  next_stp_action="STP T3+T4 backtest vs static-sector baseline · needs KG history depth"),
    ResearchItem("R1.7", "R1", "Governance", "8th Research Trigger · Signal Silence",
                  "N≥10 day silence + comparator observation · never fires when all runners silent",
                  remediation_priority=99, next_stp_action="Governance rule · no STP applicable"),
    ResearchItem("R1.9-S1", "R1", "Delivery", "R1 advisory sheet 05_R1_Advisory",
                  "Workbook builder emits R1 daily picks as advisory sheet",
                  remediation_priority=99, next_stp_action="Delivery item · STP T5 only · already renders correctly"),
    ResearchItem("R1-OPT1", "R1", "Delivery", "R1 rows in 01_Investments ACTIVE section",
                  "Scoped C19 deviation · load R1 ACTIVE from registry · SUGGESTED-tag stop",
                  remediation_priority=99, next_stp_action="Delivery item · STP T5 only · verified this session"),
    ResearchItem("R1-BANNER", "R1", "Delivery", "R1 no-dynamic-exit-protection banner",
                  "INVESTMENTS_BANNER updated per V2 §R1.9 Stage 1 precondition",
                  remediation_priority=99, next_stp_action="Delivery item · verified this session"),
]

# ── R2 ──────────────────────────────────────────────────────────────────────
R2_ITEMS: list[ResearchItem] = [
    ResearchItem("P0", "R2", "P0", "Dynamic Exit Bridge · retrospective replay",
                  "Walk-forward counterfactual replay on 539 closes · paired bootstrap",
                  remediation_priority=99,   # REJECTED · already has paired-bootstrap evidence
                  next_stp_action="REJECTED · India lower_ci<0 + n<50 · USA p=0.561 · same evidence tier as F01-05 REJECT"),
    ResearchItem("P1", "R2", "P1", "Confidence Calibration on Delivered Output",
                  "Platt A/B fit · ECE ≤0.05 gate · sustained 4-refit acceptance",
                  upstream_substrate=("CAL-HISTORY-4W",),
                  remediation_priority=1, next_stp_action="Weekly refit monitoring · re-run STP T4 after 4 consecutive weekly Platt refits (CEO-authorized P1 exemption)"),
    ResearchItem("P2", "R2", "P2", "Sector/Regime-Adjusted Ranking",
                  "α·Sector_Regime + β·Market_Regime · walk-forward α/β grid + DSR",
                  upstream_substrate=("D06-CS", "FUND-ACCUM"),
                  remediation_priority=90, next_stp_action="BLOCKED by substrate rule · no work until F01-F05 Tested"),
    ResearchItem("P3", "R2", "P3", "KG Community-Relative Scoring",
                  "γ sweep · Final = (1−γ)·Global_Percentile + γ·Community_Percentile",
                  upstream_substrate=("F01-05-OOS", "D13-KG"),
                  remediation_priority=90, next_stp_action="BLOCKED by substrate rule · no work until F01-F05 Tested"),
    ResearchItem("P4", "R2", "P4", "Cap × Sector Interaction Study",
                  "Interaction table + likelihood-ratio test on nested logistic",
                  remediation_priority=99,
                  next_stp_action="Infra SHIPPED · reports/research/r2_upgrades/p4_cap_sector_interaction.json · REAL FINDING · LR p=0.020 · Sector adds info beyond Cap · n=33 stronger-evidence tier · not enough for R2 promotion"),
    ResearchItem("P5.1", "R2", "P5", "Ensemble disagreement display + sizing",
                  "stdev across 11 models · correlate with error magnitude",
                  remediation_priority=99,
                  next_stp_action="Infra SHIPPED · display-only · sizing DEFERRED until P1 gate clears · reports/research/r2_upgrades/p5_1_disagreement_{market}.json"),
    ResearchItem("P5.2", "R2", "P5", "Regime-conditional ensemble weights",
                  "Per-regime IC-weighted · fallback to global when bucket n<30",
                  upstream_substrate=("D07-MACRO",),
                  remediation_priority=30, next_stp_action="Requires per-regime IC series ≥30 samples per bucket"),
    ResearchItem("P5.3", "R2", "P5", "Daily turnover / rotation cap",
                  "Rotation budget X% NAV/day · top-N by expected-alpha-delta",
                  remediation_priority=99,
                  next_stp_action="Infra SHIPPED · simulator · reports/research/r2_upgrades/p5_3_turnover_cap_simulation.json · 6/11 rotation days exceed 5% cap · savings 0.0075% NAV"),
    ResearchItem("P5.4", "R2", "P5", "PIT universe audit",
                  "S&P/NSE membership drift reconstruction per historical trade date",
                  remediation_priority=8, next_stp_action="STP T3 one-time · check whether prior metrics need footnoted corrections"),
    ResearchItem("P5.5", "R2", "P5", "Standing post-R1 fixed comparator",
                  "Equal-weight top-10 by 3-month momentum · monthly rebalance · no tuning",
                  remediation_priority=99,
                  next_stp_action="Infra SHIPPED · daily runner scripts/run_standing_comparator.py · ledger reports/research/comparators/standing_{market}.jsonl · India top TITAN/BAJFINANCE · USA top MRNA/CRL"),
    ResearchItem("R2-USA-PARQUET", "R2", "Data", "USA price parquet drift root fix",
                  "Un-gitignore + workflow commit-back · workstation-CI sync",
                  remediation_priority=99, next_stp_action="Data hygiene · verified this session · monitor via freshness check"),
    ResearchItem("R2-ZERO-DIAG", "R2", "Diagnostic", "R2 zero-entry diagnosis",
                  "Registry scan + rec_v3 verdict analysis · Signal Silence eval",
                  remediation_priority=99, next_stp_action="Diagnostic · no STP · findings folded into Signal Silence Trigger 8"),
]

# ── R3 ──────────────────────────────────────────────────────────────────────
R3_ITEMS: list[ResearchItem] = [
    ResearchItem("II.1-GBM", "R3", "II.1", "GBM primary model family",
                  "LightGBM WF 252/63/21/5 · SHAP importance", "Tier 1",
                  remediation_priority=18, next_stp_action="STP T3+T4 · baseline-replicate gate first · then live shadow"),
    ResearchItem("II.1-STK", "R3", "II.1", "Ensemble stacking",
                  "Meta-learner logistic on GBM+R2_base+KG scores", "Tier 2",
                  upstream_substrate=("II.1-GBM", "F01-05-OOS"),
                  remediation_priority=90, next_stp_action="BLOCKED by substrate rule · Tier 2 · wait for GBM+F01-05 Tested"),
    ResearchItem("II.1-GNN", "R3", "II.1", "GraphSAGE on KG",
                  "2-layer message passing · end-to-end vs outcome", "Tier 2/3",
                  upstream_substrate=("D13-KG", "II.1-GBM"),
                  remediation_priority=95, next_stp_action="BLOCKED · 581 nodes small for GNN · deferred by V2"),
    ResearchItem("II.1-BMA", "R3", "II.1", "Bayesian model averaging",
                  "Posterior_weight ∝ Prior × Likelihood(IC)", "Tier 2",
                  upstream_substrate=("II.1-GBM",),
                  remediation_priority=90, next_stp_action="BLOCKED by substrate rule · Tier 2 · needs base-model IC series"),
    ResearchItem("II.2-FN", "R3", "II.2", "Factor-neutral scoring",
                  "Residual = base − Σβ·factor exposure (cross-section)", "Tier 2",
                  upstream_substrate=("F04-VAL", "F05-GROWTH"),
                  remediation_priority=90, next_stp_action="BLOCKED · needs Valuation + Growth Tested"),
    ResearchItem("II.2-PAIR", "R3", "II.2", "Peer-pair statistical arbitrage",
                  "Engle-Granger cointegration · ADF residual test", "Tier 3",
                  remediation_priority=99, next_stp_action="DEFERRED · needs short infrastructure we don't have"),
    ResearchItem("II.3-CUSUM", "R3", "II.3", "CUSUM change-point detection",
                  "S_t = max(0, S_(t-1) + (x_t − μ − k)) · flag at h", "Tier 3",
                  remediation_priority=99, next_stp_action="REJECT locked · both markets rejected · no re-open without CEO override"),
    ResearchItem("II.4-PIOT", "R3", "II.4", "Piotroski F-score",
                  "9-binary formula on TTM fundamentals", "Tier 1",
                  remediation_priority=6, next_stp_action="Already Tested in F01-05 · confirm coverage_tracker stage"),
    ResearchItem("II.4-BENE", "R3", "II.4", "Beneish M-score",
                  "8-variable earnings-manipulation formula · threshold −1.78", "Tier 1",
                  remediation_priority=7, next_stp_action="Same · already in F01-05 filter grid · confirm tracker"),
    ResearchItem("II.4-GOV", "R3", "II.4", "Governance India screen",
                  "Pledge % + related-party frequency", "Tier 2",
                  upstream_substrate=("D11-GOV",),
                  remediation_priority=45, next_stp_action="Requires SEBI RPT ingest · external data ticket"),
    ResearchItem("II.5-REV", "R3", "II.5", "Analyst estimate revision momentum",
                  "(EPS_now − EPS_3mo) / |EPS_3mo|", "Tier 1",
                  remediation_priority=22, next_stp_action="STP T3+T4 · already Populated · needs predictiveness test"),
    ResearchItem("II.5-TONE", "R3", "II.5", "Transcript tone Q&A",
                  "Finance-tuned tone · Q&A separated from prepared remarks", "Tier 2",
                  upstream_substrate=("D12-NARR",),
                  remediation_priority=50, next_stp_action="Requires transcript ingest external data ticket"),
    # ── R3 Sprint-1 FOUNDATION components · CEO 2026-09-07 ────────────
    # Registered here (not in a parallel status document) so R3 uses the
    # SAME governance state machine as everything else. Stages live in the
    # 13-stage Coverage Tracker under domain "R3".
    ResearchItem("R3-INFRA-ID", "R3", "Infra", "R3 identity · Position ID namespace",
                  "Deterministic IND/USA-R3-TICKER-YYYYMMDD-sig · runner=R3 · shadow_only",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="CLOSED · 46 isolation tests · parity with canonical id format"),
    ResearchItem("R3-INFRA-ISO", "R3", "Infra", "R3 isolation contract",
                  "No production writes/imports/registry/XLSX · model-artifact namespace",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="CLOSED · tests/isolation/test_r3_contract_r3_0.py"),
    ResearchItem("R3-INFRA-LEDGER", "R3", "Infra", "Canonical shadow ledger schema v2",
                  "identity+signal+risk+outcome+comparator+attribution · one ledger",
                  "Tier 1", remediation_priority=2,
                  next_stp_action="Implemented · needs live daily writes to reach Populated"),
    ResearchItem("R3-INFRA-PERSIST", "R3", "Infra", "Shadow ledger persistence",
                  "gitignore carve-out + CI commit set · evidence survives runs",
                  "Tier 1", remediation_priority=2,
                  next_stp_action="Implemented · verify across one real CI cycle"),
    ResearchItem("R3-INFRA-OUTCOME", "R3", "Infra", "Outcome accumulator (evidence clock)",
                  "fwd 5/10/20/60 TRADING days · as-of aware · never back/forward-filled",
                  "Tier 1", remediation_priority=2,
                  next_stp_action="Implemented · 40 horizons PENDING · fills as they close"),
    ResearchItem("R3-INFRA-PLATT", "R3", "Infra", "Platt calibration (real sigmoid)",
                  "1-D logistic on OOF raw score · A/B persisted · replaces claimed-only Platt",
                  "Tier 1", remediation_priority=3,
                  next_stp_action="Implemented · unexercised · blocked by training sample"),
    ResearchItem("R3-INFRA-WF", "R3", "Infra", "Walk-forward + 5-day embargo",
                  "Expanding-window folds · replaces KFold(shuffle=True) time leakage",
                  "Tier 1", remediation_priority=3,
                  next_stp_action="Implemented · cannot execute · dataset has 2-3 distinct entry dates"),
    ResearchItem("R3-INFRA-REPRO", "R3", "Infra", "Reproducible model artifact",
                  "Serialized GBM + calibrator + feature list + seed + dataset hash + git sha",
                  "Tier 1", remediation_priority=3,
                  next_stp_action="Implemented · unexercised until a model trains"),
    ResearchItem("R3-T1-FEATURES", "R3", "Infra", "Tier-1 feature contract (24 audited)",
                  "TIER1_SCOPE 9 substrate-independent · F01-F05 15 excluded by rule",
                  "Tier 1", remediation_priority=2,
                  next_stp_action="5/9 AVAILABLE+PIT · FII-DII, PCR, short-interest, earnings-calendar NOT_AVAILABLE_AT_ASOF"),
    ResearchItem("R3-T1-HORIZON", "R3", "Infra", "R3-1A frozen replication target",
                  "fwd_5d primary · only horizon at validation_candidate n in both markets",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="CLOSED · frozen 2026-09-07 · USA 10d n=13 CI overlaps 5d"),
    ResearchItem("R3-T1-DATA", "R3", "Infra", "Tier-1 training-sample dispersion",
                  "Walk-forward needs time-dispersed entries · currently a single cross-section",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="BLOCKED · India 24 rows/3 dates · USA 500 rows/2 dates · needs daily accumulation"),
    # ── Lane B · external Tier-1 input ACQUISITION tracks ─────────────
    # Separately registered per CEO 2026-09-07 so they cannot balloon into
    # Sprint 1. Specs (grain · raw fields · PIT cutoff · hazards) are in
    # backend/research/r3/tier1_input_specs.py · no collector is written.
    ResearchItem("R3-B1-FIIDII", "R3", "LaneB", "FII/DII flow acquisition (India)",
                  "NSE daily FII/FPI + DII · MARKET-level regime feature · never per-stock",
                  "Tier 1", remediation_priority=5,
                  next_stp_action="SPEC_ONLY · build PIT collector preserving source_timestamp · NSE data is provisional/revisable"),
    ResearchItem("R3-B2-PCR", "R3", "LaneB", "Options PCR acquisition",
                  "(date, underlying, expiry) OI snapshots · pcr_near_expiry + aggregate + 60d pct",
                  "Tier 1", remediation_priority=6,
                  next_stp_action="SPEC_ONLY · requires HISTORICAL OI snapshots · live chain must never be applied backward"),
    ResearchItem("R3-B3-SHORT-USA", "R3", "LaneB", "Short interest acquisition (USA)",
                  "FINRA/SEC position snapshot · pct_float + days_to_cover + change_vs_prev",
                  "Tier 1", remediation_priority=7,
                  next_stp_action="SPEC_ONLY · position data is NOT daily short-sale volume · publication-lag PIT"),
    ResearchItem("R3-B3-SHORT-INDIA", "R3", "LaneB", "Short proxy research (India)",
                  "NSE short-sale volume / SLB / F&O short OI · candidate proxies only",
                  "Tier 1", remediation_priority=8,
                  next_stp_action="SPEC_ONLY · NO India equivalent of US short interest · must not be renamed short_interest"),
    ResearchItem("R3-B4-EARNINGS", "R3", "LaneB", "Earnings calendar acquisition",
                  "Event table · days_to/since_next · windows · publication_time is the PIT key",
                  "Tier 1", remediation_priority=6,
                  next_stp_action="SPEC_ONLY · earnings SURPRISE excluded (F01-F05 substrate) · store is_estimated_date"),
    ResearchItem("R3-LANE-A", "R3", "Infra", "Lane A · daily PIT accumulation",
                  "Daily feature snapshot per eligible name · builds walk-forward time dispersion",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="WIRED · r3_canonical_daily_shadow both markets · accumulating from 2026-09-07"),
    ResearchItem("R3-LANE-C", "R3", "Infra", "Lane C · forward validation clock",
                  "Frozen daily prediction + R2 comparator · outcomes fill only as horizons close",
                  "Tier 1", remediation_priority=1,
                  next_stp_action="WIRED · predictions withheld as NO_MODEL until an artifact trains"),
    ResearchItem("R3-LANE-A-FEATURES", "R3", "Infra",
                  "Lane A feature-substrate coverage",
                  "Tier-1 features computable universe-wide, not only for R2's selection",
                  "Tier 1", remediation_priority=2,
                  next_stp_action=("BLOCKED · Lane A now writes 50/516 LABEL rows but only "
                                    "30 carry Tier-1 features · the 5 available features come "
                                    "from R2's recommendations SSoT (15 names/market), so the "
                                    "FEATURE substrate is still R2-selected even though the "
                                    "row set is broad")),
    ResearchItem("R3-T1-TECHNICALS", "R3", "Infra",
                  "Tier-1 universe-wide PIT technicals",
                  "10 declared technicals from price bars <= asof · returns/vol/RSI/volume/52w/MA/ATR",
                  "Tier 1", remediation_priority=1,
                  next_stp_action=("IMPLEMENTED · coverage india 46/50 (92%) usa 503/516 (97.5%) "
                                    "· PIT self-test stable · fixed declared set, never tuned on outcomes")),
    ResearchItem("II.6-MH", "R3", "II.6", "Multi-horizon consensus",
                  "sign_match(5d, 17d) · conviction ×1.15/×0.7", "Tier 1",
                  upstream_substrate=("II.1-GBM",),
                  remediation_priority=28, next_stp_action="Requires GBM 5d and 17d model instances · Tier 1 after GBM Tested"),
]

# ── F01-F05 Fundamentals ─────────────────────────────────────────────────────
FUND_ITEMS: list[ResearchItem] = [
    ResearchItem("F01-05-COMP", "FUNDAMENTALS", "F01-05", "F01-05 Composite (Piotroski + FCF + IntCov − Beneish)",
                  "Cross-sectional z-score decile lift · top vs bottom decile",
                  upstream_substrate=("FUND-ACCUM",),
                  remediation_priority=3, next_stp_action="Re-run STP once fundamentals_history has 8+ quarters PIT"),
    ResearchItem("F01-05-GRID", "FUNDAMENTALS", "F01-05", "F01-05 Filter Grid (11 threshold variants)",
                  "DSR-deflated multi-testing · combined + individual filters",
                  upstream_substrate=("FUND-ACCUM",),
                  remediation_priority=4, next_stp_action="Re-run STP once accumulator has multi-quarter PIT history"),
    ResearchItem("F01-05-OOS", "FUNDAMENTALS", "F01-05", "F01-05 OOS ticker-partition",
                  "Deterministic hash-split 70/30 · fit on train tickers · eval on test tickers",
                  upstream_substrate=("FUND-ACCUM",),
                  remediation_priority=2, next_stp_action="Move to temporal OOS (not ticker-OOS) once PIT history ≥ 60d"),
    ResearchItem("FUND-ACCUM", "FUNDAMENTALS", "F01-05", "Fundamentals daily PIT accumulator",
                  "Snapshot per asof · dedupe (ticker, asof) · unblocks 8+ quarter OOS over time",
                  remediation_priority=99, next_stp_action="Data pipeline · runs unattended daily · monitored by freshness check"),
]

# ── Other Deep Research Domains ──────────────────────────────────────────────
DOMAIN_ITEMS: list[ResearchItem] = [
    ResearchItem("D06-CS", "DOMAIN", "D06", "D06 Sector momentum cross-sectional rank",
                  "Sector 20d relative strength · breadth + leadership concentration"),
    ResearchItem("D06-P2", "DOMAIN", "D06", "D06 P2 Regime Ranking backtest",
                  "α×β grid on rec_history top-N · sector + market regime score"),
    ResearchItem("D08-FLOWS", "DOMAIN", "D08", "D08 Flows walk-forward (volume-spike)",
                  "recent_5d_vol / trailing_60d_vol threshold sweep · DSR"),
    ResearchItem("T09-BRK", "DOMAIN", "T09", "T09 Deep Technical breakout quality",
                  "New N-day high + high volume · forward 5d return"),
    ResearchItem("D14-RISK", "DOMAIN", "D14", "D14 Risk correlation + tail VaR + HHI",
                  "Portfolio-level pairwise correlation · VaR-95 · Herfindahl concentration"),
    ResearchItem("D15-KELLY", "DOMAIN", "D15", "D15 Portfolio fractional Kelly",
                  "Half-Kelly capped at 25% NAV · from realized win rate + payoff"),
    ResearchItem("D16-MAE", "DOMAIN", "D16", "D16 Exit Science MAE/MFE",
                  "Max Adverse Excursion + Max Favourable Excursion per closed position"),
    ResearchItem("D18-INT", "DOMAIN", "D18", "D18 Data Integrity audit",
                  "Survivorship + revision + delisting bias · both markets"),
    ResearchItem("D19-STAT", "DOMAIN", "D19", "D19 Statistical Robustness compliance",
                  "Walk-forward + OOS + DSR + Reality Check + multiple-testing correction audit"),
]

# ── Composite Layer ──────────────────────────────────────────────────────────
COMPOSITE_ITEMS: list[ResearchItem] = [
    ResearchItem("COMP-META", "COMPOSITE", "META", "Meta-ensemble composite score",
                  "Trust_Weight(r) × Runner_Score_r · IC-adaptive across R1/R2/R3"),
    ResearchItem("COMP-SHEET", "COMPOSITE", "META", "06_Composite_Signals sheet",
                  "Workbook renders cross-runner conviction classification"),
    ResearchItem("COMP-ADM", "COMPOSITE", "META", "Trust_Weight=0 admission gate",
                  "trailing_n<50 excludes runner from composite · GAP-2 reconciliation"),
]

# ── Standalone Programs ──────────────────────────────────────────────────────
STANDALONE_ITEMS: list[ResearchItem] = [
    ResearchItem("LT-COMPOUNDER-01", "STANDALONE", "Part C", "Compounder Watchlist · Winner/Failure Genome",
                  "Isolation contract · watchlist_id namespace · retrospective-only validation"),
    ResearchItem("STP", "STANDALONE", "Framework", "Standard Testing Pattern (STP)",
                  "T1-T5 default · auto worth verdict · single vocabulary"),
    ResearchItem("COV-13", "STANDALONE", "Framework", "13-stage Coverage Tracker",
                  "Mapped→Data-required→PIT-ready→Populated→Implemented→Tested→OOS→Corrected→Incremental→Paper→Shadow→Candidate→Production",
                  remediation_priority=99, next_stp_action="Framework · no STP applicable"),
    ResearchItem("EVIDENCE-ENGINE", "STANDALONE", "Framework",
                  "Cross-Cutting Evidence Engine (V2 PDF walk-forward + bootstrap + DSR + forward paper)",
                  "252/5/63/21 folds + paired bootstrap 10k + LR + DSR + forward paper/shadow + immutable Evidence Log · common infra for every research item",
                  remediation_priority=99, next_stp_action="Framework · consumed by all other items · no STP self-test"),
    ResearchItem("FORWARD-DAILY-RUNNER", "STANDALONE", "Framework",
                  "AUDIT-04 forward-paper daily orchestrator",
                  "scripts/evidence_engine_forward_daily.py · iterates frozen candidates · matures 5/10/20/60d outcomes · reports NO_ELIGIBLE_CANDIDATES until F01-F05 substrate mature",
                  remediation_priority=99, next_stp_action="Infra SHIPPED · runs daily · zero candidates until F01-F05 clears OOS"),
]


ALL_ITEMS: list[ResearchItem] = (R1_ITEMS + R2_ITEMS + R3_ITEMS + FUND_ITEMS
                                    + DOMAIN_ITEMS + COMPOSITE_ITEMS + STANDALONE_ITEMS)


def total_count() -> int:
    return len(ALL_ITEMS)


def by_runner(runner: str) -> list[ResearchItem]:
    return [x for x in ALL_ITEMS if x.runner == runner]


def find(item_id: str) -> Optional[ResearchItem]:
    for x in ALL_ITEMS:
        if x.id == item_id: return x
    return None


if __name__ == "__main__":
    for runner in ("R1", "R2", "R3", "FUNDAMENTALS", "DOMAIN", "COMPOSITE", "STANDALONE"):
        items = by_runner(runner)
        print(f"{runner}: {len(items)}")
    print(f"TOTAL: {total_count()}")
