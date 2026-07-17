"""DEV018 ingest — fetches NSE sector indices via yfinance.

Reuses the ARCH017A canonical entities from DEV017 (no duplication).
Idempotent by checksum. Falls back through alternate tickers on empty response.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from global_intelligence.lib.schema import RawObservation, as_dict           # noqa: E402
from sector_intelligence.lib import sector_catalog                             # noqa: E402


RAW_DIR = _ROOT / "data" / "market_intelligence" / "raw"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def _fetch_one(ticker: str, period_days: int) -> pd.DataFrame:
    import yfinance as yf
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=period_days + 5)
    try:
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                          end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                          progress=False, auto_adjust=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def fetch_sector(spec: sector_catalog.SectorSpec, period_days: int = 300) -> tuple[list[RawObservation], str | None]:
    """Try each yfinance ticker in order; return (observations, ticker_used) or ([], None)."""
    code_sha = _git_sha()
    for ticker in spec.yfinance_tickers:
        df = _fetch_one(ticker, period_days)
        if df is None or df.empty:
            continue
        out: list[RawObservation] = []
        for ts, row in df.iterrows():
            close = row.get("Close")
            if pd.isna(close):
                continue
            asof_utc = (pd.Timestamp(ts).tz_localize("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                        if pd.Timestamp(ts).tzinfo is None
                        else pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
            obs = RawObservation(
                variable_key=spec.sector_key + ".close",
                asof_utc=asof_utc,
                value=float(close),
                unit=spec.unit,
                source_id=f"{spec.source_id}[{ticker}]",
                code_sha=code_sha,
                source_row={"Open": _f(row.get("Open")), "High": _f(row.get("High")),
                              "Low": _f(row.get("Low")), "Close": _f(close),
                              "Volume": _f(row.get("Volume"))},
            )
            out.append(obs)
        if out:
            return out, ticker
    return [], None


def _f(x) -> float | None:
    if x is None or pd.isna(x):
        return None
    return float(x)


def store(observations: list[RawObservation]) -> Path:
    if not observations:
        return Path()
    now = datetime.now(timezone.utc)
    partition = RAW_DIR / f"{now.year:04d}-{now.month:02d}"
    partition.mkdir(parents=True, exist_ok=True)
    fname = partition / f"observations_{now.strftime('%Y%m%d')}.parquet"

    new_df = pd.DataFrame([as_dict(o) for o in observations])
    if fname.exists():
        old = pd.read_parquet(fname)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["checksum"], keep="first")
    else:
        merged = new_df.drop_duplicates(subset=["checksum"], keep="first")
    merged.to_parquet(fname, index=False)
    return fname


def fetch_all(verbose: bool = True) -> dict:
    result = {"attempted": 0, "succeeded": 0, "rows_written": 0,
                "failures": [], "used_tickers": {}, "partition": None}
    all_new: list[RawObservation] = []
    for spec in sector_catalog.SECTORS:
        result["attempted"] += 1
        if verbose:
            print(f"        [{spec.sector_key:<36}] fetching ", end="", flush=True)
        rows, used = fetch_sector(spec)
        if rows:
            result["succeeded"] += 1
            all_new.extend(rows)
            result["used_tickers"][spec.sector_key] = used
            if verbose:
                print(f" -> {len(rows)} bars via {used}, latest={rows[-1].value:.2f} @ {rows[-1].asof_utc[:10]}")
        else:
            result["failures"].append(spec.sector_key)
            if verbose:
                print(f" -> [NO DATA] tried {spec.yfinance_tickers}")
        time.sleep(0.2)                                                  # rate-limit courtesy
    if all_new:
        partition = store(all_new)
        result["partition"] = str(partition)
        result["rows_written"] = len(all_new)
    return result
