"""Continuous Benchmark v1.0.

For every historical closed trade in learning.parquet:
  1. Compute AEGIS return                     (from parquet)
  2. Compute NIFTY return over the same window (NSEI parquet)
  3. Compute synthetic sector-peer return      (mean of same-sector
     tickers' price returns over the same window, excluding the
     target ticker)
  4. Excess alpha = AEGIS return − NIFTY return

Aggregations:
  • per_ticker  → avg alpha, n_beat_nifty, n_lost_to_nifty, beat_rate
  • by_sector   → avg alpha per sector
  • portfolio   → overall aggregates

All computations deterministic (sorted iteration, no random state).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


_ROOT = Path(__file__).resolve().parents[3]
LEARNING     = _ROOT / "reports" / "learning.parquet"
RAW_DIR      = _ROOT / "data" / "raw" / "india"
NIFTY_PATH   = RAW_DIR / "NSEI_D1.parquet"


# ── Data loaders ──────────────────────────────────────────────────────

def _load_close_series(path: Path) -> pd.Series | None:
    if not path.exists(): return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    if df.empty: return None
    close_col = next((c for c in df.columns if c.lower() in ("close", "adj close", "adj_close")), None)
    if not close_col: return None
    date_col = next((c for c in df.columns if c.lower() in ("date", "dt", "timestamp", "time")), None)
    if date_col and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col).set_index(date_col)
    else:
        try:
            df.index = pd.to_datetime(df.index, errors="coerce")
        except Exception:
            return None
        df = df.sort_index()
    return df[close_col].dropna().astype(float)


def load_nifty() -> pd.Series | None:
    return _load_close_series(NIFTY_PATH)


def _period_return(series: pd.Series, start_date, end_date) -> float | None:
    if series is None or series.empty: return None
    try:
        s = pd.to_datetime(start_date)
        e = pd.to_datetime(end_date)
    except Exception:
        return None
    # Prices at/just-before the target dates
    before_s = series[series.index <= s]
    before_e = series[series.index <= e]
    if before_s.empty or before_e.empty: return None
    p_s = float(before_s.iloc[-1])
    p_e = float(before_e.iloc[-1])
    if p_s <= 0: return None
    return (p_e - p_s) / p_s


def _synthetic_sector_return(sector: str, ticker: str, start_date, end_date,
                                _cache: dict) -> float | None:
    """Mean price return over [start, end] across all tickers in the same
    sector as `ticker` (excluding the target). We derive the sector universe
    once per call from learning.parquet (cached in `_cache`)."""
    if not sector:
        return None
    if "peers_by_sector" not in _cache:
        return None
    peers = _cache["peers_by_sector"].get(sector, [])
    peers = [t for t in peers if t != ticker]
    if not peers:
        return None
    rets: list[float] = []
    for peer in peers:
        s = _cache["price_series"].get(peer)
        if s is None:
            s = _load_close_series(RAW_DIR / f"{peer}_D1.parquet")
            _cache["price_series"][peer] = s
            if s is None: continue
        r = _period_return(s, start_date, end_date)
        if r is not None:
            rets.append(r)
    if not rets: return None
    return float(np.mean(rets))


# ── Main computation ──────────────────────────────────────────────────

def compute_benchmark(max_peers: int = 20) -> dict:
    """One-shot benchmark computation over the full learning.parquet."""
    if not LEARNING.exists():
        return {"available": False, "reason": "learning.parquet missing"}

    lf = pd.read_parquet(LEARNING)
    if lf.empty or "return_pct" not in lf.columns:
        return {"available": False, "reason": "learning.parquet empty or missing return_pct"}

    # Normalise return_pct to fraction if stored as percent
    if lf["return_pct"].abs().median() > 1.0:
        lf["return_pct"] = lf["return_pct"] / 100.0

    lf["entry_date"] = pd.to_datetime(lf["entry_date"], errors="coerce")
    lf["exit_date"]  = pd.to_datetime(lf["exit_date"],  errors="coerce")
    lf = lf.dropna(subset=["entry_date", "exit_date", "return_pct"])

    # Sorted iteration → deterministic
    lf = lf.sort_values(["ticker", "entry_date"]).reset_index(drop=True)

    nifty = load_nifty()
    nifty_available = nifty is not None and not nifty.empty

    # Peer universe per sector (up to `max_peers` most common)
    peers_by_sector: dict[str, list[str]] = {}
    if "sector" in lf.columns:
        for sector, grp in lf.groupby("sector"):
            tickers = grp["ticker"].value_counts().head(max_peers).index.tolist()
            peers_by_sector[str(sector)] = sorted([str(t) for t in tickers])

    cache = {"peers_by_sector": peers_by_sector, "price_series": {}}

    trade_rows: list[dict] = []
    for _, r in lf.iterrows():
        ticker = str(r["ticker"])
        sector = str(r.get("sector") or "")
        aegis_ret = float(r["return_pct"])
        nifty_ret  = _period_return(nifty, r["entry_date"], r["exit_date"]) if nifty_available else None
        sector_ret = _synthetic_sector_return(sector, ticker, r["entry_date"], r["exit_date"], cache)
        excess     = (aegis_ret - nifty_ret) if (nifty_ret is not None) else None
        trade_rows.append({
            "ticker":      ticker,
            "sector":      sector,
            "entry_date":  str(r["entry_date"].date()),
            "exit_date":   str(r["exit_date"].date()),
            "aegis_return": round(aegis_ret, 5),
            "nifty_return": round(nifty_ret, 5) if nifty_ret is not None else None,
            "sector_return": round(sector_ret, 5) if sector_ret is not None else None,
            "excess_alpha": round(excess, 5) if excess is not None else None,
            "beat_nifty":  (aegis_ret > nifty_ret) if nifty_ret is not None else None,
            "beat_sector": (aegis_ret > sector_ret) if sector_ret is not None else None,
        })

    tdf = pd.DataFrame(trade_rows)

    # ── Portfolio-level aggregate
    scored = tdf[tdf["excess_alpha"].notna()]
    portfolio = {
        "n_trades_total":     int(len(tdf)),
        "n_trades_benchmarked": int(len(scored)),
        "aegis_avg_return":   round(float(tdf["aegis_return"].mean()), 5),
        "aegis_median_return": round(float(tdf["aegis_return"].median()), 5),
        "nifty_avg_return":   round(float(scored["nifty_return"].mean()), 5) if len(scored) else None,
        "sector_avg_return":  round(float(scored["sector_return"].mean()), 5) if scored["sector_return"].notna().any() else None,
        "excess_alpha_avg":   round(float(scored["excess_alpha"].mean()), 5) if len(scored) else None,
        "excess_alpha_median": round(float(scored["excess_alpha"].median()), 5) if len(scored) else None,
        "n_beat_nifty":       int(scored["beat_nifty"].sum()) if len(scored) else 0,
        "n_lost_to_nifty":    int(len(scored) - scored["beat_nifty"].sum()) if len(scored) else 0,
        "pct_beat_nifty":     round(float(scored["beat_nifty"].mean()), 4) if len(scored) else None,
        "verdict":            None,
    }
    if portfolio["excess_alpha_avg"] is not None:
        if portfolio["excess_alpha_avg"] > 0.02:
            portfolio["verdict"] = "alpha_generated"
        elif portfolio["excess_alpha_avg"] < -0.02:
            portfolio["verdict"] = "underperformed_nifty"
        else:
            portfolio["verdict"] = "at_par"

    # ── Per-ticker aggregate
    per_ticker: dict[str, dict] = {}
    for ticker, grp in tdf.groupby("ticker"):
        grp_s = grp[grp["excess_alpha"].notna()]
        per_ticker[str(ticker)] = {
            "ticker":               str(ticker),
            "n_trades":             int(len(grp)),
            "aegis_avg_return":     round(float(grp["aegis_return"].mean()), 5),
            "nifty_avg_return":     round(float(grp_s["nifty_return"].mean()), 5) if len(grp_s) else None,
            "sector_avg_return":    round(float(grp_s["sector_return"].mean()), 5) if grp_s["sector_return"].notna().any() else None,
            "excess_alpha_avg":     round(float(grp_s["excess_alpha"].mean()), 5) if len(grp_s) else None,
            "n_beat_nifty":         int(grp_s["beat_nifty"].sum()) if len(grp_s) else 0,
            "pct_beat_nifty":       round(float(grp_s["beat_nifty"].mean()), 4) if len(grp_s) else None,
            "verdict":              None,
        }
        alpha = per_ticker[str(ticker)]["excess_alpha_avg"]
        if alpha is not None:
            if alpha > 0.02:   per_ticker[str(ticker)]["verdict"] = "alpha_generated"
            elif alpha < -0.02: per_ticker[str(ticker)]["verdict"] = "underperformed_nifty"
            else:               per_ticker[str(ticker)]["verdict"] = "at_par"

    # ── By-sector aggregate
    by_sector: dict[str, dict] = {}
    if "sector" in tdf.columns:
        for sector, grp in tdf.groupby("sector"):
            grp_s = grp[grp["excess_alpha"].notna()]
            by_sector[str(sector)] = {
                "sector":            str(sector),
                "n_trades":          int(len(grp)),
                "aegis_avg_return":  round(float(grp["aegis_return"].mean()), 5),
                "nifty_avg_return":  round(float(grp_s["nifty_return"].mean()), 5) if len(grp_s) else None,
                "excess_alpha_avg":  round(float(grp_s["excess_alpha"].mean()), 5) if len(grp_s) else None,
                "pct_beat_nifty":    round(float(grp_s["beat_nifty"].mean()), 4) if len(grp_s) else None,
            }

    # ── Top & bottom performers (by excess alpha, min 3 trades)
    ranking = [(t, v["excess_alpha_avg"], v["n_trades"], v["pct_beat_nifty"])
                 for t, v in per_ticker.items()
                 if v["excess_alpha_avg"] is not None and v["n_trades"] >= 3]
    ranking.sort(key=lambda x: (-(x[1] or -9), -x[2], x[0]))
    top_alpha    = [{"ticker": t, "excess_alpha_avg": a, "n_trades": n, "pct_beat_nifty": b}
                      for t, a, n, b in ranking[:10]]
    bottom_alpha = [{"ticker": t, "excess_alpha_avg": a, "n_trades": n, "pct_beat_nifty": b}
                      for t, a, n, b in ranking[-10:][::-1]]

    return {
        "available":      True,
        "index_used":     "NSEI",
        "index_available": nifty_available,
        "peers_max_per_sector": max_peers,
        "portfolio":      portfolio,
        "per_ticker":     per_ticker,
        "by_sector":      by_sector,
        "top_alpha":      top_alpha,
        "bottom_alpha":   bottom_alpha,
        # Full trade-level detail (may be large — kept for provenance)
        "trades":         trade_rows,
    }
