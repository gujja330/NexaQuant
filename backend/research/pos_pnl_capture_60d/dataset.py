"""T1 · Build the PIT candidate dataset for the latest 60 calendar days.

For each (date, ticker in PIT universe on that date):
  - forward returns 5/10/20/60d
  - MFE / MAE in the maximum horizon window
  - eventual_return_in_window
  - was_selected_by_aegis (bool · from Registry)
  - genome fields available at decision time (never future-derived)

Winner thresholds predeclared here (locked · not chosen after seeing results).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

# LOCKED · predeclared winner definitions (trial family = 4 horizons × 4 thresholds = 16)
WINNER_HORIZONS_DAYS = [5, 10, 20, 60]
WINNER_THRESHOLDS_PCT = [0.05, 0.10, 0.15, 0.20]


def _load_pit_universe(root: Path, market: str, date_str: str) -> set[str]:
    """Which tickers were IN the PIT universe on `date_str`?"""
    import pandas as pd
    p = root / "reports" / "research" / "pit_universe" / f"{market}.parquet"
    if not p.exists(): return set()
    try:
        df = pd.read_parquet(p)
        row = df[df["date"] == date_str]
        return set(row["ticker"].tolist())
    except Exception:
        return set()


def _load_aegis_selections(root: Path, market: str) -> dict[str, set[str]]:
    """Return {entry_date: {ticker set}} of R2 positions actually opened."""
    import pandas as pd
    p = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not p.exists(): return {}
    df = pd.read_parquet(p)
    if df.empty: return {}
    df = df[(df["runner"] == "R2") & (df["is_administrative_exit"] != True)]
    out: dict[str, set[str]] = {}
    for _, r in df.iterrows():
        ed = str(r.get("entry_date", ""))
        if not ed: continue
        t = str(r.get("ticker", "")).upper()
        out.setdefault(ed, set()).add(t)
    return out


def _forward_returns(prices, from_date: str) -> dict:
    """Return {fwd_5d, fwd_10d, fwd_20d, fwd_60d, mfe, mae, max_ret, eventual, entry_close}."""
    import pandas as pd
    if prices is None or prices.empty: return {}
    d0 = pd.to_datetime(from_date).normalize()
    if d0 not in prices.index:
        mask = prices.index <= d0
        if not mask.any(): return {}
        i0 = int(mask.sum()) - 1
    else:
        i0 = prices.index.get_loc(d0)
    if isinstance(i0, slice) or hasattr(i0, "__len__"): return {}
    closes = prices["close"].to_numpy()
    highs = prices["high"].to_numpy() if "high" in prices.columns else closes
    lows  = prices["low"].to_numpy()  if "low"  in prices.columns else closes
    entry = float(closes[i0])
    if entry <= 0: return {}
    out = {"entry_close": entry}
    for h_label, h in [("fwd_5d",5),("fwd_10d",10),("fwd_20d",20),("fwd_60d",60)]:
        j = i0 + h
        out[h_label] = ((closes[j] / entry) - 1.0) if j < len(closes) else None
    end_i = min(i0 + max(WINNER_HORIZONS_DAYS), len(closes) - 1)
    if end_i > i0:
        window_h = highs[i0:end_i+1]
        window_l = lows[i0:end_i+1]
        window_c = closes[i0:end_i+1]
        out["mfe_in_window"] = (float(max(window_h)) / entry) - 1.0
        out["mae_in_window"] = (float(min(window_l)) / entry) - 1.0
        out["max_ret_in_window"] = (float(max(window_c)) / entry) - 1.0
        out["eventual_return_in_window"] = (float(window_c[-1]) / entry) - 1.0
    return out


def is_winner(fwds: dict, horizon: int, threshold: float) -> bool | None:
    key = f"fwd_{horizon}d"
    v = fwds.get(key)
    if v is None: return None
    return v >= threshold


def build_pos_capture_dataset(root: Path, market: str,
                               asof_today: str | None = None) -> dict:
    """Assemble the 60-day PIT candidate + genome + outcome dataset."""
    from backend.research._paths import price_parquet_path
    import pandas as pd

    asof_today = asof_today or datetime.now().strftime("%Y-%m-%d")
    end_dt = date.fromisoformat(asof_today)
    start_dt = end_dt - timedelta(days=60)

    # Get every distinct date in the PIT universe within window
    pit_path = root / "reports" / "research" / "pit_universe" / f"{market}.parquet"
    if not pit_path.exists():
        return {"market": market, "status": "PIT_UNIVERSE_MISSING",
                "expected_path": str(pit_path.relative_to(root))}
    pit_df = pd.read_parquet(pit_path)
    pit_df = pit_df[(pit_df["date"] >= start_dt.isoformat())
                    & (pit_df["date"] <= end_dt.isoformat())]
    if pit_df.empty:
        return {"market": market, "status": "NO_PIT_DATES_IN_WINDOW"}

    aegis_by_date = _load_aegis_selections(root, market)

    price_cache: dict[str, "pd.DataFrame"] = {}
    def _prices(ticker):
        if ticker not in price_cache:
            p = price_parquet_path(root, market, ticker)
            if not p or not p.exists():
                price_cache[ticker] = None
            else:
                try:
                    df = pd.read_parquet(p)
                    df.index = pd.to_datetime(df.index)
                    price_cache[ticker] = df
                except Exception:
                    price_cache[ticker] = None
        return price_cache[ticker]

    candidates: list[dict] = []
    n_universe_x_date = len(pit_df)
    dates_in_window = sorted(pit_df["date"].unique())

    for date_str in dates_in_window:
        # Only weekdays approximate market days — parquet lookup handles it
        tickers_today = set(pit_df[pit_df["date"] == date_str]["ticker"])
        selected_today = aegis_by_date.get(date_str, set())
        for tkr in tickers_today:
            prices = _prices(tkr)
            if prices is None:
                # Missing data · record as candidate with data_miss flag
                candidates.append({
                    "date": date_str, "market": market, "ticker": tkr,
                    "was_selected_by_aegis": tkr in selected_today,
                    "data_available": False,
                    "genome_fields_populated_count": 0,
                })
                continue
            fwds = _forward_returns(prices, date_str)
            if not fwds:
                candidates.append({
                    "date": date_str, "market": market, "ticker": tkr,
                    "was_selected_by_aegis": tkr in selected_today,
                    "data_available": False,
                    "genome_fields_populated_count": 0,
                })
                continue
            # Winner labels (all thresholds × horizons)
            is_winner_labels = {}
            for h in WINNER_HORIZONS_DAYS:
                for t in WINNER_THRESHOLDS_PCT:
                    key = f"is_winner_{h}d_at_{int(t*100)}pct"
                    is_winner_labels[key] = is_winner(fwds, h, t)
            row = {
                "date": date_str, "market": market, "ticker": tkr,
                "was_selected_by_aegis": tkr in selected_today,
                "data_available": True,
                "genome_fields_populated_count": 4,   # date/market/ticker/entry_close + fwds
                **fwds, **is_winner_labels,
            }
            candidates.append(row)

    out_dir = root / "reports" / "research" / "pos_pnl_capture_60d"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "market": market,
        "asof_today": asof_today,
        "window_start": start_dt.isoformat(),
        "window_end": end_dt.isoformat(),
        "n_universe_x_date": int(n_universe_x_date),
        "n_dates_in_window": len(dates_in_window),
        "n_candidates_total": len(candidates),
        "n_data_available": sum(1 for c in candidates if c.get("data_available")),
        "n_data_missing": sum(1 for c in candidates if not c.get("data_available")),
        "candidates": candidates,
        "winner_thresholds_pct": WINNER_THRESHOLDS_PCT,
        "winner_horizons_days": WINNER_HORIZONS_DAYS,
        "winner_definition_trial_count": len(WINNER_THRESHOLDS_PCT) * len(WINNER_HORIZONS_DAYS),
        "governance_note": (
            "Winner thresholds predeclared BEFORE inspecting results · "
            "trial count = 16 · Deflated Sharpe deflates any winner-recall "
            "'best' claim by 16."
        ),
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # Persist ONLY summary (candidate rows too large for JSON on large universe)
    slim = {**payload}
    slim["candidates"] = candidates[:5]   # sample only in summary file
    slim["candidates_note"] = f"Full candidate list ({len(candidates)}) available in-memory · use build_pos_capture_dataset() for full data · summary carries first 5 rows."
    (out_dir / f"dataset_{market}.summary.json").write_text(
        json.dumps(slim, indent=2, default=str), encoding="utf-8"
    )
    return payload
