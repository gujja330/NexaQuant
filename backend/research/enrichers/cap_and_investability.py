"""B3 · Cap bucket + Investability enricher · Sprint A · Batch B
CEO 2026-09-03 · unblocks P4 Cap × Sector × Investability LR test.

Populates:
  cap_bucket · one of {micro, small, mid, large, mega}
  investability · one of {liquid, less_liquid, illiquid}

Uses market_cap from yfinance provider (PIT via entry_date · falls back
to today's value if PIT unavailable · logged as "current_fallback"
provenance).

## Cap bucket thresholds (documented · additive-only)

USD-denominated boundaries (USA · direct); India converted at
approximately 1 USD ≈ 83 INR for the threshold set. Any change to these
boundaries is an amendment with a new fingerprint.

    micro:   [0,          300_000_000)      // < $300M
    small:   [300M,       2_000_000_000)    // $300M-$2B
    mid:     [2B,         10_000_000_000)   // $2B-$10B
    large:   [10B,        200_000_000_000)  // $10B-$200B
    mega:    [200B,       inf)              // > $200B

## Investability

Derived from average daily dollar volume over trailing 20 days:
    liquid       · ADV >= $10M
    less_liquid  · ADV between $1M-$10M
    illiquid     · ADV < $1M

## No fabrication

Missing market_cap → cap_bucket = None + `cap_source = "missing"`.
Missing prices/volume → investability = None + `investability_source = "missing"`.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

CAP_THRESHOLDS_USD = [
    ("micro", 0,             300_000_000),
    ("small", 300_000_000,   2_000_000_000),
    ("mid",   2_000_000_000, 10_000_000_000),
    ("large", 10_000_000_000, 200_000_000_000),
    ("mega",  200_000_000_000, float("inf")),
]

INR_PER_USD = 83.0

INVESTABILITY_THRESHOLDS_USD = {
    "liquid":      10_000_000,
    "less_liquid": 1_000_000,
}


def _cap_bucket(market_cap_native: float, market: str) -> str | None:
    if market_cap_native is None:
        return None
    mc_usd = float(market_cap_native)
    if market == "india":
        mc_usd = mc_usd / INR_PER_USD
    for label, lo, hi in CAP_THRESHOLDS_USD:
        if lo <= mc_usd < hi:
            return label
    return None


def _investability(adv_native: float, market: str) -> str | None:
    if adv_native is None or adv_native <= 0:
        return None
    adv_usd = float(adv_native)
    if market == "india":
        adv_usd = adv_usd / INR_PER_USD
    if adv_usd >= INVESTABILITY_THRESHOLDS_USD["liquid"]: return "liquid"
    if adv_usd >= INVESTABILITY_THRESHOLDS_USD["less_liquid"]: return "less_liquid"
    return "illiquid"


def _adv_from_parquet(root: Path, market: str, ticker: str, asof: str) -> float | None:
    """Average daily $ volume over trailing 20 trading days from asof.
    PIT · never uses bars after asof."""
    from backend.research._paths import price_parquet_path
    import pandas as pd
    p = price_parquet_path(root, market, ticker)
    if not p or not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        asof_dt = pd.to_datetime(asof).normalize()
        window = df[df.index <= asof_dt].tail(20)
        if len(window) < 5: return None
        close = window["close"].to_numpy()
        vol_col = "tick_volume" if "tick_volume" in window.columns else "volume"
        if vol_col not in window.columns: return None
        vol = window[vol_col].to_numpy()
        dollar_vol = (close * vol).mean()
        return float(dollar_vol) if dollar_vol > 0 else None
    except Exception:
        return None


def _market_cap_from_yfinance(ticker: str, market: str) -> tuple[float | None, str]:
    """Return (market_cap_native, provenance_tag). Uses today's value ·
    tagged as 'current_fallback' since yfinance doesn't give PIT easily."""
    try:
        import yfinance as yf
        symbol = ticker if "." in ticker else (f"{ticker}.NS" if market == "india" else ticker)
        y = yf.Ticker(symbol)
        info = y.info or {}
        mc = info.get("marketCap")
        if mc is not None and mc > 0:
            return float(mc), "yfinance:current_fallback"
    except Exception:
        pass
    return None, "missing"


