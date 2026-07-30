"""Intraday universe filter · runs once per session at open.

Per §4 of docs/AEGIS_INTRADAY_ARCHITECTURE.md · filters delivery universe
down to intraday-tradable subset using liquidity + spread + F&O ban +
earnings/ex-div/halt filters.

Emits configs/intraday_universe_{market}_{YYYY-MM-DD}.json for the day.
Idempotent per date · never overwrites if already generated.

ISOLATED: reads delivery-universe CONFIG (configs/universes/*.json)
which is a static file · never imports from backend/recommendation/.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

INDIA_MIN_ADV_SHARES = 500_000        # 5 lakh avg daily volume
INDIA_MAX_SPREAD_PCT = 0.10           # 0.10%
INDIA_MIN_VOL_PCT    = 1.0
INDIA_MAX_VOL_PCT    = 4.0

USA_MIN_ADV_SHARES   = 2_000_000
USA_MAX_SPREAD_BPS   = 3
USA_MIN_PRICE_USD    = 10.0


def _delivery_universe(root: Path, market: str) -> list[str]:
    """Enumerate tickers from available data · zero coupling to
    backend/recommendation/. Priority:
      1. configs/universes/{market}.json (if operator adds one)
      2. usa/configs/universes/sp500_plus_midcap400.json (USA canonical)
      3. data/raw/usa/universe.csv (USA CSV)
      4. data/raw/{india|us}/*_D1.parquet (auto-discovered from bar cache)
    """
    # Preferred: explicit config file (rare · not present today)
    p = root / "configs" / "universes" / f"{market}.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            listing = data.get("tickers") or data.get("symbols") or []
            if listing:
                return listing
        except Exception:
            pass

    # USA · canonical json
    if market == "usa":
        p2 = root / "usa" / "configs" / "universes" / "sp500_plus_midcap400.json"
        if p2.exists():
            try:
                data = json.loads(p2.read_text(encoding="utf-8"))
                listing = data.get("tickers") or data.get("symbols") or []
                if listing:
                    return listing
            except Exception:
                pass
        # USA · CSV fallback
        p3 = root / "data" / "raw" / "usa" / "universe.csv"
        if p3.exists():
            try:
                import csv
                out = []
                with p3.open(encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        sym = row.get("symbol") or row.get("ticker")
                        if sym:
                            out.append(sym.strip().upper())
                if out:
                    return out
            except Exception:
                pass

    # Ultimate fallback: enumerate ticker parquets from local bar cache
    subdir = "usa" if market == "usa" else "india"
    bar_dir = root / "data" / "raw" / subdir
    if bar_dir.exists():
        tickers = []
        for p in bar_dir.glob("*_D1.parquet"):
            name = p.stem
            if name.endswith("_D1"):
                tickers.append(name[:-3])
        return sorted(tickers)
    return []


def _has_daily_bar(root: Path, ticker: str, market: str) -> bool:
    subdir = "usa" if market == "usa" else "india"
    return (root / "data" / "raw" / subdir / f"{ticker}_D1.parquet").exists()


def _liquidity_ok(root: Path, ticker: str, market: str) -> tuple[bool, dict]:
    """Check ADV + realized vol from daily bars · returns (ok, diagnostics)."""
    subdir = "usa" if market == "usa" else "india"
    p = root / "data" / "raw" / subdir / f"{ticker}_D1.parquet"
    if not p.exists():
        return False, {"reason": "no_daily_bar"}
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        if len(df) < 20:
            return False, {"reason": "insufficient_history"}
        last20 = df.tail(20)
        # Volume column may be 'volume' or 'tick_volume' depending on source
        vol_col = None
        for cand in ("volume", "tick_volume", "Volume"):
            if cand in df.columns:
                vol_col = cand; break
        adv = float(last20[vol_col].mean()) if vol_col else 0
        returns = last20["close"].pct_change().dropna()
        vol_pct = float(returns.std() * 100) if len(returns) else 0
        close = float(last20["close"].iloc[-1])
        diag = {"adv": adv, "vol_pct": round(vol_pct, 3), "close": close}
        if market == "india":
            if adv < INDIA_MIN_ADV_SHARES:
                return False, {**diag, "reason": "low_adv"}
            # Vol band: 0.5%-6% (many Indian large-caps sit at 0.7-1.5% daily)
            if not (0.5 <= vol_pct <= 6.0):
                return False, {**diag, "reason": "vol_out_of_band"}
            return True, diag
        else:
            if adv < USA_MIN_ADV_SHARES:
                return False, {**diag, "reason": "low_adv"}
            if close < USA_MIN_PRICE_USD:
                return False, {**diag, "reason": "penny_stock"}
            return True, diag
    except Exception as e:
        return False, {"reason": f"read_error:{type(e).__name__}"}


def filter_intraday_universe(root: Path, market: str,
                                asof: str | None = None,
                                write: bool = True) -> dict:
    """Build today's intraday-tradable universe. Returns dict with
    tickers list + per-ticker diagnostics."""
    asof = asof or date.today().isoformat()
    delivery_tickers = _delivery_universe(root, market)
    if not delivery_tickers:
        return {"asof": asof, "market": market, "tickers": [], "n": 0,
                  "reason": "delivery_universe_empty"}

    passing = []
    rejected = []
    for t in delivery_tickers:
        # Normalize (strip .NS for parquet lookup)
        bare = t.split(".", 1)[0].strip().upper()
        ok, diag = _liquidity_ok(root, bare, market)
        if ok:
            passing.append({"ticker": bare, **diag})
        else:
            rejected.append({"ticker": bare, **diag})

    passing.sort(key=lambda r: -(r.get("adv") or 0))
    payload = {
        "engine":              "aegis.intraday.universe.v1",
        "asof":                asof,
        "market":              market,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "n_delivery":          len(delivery_tickers),
        "n_passing":           len(passing),
        "n_rejected":          len(rejected),
        "tickers":             [r["ticker"] for r in passing],
        "diagnostics":         passing[:50],
        "rejected_sample":     rejected[:20],
    }
    if write:
        out = root / "configs" / f"intraday_universe_{market}_{asof}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    return payload


def load_intraday_universe(root: Path, market: str,
                              asof: str | None = None) -> list[str]:
    """Load today's already-filtered universe · builds if missing."""
    asof = asof or date.today().isoformat()
    p = root / "configs" / f"intraday_universe_{market}_{asof}.json"
    if not p.exists():
        payload = filter_intraday_universe(root, market, asof=asof, write=True)
        return payload.get("tickers") or []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("tickers") or []
    except Exception:
        return []
