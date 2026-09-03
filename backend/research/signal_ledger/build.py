"""AEGIS · Daily Signal Ledger · builder

Sources:
  - reports/recommendations_history/{market}/*.json    (per-day R2 snapshots)
  - usa/reports/recommendations_history/{market}/*.json
  - data/raw/{market}/{TICKER}_D1.parquet              (OHLC)

Output:
  - reports/research/signal_ledger/{market}.parquet    (append + dedupe)

Ledger schema fixed as LEDGER_SCHEMA below. Forward returns use close-to-close
over 5/10/20/60 trading days from the entry date. If any of the horizons
extends past the last available bar, the return is NaN (not zero).

Deterministic + idempotent · Article 30 shared-indicator conventions apply
to entry price (close on asof).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

_ROOT = Path(__file__).resolve().parents[3]

LEDGER_SCHEMA = [
    "asof",                       # yyyy-mm-dd of snapshot
    "market",                     # india | usa
    "runner",                     # R1 | R2 | R3
    "ticker",
    "action",                     # canonical: BUY/ADD/HOLD/TRIM/SELL/EXIT
    "ensemble_score",             # [-1, 1]
    "calibrated_confidence",      # [0, 1]
    "regime_adjusted_confidence", # [0, 1]
    "model_agreement",            # [0, 1] · fraction of models agreeing
    "disagreement_flag",          # bool
    "n_models_scoring",           # int
    "sector",
    "industry",
    "entry_price",                # close on asof (float)
    "ret_5d",
    "ret_10d",
    "ret_20d",
    "ret_60d",
    "ledger_built_utc",
]


def _parquet_path(root: Path, market: str, ticker: str) -> Path:
    from backend.research._paths import price_parquet_path
    resolved = price_parquet_path(root, market, ticker)
    if resolved: return resolved
    return root / "data" / "raw" / market / f"{ticker}_D1.parquet"


def _clean_ticker_key(t: str) -> str:
    """India tickers arrive as 'RELIANCE.NS'; parquets are 'RELIANCE_D1.parquet'."""
    if not t:
        return ""
    t = str(t).upper()
    # Strip .NS / .BO suffix for India
    for suf in (".NS", ".BO", ".NSE", ".BSE"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    return t


def _fwd_return(closes, entry_idx: int, horizon: int) -> Optional[float]:
    """close-to-close forward return over `horizon` trading days.
    Returns None if horizon extends past series end."""
    if entry_idx < 0 or entry_idx >= len(closes):
        return None
    exit_idx = entry_idx + horizon
    if exit_idx >= len(closes):
        return None
    ep = float(closes[entry_idx])
    xp = float(closes[exit_idx])
    if ep <= 0:
        return None
    return (xp / ep) - 1.0


def _snapshot_files(root: Path, market: str) -> list[Path]:
    out: list[Path] = []
    a = root / "reports" / "recommendations_history" / market
    if a.exists():
        out.extend(sorted(a.glob("*.json")))
    b = root / "usa" / "reports" / "recommendations_history" / market
    if b.exists():
        out.extend(sorted(b.glob("*.json")))
    # Include today's live file
    live = (root / "reports" / "recommendations_v3.json") if market != "usa" else (
        root / "usa" / "reports" / "recommendations_v3.json"
    )
    if live.exists():
        out.append(live)
    return out


def _rows_from_snapshot(snapshot_path: Path, market: str) -> Iterable[dict]:
    try:
        d = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    if not isinstance(d, dict):
        return []
    if d.get("market") not in (market, market.lower()):
        # allow when a per-file snapshot doesn't stamp market
        pass
    asof = str(d.get("asof") or "")
    if not asof:
        return []
    recs = d.get("recommendations") or []
    rows = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        rows.append({
            "asof": asof,
            "market": market,
            "runner": "R2",
            "ticker": _clean_ticker_key(r.get("ticker", "")),
            "action": str(r.get("action", "HOLD")).upper(),
            "ensemble_score": r.get("ensemble_score"),
            "calibrated_confidence": r.get("calibrated_confidence"),
            "regime_adjusted_confidence": r.get("regime_adjusted_confidence"),
            "model_agreement": r.get("model_agreement"),
            "disagreement_flag": bool(r.get("disagreement_flag")),
            "n_models_scoring": r.get("n_models_scoring"),
            "sector": r.get("sector"),
            "industry": r.get("industry"),
        })
    return rows


def _attach_prices_and_returns(rows: list[dict], root: Path) -> list[dict]:
    """Load each ticker's parquet lazily and attach entry_price + ret_*."""
    import pandas as pd

    cache: dict[str, "pd.DataFrame"] = {}
    for row in rows:
        market = row["market"]
        tkr_key = row["ticker"]
        if not tkr_key:
            continue
        cache_key = f"{market}:{tkr_key}"
        if cache_key not in cache:
            p = _parquet_path(root, market, tkr_key)
            if not p.exists():
                cache[cache_key] = None
                continue
            try:
                df = pd.read_parquet(p)
                # normalize date index
                if "time" in df.columns:
                    df = df.rename(columns={"time": "date"})
                    df.index = pd.to_datetime(df.index)
                cache[cache_key] = df
            except Exception:
                cache[cache_key] = None
                continue
        df = cache[cache_key]
        if df is None or df.empty:
            continue
        asof_dt = pd.to_datetime(row["asof"]).normalize()
        # Find entry row · asof exactly, else last bar <= asof
        try:
            if asof_dt in df.index:
                entry_idx = df.index.get_loc(asof_dt)
            else:
                mask = df.index <= asof_dt
                if not mask.any():
                    continue
                entry_idx = mask.sum() - 1
        except Exception:
            continue
        if isinstance(entry_idx, slice) or hasattr(entry_idx, "__len__"):
            # duplicate index guard
            continue
        closes = df["close"].to_numpy()
        row["entry_price"] = float(closes[entry_idx]) if entry_idx >= 0 else None
        row["ret_5d"] = _fwd_return(closes, entry_idx, 5)
        row["ret_10d"] = _fwd_return(closes, entry_idx, 10)
        row["ret_20d"] = _fwd_return(closes, entry_idx, 20)
        row["ret_60d"] = _fwd_return(closes, entry_idx, 60)
    return rows


