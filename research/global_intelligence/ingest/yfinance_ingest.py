"""DEV017 v0.1 ingest — yfinance-only fetcher.

Fetches the ARCH017 §3 variable catalogue subset that is available via yfinance.
Writes RawObservation rows to data/market_intelligence/raw/YYYY-MM/*.parquet.

Idempotent by checksum (ARCH017A §4.2).
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from ..lib import catalog
from ..lib.schema import RawObservation, as_dict


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "market_intelligence" / "raw"


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def fetch_variable(spec: catalog.VariableSpec, period_days: int = 300) -> list[RawObservation]:
    """Fetch the latest N days of a single variable. Returns RawObservations.

    Default 300 days = enough for 120-day momentum + 252-day percentile normalisation.
    Subsequent runs dedup by checksum (ARCH017A §4.2 idempotence) so re-fetch is free.
    """
    import yfinance as yf                                            # local import for testability

    code_sha = _git_sha()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=period_days + 5)                    # buffer for weekends
    try:
        df = yf.download(spec.yfinance_ticker,
                          start=start.strftime("%Y-%m-%d"),
                          end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                          progress=False, auto_adjust=False, threads=False)
    except Exception as e:
        print(f"        [WARN] fetch failed {spec.variable_key}: {e}")
        return []

    if df is None or df.empty:
        return []

    # yfinance returns MultiIndex columns when auto_adjust=False in some versions
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    out: list[RawObservation] = []
    for ts, row in df.iterrows():
        close = row.get("Close")
        if pd.isna(close):
            continue
        asof_utc = pd.Timestamp(ts).tz_localize("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ") \
            if pd.Timestamp(ts).tzinfo is None \
            else pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        obs = RawObservation(
            variable_key=spec.variable_key,
            asof_utc=asof_utc,
            value=float(close),
            unit=spec.unit,
            source_id=spec.source_id,
            code_sha=code_sha,
            source_row={"Open": _f(row.get("Open")), "High": _f(row.get("High")),
                          "Low": _f(row.get("Low")), "Close": _f(close),
                          "Volume": _f(row.get("Volume"))},
        )
        out.append(obs)
    return out


def _f(x) -> float | None:
    if x is None or pd.isna(x):
        return None
    return float(x)


def store(observations: list[RawObservation]) -> Path:
    """Append observations to the current-month parquet partition."""
    if not observations:
        return Path()
    now = datetime.now(timezone.utc)
    partition = RAW_DIR / f"{now.year:04d}-{now.month:02d}"
    partition.mkdir(parents=True, exist_ok=True)
    fname = partition / f"observations_{now.strftime('%Y%m%d')}.parquet"

    new_df = pd.DataFrame([as_dict(o) for o in observations])
    # Dedup by checksum (ARCH017A §4.2 idempotence)
    if fname.exists():
        old = pd.read_parquet(fname)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["checksum"], keep="first")
    else:
        merged = new_df.drop_duplicates(subset=["checksum"], keep="first")
    merged.to_parquet(fname, index=False)
    return fname


def fetch_all(verbose: bool = True) -> dict:
    """Fetch every variable in the catalog. Return a summary."""
    result = {"variables_attempted": 0, "variables_succeeded": 0,
                "rows_written": 0, "failures": [], "partition": None}
    all_new: list[RawObservation] = []
    for spec in catalog.ALL_VARIABLES:
        result["variables_attempted"] += 1
        if verbose:
            print(f"        [{spec.variable_key:<38}] fetching {spec.yfinance_ticker:>10} ", end="", flush=True)
        rows = fetch_variable(spec)
        if rows:
            result["variables_succeeded"] += 1
            all_new.extend(rows)
            if verbose:
                print(f" -> {len(rows)} bars, latest={rows[-1].value:.2f} @ {rows[-1].asof_utc[:10]}")
        else:
            result["failures"].append(spec.variable_key)
            if verbose:
                print(f" -> [NO DATA]")
        time.sleep(0.15)                                               # rate-limit courtesy

    if all_new:
        partition = store(all_new)
        result["partition"] = str(partition)
        result["rows_written"] = len(all_new)
    return result
