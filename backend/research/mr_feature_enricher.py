"""AEGIS · M-R · Feature Enricher · Sprint M Phase C prep.

Enriches mr_prediction_autopsy_{market}.jsonl with historical features
FROZEN AT PREDICTION DATE (no look-ahead):

  - RSI_14              14-period Wilder RSI as of prediction close
  - ma20_dist_pct       (close - MA20)/MA20 * 100
  - ma50_dist_pct       (close - MA50)/MA50 * 100
  - ma200_dist_pct      (close - MA200)/MA200 * 100
  - vol_20d_pct         20-day close std/mean
  - trend               ABOVE_MA200 / BELOW_MA200 / UNKNOWN
  - avg_dv_60d          60-day avg(close * volume) · liquidity proxy
  - cap_bucket          LARGE / MID / SMALL (derived from avg_dv)
  - momentum_20d_pct    (close - close_20d_ago)/close_20d_ago * 100
  - momentum_60d_pct    same for 60d

Also merges fundamentals (returnOnEquity, quality_score, PE, PB, debt/eq)
from fundamentals.parquet · these are as-of-parquet-write time · noted
as "fundamentals_asof_current" since we don't have historical fundamentals
snapshots. Flagged in output for downstream discipline.

Under M-R sandbox rules. Writes only reports/research/*_enriched.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT


ENGINE_ID = "aegis.mr_feature_enricher.v0.1"
SCHEMA_FINGERPRINT = "aegis.mr_enricher.v0.1.20260827"


def _load_parquet_cached(root: Path, ticker: str, market: str, cache: dict):
    if ticker in cache: return cache[ticker]
    import pandas as pd
    clean = ticker.upper().replace(".NS","").replace(".BO","")
    base = "usa/data/raw/us" if market.lower()=="usa" else "data/raw/india"
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists():
        cache[ticker] = None; return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        vol = None
        for cand in ("volume","Volume","tick_volume","Tick_Volume","real_volume"):
            if cand in df.columns: vol = cand; break
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        cache[ticker] = (df, col, vol)
        return cache[ticker]
    except Exception:
        cache[ticker] = None; return None


def _slice_upto(df, col, iso: str, lookback: int) -> Optional[list]:
    """Return `lookback` close values ending at or before iso · NO lookahead."""
    try:
        dates = sorted(df.index)
        earlier = [d for d in dates if d <= iso]
        if len(earlier) < lookback: return None
        return [float(df.loc[d, col]) for d in earlier[-lookback:]]
    except Exception:
        return None


def _rsi14(closes: list) -> Optional[float]:
    if not closes or len(closes) < 15: return None
    gains = []; losses = []
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i-1]
        gains.append(max(ch, 0))
        losses.append(max(-ch, 0))
    ag = mean(gains[:14]); al = mean(losses[:14])
    for i in range(14, len(gains)):
        ag = (ag*13 + gains[i]) / 14
        al = (al*13 + losses[i]) / 14
    if al == 0: return 100.0
    rs = ag / al
    return round(100 - 100/(1+rs), 2)


def _ma_dist(closes: list, window: int) -> Optional[float]:
    if not closes or len(closes) < window: return None
    ma = sum(closes[-window:]) / window
    if ma == 0: return None
    return round((closes[-1] - ma) / ma * 100, 3)


def _vol_pct(closes: list, window: int = 20) -> Optional[float]:
    if not closes or len(closes) < window: return None
    ret = [(closes[i]-closes[i-1])/closes[i-1] for i in range(-window+1, 0) if closes[i-1]]
    if not ret: return None
    m = mean(ret)
    sd = pstdev(ret) if len(ret) > 1 else 0
    return round(sd * 100, 3)


def _momentum(closes: list, lookback: int) -> Optional[float]:
    if not closes or len(closes) < lookback+1: return None
    p0 = closes[-lookback-1]
    p1 = closes[-1]
    if p0 <= 0: return None
    return round((p1 - p0) / p0 * 100, 3)


def _avg_dv_60d(df, col, vol_col, iso: str) -> Optional[float]:
    if vol_col is None: return None
    try:
        dates = sorted(df.index)
        earlier = [d for d in dates if d <= iso]
        if len(earlier) < 60: return None
        window = earlier[-60:]
        vals = []
        for d in window:
            c = float(df.loc[d, col])
            v = float(df.loc[d, vol_col]) if df.loc[d, vol_col] is not None else 0
            vals.append(c * v)
        return round(mean(vals), 0)
    except Exception:
        return None


def _cap_bucket(avg_dv: Optional[float], market: str) -> str:
    if avg_dv is None: return "UNKNOWN"
    if market.lower() == "usa":
        if avg_dv > 5e8:  return "LARGE"
        if avg_dv > 5e7:  return "MID"
        return "SMALL"
    else:
        if avg_dv > 5e8:  return "LARGE"
        if avg_dv > 5e7:  return "MID"
        return "SMALL"


def _load_fundamentals(root: Path, market: str) -> dict:
    import pandas as pd
    p = root / ("data/raw/india/fundamentals.parquet" if market.lower()=="india"
                else "usa/data/raw/us/fundamentals.parquet")
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        return {str(idx).upper(): {c: (float(v) if not pd.isna(v) else None)
                                     for c, v in row.items()
                                     if isinstance(v, (int, float)) or not pd.isna(v)}
                for idx, row in d.iterrows()}
    except Exception:
        return {}


def enrich(root: Path, market: str) -> tuple:
    src = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not src.exists(): return (0, None)
    fundamentals = _load_fundamentals(root, market)
    cache: dict = {}
    out_rows = []
    for ln in src.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: row = json.loads(ln)
        except Exception: continue
        tk = row.get("ticker","")
        dt = row.get("prediction_date","")
        if not (tk and dt):
            out_rows.append(row); continue
        pair = _load_parquet_cached(root, tk, market, cache)
        if pair is None:
            out_rows.append(row); continue
        df, col, vol_col = pair
        # Feature freeze: use only data up to prediction_date
        closes_200 = _slice_upto(df, col, dt, 200) or _slice_upto(df, col, dt, 60) \
                     or _slice_upto(df, col, dt, 20)
        closes_60 = closes_200[-60:] if closes_200 and len(closes_200)>=60 else None
        closes_20 = closes_200[-20:] if closes_200 and len(closes_200)>=20 else None
        rsi = _rsi14(closes_200[-100:]) if closes_200 and len(closes_200)>=100 else None
        row["rsi_14"]              = rsi
        row["ma20_dist_pct"]       = _ma_dist(closes_200, 20) if closes_200 else None
        row["ma50_dist_pct"]       = _ma_dist(closes_200, 50) if closes_200 and len(closes_200)>=50 else None
        row["ma200_dist_pct"]      = _ma_dist(closes_200, 200) if closes_200 and len(closes_200)>=200 else None
        row["vol_20d_pct"]         = _vol_pct(closes_200, 20) if closes_200 else None
        row["momentum_20d_pct"]    = _momentum(closes_200, 20) if closes_200 else None
        row["momentum_60d_pct"]    = _momentum(closes_200, 60) if closes_200 and len(closes_200)>=61 else None
        row["trend"]               = ("ABOVE_MA200" if row.get("ma200_dist_pct") is not None
                                        and row["ma200_dist_pct"] > 0
                                     else "BELOW_MA200" if row.get("ma200_dist_pct") is not None
                                        else "UNKNOWN")
        row["avg_dv_60d"]          = _avg_dv_60d(df, col, vol_col, dt)
        row["cap_bucket"]          = _cap_bucket(row["avg_dv_60d"], market)
        # Fundamentals · flagged as current-snapshot not historical
        tk_key = tk.upper().replace(".NS","").replace(".BO","")
        f = fundamentals.get(tk_key, {})
        row["fund_roe"]            = f.get("returnOnEquity")
        row["fund_quality_score"]  = f.get("quality_score")
        row["fund_pe"]             = f.get("trailingPE")
        row["fund_pb"]             = f.get("priceToBook")
        row["fund_debt_equity"]    = f.get("debtToEquity")
        row["fundamentals_asof"]   = "CURRENT_SNAPSHOT_NOT_HISTORICAL"
        out_rows.append(row)
    dst = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    return (len(out_rows), dst)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        n, dst = enrich(root, m)
        print(f"[enricher:{m}] rows={n} -> {dst.name if dst else 'none'}")
