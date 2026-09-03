"""T1 · Define the 60-day cohort correctly.

Latest 60 CALENDAR days of AEGIS output · not 60 trades · not 60 trading
days · not 60d holding horizon · not only closed trades.

Each observation tied to immutable Position ID + daily trajectory attached.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]


def _resolve_price_series(root, market: str, ticker: str):
    from backend.research._paths import price_parquet_path
    import pandas as pd
    p = price_parquet_path(root, market, str(ticker).upper())
    if not p or not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def _build_daily_trajectory(prices, entry_date: str, exit_date: str | None,
                            asof_today: str) -> list[dict]:
    """Return list of {date, close, unrealized_pct_from_entry} rows from
    max(entry_date, window_start) through min(exit_date, asof_today)."""
    import pandas as pd
    if prices is None or prices.empty: return []
    try:
        entry_dt = pd.to_datetime(entry_date).normalize()
    except Exception:
        return []
    end_dt = pd.to_datetime(asof_today).normalize()
    if exit_date:
        try:
            exit_dt = pd.to_datetime(exit_date).normalize()
            if exit_dt < end_dt: end_dt = exit_dt
        except Exception:
            pass
    if entry_dt not in prices.index:
        mask = prices.index <= entry_dt
        if not mask.any(): return []
        entry_price = float(prices.loc[mask, "close"].iloc[-1])
    else:
        entry_price = float(prices.loc[entry_dt, "close"])
    if entry_price <= 0: return []
    window = prices.loc[(prices.index >= entry_dt) & (prices.index <= end_dt)]
    rows = []
    for dt, r in window.iterrows():
        try:
            cp = float(r["close"])
            rows.append({
                "date": dt.date().isoformat(),
                "close": cp,
                "unrealized_pct": (cp / entry_price) - 1.0,
                "high": float(r.get("high", cp)),
                "low": float(r.get("low", cp)),
            })
        except Exception:
            continue
    return rows


def build_60d_dataset(root: Path, market: str,
                     asof_today: str | None = None) -> dict:
    """Return per-position rows for the latest 60 calendar days.

    Position INCLUSION rule:
        entry_date >= (asof_today - 60d)  OR
        (exit_date is None AND active in window)  OR
        (exit_date >= asof_today - 60d · fresh exit during window)
    """
    import pandas as pd
    asof_today = asof_today or datetime.now().strftime("%Y-%m-%d")
    asof_dt = date.fromisoformat(asof_today)
    window_start = asof_dt - timedelta(days=60)

    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return {"market": market, "status": "OUTCOME_DATASET_MISSING",
                "asof_today": asof_today}
    od = pd.read_parquet(od_path)
    if od.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}

    # Filter to 60-day window
    def _in_window(row):
        try:
            ed = date.fromisoformat(str(row.get("entry_date","")))
            if ed >= window_start: return True
            xd_raw = row.get("exit_date")
            if xd_raw is None or (isinstance(xd_raw, float) and pd.isna(xd_raw)):
                return True   # still active
            xd = date.fromisoformat(str(xd_raw))
            if xd >= window_start: return True
        except Exception:
            return False
        return False

    filt = od[od.apply(_in_window, axis=1)].copy()
    if filt.empty:
        return {"market": market, "status": "NO_POSITIONS_IN_WINDOW",
                "asof_today": asof_today, "window_start": window_start.isoformat()}

    # Attach daily trajectory per position
    trajectories: list[dict] = []
    for _, r in filt.iterrows():
        prices = _resolve_price_series(root, market, str(r["ticker"]))
        daily = _build_daily_trajectory(
            prices,
            str(r["entry_date"]),
            str(r["exit_date"]) if pd.notna(r["exit_date"]) else None,
            asof_today,
        )
        if not daily: continue
        # Trajectory summary stats
        pcts = [d["unrealized_pct"] for d in daily]
        highs = [d["high"] / daily[0]["close"] - 1 for d in daily]
        lows  = [d["low"]  / daily[0]["close"] - 1 for d in daily]
        mfe = max(highs) if highs else None
        mae = min(lows) if lows else None
        # First-crossing days (calendar days from entry)
        def _first_day_below(threshold_pct):
            for i, p in enumerate(pcts):
                if p <= threshold_pct: return i
            return None
        first_neg     = _first_day_below(0.0)
        first_neg_1   = _first_day_below(-0.01)
        first_neg_2   = _first_day_below(-0.02)
        first_neg_3   = _first_day_below(-0.03)
        first_neg_5   = _first_day_below(-0.05)
        first_neg_7   = _first_day_below(-0.07)
        worst = min(pcts)
        worst_day = pcts.index(worst) if pcts else None
        eventual = pcts[-1]
        recovered_from_worst = worst < 0 and eventual > worst + 0.02
        became_profitable = eventual > 0

        trajectories.append({
            "position_id": r["position_id"],
            "market": market,
            "runner": r["runner"],
            "ticker": r["ticker"],
            "sector": r.get("sector"),
            "cap_bucket": r.get("cap_bucket"),
            "investability": r.get("investability"),
            "regime_at_entry": r.get("regime_at_entry"),
            "entry_date": str(r["entry_date"]),
            "exit_date": str(r["exit_date"]) if pd.notna(r["exit_date"]) else None,
            "exit_reason": str(r.get("exit_reason") or "")[:40],
            "is_administrative_exit": bool(r.get("is_administrative_exit")),
            "n_daily_snapshots": len(daily),
            "entry_close": daily[0]["close"] if daily else None,
            "eventual_pct": round(eventual, 4),
            "worst_pct": round(worst, 4),
            "worst_day_from_entry": worst_day,
            "mfe_pct": round(mfe, 4) if mfe is not None else None,
            "mae_pct": round(mae, 4) if mae is not None else None,
            "first_negative_day": first_neg,
            "first_neg1_day": first_neg_1,
            "first_neg2_day": first_neg_2,
            "first_neg3_day": first_neg_3,
            "first_neg5_day": first_neg_5,
            "first_neg7_day": first_neg_7,
            "recovered_from_worst": recovered_from_worst,
            "became_profitable": became_profitable,
            "daily_trajectory": daily,
        })

    out_dir = root / "reports" / "research" / "neg_pnl_control_60d"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"dataset_{market}.json").write_text(
        json.dumps({
            "market": market, "asof_today": asof_today,
            "window_start": window_start.isoformat(),
            "n_positions": len(trajectories),
            "trajectories": trajectories,
            "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, indent=2, default=str), encoding="utf-8"
    )
    return {
        "market": market, "asof_today": asof_today,
        "window_start": window_start.isoformat(),
        "n_positions": len(trajectories),
        "trajectories": trajectories,
    }
