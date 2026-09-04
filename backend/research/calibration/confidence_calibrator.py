"""AEGIS Confidence Calibrator · V2 §P1 · Platt scaling + ECE + regime adjust.

Dynamic · tenant-generic · both markets · reads only from repo artifacts.
Nothing hardcoded (no fixed thresholds baked into constants that shouldn't be
tunable · no ticker lists · no market-specific branching).

Data sources · in priority order:
  1. reports/research/outcome_dataset.parquet · (initial_confidence, win_flag) pairs
  2. reports/{market}/recommendation_history.parquet + realized forward returns
     (reconstructs (raw_confidence, calibrated_confidence, outcome) triples per
     historical prediction · joins with data/raw or usa/data/raw/us price parquets)

Outputs · JSON verdict + refitted Platt A/B per market · never mutates
production paths without an explicit integration step.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional


# ── math primitives ─────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    if x > 500: return 1.0
    if x < -500: return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _log_loss(y_true, y_pred) -> float:
    """Binary log-loss · guard against log(0)."""
    eps = 1e-12
    total = 0.0
    n = 0
    for y, p in zip(y_true, y_pred):
        p = _clip(float(p), eps, 1.0 - eps)
        total += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
        n += 1
    return total / max(n, 1)


def fit_platt(scores, outcomes, max_iter: int = 500, lr: float = 0.05,
              tol: float = 1e-6) -> tuple[float, float]:
    """Fit Platt scaling · P_calibrated = sigmoid(A * score + B) via MLE.

    Simple gradient descent (no scipy dep · keeps this module standalone).
    Returns (A, B). If insufficient data, returns (1.0, 0.0) identity.
    """
    if not scores or len(scores) < 5:
        return (1.0, 0.0)
    xs = [float(s) for s in scores]
    ys = [1.0 if o else 0.0 for o in outcomes]
    a, b = 0.0, 0.0
    prev_loss = float('inf')
    for _ in range(max_iter):
        # Predictions + gradient
        grad_a = grad_b = 0.0
        loss = 0.0
        for x, y in zip(xs, ys):
            p = _sigmoid(a * x + b)
            p_c = _clip(p, 1e-12, 1.0 - 1e-12)
            loss += -(y * math.log(p_c) + (1.0 - y) * math.log(1.0 - p_c))
            grad_a += (p - y) * x
            grad_b += (p - y)
        loss /= len(xs)
        grad_a /= len(xs)
        grad_b /= len(xs)
        a -= lr * grad_a
        b -= lr * grad_b
        if abs(prev_loss - loss) < tol:
            break
        prev_loss = loss
    return (a, b)


def apply_platt(scores, a: float, b: float) -> list[float]:
    return [_sigmoid(a * float(s) + b) for s in scores]


def expected_calibration_error(probs, outcomes, n_bins: int = 10) -> float:
    """ECE · standard equal-width bin implementation.

    Each bin's contribution = |mean(pred) − mean(actual)| × (n_bin / n_total).
    Returns 0.0 when insufficient data.
    """
    if not probs or len(probs) < n_bins:
        return 0.0
    n = len(probs)
    bins = [[] for _ in range(n_bins)]
    for p, o in zip(probs, outcomes):
        p_c = _clip(float(p), 0.0, 0.999999)
        idx = min(int(p_c * n_bins), n_bins - 1)
        bins[idx].append((p_c, 1.0 if o else 0.0))
    ece = 0.0
    for bucket in bins:
        if not bucket: continue
        mean_p = sum(x[0] for x in bucket) / len(bucket)
        mean_y = sum(x[1] for x in bucket) / len(bucket)
        ece += abs(mean_p - mean_y) * (len(bucket) / n)
    return ece


def brier_score(probs, outcomes) -> float:
    if not probs: return 0.0
    total = 0.0
    for p, o in zip(probs, outcomes):
        y = 1.0 if o else 0.0
        total += (float(p) - y) ** 2
    return total / len(probs)


# ── outcome loader ──────────────────────────────────────────────────────────

def _load_price_parquet(root: Path, market: str, ticker: str):
    """Return a pandas DataFrame indexed by date or None."""
    try:
        import pandas as pd
        from backend.research._paths import price_parquet_path
        p = price_parquet_path(root, market, str(ticker).upper().split(".", 1)[0])
        if not p or not p.exists(): return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception:
        return None


def forward_return_pct(root: Path, market: str, ticker: str,
                        entry_date: str, horizon_days: int = 17) -> Optional[float]:
    """Realized forward return · dynamic horizon (default 17d matches V2)."""
    df = _load_price_parquet(root, market, ticker)
    if df is None or df.empty: return None
    import pandas as pd
    try:
        entry_dt = pd.Timestamp(entry_date)
    except Exception:
        return None
    # Entry price = first bar at-or-after entry_date
    entry_slice = df[df.index >= entry_dt]
    if entry_slice.empty: return None
    entry_row = entry_slice.iloc[0]
    entry_price = float(entry_row["close"])
    if entry_price <= 0: return None
    exit_dt_target = entry_slice.index[0] + pd.Timedelta(days=horizon_days * 1.5)
    exit_slice = df[df.index >= exit_dt_target]
    if exit_slice.empty:
        # Use last available bar
        exit_price = float(df["close"].iloc[-1])
    else:
        exit_price = float(exit_slice.iloc[0]["close"])
    return (exit_price / entry_price - 1.0) * 100.0


# ── dataset construction ────────────────────────────────────────────────────

@dataclass
class CalibrationSample:
    market: str
    ticker: str
    asof: str
    raw_confidence: Optional[float]
    calibrated_confidence: Optional[float]
    regime_adjusted_confidence: Optional[float]
    action: str
    ensemble_score: Optional[float]
    forward_return_pct: Optional[float]
    win_flag: Optional[bool]


def build_calibration_dataset(root: Path, market: str,
                                horizon_days: int = 17,
                                buy_only: bool = False) -> list[CalibrationSample]:
    """Build (confidence, outcome) samples for calibration · dynamic.

    MODE A (preferred) · Load closed R2 positions from outcome_dataset.parquet
    where (initial_confidence, win_flag, exit_pnl_pct) are already attached.

    MODE B (augmentation) · Reconstruct from recommendation_history · for each
    historical prediction not already in Mode A, compute realized forward
    return via price parquet · attach as additional sample.

    Dedupes by (ticker, asof) · both modes contribute one sample per key.
    """
    import pandas as pd
    samples: dict[tuple[str, str], CalibrationSample] = {}

    # MODE A · outcome_dataset (canonical closed positions with entry-time confidence)
    outcome_p = root / "reports" / "research" / "outcome_dataset.parquet"
    if outcome_p.exists():
        outc = pd.read_parquet(outcome_p)
        m_outc = outc[(outc["country"].str.lower() == market.lower())
                       & (outc["is_closed"] == True)
                       & (outc["runner"] == "R2")]
        for _, r in m_outc.iterrows():
            ticker = str(r["ticker"]).upper()
            entry = str(r["entry_date"])[:10]
            key = (ticker, entry)
            samples[key] = CalibrationSample(
                market=market.lower(),
                ticker=ticker,
                asof=entry,
                raw_confidence=(float(r["initial_confidence"])
                                if pd.notna(r.get("initial_confidence")) else None),
                calibrated_confidence=None,   # not preserved historically
                regime_adjusted_confidence=None,
                action="BUY",                  # closed R2 = accepted BUY
                ensemble_score=(float(r["initial_model_score"])
                                if pd.notna(r.get("initial_model_score")) else None),
                forward_return_pct=(float(r["exit_pnl_pct"])
                                     if pd.notna(r.get("exit_pnl_pct")) else None),
                win_flag=(bool(r["win_flag"]) if pd.notna(r.get("win_flag")) else None),
            )

    # MODE B · reconstruct from recommendation_history for any (ticker, asof)
    # not already covered by Mode A · adds coverage where outcome_dataset is thin
    hist_p = (root / market / "reports" / "recommendation_history.parquet"
              if market.lower() == "usa"
              else root / "reports" / "recommendation_history.parquet")
    if hist_p.exists():
        hist = pd.read_parquet(hist_p)
        added = 0
        for _, row in hist.iterrows():
            recs = row.get("recommendations")
            if isinstance(recs, str):
                try: recs = json.loads(recs)
                except Exception: continue
            elif hasattr(recs, "tolist"):
                recs = recs.tolist()
            if not isinstance(recs, list): continue
            asof = str(row.get("asof", ""))
            for r in recs:
                if not isinstance(r, dict): continue
                action = str(r.get("action", "")).upper()
                if buy_only and action != "BUY": continue
                ticker = str(r.get("ticker", "")).upper()
                if not ticker: continue
                key = (ticker, asof)
                if key in samples: continue    # Mode A wins if present
                samples[key] = CalibrationSample(
                    market=market.lower(),
                    ticker=ticker,
                    asof=asof,
                    raw_confidence=r.get("raw_confidence"),
                    calibrated_confidence=r.get("calibrated_confidence"),
                    regime_adjusted_confidence=r.get("regime_adjusted_confidence"),
                    action=action,
                    ensemble_score=r.get("ensemble_score"),
                    forward_return_pct=None,
                    win_flag=None,
                )
                added += 1
        # Attach realized forward return only for Mode B samples that lack it
        for s in samples.values():
            if s.forward_return_pct is not None: continue
            fr = forward_return_pct(root, market, s.ticker, s.asof, horizon_days)
            s.forward_return_pct = fr
            if fr is not None: s.win_flag = fr > 0.0
    return list(samples.values())
