"""P0-EXTENSION-01 · Dynamic Exit Bridge parameter surface · CEO 2026-09-03.

Additive extension to P0-original (E-001 · FAIL preserved).

Trial family = k × m × horizon = 5 × 4 × 3 = **60 trials**.
Deflated Sharpe deflation applies n_trials=60 (not 1).

For each (k, m, horizon) grid point:
  · replay every closed non-admin R2 position through PIT ATR-14 trailing stop
  · OHLC pessimistic ordering when high-low span both stop and target (CANONICAL 1)
  · counterfactual vs actual · paired bootstrap 10 000
  · regime-segmented result (uses regime_at_entry enrichment · V2 §7)

Acceptance per PDF:
  · best variant delta > actual · lower-CI ≥ 0 · n ≥ 50 · **AND survives DSR deflation by 60**

Output: reports/research/r2_upgrades/p0_extension_01_{market}.json
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

K_STOP_GRID = [1.0, 1.5, 2.0, 2.5, 3.0]           # 5 values
M_TARGET_GRID = [1.5, 2.0, 3.0, 4.0]              # 4 values
HORIZON_GRID = [20, 40, 60]                        # 3 values
N_TRIALS = len(K_STOP_GRID) * len(M_TARGET_GRID) * len(HORIZON_GRID)  # 60


def _clean_ticker(t: str) -> str:
    if not t: return ""
    t = str(t).upper()
    for suf in (".NS", ".BO", ".NSE", ".BSE"):
        if t.endswith(suf): return t[: -len(suf)]
    return t


def _atr14_at(prices, entry_idx: int):
    if entry_idx < 14: return None
    highs = prices["high"].to_numpy(); lows = prices["low"].to_numpy(); closes = prices["close"].to_numpy()
    trs = []
    for i in range(entry_idx - 13, entry_idx + 1):
        if i <= 0: continue
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i-1]),
                       abs(lows[i] - closes[i-1])))
    if not trs: return None
    return sum(trs) / len(trs)


def _replay(prices, entry_date: str, k_stop: float, m_target: float, horizon: int):
    """Apply pessimistic-stop-first ordering when both hit in same day."""
    import pandas as pd
    if prices is None or prices.empty: return None
    try:
        d0 = pd.to_datetime(entry_date).normalize()
    except Exception: return None
    if d0 not in prices.index:
        mask = prices.index <= d0
        if not mask.any(): return None
        entry_idx = int(mask.sum()) - 1
    else:
        entry_idx = prices.index.get_loc(d0)
    if isinstance(entry_idx, slice) or hasattr(entry_idx, "__len__"): return None

    atr = _atr14_at(prices, entry_idx)
    if atr is None or atr <= 0: return None

    closes = prices["close"].to_numpy(); highs = prices["high"].to_numpy(); lows = prices["low"].to_numpy()
    entry_price = float(closes[entry_idx])
    base_stop = entry_price - k_stop * atr
    target = entry_price + m_target * atr
    stop = base_stop; running_high = entry_price
    max_i = min(entry_idx + horizon, len(closes) - 1)
    for i in range(entry_idx + 1, max_i + 1):
        if closes[i] > running_high:
            running_high = float(closes[i])
            new_stop = running_high - k_stop * atr
            if new_stop > stop: stop = new_stop
        stop_hit = lows[i] <= stop
        target_hit = highs[i] >= target
        # PESSIMISTIC · CANONICAL 1
        if stop_hit and target_hit:
            return (float(stop), "STOP_HIT_PESS", i - entry_idx)
        if stop_hit:
            return (float(stop), "STOP_HIT", i - entry_idx)
        if target_hit:
            return (float(target), "TARGET_HIT", i - entry_idx)
    if max_i > entry_idx:
        return (float(closes[max_i]), "HORIZON_EXPIRED", max_i - entry_idx)
    return None


def _paired_bootstrap(deltas, n_resamples=10_000, seed=42):
    if not deltas: return {"n": 0, "mean_delta": None, "ci_low": None, "ci_high": None, "p_two": None}
    import random
    n = len(deltas); rng = random.Random(seed)
    obs = sum(deltas) / n
    means = []
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * n_resamples)]; hi = means[int(0.975 * n_resamples)]
    n_beyond = sum(1 for m in means if (m <= 0 if obs >= 0 else m >= 0))
    return {"n": n, "mean_delta": obs, "ci_low": lo, "ci_high": hi,
            "p_two": min(2.0 * n_beyond / n_resamples, 1.0), "n_resamples": n_resamples}


def _sr(xs):
    if not xs: return 0.0
    mu = sum(xs) / len(xs)
    var = sum((x - mu)**2 for x in xs) / max(1, len(xs) - 1)
    sd = math.sqrt(var)
    return (mu / sd) if sd > 0 else 0.0


def _dsr_p(observed_sr, n_trials, n_returns):
    """Deflated Sharpe · returns p_value that observed SR > 0 after selection."""
    from backend.research.walkforward.deflated_sharpe import deflated_sharpe_ratio
    r = deflated_sharpe_ratio(observed_sr, n_trials=n_trials, n_returns=n_returns)
    return r


def replay_market(root: Path, market: str) -> dict:
    from backend.research.outcome_dataset import load_outcome_dataset
    from backend.research._paths import price_parquet_path
    import pandas as pd

    dset = load_outcome_dataset(root, market)
    if dset.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}
    dset = dset[(dset["runner"] == "R2")
                & (dset["exit_date"].notna())
                & (dset["is_administrative_exit"] != True)
                & (dset["entry_price"].notna())
                & (dset["exit_price"].notna())].copy()
    if dset.empty:
        return {"market": market, "status": "NO_CLOSED_NON_ADMIN_R2"}

    price_cache: dict[str, "pd.DataFrame"] = {}
    def _prices(ticker):
        t = _clean_ticker(ticker)
        if t not in price_cache:
            p = price_parquet_path(root, market, t)
            if not p or not p.exists(): price_cache[t] = None
            else:
                try:
                    df = pd.read_parquet(p)
                    df.index = pd.to_datetime(df.index)
                    price_cache[t] = df
                except Exception: price_cache[t] = None
        return price_cache[t]

    # Prebuild per-position actual_return
    positions = []
    for _, r in dset.iterrows():
        actual = float(r["realized_return_pct"] or 0.0)
        positions.append({
            "position_id": r["position_id"],
            "ticker": r["ticker"],
            "entry_date": str(r["entry_date"]),
            "entry_price": float(r["entry_price"]),
            "regime_at_entry": str(r.get("regime_at_entry") or "UNKNOWN"),
            "actual_return_pct": actual,
        })

    # Run 60-trial grid
    trials = []
    from itertools import product
    for k, m, h in product(K_STOP_GRID, M_TARGET_GRID, HORIZON_GRID):
        deltas = []; cf_returns = []; by_regime = {}
        for p in positions:
            prices = _prices(p["ticker"])
            if prices is None: continue
            cf = _replay(prices, p["entry_date"], k, m, h)
            if cf is None: continue
            cf_price, cf_reason, cf_days = cf
            cf_ret = (cf_price / p["entry_price"]) - 1.0
            deltas.append(cf_ret - p["actual_return_pct"])
            cf_returns.append(cf_ret)
            reg = p["regime_at_entry"]
            by_regime.setdefault(reg, []).append(cf_ret - p["actual_return_pct"])
        if not deltas: continue
        pb = _paired_bootstrap(deltas)
        sr = _sr(cf_returns)
        dsr = _dsr_p(sr, N_TRIALS, len(cf_returns))
        trials.append({
            "k_stop": k, "m_target": m, "horizon_days": h,
            "n": len(deltas), "mean_delta": pb["mean_delta"],
            "ci_low": pb["ci_low"], "ci_high": pb["ci_high"], "p_two": pb["p_two"],
            "sharpe_counterfactual": sr,
            "dsr": dsr,
            "by_regime": {r: {"n": len(vs), "mean_delta": sum(vs)/len(vs)}
                          for r, vs in by_regime.items()},
        })

    # Rank by mean_delta descending (positive = better)
    trials.sort(key=lambda t: -(t["mean_delta"] or -1e9))
    best = trials[0] if trials else None

    # PDF gate: mean_delta > 0 · ci_low >= 0 · n >= 50 · AND DSR-survivor
    passes_expectancy = bool(best) and (best.get("mean_delta") or -1) > 0
    passes_ci = bool(best) and (best.get("ci_low") or -1) >= 0
    passes_n = bool(best) and (best.get("n") or 0) >= 50
    passes_dsr = bool(best) and (best.get("dsr", {}).get("p_value", 1.0) or 1.0) < 0.05

    result = {
        "market": market,
        "n_trials_family": N_TRIALS,
        "trials_run": len(trials),
        "n_positions_available": len(positions),
        "best_trial": best,
        "gate_criteria": {
            "mean_delta_gt_0": passes_expectancy,
            "ci_low_ge_0": passes_ci,
            "n_ge_50": passes_n,
            "dsr_p_lt_0.05_deflated_by_60": passes_dsr,
        },
        "P0_EXT_GATE_PASS": passes_expectancy and passes_ci and passes_n and passes_dsr,
        "governance_note": ("Additive extension · does NOT replace E-001 P0-original. "
                            f"Trial family = {N_TRIALS} · DSR deflation applied with n_trials={N_TRIALS}."),
        "parameters_swept": {
            "k_stop": K_STOP_GRID, "m_target": M_TARGET_GRID, "horizon_days": HORIZON_GRID,
        },
        "all_trials": trials,
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research" / "r2_upgrades"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"p0_extension_01_{market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = replay_market(root, m)
        print(f"[p0-ext-01] {m} · trials={r.get('trials_run')} · n_positions={r.get('n_positions_available')} · best delta={r.get('best_trial',{}).get('mean_delta') if r.get('best_trial') else None} · GATE={r.get('P0_EXT_GATE_PASS')}")


if __name__ == "__main__":
    main()
