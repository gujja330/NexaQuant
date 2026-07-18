"""Decision Attribution v1.0 · per-recommendation credit assignment.

For every current recommendation, decompose the decision into per-subsystem
contribution % (Research / Fusion / Winner Genome / Validation / Risk /
DNA / Sector / Market). Contributions sum to 100.

For subsystem-accuracy-over-time, join historical closed trades from
learning.parquet with the signal each subsystem produced at entry — the
result tells us WHICH subsystem was creating alpha and which was
destroying it.

Deterministic — sorted iteration, fixed weights per subsystem, min-max
normalisation on today's cohort.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"

# ── Fixed subsystem weights (deterministic; tuned to sum to ~1.0)
# These blend into the overall decision — every subsystem's raw signal is
# min-max scaled per cohort, then multiplied by its weight. Contribution %
# is the weight-adjusted share of the total.
SUBSYSTEM_WEIGHTS: dict[str, float] = {
    "research":        0.22,   # composite_decision_score
    "fusion":          0.20,   # intelligence_score (10-dimension weighted)
    "winner_genome":   0.14,   # n_matched × avg_lift
    "validation":      0.14,   # historical win_rate × reliability
    "risk":            0.10,   # sizing verdict + target_weight
    "dna":             0.08,   # DNA pattern priors
    "sector":          0.07,   # sector_score
    "market":          0.05,   # global_score
}


# ── Helpers ────────────────────────────────────────────────────────────

def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _minmax(x: pd.Series) -> pd.Series:
    """0..1 scaling; if all values equal → 0.5. NaN → 0."""
    s = x.astype(float)
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi <= lo:
        return s.notna().astype(float) * 0.5
    return ((s - lo) / (hi - lo)).fillna(0.0)


# ── Signal extraction from today's artifacts ───────────────────────────

def extract_current_signals() -> pd.DataFrame:
    """One row per current recommendation with the raw signal each
    subsystem produced. Columns = SUBSYSTEM_WEIGHTS.keys() + 'ticker'."""
    recs   = _load(REPORTS / "recommendations.json")           or {}
    intel  = _load(REPORTS / "investment_intelligence.json")   or {}
    wg     = _load(REPORTS / "winner_genome.json")             or {}
    sv     = _load(REPORTS / "stock_validation.json")          or {}
    risk   = _load(REPORTS / "risk_capital_v2_latest.json")    or {}
    dna    = _load(REPORTS / "recommendation_dna_feedback.json") or {}
    gc     = _load(REPORTS / "global_context.json")            or {}

    intel_by_ticker = {str(r.get("ticker")): r for r in (intel.get("reports") or [])}
    wg_matches      = wg.get("matches") or {}
    sv_tickers      = sv.get("tickers") or {}
    sizing_by_ticker = {str(s.get("ticker")): s for s in (risk.get("sizing") or [])}
    dna_by_ticker   = {}  # DNA feedback is pattern-level; skip per-ticker for v1.0
    global_score    = _global_signal_scalar(gc)

    rows: list[dict] = []
    for r in (recs.get("recommendations") or []):
        t = str(r.get("ticker") or "")
        if not t:
            continue
        ii   = intel_by_ticker.get(t) or {}
        wm   = wg_matches.get(t) or {}
        sv_r = sv_tickers.get(t) or {}
        rk   = sizing_by_ticker.get(t) or {}

        # Research: raw composite_decision_score, 0..100
        s_research = r.get("composite_decision_score")

        # Fusion: intelligence_score (0..100, from fusion engine)
        s_fusion   = ii.get("intelligence_score")

        # Winner Genome: matched signature "strength" ~ n_matched × avg_lift
        n_match    = wm.get("n_signatures_matched") or 0
        avg_lift   = wm.get("avg_signature_lift") or 0.0
        s_wg       = float(n_match) * float(avg_lift)   # 0 if no match

        # Validation: historical win_rate × (reliability_stars/5)
        wr         = sv_r.get("win_rate") or 0.0
        rel        = (sv_r.get("reliability_stars") or 0) / 5.0
        s_valid    = float(wr) * rel

        # Risk: target_weight if not BLOCK, otherwise 0
        verdict    = (rk.get("verdict") or "").upper()
        tw         = float(rk.get("target_weight") or 0.0)
        if verdict == "BLOCK":     s_risk = 0.0
        elif verdict == "WARNING": s_risk = tw * 0.5
        else:                      s_risk = tw

        # DNA: pattern-level average prior applied uniformly (no per-ticker mapping
        # in DNA feedback v1.5). Signal = mean of high-prior pattern win-rates.
        # This is a placeholder until DNA v2.0 exposes per-ticker priors.
        s_dna      = _dna_scalar(dna)

        # Sector: sector_score (0..100)
        s_sector   = r.get("sector_score")

        # Market: global_score (per-day scalar, same for every ticker today)
        s_market   = global_score

        rows.append({
            "ticker":         t,
            "research":       s_research,
            "fusion":         s_fusion,
            "winner_genome":  s_wg,
            "validation":     s_valid,
            "risk":           s_risk,
            "dna":            s_dna,
            "sector":         s_sector,
            "market":         s_market,
        })

    df = pd.DataFrame(rows).sort_values("ticker", kind="mergesort").reset_index(drop=True)
    return df


def _dna_scalar(dna: dict) -> float:
    """Pattern-level average prior (0..1) — DNA v1.5 does not expose
    per-ticker priors. Placeholder until DNA v2.0 lands."""
    priors_hi = dna.get("priors_high") or []
    if not priors_hi:
        return 0.5
    vals = [p.get("prior") for p in priors_hi if p.get("prior") is not None]
    if not vals:
        return 0.5
    return float(sum(vals) / len(vals))


def _global_signal_scalar(gc: dict) -> float:
    """Extract a bull/bear scalar from global_context. Positive = risk-on,
    negative = risk-off. Falls back to 0 (neutral)."""
    # composites.global_risk is a decent proxy: lower = more risk-on
    comps = gc.get("composites") or {}
    gr    = comps.get("global_risk")
    if isinstance(gr, dict):
        z = gr.get("z_score") or gr.get("value") or 0.0
        # Invert (high risk → low market signal)
        return float(-z) if z is not None else 0.0
    return 0.0


# ── Contribution % per recommendation ──────────────────────────────────

def compute_contributions(signals: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker weighted contribution % — sums to 100 for each row."""
    if signals.empty:
        return signals

    scaled = pd.DataFrame(index=signals.index)
    scaled["ticker"] = signals["ticker"]
    for subsystem in SUBSYSTEM_WEIGHTS:
        s = signals[subsystem] if subsystem in signals.columns else pd.Series([0.0] * len(signals))
        scaled[subsystem + "_scaled"] = _minmax(s)

    # Weighted signal per subsystem
    weighted = pd.DataFrame(index=signals.index)
    weighted["ticker"] = signals["ticker"]
    for subsystem, w in SUBSYSTEM_WEIGHTS.items():
        weighted[subsystem] = scaled[subsystem + "_scaled"] * w

    # Normalize so each row sums to 100
    subsystem_cols = list(SUBSYSTEM_WEIGHTS.keys())
    row_totals = weighted[subsystem_cols].sum(axis=1)
    for col in subsystem_cols:
        with np.errstate(divide="ignore", invalid="ignore"):
            weighted[col] = np.where(row_totals > 0,
                                       (weighted[col] / row_totals) * 100.0,
                                       100.0 / len(subsystem_cols))
    weighted["decision_strength"] = row_totals   # unnormalised, for sorting
    return weighted


