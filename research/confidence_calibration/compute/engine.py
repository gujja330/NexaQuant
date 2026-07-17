"""DEV029 orchestration.

Fits all 5 calibration methods on the DEV025 trade history, selects the best
by Brier score, produces reliability diagrams + warnings + calibration history.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from confidence_calibration.lib import methods, metrics                             # noqa: E402


REPORTS_DIR = _ROOT / "reports"
LEARNING_PARQUET = REPORTS_DIR / "learning.parquet"
CALIB_HISTORY = _ROOT / "data" / "market_intelligence" / "derived" / "calibration_history.parquet"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _load_learning() -> pd.DataFrame:
    if not LEARNING_PARQUET.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(LEARNING_PARQUET)
    except Exception:
        return pd.DataFrame()


def _train_test_split(df: pd.DataFrame, seed: int = 42, train_frac: float = 0.7):
    """Time-based split — earlier trades train, later ones test.

    Reference: proper calibration validation uses OOS data. We sort by entry_date
    and take first train_frac% as train, rest as test."""
    if df.empty:
        return df, df
    df = df.sort_values("entry_date")
    n = len(df)
    split = int(n * train_frac)
    return df.iloc[:split], df.iloc[split:]


def _select_best_calibrator(fitted: dict, test_conf: np.ndarray,
                              test_outcomes: np.ndarray) -> tuple[str, dict]:
    """Score every fitted calibrator on the test set; pick lowest Brier."""
    scoreboard = {}
    for name, calibrator in fitted.items():
        p_cal = calibrator.predict(test_conf)
        m = metrics.all_metrics(p_cal, test_outcomes)
        scoreboard[name] = m
    best_name = min(scoreboard, key=lambda k: scoreboard[k]["brier_score"])
    return best_name, scoreboard


def _detect_warnings(reliability: list[dict], min_evidence: int = 20) -> list[dict]:
    warnings = []
    total_n = sum(r["n"] for r in reliability)
    for r in reliability:
        if r["n"] == 0:
            warnings.append({
                "bin":     f"[{r['bin_lo']:.2f}, {r['bin_hi']:.2f}]",
                "type":    "sparse_region",
                "message": "No predictions in this range - cannot verify calibration",
            })
            continue
        if r["n"] < min_evidence:
            warnings.append({
                "bin":     f"[{r['bin_lo']:.2f}, {r['bin_hi']:.2f}]",
                "type":    "insufficient_evidence",
                "n":       r["n"],
                "message": f"Only {r['n']} predictions (< {min_evidence}) - bin unreliable",
            })
        gap = r.get("gap")
        if gap is not None:
            if gap > 0.10:
                warnings.append({
                    "bin":       f"[{r['bin_lo']:.2f}, {r['bin_hi']:.2f}]",
                    "type":      "overconfidence",
                    "predicted": r["predicted"], "observed": r["observed"], "gap": gap,
                    "message":   f"Overconfident: predicted {r['predicted']:.2f}, observed {r['observed']:.2f}",
                })
            elif gap < -0.10:
                warnings.append({
                    "bin":       f"[{r['bin_lo']:.2f}, {r['bin_hi']:.2f}]",
                    "type":      "underconfidence",
                    "predicted": r["predicted"], "observed": r["observed"], "gap": gap,
                    "message":   f"Underconfident: predicted {r['predicted']:.2f}, observed {r['observed']:.2f}",
                })
    return warnings


def _append_history(row: dict) -> None:
    """Append this run's key metrics to the calibration history parquet."""
    CALIB_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame([row])
    if CALIB_HISTORY.exists():
        old = pd.read_parquet(CALIB_HISTORY)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_parquet(CALIB_HISTORY, index=False)