def load_ledger(root: Path, market: str):
    """Load existing ledger or return empty DataFrame with correct schema."""
    import pandas as pd
    p = root / "reports" / "research" / "signal_ledger" / f"{market}.parquet"
    if not p.exists():
        return pd.DataFrame(columns=LEDGER_SCHEMA)
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame(columns=LEDGER_SCHEMA)


def build_ledger(root: Path, market: str) -> dict:
    """Rebuild ledger for `market` from all available snapshots.

    Returns build summary dict."""
    import pandas as pd

    rows: list[dict] = []
    files = _snapshot_files(root, market)
    for fp in files:
        for r in _rows_from_snapshot(fp, market):
            rows.append(r)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in rows:
        r["ledger_built_utc"] = now

    rows = _attach_prices_and_returns(rows, root)

    if not rows:
        return {"market": market, "n_rows": 0, "n_snapshots": len(files),
                "note": "no snapshots or empty rec files"}

    df = pd.DataFrame(rows)
    # Enforce schema order (missing cols → NaN)
    for c in LEDGER_SCHEMA:
        if c not in df.columns:
            df[c] = None
    df = df[LEDGER_SCHEMA]

    # Dedupe by (market, runner, asof, ticker) · last-write wins
    df = df.drop_duplicates(subset=["market", "runner", "asof", "ticker"], keep="last")
    df = df.sort_values(["asof", "ticker"]).reset_index(drop=True)

    out = root / "reports" / "research" / "signal_ledger"
    out.mkdir(parents=True, exist_ok=True)
    parquet_path = out / f"{market}.parquet"
    df.to_parquet(parquet_path, index=False)

    # Also emit compact JSON summary for quick inspection
    n_by_asof = df.groupby("asof").size().to_dict()
    n_by_action = df.groupby("action").size().to_dict()
    n_with_ret5 = int(df["ret_5d"].notna().sum())
    summary = {
        "market": market,
        "n_rows": int(len(df)),
        "n_snapshots": len(files),
        "n_by_asof": {str(k): int(v) for k, v in n_by_asof.items()},
        "n_by_action": {str(k): int(v) for k, v in n_by_action.items()},
        "n_with_ret_5d": n_with_ret5,
        "parquet_path": str(parquet_path.relative_to(root)),
        "built_utc": now,
    }
    (out / f"{market}.summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    summary = build_ledger(root, args.market)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