# ── Subsystem accuracy from learning.parquet ───────────────────────────

def subsystem_accuracy_over_time() -> dict:
    """For every subsystem where we have historical signals in learning.parquet,
    compute an accuracy score = P(winner | subsystem said high).

    Uses learning.parquet columns:
      score_at_entry           → research subsystem historical signal
      confidence               → fusion proxy (confidence is fusion-tier output)
      dim_momentum/dim_trend/… → per-dimension signals feeding fusion
      is_winner                → outcome
    """
    p = REPORTS / "learning.parquet"
    if not p.exists():
        return {"available": False, "reason": "learning.parquet missing"}
    lf = pd.read_parquet(p)
    if lf.empty or "is_winner" not in lf.columns:
        return {"available": False, "reason": "no winner labels"}

    # normalize return_pct if stored as percent
    if "return_pct" in lf.columns and lf["return_pct"].abs().median() > 1.0:
        lf["return_pct"] = lf["return_pct"] / 100.0

    baseline_wr = float(lf["is_winner"].mean())
    signals_map = {
        "research":  "score_at_entry",
        "fusion":    "confidence",
        # dimension signals as proxies (loosely mapped to subsystems)
        "momentum":  "dim_momentum",
        "trend":     "dim_trend",
        "rs_nifty":  "dim_rs_nifty",
        "volatility":"dim_volatility",
        "drawdown":  "dim_drawdown",
        "position_52w": "dim_position_52w",
    }

    accuracy: dict[str, dict] = {}
    for subsystem, col in signals_map.items():
        if col not in lf.columns:
            continue
        s = lf[col].dropna()
        if s.empty:
            continue

        # Split at the 60th percentile: "high signal" cohort
        thresh = float(s.quantile(0.60))
        high_mask = lf[col] >= thresh
        low_mask  = lf[col] <  thresh
        if int(high_mask.sum()) < 20 or int(low_mask.sum()) < 20:
            continue

        wr_high = float(lf.loc[high_mask, "is_winner"].mean())
        wr_low  = float(lf.loc[low_mask,  "is_winner"].mean())
        # Alpha contribution: lift of "high signal" over baseline, minus
        # penalty for "low signal" being worse than baseline
        lift = wr_high / baseline_wr if baseline_wr > 0 else 0.0
        alpha_created = wr_high - baseline_wr    # positive = adds alpha
        # Return contribution
        avg_ret_high = float(lf.loc[high_mask, "return_pct"].mean()) if "return_pct" in lf.columns else None
        avg_ret_low  = float(lf.loc[low_mask,  "return_pct"].mean()) if "return_pct" in lf.columns else None

        accuracy[subsystem] = {
            "signal_column":   col,
            "n_high_signal":   int(high_mask.sum()),
            "n_low_signal":    int(low_mask.sum()),
            "threshold":       round(thresh, 4),
            "wr_high":         round(wr_high, 4),
            "wr_low":          round(wr_low, 4),
            "baseline_wr":     round(baseline_wr, 4),
            "lift":            round(lift, 3),
            "alpha_created":   round(alpha_created, 4),
            "avg_return_high": round(avg_ret_high, 4) if avg_ret_high is not None else None,
            "avg_return_low":  round(avg_ret_low, 4)  if avg_ret_low  is not None else None,
            "verdict":         "alpha_creator" if alpha_created > 0.02 else
                                 "alpha_destroyer" if alpha_created < -0.02 else "neutral",
        }
    return {
        "available":    True,
        "baseline_wr":  round(baseline_wr, 4),
        "n_trades":     int(len(lf)),
        "subsystems":   accuracy,
    }


