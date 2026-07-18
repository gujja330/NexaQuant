"""Recommendation DNA v2.0 · Winner Genome.

Mines the historical trade record for the *pre-trade characteristics*
that separated top-decile winners from the rest. Emits an Alpha Signature
library and per-current-recommendation match score.

Method (deterministic):
  1. Load closed trades from learning.parquet (fallback) or the Institutional
     Memory archive (preferred, once ≥ N days accumulate).
  2. Discretise every candidate feature into deterministic quintile buckets.
  3. For each (feature, bucket) cell: winner_rate, lift = winner_rate / baseline,
     χ² statistic, p-value. Keep cells with lift ≥ 1.30 and n ≥ 15.
  4. Group high-lift cells into Alpha Signatures via greedy conjunction:
     the top-lift single feature is the seed, then any co-occurring feature
     bucket that materially raises the joint lift is added.
  5. For every current recommendation, score how many signatures it matches
     and emit a plain-language "looks similar to N historical winners" summary.

Fixed random_state everywhere. Sorted iteration for reproducibility.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
LEARNING = _ROOT / "reports" / "learning.parquet"
RECS     = _ROOT / "reports" / "recommendations.json"
INTEL    = _ROOT / "reports" / "investment_intelligence.json"
PRICES   = _ROOT / "reports" / "price_context.json"

RANDOM_STATE = 42

# ── Feature engineering ─────────────────────────────────────────────────

# Continuous features from learning.parquet + engineered ones.
# NOTE: n_bars_held is realized in the training set but a *predicted* value on
# current recommendations — mismatched semantics, so it's used for training-set
# insight only and excluded from current-rec matching (see MATCH_FEATURES).
CONT_FEATURES = [
    "score_at_entry",
    "confidence",
    "dim_momentum", "dim_trend", "dim_rs_nifty",
    "dim_volatility", "dim_drawdown", "dim_position_52w",
]
CAT_FEATURES = ["sector", "industry"]

# Number of quintile buckets for continuous features
N_BUCKETS = 5


def _bucket_labels(n: int) -> list[str]:
    if n == 5:  return ["very_low", "low", "medium", "high", "very_high"]
    if n == 3:  return ["low", "medium", "high"]
    return [f"q{i+1}" for i in range(n)]


def _bucketize(series: pd.Series, n: int = N_BUCKETS) -> pd.Series:
    """Assign quintile bucket labels. NaN preserved."""
    s = series.dropna()
    if s.empty:
        return pd.Series([None] * len(series), index=series.index, dtype=object)
    try:
        cats = pd.qcut(s, n, labels=_bucket_labels(n), duplicates="drop")
    except (ValueError, IndexError):
        return pd.Series([None] * len(series), index=series.index, dtype=object)
    out = pd.Series([None] * len(series), index=series.index, dtype=object)
    out.loc[s.index] = cats.astype(str)
    return out


# ── Loading historical trades ──────────────────────────────────────────

def load_trades(min_trades: int = 30) -> pd.DataFrame:
    """Load closed trades. Empty DataFrame if fewer than `min_trades`."""
    if not LEARNING.exists():
        return pd.DataFrame()
    df = pd.read_parquet(LEARNING)
    if "is_winner" not in df.columns or "return_pct" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["return_pct"]).copy()
    if len(df) < min_trades:
        return df.iloc[0:0].copy()

    # learning.parquet stores return_pct as percent (e.g. 6.17); normalise to fraction
    if df["return_pct"].abs().median() > 1.0:
        df["return_pct"] = df["return_pct"] / 100.0
    for c in ("mfe_pct", "mae_pct"):
        if c in df.columns and df[c].abs().median() > 1.0:
            df[c] = df[c] / 100.0

    # Winner definition (top decile of realised return)
    top10_thresh = df["return_pct"].quantile(0.90)
    df["is_top_decile"] = df["return_pct"] >= top10_thresh
    return df.sort_values(["ticker", "entry_date"], kind="mergesort").reset_index(drop=True)


# ── Signature mining ───────────────────────────────────────────────────

def _cell_stats(df: pd.DataFrame, mask: pd.Series, target: str) -> dict:
    """Compute {n, n_winners, winner_rate, lift, chi2, p_value} for a cell.

    Deterministic — every input flows from sorted DataFrames.
    """
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "n_winners": 0, "winner_rate": 0.0, "lift": 0.0,
                "chi2": 0.0, "p_value": 1.0}
    n_win_in_cell    = int(df.loc[mask, target].sum())
    n_win_total      = int(df[target].sum())
    n_total          = len(df)
    baseline         = n_win_total / n_total if n_total else 0.0
    winner_rate      = n_win_in_cell / n if n else 0.0
    lift             = (winner_rate / baseline) if baseline > 0 else 0.0

    # χ² for a 2x2 contingency [in_cell × is_winner]
    a = n_win_in_cell
    b = n - a
    c = n_win_total - a
    d = n_total - n - c
    expected = np.array([
        [(a + b) * (a + c) / n_total, (a + b) * (b + d) / n_total],
        [(c + d) * (a + c) / n_total, (c + d) * (b + d) / n_total],
    ]) if n_total else np.zeros((2, 2))
    observed = np.array([[a, b], [c, d]])
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2_terms = np.where(expected > 0, (observed - expected) ** 2 / expected, 0.0)
    chi2 = float(chi2_terms.sum())
    # Approximate p-value from χ² df=1 (asymptotic)
    p_value = float(math.erfc(math.sqrt(chi2 / 2))) if chi2 > 0 else 1.0

    return {"n": n, "n_winners": n_win_in_cell,
            "winner_rate": round(winner_rate, 4),
            "lift": round(lift, 3),
            "chi2": round(chi2, 3), "p_value": round(p_value, 4)}


def mine_cells(df: pd.DataFrame,
                 min_n: int = 15, min_lift: float = 1.30) -> list[dict]:
    """One (feature, bucket) row per cell that beats the thresholds."""
    if df.empty: return []
    target = "is_top_decile"

    # Prepare bucketised copy
    work = df.copy()
    for f in CONT_FEATURES:
        if f in work.columns:
            work[f + "_b"] = _bucketize(work[f])
    features_bucketed = [f + "_b" for f in CONT_FEATURES if f + "_b" in work.columns]
    features_cat      = [f for f in CAT_FEATURES if f in work.columns]

    cells: list[dict] = []
    for feat in features_bucketed + features_cat:
        vals = sorted([v for v in work[feat].dropna().unique().tolist()])
        for v in vals:
            mask = work[feat] == v
            s = _cell_stats(work, mask, target)
            if s["n"] < min_n or s["lift"] < min_lift:
                continue
            cells.append({
                "feature":  feat.replace("_b", ""),
                "bucket":   v,
                "kind":     "quantile" if feat.endswith("_b") else "categorical",
                **s,
            })
    cells.sort(key=lambda c: (-c["lift"], -c["chi2"], c["feature"], c["bucket"]))
    return cells


def _greedy_signature(seed_cell: dict, df: pd.DataFrame,
                        candidate_cells: list[dict], max_features: int = 4) -> dict:
    """Build a multi-feature signature by greedily conjoining with other cells."""
    target = "is_top_decile"
    work = df.copy()
    for f in CONT_FEATURES:
        if f in work.columns:
            work[f + "_b"] = _bucketize(work[f])

    def _mask_for(cell: dict) -> pd.Series:
        col = cell["feature"] + ("_b" if cell["kind"] == "quantile" else "")
        return work[col] == cell["bucket"]

    chosen: list[dict] = [seed_cell]
    mask = _mask_for(seed_cell)
    used_features = {seed_cell["feature"]}

    for cell in candidate_cells:
        if len(chosen) >= max_features: break
        if cell["feature"] in used_features: continue
        new_mask = mask & _mask_for(cell)
        s = _cell_stats(work, new_mask, target)
        if s["n"] < 6:                          # too specific
            continue
        # Accept if lift materially improves
        prev_stats = _cell_stats(work, mask, target)
        if s["lift"] < prev_stats["lift"] * 1.05:
            continue
        chosen.append(cell)
        used_features.add(cell["feature"])
        mask = new_mask

    joint = _cell_stats(work, mask, target)
    return {
        "features": [{"feature": c["feature"], "bucket": c["bucket"],
                      "kind":    c["kind"]} for c in chosen],
        "n":                joint["n"],
        "n_winners":        joint["n_winners"],
        "winner_rate":      joint["winner_rate"],
        "lift":             joint["lift"],
        "chi2":             joint["chi2"],
        "p_value":          joint["p_value"],
    }


def _signature_fingerprint(sig: dict) -> str:
    """Canonical fingerprint = sorted (feature,bucket) pairs. Order-independent."""
    return "|".join(sorted(f'{f["feature"]}={f["bucket"]}' for f in sig["features"]))


def build_signatures(df: pd.DataFrame,
                       min_n: int = 15, min_lift: float = 1.30,
                       max_signatures: int = 20) -> list[dict]:
    """Compose top signatures via greedy conjunction from mined cells.

    Deduplicates by canonical feature-set fingerprint so
    'A=x · B=y' and 'B=y · A=x' collapse into one signature.
    """
    cells = mine_cells(df, min_n=min_n, min_lift=min_lift)
    if not cells:
        return []
    signatures: list[dict] = []
    seen_seeds:     set[str] = set()
    seen_fingerprints: set[str] = set()
    for seed in cells:
        seed_key = f"{seed['feature']}:{seed['bucket']}"
        if seed_key in seen_seeds:
            continue
        seen_seeds.add(seed_key)
        sig = _greedy_signature(seed, df, cells)
        fp = _signature_fingerprint(sig)
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        signatures.append(sig)
        if len(signatures) >= max_signatures:
            break

    # Deterministic ordering
    signatures.sort(key=lambda s: (-s["lift"], -s["chi2"], -s["n"]))
    # Assign stable IDs (1-based, ordered)
    for i, s in enumerate(signatures, 1):
        s["signature_id"] = i
        s["fingerprint"]  = _signature_fingerprint(s)
    return signatures


def enrich_signature_returns(signatures: list[dict], df: pd.DataFrame) -> None:
    """Attach `avg_return`, `median_return`, `sample` fields for each signature."""
    if df.empty:
        return
    work = df.copy()
    for f in CONT_FEATURES:
        if f in work.columns:
            work[f + "_b"] = _bucketize(work[f])

    for sig in signatures:
        mask = pd.Series(True, index=work.index)
        for f in sig["features"]:
            col = f["feature"] + ("_b" if f["kind"] == "quantile" else "")
            mask = mask & (work[col] == f["bucket"])
        sample = work[mask]
        if sample.empty:
            sig["avg_return"] = None
            sig["median_return"] = None
            sig["sample"] = 0
            continue
        sig["avg_return"]    = round(float(sample["return_pct"].mean()), 4)
        sig["median_return"] = round(float(sample["return_pct"].median()), 4)
        sig["sample"]        = int(len(sample))
        # Deterministic sample tickers (up to 5, sorted)
        winners_in_sample = sample[sample["is_top_decile"]]
        sig["example_winners"] = sorted(
            winners_in_sample["ticker"].astype(str).unique().tolist()
        )[:5]


# ── Current-recommendation matching ────────────────────────────────────

def _feature_snapshot_for_current(rec_json: dict, intel_json: dict, price_json: dict,
                                    df_bucket_edges: dict[str, list[float]]) -> pd.DataFrame:
    """Reconstruct a per-ticker feature snapshot for TODAY's recommendations,
    using the same bucketisation edges the training set produced."""
    intel_by_ticker: dict[str, dict] = {}
    for r in (intel_json.get("reports") or []):
        intel_by_ticker[str(r.get("ticker"))] = r

    rows = []
    for r in (rec_json.get("recommendations") or []):
        t = r.get("ticker")
        if not t: continue
        ii = intel_by_ticker.get(str(t), {})
        # Map fusion dimensions back to learning-parquet dims where possible
        dims = {d["name"]: d.get("score") for d in (ii.get("dimensions") or [])}
        rows.append({
            "ticker":            t,
            "sector":            r.get("sector"),
            "industry":          r.get("industry"),
            "score_at_entry":    r.get("composite_decision_score"),
            "confidence":        r.get("confidence"),
            "dim_momentum":      dims.get("momentum") or dims.get("technical"),
            "dim_trend":         dims.get("trend"),
            "dim_rs_nifty":      dims.get("relative_strength"),
            "dim_volatility":    dims.get("volatility") or dims.get("risk"),
            "dim_drawdown":      dims.get("drawdown"),
            "dim_position_52w":  dims.get("position_52w") or dims.get("technical"),
            "n_bars_held":       (r.get("entry_exit") or {}).get("expected_holding_days"),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)

    # Apply the SAME edges the training set used, so buckets align.
    for f in CONT_FEATURES:
        if f not in df.columns: continue
        edges = df_bucket_edges.get(f)
        if not edges:
            df[f + "_b"] = None
            continue
        labels = _bucket_labels(len(edges) - 1)
        try:
            df[f + "_b"] = pd.cut(df[f], bins=edges, labels=labels,
                                    include_lowest=True).astype(object)
        except Exception:
            df[f + "_b"] = None
    return df


def _training_bucket_edges(df: pd.DataFrame) -> dict[str, list[float]]:
    """Return the qcut bucket edges used for each continuous feature in `df`."""
    out: dict[str, list[float]] = {}
    for f in CONT_FEATURES:
        if f not in df.columns: continue
        s = df[f].dropna()
        if s.empty: continue
        try:
            _, edges = pd.qcut(s, N_BUCKETS, retbins=True, duplicates="drop")
        except (ValueError, IndexError):
            continue
        out[f] = [float(x) for x in edges]
    return out


def match_current(signatures: list[dict], trades_df: pd.DataFrame) -> dict:
    """For every current recommendation, count matching signatures."""
    if not RECS.exists():
        return {}
    rec_json   = json.loads(RECS.read_text(encoding="utf-8"))
    intel_json = json.loads(INTEL.read_text(encoding="utf-8")) if INTEL.exists() else {}
    price_json = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else {}
    edges = _training_bucket_edges(trades_df)

    df_cur = _feature_snapshot_for_current(rec_json, intel_json, price_json, edges)
    if df_cur.empty:
        return {}

    matches: dict[str, dict] = {}
    for _, row in df_cur.iterrows():
        t = str(row["ticker"])
        matched: list[dict] = []
        for sig in signatures:
            hit = True
            for f in sig["features"]:
                col = f["feature"] + ("_b" if f["kind"] == "quantile" else "")
                v = row.get(col)
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    hit = False; break
                if str(v) != str(f["bucket"]):
                    hit = False; break
            if hit:
                matched.append(sig)

        if matched:
            n_hist_winners  = sum(s.get("n_winners", 0) for s in matched)
            n_hist_sample   = sum(s.get("n", 0) for s in matched)
            avg_lift        = round(float(np.mean([s["lift"] for s in matched])), 3)
            best_avg_return = max((s.get("avg_return") or 0.0) for s in matched)
            hist_success    = round(n_hist_winners / n_hist_sample, 3) if n_hist_sample else 0.0
            plain_language  = (
                f"Looks similar to {n_hist_winners} historical top-decile winners · "
                f"avg return {best_avg_return * 100:.1f}% · "
                f"historical success {hist_success * 100:.0f}%"
            )
        else:
            n_hist_winners = 0; hist_success = 0.0; avg_lift = 0.0; best_avg_return = 0.0
            plain_language = "No signature match today · profile not seen among top-decile winners"

        matches[t] = {
            "ticker":                 t,
            "n_signatures_matched":   len(matched),
            "signature_ids":          [s["signature_id"] for s in matched],
            "n_historical_winners":   n_hist_winners,
            "historical_success":     hist_success,
            "avg_signature_lift":     avg_lift,
            "best_avg_return":        round(best_avg_return, 4),
            "plain_language":         plain_language,
        }
    return matches


# ── Top-level ──────────────────────────────────────────────────────────

def run_winner_genome(
    min_trades: int = 30,
    min_n: int = 15,
    min_lift: float = 1.30,
    max_signatures: int = 20,
) -> dict:
    """One-call entry point. Returns a dashboard-ready dict."""
    df = load_trades(min_trades=min_trades)
    if df.empty or "is_top_decile" not in df.columns:
        return {
            "engine":        "recommendation_dna",
            "version":       "v2.0",
            "mode":          "insufficient_data",
            "n_trades":      0,
            "n_top_decile":  0,
            "signatures":    [],
            "matches":       {},
            "note":          f"Need ≥ {min_trades} closed trades to mine signatures.",
        }

    signatures = build_signatures(df, min_n=min_n, min_lift=min_lift,
                                     max_signatures=max_signatures)
    enrich_signature_returns(signatures, df)
    matches = match_current(signatures, df)

    n_matched = sum(1 for v in matches.values() if v["n_signatures_matched"] > 0)
    return {
        "engine":         "recommendation_dna",
        "version":        "v2.0",
        "mode":           "learning_parquet",   # switches to "archive" when the archive is deep enough
        "n_trades":       int(len(df)),
        "n_top_decile":   int(df["is_top_decile"].sum()),
        "top_decile_threshold": round(float(df["return_pct"].quantile(0.90)), 4),
        "n_signatures":   len(signatures),
        "n_current_matched": n_matched,
        "signatures":     signatures,
        "matches":        matches,
        "random_state":   RANDOM_STATE,
    }
