"""Historical learning features — from the learning corpus (if available).

Reads `reports/learning.parquet` (India) or `usa/reports/learning.parquet`
(USA · not yet built). Emits null if the corpus is missing — that's the
walk-forward-honest signal.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from backend.canonical.schemas import CanonicalDataset


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str,
             repo_root: Path | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {t: {} for t in universe}
    if repo_root is None:
        return out
    if market_name == "usa":
        p = repo_root / "usa" / "reports" / "learning.parquet"
    else:
        p = repo_root / "reports" / "learning.parquet"
    if not p.exists():
        return out
    try:
        df = pd.read_parquet(p)
    except Exception:
        return out
    if "ticker" not in df.columns or df.empty:
        return out
    # walk-forward: filter to rows entered before asof if entry_date exists
    if "entry_date" in df.columns:
        df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
        df = df[df["entry_date"].dt.date <= asof]
    for t in universe:
        rows = df[df["ticker"] == t]
        if rows.empty:
            continue
        n = int(len(rows))
        wr = None; avg_r = None
        if "is_winner" in rows.columns:
            wr = round(float(rows["is_winner"].mean()), 4)
        if "return_pct" in rows.columns:
            avg_r = round(float(rows["return_pct"].mean()), 4)
        out[t]["hist_ticker_n_trades"]       = n
        out[t]["hist_ticker_win_rate"]       = wr
        out[t]["hist_ticker_avg_return_pct"] = avg_r
    return out