# ── Winners / losers subsystem attribution (for closed trades) ─────────

def per_trade_attribution() -> list[dict]:
    """For each historical closed trade, compute a rough per-subsystem
    'contribution to outcome' — did each subsystem's signal align with the
    realized outcome? Returns a list of trade-level attribution rows."""
    p = REPORTS / "learning.parquet"
    if not p.exists():
        return []
    lf = pd.read_parquet(p)
    if lf.empty:
        return []

    if "return_pct" in lf.columns and lf["return_pct"].abs().median() > 1.0:
        lf["return_pct"] = lf["return_pct"] / 100.0

    # Signals available in learning.parquet mapped to subsystems
    signal_cols = {
        "research":     "score_at_entry",
        "fusion":       "confidence",
        "momentum":     "dim_momentum",
        "trend":        "dim_trend",
        "rs_nifty":     "dim_rs_nifty",
        "volatility":   "dim_volatility",
        "drawdown":     "dim_drawdown",
        "position_52w": "dim_position_52w",
    }
    thresholds = {}
    for sub, col in signal_cols.items():
        if col in lf.columns:
            thresholds[sub] = float(lf[col].dropna().quantile(0.60))

    out: list[dict] = []
    for _, r in lf.iterrows():
        wins = bool(r.get("is_winner"))
        entry = {
            "ticker":       str(r.get("ticker")),
            "entry_date":   str(r.get("entry_date"))[:10] if pd.notna(r.get("entry_date")) else None,
            "return_pct":   float(r["return_pct"]) if pd.notna(r.get("return_pct")) else None,
            "is_winner":    wins,
        }
        contributions: dict[str, str] = {}
        for sub, col in signal_cols.items():
            if col not in lf.columns:
                continue
            v = r.get(col)
            if pd.isna(v):
                contributions[sub] = "no_signal"
                continue
            said_high = float(v) >= thresholds[sub]
            if said_high and wins:      contributions[sub] = "correct"
            elif said_high and not wins:contributions[sub] = "false_positive"
            elif (not said_high) and (not wins): contributions[sub] = "correct_reject"
            else:                        contributions[sub] = "missed_winner"
        entry["subsystem_calls"] = contributions
        out.append(entry)
    return out