def enrich_cap_investability(root: Path, market: str,
                             use_yfinance: bool = True) -> dict:
    """In-place merge cap_bucket + investability onto Outcome Dataset.

    use_yfinance=False skips the network call (test/CI mode) · leaves
    cap_bucket None with provenance "yfinance_skipped".
    """
    import pandas as pd
    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return {"market": market, "status": "OUTCOME_DATASET_MISSING"}
    df = pd.read_parquet(od_path)
    if df.empty:
        return {"market": market, "status": "OUTCOME_DATASET_EMPTY"}

    for c in ("cap_bucket", "investability",
              "cap_source", "investability_source",
              "market_cap_at_entry_native", "adv_20d_native"):
        if c not in df.columns:
            df[c] = None

    # Ticker-level cap cache (one yfinance call per unique ticker)
    unique_tickers = df["ticker"].dropna().unique().tolist()
    cap_cache: dict[str, tuple[float | None, str]] = {}
    if use_yfinance:
        for t in unique_tickers:
            cap_cache[t] = _market_cap_from_yfinance(t, market)
    else:
        for t in unique_tickers:
            cap_cache[t] = (None, "yfinance_skipped")

    from collections import Counter
    cap_dist: Counter = Counter()
    inv_dist: Counter = Counter()

    for i in df.index:
        ticker = str(df.at[i, "ticker"]) if pd.notna(df.at[i, "ticker"]) else ""
        entry_date = str(df.at[i, "entry_date"]) if pd.notna(df.at[i, "entry_date"]) else ""
        # Cap bucket
        mc, cap_src = cap_cache.get(ticker, (None, "missing"))
        df.at[i, "market_cap_at_entry_native"] = mc
        df.at[i, "cap_bucket"] = _cap_bucket(mc, market) if mc else None
        df.at[i, "cap_source"] = cap_src
        cap_dist[str(df.at[i, "cap_bucket"] or "null")] += 1
        # Investability from PIT ADV
        adv = _adv_from_parquet(root, market, ticker, entry_date) if entry_date else None
        df.at[i, "adv_20d_native"] = adv
        inv = _investability(adv, market) if adv else None
        df.at[i, "investability"] = inv
        df.at[i, "investability_source"] = "parquet_pit_adv" if adv else "missing"
        inv_dist[str(inv or "null")] += 1

    df.to_parquet(od_path, index=False)

    summary = {
        "market": market,
        "status": "ENRICHED",
        "n_rows": int(len(df)),
        "n_unique_tickers": len(unique_tickers),
        "cap_distribution": dict(cap_dist),
        "investability_distribution": dict(inv_dist),
        "cap_thresholds_usd": {label: (lo, hi if hi != float("inf") else "inf")
                                for label, lo, hi in CAP_THRESHOLDS_USD},
        "investability_thresholds_usd": INVESTABILITY_THRESHOLDS_USD,
        "inr_per_usd_used": INR_PER_USD,
        "cap_provenance_note": (
            "yfinance marketCap is current-value; PIT market_cap requires "
            "shares_out(entry_date) × close(entry_date). This enricher tags "
            "cap_source='yfinance:current_fallback' so downstream analysis "
            "knows to treat cap_bucket as approximate for pre-today entries."
        ),
        "investability_provenance_note": (
            "Investability derived from PIT parquet ADV(20d) at entry_date. "
            "Fully PIT-safe."
        ),
        "no_fabrication_note": "Missing → None with source tag.",
        "enriched_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out_dir = root / "reports" / "research" / "enrichers"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"cap_investability_{market}.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), default="both")
    ap.add_argument("--no-yfinance", action="store_true",
                    help="skip network calls · fills cap_bucket=None")
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = enrich_cap_investability(root, m, use_yfinance=not args.no_yfinance)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
