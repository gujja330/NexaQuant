"""Correlation matrix · rolling 30d return correlations across universe.

Output: reports/correlation_matrix.json
{
  "asof": "2026-08-05",
  "window_days": 30,
  "n_tickers": 229,
  "high_correlation_pairs": [{"a":"TCS","b":"INFY","corr":0.87}, ...],
  "sector_avg_correlation": {"IT": 0.62, "Financials": 0.55, ...},
  "portfolio_concentration_risk": [{"ticker":"TCS","avg_corr_to_others":0.71,"warning":true}]
}

Rendered small · full matrix would be 229×229. We keep highlights only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


HIGH_CORR_THRESHOLD = 0.75


def _bars_dir(root: Path, market: str) -> Path:
    if market == "usa":
        return root / "usa" / "data" / "raw" / "us"
    return root / "data" / "raw" / "india"


def _sector_map(root: Path, market: str) -> dict:
    if market == "india":
        try:
            import sys as _sys
            _sys.path.insert(0, str(root))
            from india.sectors import SECTORS as _S
            return {k.upper(): v for k, v in _S.items()}
        except Exception:
            pass
    return {}


def compute_correlation(root: Path, market: str, asof: str,
                              window_days: int = 30) -> dict:
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        return {"available": False, "reason": "pandas/numpy missing"}

    bars = _bars_dir(root, market)
    if not bars.exists():
        return {"available": False, "reason": f"no bars at {bars}"}

    # Load closes for every ticker
    closes = {}
    for pq in bars.glob("*_D1.parquet"):
        if pq.name.startswith("_IDX_"): continue
        ticker = pq.stem.replace("_D1", "").replace(".NS", "").replace(".BO", "")
        try:
            df = pd.read_parquet(pq)
            col = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
            if col is None: continue
            if len(df) < window_days + 5: continue
            closes[ticker.upper()] = df[col].tail(window_days + 1).values
        except Exception:
            continue

    if len(closes) < 3:
        return {"available": False, "reason": f"only {len(closes)} tickers with data"}

    # Returns matrix
    rets = {}
    for t, c in closes.items():
        if len(c) < 2: continue
        r = np.diff(c) / c[:-1]
        if len(r) >= window_days:
            rets[t] = r[-window_days:]

    if len(rets) < 3:
        return {"available": False, "reason": f"only {len(rets)} tickers with returns"}

    # Build correlation matrix
    df = pd.DataFrame(rets)
    corr = df.corr()

    # Extract high-correlation pairs (upper triangle only)
    high_pairs = []
    n_ticks = len(df.columns)
    for i in range(n_ticks):
        for j in range(i + 1, n_ticks):
            c = corr.iloc[i, j]
            if abs(c) >= HIGH_CORR_THRESHOLD:
                high_pairs.append({
                    "a": df.columns[i], "b": df.columns[j],
                    "corr": round(float(c), 3),
                })
    high_pairs.sort(key=lambda x: -abs(x["corr"]))

    # Per-ticker avg correlation to all others (concentration risk)
    avg_corr = {}
    for t in df.columns:
        row = corr[t].drop(t)
        avg_corr[t] = round(float(row.mean()), 3)
    concentration = [{"ticker": t, "avg_corr_to_others": v,
                            "warning": v > 0.55}
                          for t, v in sorted(avg_corr.items(), key=lambda x: -x[1])[:20]]

    # Sector-level avg correlation
    sector_map = _sector_map(root, market)
    from collections import defaultdict
    sec_pairs = defaultdict(list)
    for i in range(n_ticks):
        for j in range(i + 1, n_ticks):
            si = sector_map.get(df.columns[i], "Unknown")
            sj = sector_map.get(df.columns[j], "Unknown")
            if si == sj:
                sec_pairs[si].append(float(corr.iloc[i, j]))
    sector_avg = {s: round(sum(v) / len(v), 3)
                       for s, v in sec_pairs.items() if len(v) >= 3}

    return {
        "engine":                "aegis.context.correlation.v0.1",
        "asof":                  asof, "market": market,
        "generated_utc":         datetime.now(timezone.utc).isoformat(),
        "available":             True,
        "window_days":           window_days,
        "n_tickers":             n_ticks,
        "n_high_correlation_pairs": len(high_pairs),
        "high_correlation_pairs": high_pairs[:30],
        "sector_avg_correlation": sector_avg,
        "portfolio_concentration_risk": concentration,
    }


def emit(root: Path, payload: dict) -> Path:
    p = root / "reports" / "correlation_matrix.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
