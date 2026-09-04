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


# ── R1 ──────────────────────────────────────────────────────────────────────
R1_ITEMS: list[ResearchItem] = [
    ResearchItem("R1.1", "R1", "Self-analysis", "R1 engine self-analysis · 3 candidate models",
                  "Code trace · verify baseline HGB + LR + heuristic still running · Precision@10 selector"),
    ResearchItem("R1.2", "R1", "Perf-analysis", "R1 real 25-trade performance analysis",
                  "Query registry · exclude admin exits · sector + filter-strategy hypotheticals"),
    ResearchItem("R1.5.3", "R1", "KG-filter", "KG-community rolling group filter",
                  "Replace static GICS with 57 KG communities · rolling top-N acceptance"),
    ResearchItem("R1.7", "R1", "Governance", "8th Research Trigger · Signal Silence",
                  "N≥10 day silence + comparator observation · never fires when all runners silent"),
    ResearchItem("R1.9-S1", "R1", "Delivery", "R1 advisory sheet 05_R1_Advisory",
                  "Workbook builder emits R1 daily picks as advisory sheet"),
    ResearchItem("R1-OPT1", "R1", "Delivery", "R1 rows in 01_Investments ACTIVE section",
                  "Scoped C19 deviation · load R1 ACTIVE from registry · SUGGESTED-tag stop"),
    ResearchItem("R1-BANNER", "R1", "Delivery", "R1 no-dynamic-exit-protection banner",
                  "INVESTMENTS_BANNER updated per V2 §R1.9 Stage 1 precondition"),
]

# ── R2 ──────────────────────────────────────────────────────────────────────
R2_ITEMS: list[ResearchItem] = [
    ResearchItem("P0", "R2", "P0", "Dynamic Exit Bridge · retrospective replay",
                  "Walk-forward counterfactual replay on 539 closes · paired bootstrap"),
    ResearchItem("P1", "R2", "P1", "Confidence Calibration on Delivered Output",
                  "Platt A/B fit · ECE ≤0.05 gate · sustained 4-refit acceptance"),
    ResearchItem("P2", "R2", "P2", "Sector/Regime-Adjusted Ranking",
                  "α·Sector_Regime + β·Market_Regime · walk-forward α/β grid + DSR"),
    ResearchItem("P3", "R2", "P3", "KG Community-Relative Scoring",
                  "γ sweep · Final = (1−γ)·Global_Percentile + γ·Community_Percentile"),
    ResearchItem("P4", "R2", "P4", "Cap × Sector Interaction Study",
                  "Interaction table + likelihood-ratio test on nested logistic"),
    ResearchItem("P5.1", "R2", "P5", "Ensemble disagreement display + sizing",
                  "stdev across 11 models · correlate with error magnitude"),
    ResearchItem("P5.2", "R2", "P5", "Regime-conditional ensemble weights",
                  "Per-regime IC-weighted · fallback to global when bucket n<30"),
    ResearchItem("P5.3", "R2", "P5", "Daily turnover / rotation cap",
                  "Rotation budget X% NAV/day · top-N by expected-alpha-delta"),
    ResearchItem("P5.4", "R2", "P5", "PIT universe audit",
                  "S&P/NSE membership drift reconstruction per historical trade date"),
    ResearchItem("P5.5", "R2", "P5", "Standing post-R1 fixed comparator",
                  "Equal-weight top-10 by 3-month momentum · monthly rebalance · no tuning"),
    ResearchItem("R2-USA-PARQUET", "R2", "Data", "USA price parquet drift root fix",
                  "Un-gitignore + workflow commit-back · workstation-CI sync"),
    ResearchItem("R2-ZERO-DIAG", "R2", "Diagnostic", "R2 zero-entry diagnosis",
                  "Registry scan + rec_v3 verdict analysis · Signal Silence eval"),
]

# ── R3 ──────────────────────────────────────────────────────────────────────
R3_ITEMS: list[ResearchItem] = [
    ResearchItem("II.1-GBM", "R3", "II.1", "GBM primary model family", "LightGBM WF 252/63/21/5 · SHAP importance", "Tier 1"),
    ResearchItem("II.1-STK", "R3", "II.1", "Ensemble stacking", "Meta-learner logistic on GBM+R2_base+KG scores", "Tier 2"),
    ResearchItem("II.1-GNN", "R3", "II.1", "GraphSAGE on KG", "2-layer message passing · end-to-end vs outcome", "Tier 2/3"),
    ResearchItem("II.1-BMA", "R3", "II.1", "Bayesian model averaging", "Posterior_weight ∝ Prior × Likelihood(IC)", "Tier 2"),
    ResearchItem("II.2-FN", "R3", "II.2", "Factor-neutral scoring", "Residual = base − Σβ·factor exposure (cross-section)", "Tier 2"),
    ResearchItem("II.2-PAIR", "R3", "II.2", "Peer-pair statistical arbitrage", "Engle-Granger cointegration · ADF residual test", "Tier 3"),
    ResearchItem("II.3-CUSUM", "R3", "II.3", "CUSUM change-point detection", "S_t = max(0, S_(t-1) + (x_t − μ − k)) · flag at h", "Tier 3"),
    ResearchItem("II.4-PIOT", "R3", "II.4", "Piotroski F-score", "9-binary formula on TTM fundamentals", "Tier 1"),
    ResearchItem("II.4-BENE", "R3", "II.4", "Beneish M-score", "8-variable earnings-manipulation formula · threshold −1.78", "Tier 1"),
    ResearchItem("II.4-GOV", "R3", "II.4", "Governance India screen", "Pledge % + related-party frequency", "Tier 2"),
    ResearchItem("II.5-REV", "R3", "II.5", "Analyst estimate revision momentum", "(EPS_now − EPS_3mo) / |EPS_3mo|", "Tier 1"),
    ResearchItem("II.5-TONE", "R3", "II.5", "Transcript tone Q&A", "Finance-tuned tone · Q&A separated from prepared remarks", "Tier 2"),
    ResearchItem("II.6-MH", "R3", "II.6", "Multi-horizon consensus", "sign_match(5d, 17d) · conviction ×1.15/×0.7", "Tier 1"),
]

# ── F01-F05 Fundamentals ─────────────────────────────────────────────────────
FUND_ITEMS: list[ResearchItem] = [
    ResearchItem("F01-05-COMP", "FUNDAMENTALS", "F01-05", "F01-05 Composite (Piotroski + FCF + IntCov − Beneish)",
                  "Cross-sectional z-score decile lift · top vs bottom decile"),
    ResearchItem("F01-05-GRID", "FUNDAMENTALS", "F01-05", "F01-05 Filter Grid (11 threshold variants)",
                  "DSR-deflated multi-testing · combined + individual filters"),
    ResearchItem("F01-05-OOS", "FUNDAMENTALS", "F01-05", "F01-05 OOS ticker-partition",
                  "Deterministic hash-split 70/30 · fit on train tickers · eval on test tickers"),
    ResearchItem("FUND-ACCUM", "FUNDAMENTALS", "F01-05", "Fundamentals daily PIT accumulator",
                  "Snapshot per asof · dedupe (ticker, asof) · unblocks 8+ quarter OOS over time"),
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
                  "Mapped→Data-required→PIT-ready→Populated→Implemented→Tested→OOS→Corrected→Incremental→Paper→Shadow→Candidate→Production"),
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
