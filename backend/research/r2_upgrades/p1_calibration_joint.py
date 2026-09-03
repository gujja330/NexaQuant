"""R2 · P1 · Joint Platt Calibration on (raw_score, regime_encoded, win/loss)
CANONICAL 2 · CEO 2026-09-03

Replaces the two-stage sequence (Platt(A,B) then × regime_multiplier ∈ [0.7,1.3])
with a joint logistic regression:

    log(p / (1-p)) = w0 + w1 * raw_score + w2 * regime_encoded + w3 * (raw × regime)

Regime is one-hot encoded across {NORMAL, WEAKENING, RISK_OFF, CRASH, RECOVERY, UNKNOWN}.
The interaction term (raw × regime) is what makes the fit "joint" · it does
not assume regime miscalibration is independent of raw-score miscalibration.

Weekly recurring job:
  1. Load trailing 180-day outcome dataset
  2. If n < 50 · load previous calibration (do not refit)
  3. Fit new calibration on (raw_score, regime, win/loss)
  4. Compute ECE_before + ECE_after
  5. If ECE_after > ECE_before + 0.005 · DO NOT DEPLOY · retain previous
  6. Save calibration to configs/r2_calibration_{market}.json + freeze

Output:
  reports/research/r2_upgrades/p1_calibration_{market}.json  · fit + gate
  configs/r2_calibration_{market}.json                       · deployed weights
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parents[3]

REGIME_ORDER = ["NORMAL", "WEAKENING", "RISK_OFF", "CRASH", "RECOVERY", "UNKNOWN"]


def _regime_one_hot(regime: str) -> list[float]:
    r = str(regime or "UNKNOWN").upper()
    return [1.0 if r == g else 0.0 for g in REGIME_ORDER]


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _design(raw_scores: Sequence[float], regimes: Sequence[str]) -> list[list[float]]:
    """Build design matrix · [1, raw, regime_1h..., raw*regime_1h...] per row."""
    X: list[list[float]] = []
    for s, r in zip(raw_scores, regimes):
        onehot = _regime_one_hot(r)
        interaction = [s * v for v in onehot]
        row = [1.0, float(s)] + onehot + interaction
        X.append(row)
    return X


def _fit_logistic(X: list[list[float]], y: Sequence[int],
                  max_iter: int = 400, lr: float = 0.05,
                  l2: float = 0.001) -> list[float]:
    """Batch gradient descent with L2 · no external ML lib · deterministic."""
    if not X:
        return []
    p_dim = len(X[0])
    n = len(X)
    w = [0.0] * p_dim
    for it in range(max_iter):
        grad = [0.0] * p_dim
        for xi, yi in zip(X, y):
            z = sum(w[k] * xi[k] for k in range(p_dim))
            pred = _sigmoid(z)
            err = pred - float(yi)
            for k in range(p_dim):
                grad[k] += err * xi[k]
        for k in range(p_dim):
            grad[k] = grad[k] / n + l2 * w[k]
            w[k] -= lr * grad[k]
    return w


def predict_joint(weights: list[float], raw_score: float, regime: str) -> float:
    """Return calibrated probability given trained weights."""
    if not weights:
        return _sigmoid(raw_score)
    X = _design([raw_score], [regime])[0]
    z = sum(weights[k] * X[k] for k in range(len(weights)))
    return _sigmoid(z)


def expected_calibration_error(y_true: Sequence[int], y_prob: Sequence[float],
                               n_bins: int = 10) -> float:
    """ECE · weighted average |confidence - accuracy| across probability bins."""
    if not y_prob:
        return 0.0
    bins = [[] for _ in range(n_bins)]
    for t, p in zip(y_true, y_prob):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((t, p))
    total = len(y_prob)
    ece = 0.0
    for b in bins:
        if not b: continue
        acc = sum(t for t, _ in b) / len(b)
        conf = sum(p for _, p in b) / len(b)
        ece += (len(b) / total) * abs(conf - acc)
    return ece


def fit_and_gate(market: str, outcome_rows: list[dict],
                 min_n: int = 50,
                 ece_worsen_tolerance: float = 0.005) -> dict:
    """Full weekly job · fit + ECE gate + config emission."""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    def _is_num(x):
        try:
            f = float(x)
            return not math.isnan(f)
        except (TypeError, ValueError):
            return False
    valid = [r for r in outcome_rows
             if _is_num(r.get("entry_signal_score"))
             and _is_num(r.get("realized_return_pct"))
             and (r.get("is_administrative_exit") in (False, 0, None) or
                  str(r.get("is_administrative_exit")).lower() == "false")]
    n = len(valid)
    if n < min_n:
        return {
            "market": market, "n": n,
            "gate_status": "INSUFFICIENT_SAMPLE",
            "note": f"n={n} < min_n={min_n} · retain previous calibration",
            "fit_utc": now,
        }
    raws = [float(r["entry_signal_score"]) for r in valid]
    regs = [str(r.get("regime_at_entry") or "UNKNOWN") for r in valid]
    ys = [1 if float(r["realized_return_pct"]) > 0 else 0 for r in valid]

    # ECE_before · use raw sigmoid on raw_score
    before_probs = [_sigmoid(x) for x in raws]
    ece_before = expected_calibration_error(ys, before_probs)

    X = _design(raws, regs)
    w = _fit_logistic(X, ys)
    after_probs = [_sigmoid(sum(w[k]*xi[k] for k in range(len(w)))) for xi in X]
    ece_after = expected_calibration_error(ys, after_probs)

    deployed = ece_after <= ece_before + ece_worsen_tolerance
    return {
        "market": market,
        "n": n,
        "ece_before": ece_before,
        "ece_after": ece_after,
        "ece_delta": ece_after - ece_before,
        "weights": w,
        "regime_order": REGIME_ORDER,
        "gate_status": "DEPLOYED" if deployed else "REJECTED_ECE_WORSENED",
        "gate_pass": deployed,
        "note": (
            "Joint Platt on (raw_score, regime_encoded, win/loss) · "
            "replaces two-stage Platt-then-regime-multiplier per CEO CANONICAL 2"
        ),
        "fit_utc": now,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    from backend.research.outcome_dataset import load_outcome_dataset
    df = load_outcome_dataset(root, args.market)
    rows = df.to_dict("records") if not df.empty else []
    result = fit_and_gate(args.market, rows)
    out = root / "reports" / "research" / "r2_upgrades"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"p1_calibration_{args.market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    if result.get("gate_pass"):
        cfg = root / "configs" / f"r2_calibration_{args.market}.json"
        cfg.write_text(json.dumps({
            "weights": result["weights"],
            "regime_order": REGIME_ORDER,
            "kind": "joint_platt",
            "fit_utc": result["fit_utc"],
            "n": result["n"],
        }, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
