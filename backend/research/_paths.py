"""Path resolver for raw price parquets · handles both layouts:

  India: data/raw/india/{TICKER}_D1.parquet
  USA  : usa/data/raw/us/{TICKER}_D1.parquet   (CI writes here per usa_daily.py)
         data/raw/usa/{TICKER}_D1.parquet      (legacy · unused by USA CI)

Every R2/R3 research module should call price_parquet_path() to get the
correct location. Prevents the class of bug where "USA data is 66 days
stale" turns out to be "we were looking in the wrong directory".
"""
from __future__ import annotations

from pathlib import Path


def price_parquet_path(root: Path, market: str, ticker: str):
    """Resolve the parquet path for (market, ticker). Return Path or None."""
    t = str(ticker).upper()
    # Try _D1 then bare
    candidates = []
    if market == "usa":
        # CI-canonical USA location
        candidates.append(root / "usa" / "data" / "raw" / "us" / f"{t}_D1.parquet")
        candidates.append(root / "usa" / "data" / "raw" / "us" / f"{t}.parquet")
        # Legacy · rarely populated
        candidates.append(root / "data" / "raw" / "usa" / f"{t}_D1.parquet")
        candidates.append(root / "data" / "raw" / "usa" / f"{t}.parquet")
    else:
        candidates.append(root / "data" / "raw" / market / f"{t}_D1.parquet")
        candidates.append(root / "data" / "raw" / market / f"{t}.parquet")
    for p in candidates:
        if p.exists():
            return p
    return None


def price_parquet_dir(root: Path, market: str) -> Path:
    """Directory that HAS raw price parquets · used for freshness checks."""
    if market == "usa":
        p = root / "usa" / "data" / "raw" / "us"
        if p.exists(): return p
    return root / "data" / "raw" / market