def run(min_trades: int = 100, verbose: bool = True) -> dict:
    trades = _load_learning()
    if trades.empty:
        return {"error": "learning.parquet missing — run DEV025 first"}
    if len(trades) < min_trades:
        return {"error": f"only {len(trades)} trades; need {min_trades}+"}

    if verbose:
        print(f"  loaded {len(trades)} trades from DEV025 learning.parquet")

    train, test = _train_test_split(trades)
    train_conf = train["confidence"].values.astype(float)
    train_y = train["is_winner"].astype(int).values
    test_conf = test["confidence"].values.astype(float)
    test_y = test["is_winner"].astype(int).values

    if verbose:
        print(f"  train {len(train)} · test {len(test)}")
        print(f"  train win rate: {train_y.mean():.3f}   test win rate: {test_y.mean():.3f}")

    # Raw baseline
    raw_test_metrics = metrics.all_metrics(test_conf, test_y)
    if verbose:
        print(f"  raw (uncalibrated) test: Brier={raw_test_metrics['brier_score']:.4f}  "
                f"ECE={raw_test_metrics['ece']:.4f}")

    # Fit all methods on train
    fitted = methods.fit_all(train_conf, train_y)
    if verbose:
        print(f"  fitted {len(fitted)} calibration methods on train set")

    # Select best on test
    best_name, scoreboard = _select_best_calibrator(fitted, test_conf, test_y)
    if verbose:
        print(f"  best method: {best_name}   (Brier={scoreboard[best_name]['brier_score']:.4f})")

    # Full corpus calibrated prediction for reliability diagram
    all_conf = trades["confidence"].values.astype(float)
    all_y = trades["is_winner"].astype(int).values
    calibrator = fitted[best_name]
    calibrated_all = calibrator.predict(all_conf)

    raw_reliability = metrics.reliability_curve(all_conf, all_y)
    calibrated_reliability = metrics.reliability_curve(calibrated_all, all_y)

    raw_all_metrics = metrics.all_metrics(all_conf, all_y)
    cal_all_metrics = metrics.all_metrics(calibrated_all, all_y)

    warnings = _detect_warnings(raw_reliability)

    # Confidence-bias analysis per predicted bin
    bias_analysis = _bias_analysis(all_conf, calibrated_all, all_y)

    # Append to history
    now = datetime.now(timezone.utc).isoformat() + "Z"
    _append_history({
        "run_utc":          now,
        "n_trades":         len(trades),
        "best_method":      best_name,
        "raw_brier":        raw_all_metrics["brier_score"],
        "cal_brier":        cal_all_metrics["brier_score"],
        "raw_ece":          raw_all_metrics["ece"],
        "cal_ece":          cal_all_metrics["ece"],
        "raw_log_loss":     raw_all_metrics["log_loss"],
        "cal_log_loss":     cal_all_metrics["log_loss"],
        "raw_bias":         raw_all_metrics["confidence_bias"],
        "cal_bias":         cal_all_metrics["confidence_bias"],
    })

    return {
        "run_utc":                now,
        "code_sha":               _git_sha(),
        "dev_version":            "DEV029 v0.1",
        "n_trades_total":         len(trades),
        "n_trades_train":         len(train),
        "n_trades_test":          len(test),
        "best_method":            best_name,
        "best_method_params":     calibrator.params,
        "scoreboard":             scoreboard,
        "raw_metrics_all":        raw_all_metrics,
        "calibrated_metrics_all": cal_all_metrics,
        "raw_reliability":        raw_reliability,
        "calibrated_reliability": calibrated_reliability,
        "warnings":               warnings,
        "bias_analysis":          bias_analysis,
        "_all_conf":              all_conf,
        "_calibrated":            calibrated_all,
        "_all_y":                 all_y,
    }


def _bias_analysis(raw_conf: np.ndarray, cal_conf: np.ndarray,
                    outcomes: np.ndarray, n_bins: int = 5) -> list[dict]:
    """For each raw-confidence bucket: raw vs calibrated vs actual."""
    edges = np.linspace(0.5, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (raw_conf >= lo) & (raw_conf < hi) if i < n_bins - 1 else \
                (raw_conf >= lo) & (raw_conf <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({
            "raw_bin":      f"[{lo:.2f}, {hi:.2f}]",
            "n":            n,
            "raw_avg":      round(float(raw_conf[mask].mean()), 4),
            "calibrated_avg": round(float(cal_conf[mask].mean()), 4),
            "actual":       round(float(outcomes[mask].mean()), 4),
            "raw_bias":     round(float(raw_conf[mask].mean() - outcomes[mask].mean()), 4),
            "cal_bias":     round(float(cal_conf[mask].mean() - outcomes[mask].mean()), 4),
        })
    return rows