# ── Top-level ──────────────────────────────────────────────────────────

def run_attribution() -> dict:
    signals = extract_current_signals()
    contribs = compute_contributions(signals)

    per_rec: dict[str, dict] = {}
    if not signals.empty:
        subsystem_cols = list(SUBSYSTEM_WEIGHTS.keys())
        for i in range(len(signals)):
            t = str(signals.iloc[i]["ticker"])
            contributions = {s: round(float(contribs.iloc[i][s]), 2)
                             for s in subsystem_cols}
            raw_signals = {s: (float(signals.iloc[i][s]) if pd.notna(signals.iloc[i][s]) else None)
                           for s in subsystem_cols}
            per_rec[t] = {
                "contributions":    contributions,
                "raw_signals":      raw_signals,
                "decision_strength": round(float(contribs.iloc[i]["decision_strength"]), 4),
            }

    accuracy = subsystem_accuracy_over_time()
    trade_attrib = per_trade_attribution()

    # Cross-cutting: which subsystem was the biggest alpha creator / destroyer?
    creators, destroyers = [], []
    if accuracy.get("available") and accuracy.get("subsystems"):
        by_alpha = sorted(accuracy["subsystems"].items(),
                            key=lambda kv: -kv[1]["alpha_created"])
        creators   = [{"subsystem": k, **v} for k, v in by_alpha[:5]]
        destroyers = [{"subsystem": k, **v}
                        for k, v in sorted(accuracy["subsystems"].items(),
                                             key=lambda kv: kv[1]["alpha_created"])[:5]
                        if v["alpha_created"] < 0]

    return {
        "engine":              "decision_attribution",
        "version":             "v1.0",
        "n_recommendations":   len(per_rec),
        "subsystem_weights":   dict(SUBSYSTEM_WEIGHTS),
        "per_recommendation":  per_rec,
        "subsystem_accuracy":  accuracy,
        "n_trade_attributions": len(trade_attrib),
        "top_alpha_creators":  creators,
        "top_alpha_destroyers": destroyers,
    }
