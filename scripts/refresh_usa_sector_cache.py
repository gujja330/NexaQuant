"""One-shot USA sector cache refresh · fetches GICS sectors from yfinance
for every ticker in usa/reports/universe.json and writes them into
reports/sector_cache.json[usa].

Idempotent · resumable · fail-open per-ticker. Skips tickers already cached.

Run:  python scripts/refresh_usa_sector_cache.py
      python scripts/refresh_usa_sector_cache.py --force   # re-fetch even cached

Rationale (2026-08-11 CEO P0 pipeline hygiene): portfolio engine reported
n_sectors=0 because usa/configs/universe.yaml stamped `default_sector:
"Large-Cap"` (a cap-size, not a sector) on all 507 tickers. Real GICS
sectors need to come from a data source. markets/usa/sectors.csv only
covered 227 of the 516-ticker active universe. This script closes that
gap by walking the ACTUAL usa/reports/universe.json and fetching missing
sectors from yfinance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Yahoo GICS labels → canonical names used throughout AEGIS (matches
# what India's sector_cache uses: "Technology", "Financial Services", ...)
_CANONICAL = {
    "Technology":              "Technology",
    "Financial Services":      "Financial Services",
    "Healthcare":              "Healthcare",
    "Consumer Cyclical":       "Consumer Cyclical",
    "Consumer Defensive":      "Consumer Defensive",
    "Communication Services":  "Communication Services",
    "Industrials":             "Industrials",
    "Energy":                  "Energy",
    "Utilities":               "Utilities",
    "Real Estate":             "Real Estate",
    "Basic Materials":         "Basic Materials",
}


def _load_cache(p: Path) -> dict:
    if not p.exists():
        return {"india": {}, "usa": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {"india": {}, "usa": {}}
    except Exception:
        return {"india": {}, "usa": {}}


def _load_universe(p: Path) -> list[str]:
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    tickers = d.get("tickers") or []
    out = []
    for t in tickers:
        sym = t.get("symbol") if isinstance(t, dict) else str(t)
        if sym: out.append(str(sym).upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                       help="re-fetch even tickers already in cache")
    ap.add_argument("--limit", type=int, default=0,
                       help="stop after N new fetches (0 = no limit) · useful for smoke")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("FATAL: yfinance not installed · pip install yfinance")
        return 1

    cache_path = _ROOT / "reports" / "sector_cache.json"
    universe_path = _ROOT / "usa" / "reports" / "universe.json"

    cache = _load_cache(cache_path)
    if not isinstance(cache.get("usa"), dict):
        cache["usa"] = {}
    tickers = _load_universe(universe_path)
    if not tickers:
        print(f"FATAL: no tickers in {universe_path}")
        return 1

    print(f"[refresh_usa_sector_cache] universe={len(tickers)} · "
              f"already cached={len(cache['usa'])}")

    fetched = skipped = failed = 0
    t0 = time.time()
    for i, sym in enumerate(tickers, 1):
        if not args.force and sym in cache["usa"]:
            skipped += 1
            continue
        if args.limit and fetched >= args.limit:
            break
        try:
            info = yf.Ticker(sym).get_info()
            raw = info.get("sector") if isinstance(info, dict) else None
            if raw:
                cache["usa"][sym] = _CANONICAL.get(raw, raw)
                fetched += 1
                print(f"  [{i:>3}/{len(tickers)}] {sym:6}  {cache['usa'][sym]}")
            else:
                failed += 1
                print(f"  [{i:>3}/{len(tickers)}] {sym:6}  no sector · skipping")
        except Exception as e:
            failed += 1
            print(f"  [{i:>3}/{len(tickers)}] {sym:6}  ERROR · {type(e).__name__}")
        # Persist every 20 fetches so a mid-run interrupt doesn't lose work
        if fetched and fetched % 20 == 0:
            cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                                       encoding="utf-8")

    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    elapsed = time.time() - t0
    print(f"\n[refresh_usa_sector_cache] done · fetched={fetched} skipped={skipped} "
              f"failed={failed} · usa coverage now {len(cache['usa'])}/{len(tickers)} "
              f"({100*len(cache['usa'])/len(tickers):.1f}%) · elapsed {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
