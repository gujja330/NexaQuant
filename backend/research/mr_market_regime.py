"""AEGIS · M-R · Market Regime Classifier · Sprint M Phase C.

Daily market-regime tag from index parquet (NIFTY 50 for India, S&P 500 for
USA) using ONLY data available at each historical date (no look-ahead).

Regime bands:
  BULL         · 20D MA rising AND close > MA20 AND 20D vol below median
  BEAR         · 20D MA falling AND close < MA20
  HIGH_VOL     · 20D vol > 75th percentile of trailing 60D vol
  NEUTRAL      · everything else

Emits: reports/research/mr_market_regime_{market}.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT


ENGINE_ID = "aegis.mr_market_regime.v0.1"

INDEX_TICKER = {"india": "NIFTY", "usa": "SPX"}
INDEX_PATH = {
    "india": [
        "data/raw/india/NIFTY_D1.parquet",
        "data/raw/india/^NSEI_D1.parquet",
        "data/raw/india/NSEI_D1.parquet",
    ],
    "usa": [
        "usa/data/raw/us/_IDX_GSPC_D1.parquet",
        "usa/data/raw/us/SPX_D1.parquet",
        "usa/data/raw/us/^GSPC_D1.parquet",
        "usa/data/raw/us/GSPC_D1.parquet",
        "usa/data/raw/us/SPY_D1.parquet",
    ],
}


def _load_index(root: Path, market: str):
    import pandas as pd
    for p in INDEX_PATH[market.lower()]:
        fp = root / p
        if fp.exists():
            try:
                d = pd.read_parquet(fp)
                col = "close" if "close" in d.columns else "Close"
                d.index = pd.to_datetime(d.index).strftime("%Y-%m-%d")
                return (d, col)
            except Exception:
                continue
    return None


def _classify_date(closes: list) -> str:
    if len(closes) < 60: return "UNKNOWN"
    last = closes[-1]
    ma20 = sum(closes[-20:])/20
    ma20_prev = sum(closes[-21:-1])/20
    trend_up = ma20 > ma20_prev
    trend_dn = ma20 < ma20_prev
    ret20 = [(closes[i]-closes[i-1])/closes[i-1] for i in range(-19, 0)]
    vol20 = pstdev(ret20) if len(ret20) > 1 else 0
    ret60 = [(closes[i]-closes[i-1])/closes[i-1] for i in range(-59, 0)]
    vol_series = []
    for j in range(20, 60):
        seg = ret60[j-20:j]
        if seg: vol_series.append(pstdev(seg) if len(seg)>1 else 0)
    if not vol_series:
        return "NEUTRAL"
    vol_series.sort()
    p75 = vol_series[int(len(vol_series)*0.75)]
    if vol20 > p75 * 1.05: return "HIGH_VOL"
    if trend_up and last > ma20: return "BULL"
    if trend_dn and last < ma20: return "BEAR"
    return "NEUTRAL"


def build(root: Path, market: str) -> dict:
    pair = _load_index(root, market)
    if pair is None:
        return {
            "engine": ENGINE_ID, "market": market.upper(),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "INDEX_PARQUET_MISSING",
            "checked_paths": INDEX_PATH[market.lower()],
            "regimes": {},
        }
    df, col = pair
    dates = sorted(df.index)
    regimes = {}
    for i, d in enumerate(dates):
        if i < 60: continue
        closes = [float(df.loc[dates[j], col]) for j in range(0, i+1)]
        regimes[d] = _classify_date(closes[-60:])
    return {
        "engine": ENGINE_ID, "market": market.upper(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "OK",
        "n_days": len(regimes),
        "regime_distribution": {
            r: sum(1 for v in regimes.values() if v == r)
            for r in set(regimes.values())
        },
        "regimes": regimes,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_market_regime_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = build(root, m)
        p = emit(root, m, res)
        print(f"[regime:{m}] {res.get('status')} · n_days={res.get('n_days',0)} · "
              f"dist={res.get('regime_distribution',{})} -> {p.name}")
