"""R2 · P0 · Exit Bridge Retrospective Replay
Sprint A · CEO 2026-09-03

For every historical non-administrative R2 close in the Outcome Dataset:

  Actual exit          · from Registry (STOP_HIT / TARGET_HIT / HORIZON / MANUAL)
  Counterfactual exit  · replay through the dynamic-risk logic using
                         ONLY information available on each historical day
                         (PIT ATR-14 · k=2.0 stop · m=3.0 target · 60d horizon)

Comparison:
  - Actual realized P&L per position
  - Counterfactual P&L per position
  - Paired bootstrap CI (10,000 resamples) for mean(counterfactual - actual)
  - Deflated Sharpe on counterfactual return stream (n_trials=1 for P0)
  - Segmented by (market, regime)

Acceptance (Sprint A P0 gate · from pasted plan):
  - counterfactual_mean >= actual_mean
  - lower CI bound >= 0
  - n_positions >= 50

Output:
  reports/research/r2_upgrades/p0_exit_bridge_replay_{market}.json
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]

DYN_K = 2.0            # stop multiplier
DYN_M = 3.0            # target multiplier
DYN_HORIZON = 60       # trading days


def _clean_ticker(t: str) -> str:
    if not t: return ""
    t = str(t).upper()
    for suf in (".NS", ".BO", ".NSE", ".BSE"):
        if t.endswith(suf): return t[: -len(suf)]
    return t


def _parquet_path(root: Path, market: str, ticker: str) -> Path:
    from backend.research._paths import price_parquet_path
    resolved = price_parquet_path(root, market, ticker)
    if resolved: return resolved
    # Return non-existent path (for .exists() False fallback)
    return root / "data" / "raw" / market / f"{ticker}_D1.parquet"


def _atr14_at(prices, entry_idx: int) -> Optional[float]:
    if entry_idx < 14: return None
    highs = prices["high"].to_numpy()
    lows = prices["low"].to_numpy()
    closes = prices["close"].to_numpy()
    trs = []
    for i in range(entry_idx - 13, entry_idx + 1):
        if i <= 0: continue
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        )
        trs.append(tr)
    if not trs: return None
    return sum(trs) / len(trs)


def _replay_position(prices, entry_date: str,
                     actual_exit_date: Optional[str]) -> Optional[dict]:
    """Simulate dynamic-exit replay from entry through 60d horizon.

    Trailing stop: base = entry_close - k*ATR14(entry). Ratchets up on
    new closing highs · stop = max(prev_stop, high_close - k*ATR14(t)).
    Target: entry_close + m*ATR14(entry).

    Fires on the first of (stop|target|horizon) hit.
    Returns dict with counterfactual_exit_date, exit_price, exit_reason.
    """
    import pandas as pd

    try:
        d0 = pd.to_datetime(entry_date).normalize()
    except Exception:
        return None
    if d0 not in prices.index:
        mask = prices.index <= d0
        if not mask.any(): return None
        entry_idx = int(mask.sum()) - 1
    else:
        entry_idx = prices.index.get_loc(d0)
    if isinstance(entry_idx, slice) or hasattr(entry_idx, "__len__"):
        return None

    atr = _atr14_at(prices, entry_idx)
    if atr is None or atr <= 0: return None

    closes = prices["close"].to_numpy()
    highs = prices["high"].to_numpy()
    lows = prices["low"].to_numpy()
    entry_price = float(closes[entry_idx])

    base_stop = entry_price - DYN_K * atr
    target = entry_price + DYN_M * atr
    stop = base_stop
    running_high = entry_price

    max_i = min(entry_idx + DYN_HORIZON, len(closes) - 1)
    for i in range(entry_idx + 1, max_i + 1):
        # Ratchet stop upward as trailing high extends
        if closes[i] > running_high:
            running_high = float(closes[i])
            new_stop = running_high - DYN_K * atr
            if new_stop > stop:
                stop = new_stop
        # PESSIMISTIC OHLC ORDERING (CEO CANONICAL FIX #1 · 2026-09-03)
        # ---------------------------------------------------------------
        # When the day's high-low range contains BOTH the stop AND the
        # target, we cannot know from daily bars which fired first.
        # Statistically-honest handling: assume the worse outcome resolved
        # first · i.e. the stop hit before the target. This prevents the
        # counterfactual from cherry-picking the better exit and
        # overstating the exit-bridge lift.
        stop_hit = lows[i] <= stop
        target_hit = highs[i] >= target
        if stop_hit and target_hit:
            # Ambiguous day · pessimistic → stop
            return {
                "counterfactual_exit_date": prices.index[i].date().isoformat(),
                "counterfactual_exit_price": float(stop),
                "counterfactual_exit_reason": "DYNAMIC_STOP_HIT_PESSIMISTIC",
                "counterfactual_holding_days": int(i - entry_idx),
                "ohlc_ambiguous": True,
            }
        if stop_hit:
            return {
                "counterfactual_exit_date": prices.index[i].date().isoformat(),
                "counterfactual_exit_price": float(stop),
                "counterfactual_exit_reason": "DYNAMIC_STOP_HIT",
                "counterfactual_holding_days": int(i - entry_idx),
                "ohlc_ambiguous": False,
            }
        if target_hit:
            return {
                "counterfactual_exit_date": prices.index[i].date().isoformat(),
                "counterfactual_exit_price": float(target),
                "counterfactual_exit_reason": "DYNAMIC_TARGET_HIT",
                "counterfactual_holding_days": int(i - entry_idx),
                "ohlc_ambiguous": False,
            }
    # horizon
    if max_i > entry_idx:
        return {
            "counterfactual_exit_date": prices.index[max_i].date().isoformat(),
            "counterfactual_exit_price": float(closes[max_i]),
            "counterfactual_exit_reason": "DYNAMIC_HORIZON_EXPIRED",
            "counterfactual_holding_days": int(max_i - entry_idx),
            "ohlc_ambiguous": False,
        }
    return None


def replay_market(root: Path, market: str) -> dict:
    import pandas as pd
    from backend.research.outcome_dataset import load_outcome_dataset
    from backend.research.walkforward.bootstrap import paired_bootstrap_ci
    from backend.research.walkforward.deflated_sharpe import (
        deflated_sharpe_ratio, sharpe,
    )

    dset = load_outcome_dataset(root, market)
    if dset.empty:
        return {"market": market, "note": "outcome_dataset empty"}

    # Only production runner (R2), only closed non-admin
    dset_all = dset[
        (dset["runner"] == "R2")
        & (dset["exit_date"].notna())
        & (~dset["is_administrative_exit"])
    ].copy()

    if dset_all.empty:
        return {"market": market, "n_positions": 0,
                "note": "no closed non-admin R2 positions in Outcome Dataset",
                "P0_GATE_PASS": False,
                "P0_GATE_STATUS": "NO_HISTORY"}

    # Second filter · has both prices (needed for replay math)
    dset = dset_all[
        dset_all["entry_price"].notna() & dset_all["exit_price"].notna()
    ].copy()

    if dset.empty:
        # DATA-BLOCKED · we have closed non-admin R2 positions but their
        # entry_date falls outside the price coverage window. This is the
        # common case in dev · fresh yfinance pull needed.
        return {
            "market": market,
            "n_positions": 0,
            "n_r2_closed_non_admin_available": int(len(dset_all)),
            "note": (
                "DATA-BLOCKED · Outcome Dataset has non-admin closed R2 "
                "positions but price data doesn't reach their entry dates. "
                "Fresh yfinance pull needed for data/raw/{market}/*.parquet."
            ),
            "P0_GATE_PASS": False,
            "P0_GATE_STATUS": "BLOCKED_DATA",
        }

    price_cache: dict[str, "pd.DataFrame"] = {}

    rows = []
    for _, r in dset.iterrows():
        ticker = _clean_ticker(str(r["ticker"]))
        if ticker not in price_cache:
            p = _parquet_path(root, market, ticker)
            if not p.exists():
                price_cache[ticker] = None; continue
            try:
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                price_cache[ticker] = df
            except Exception:
                price_cache[ticker] = None; continue
        prices = price_cache.get(ticker)
        if prices is None or prices.empty: continue

        cf = _replay_position(prices, str(r["entry_date"]),
                              str(r["exit_date"]))
        if cf is None: continue

        actual_ret = float(r["realized_return_pct"] or 0.0)
        entry_price = float(r["entry_price"])
        cf_ret = (cf["counterfactual_exit_price"] / entry_price) - 1.0

        # Sanitize actual_exit_reason · Registry has occasionally stored
        # narrative text ("→ GNFC · +6.7pp alpha") in closed_reason ·
        # canonicalize to a small enum for clean distribution stats.
        raw_reason = str(r.get("exit_reason") or "")
        upper = raw_reason.upper()
        if "STOP" in upper:            canonical_reason = "STOP_HIT"
        elif "TARGET" in upper:        canonical_reason = "TARGET_HIT"
        elif "HORIZON" in upper:       canonical_reason = "HORIZON_EXPIRED"
        elif "MANUAL" in upper:        canonical_reason = "MANUAL"
        elif "ADMIN" in upper:         canonical_reason = "ADMIN"
        elif "RETIRED" in upper:       canonical_reason = "RETIRED"
        elif "->" in raw_reason or "→" in raw_reason: canonical_reason = "ROTATION"
        elif not raw_reason:           canonical_reason = "UNSPECIFIED"
        else:                          canonical_reason = "OTHER"

        rows.append({
            "position_id": r["position_id"],
            "ticker": ticker,
            "sector": r.get("sector"),
            "regime_at_entry": r.get("regime_at_entry"),
            "entry_date": str(r["entry_date"]),
            "exit_date": str(r["exit_date"]),
            "actual_exit_reason_raw": raw_reason[:120],
            "actual_exit_reason": canonical_reason,
            "actual_holding_days": r.get("holding_days"),
            "actual_return_pct": actual_ret,
            "counterfactual_exit_date": cf["counterfactual_exit_date"],
            "counterfactual_exit_reason": cf["counterfactual_exit_reason"],
            "counterfactual_holding_days": cf["counterfactual_holding_days"],
            "counterfactual_return_pct": cf_ret,
            "ohlc_ambiguous": cf.get("ohlc_ambiguous", False),
            "delta": cf_ret - actual_ret,
        })

    if not rows:
        # Distinguish data-blocked from truly-zero
        n_r2_closed_non_admin = int(len(dset))
        n_price_files_missing = sum(1 for _, r in dset.iterrows()
                                    if not _parquet_path(root, market,
                                                         _clean_ticker(str(r["ticker"]))).exists())
        return {
            "market": market,
            "n_positions": 0,
            "n_r2_closed_non_admin_available": n_r2_closed_non_admin,
            "n_price_files_missing": n_price_files_missing,
            "note": (
                "DATA-BLOCKED · outcome dataset has non-admin closed R2 "
                "positions but price data doesn't reach their entry dates. "
                "Refresh data/raw/{market}/*.parquet then re-run."
            ),
            "P0_GATE_PASS": False,
            "P0_GATE_STATUS": "BLOCKED_DATA",
        }

    actual = [x["actual_return_pct"] for x in rows]
    counter = [x["counterfactual_return_pct"] for x in rows]

    ci = paired_bootstrap_ci(actual, counter, n_resamples=10_000,
                             conf=0.95, seed=42)

    def _mean(xs): return sum(xs) / len(xs) if xs else 0.0

    # SR on counterfactual per-position return · not annualized because
    # positions are event-sampled · this is a trade-Sharpe.
    def _trade_sharpe(xs):
        if not xs: return 0.0
        n = len(xs)
        mu = _mean(xs)
        var = sum((x - mu)**2 for x in xs) / max(1, n - 1)
        sd = math.sqrt(var)
        return (mu / sd) if sd > 0 else 0.0

    sr_actual = _trade_sharpe(actual)
    sr_counter = _trade_sharpe(counter)
    dsr = deflated_sharpe_ratio(sr_counter, n_trials=1, n_returns=len(counter))

    # Segment by regime
    by_regime: dict[str, dict] = {}
    for row in rows:
        reg = str(row.get("regime_at_entry") or "UNKNOWN")
        by_regime.setdefault(reg, {"n": 0, "actual_sum": 0.0, "counter_sum": 0.0,
                                    "delta_sum": 0.0})
        by_regime[reg]["n"] += 1
        by_regime[reg]["actual_sum"] += row["actual_return_pct"]
        by_regime[reg]["counter_sum"] += row["counterfactual_return_pct"]
        by_regime[reg]["delta_sum"] += row["delta"]
    for reg, d in by_regime.items():
        n = d["n"]
        d["mean_actual"] = d["actual_sum"] / n
        d["mean_counter"] = d["counter_sum"] / n
        d["mean_delta"] = d["delta_sum"] / n
        del d["actual_sum"]; del d["counter_sum"]; del d["delta_sum"]

    # Exit-reason breakdown
    from collections import Counter
    actual_reasons = Counter(r["actual_exit_reason"] for r in rows)
    counter_reasons = Counter(r["counterfactual_exit_reason"] for r in rows)

    n = len(rows)
    passes_expectancy = _mean(counter) >= _mean(actual)
    passes_ci = (ci["ci_low"] is not None and ci["ci_low"] >= 0)
    passes_n = n >= 50
    gate_pass = passes_expectancy and passes_ci and passes_n

    n_ambiguous = sum(1 for r in rows if r.get("ohlc_ambiguous"))
    result = {
        "market": market,
        "n_positions": n,
        "n_ohlc_ambiguous_days": n_ambiguous,
        "n_ohlc_ambiguous_pct": (n_ambiguous / n) if n else 0.0,
        "mean_actual_return_pct": _mean(actual),
        "mean_counterfactual_return_pct": _mean(counter),
        "mean_delta_pct": _mean(counter) - _mean(actual),
        "median_actual_pct": sorted(actual)[n//2] if n else 0.0,
        "median_counter_pct": sorted(counter)[n//2] if n else 0.0,
        "paired_bootstrap": ci,
        "trade_sharpe_actual": sr_actual,
        "trade_sharpe_counterfactual": sr_counter,
        "deflated_sharpe_counter": dsr,
        "by_regime": by_regime,
        "actual_exit_reasons": dict(actual_reasons),
        "counterfactual_exit_reasons": dict(counter_reasons),
        "parameters": {
            "k_stop": DYN_K, "m_target": DYN_M, "horizon_days": DYN_HORIZON,
            "atr_window": 14,
            "ohlc_ambiguity_resolution": "PESSIMISTIC_STOP_FIRST",  # CANONICAL 1
        },
        "gate_criteria": {
            "expectancy_ge_actual": passes_expectancy,
            "lower_ci_ge_zero": passes_ci,
            "n_ge_50": passes_n,
        },
        "P0_GATE_PASS": gate_pass,
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_dir = root / "reports" / "research" / "r2_upgrades"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"p0_exit_bridge_replay_{market}.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    r = replay_market(Path(args.root), args.market)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
