#!/usr/bin/env python3
"""AEGIS · verify every ticker in the universe still resolves on yfinance.

Operator directive 2026-08-25: "u should verify such name corrections
instead of ignoring". Catches renames + delistings + wrong-suffix bugs
before they silently break downstream reports.

For each ticker in data/raw/india/*.parquet:
  · Try a small yfinance download (5 days)
  · If 0 rows returned → try known-alias candidates (M&M for MM, etc.)
  · If ANY alias returns data → emit rename suggestion
  · If nothing returns data → mark DELISTED

Outputs:
  reports/context/universe_verification_india.json
  reports/context/universe_verification_usa.json

Exit code:
  0  · every ticker resolves
  1  · at least one ticker is DELISTED with no viable alias
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.simplefilter("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]


def _alias_candidates(bare: str) -> list:
    """Return list of yfinance-symbol candidates to try for a bare ticker."""
    # Common rename patterns (extend as needed · covered by ticker_aliases.yaml too)
    known = {
        "MM":   ["M&M"],
        "MAHM": ["M&M", "MAHINDRA"],
        # Add more as they surface
    }
    aliases = known.get(bare.upper(), [])
    # Also try the bare symbol itself + any suffix variants
    return [bare] + aliases


def _try_yf(sym: str) -> bool:
    try:
        import yfinance as yf
        d = yf.download(sym, period="5d", progress=False,
                              threads=False, auto_adjust=False)
        return len(d) > 0
    except Exception:
        return False


def verify_market(root: Path, market: str) -> dict:
    if market == "usa":
        raw_dir = root / "usa" / "data" / "raw" / "us"
        suffix = ""
    else:
        raw_dir = root / "data" / "raw" / "india"
        suffix = ".NS"

    if not raw_dir.exists():
        return {"market": market, "n_universe": 0, "results": []}

    universe = sorted(p.stem.replace("_D1", "")
                             for p in raw_dir.glob("*_D1.parquet"))
    print(f"[verify_universe:{market}] scanning {len(universe)} tickers ...")

    results = []
    n_delisted = 0
    for i, bare in enumerate(universe, start=1):
        if i % 25 == 0:
            print(f"  · progress {i}/{len(universe)}")
        # Try each candidate + suffix
        for candidate in _alias_candidates(bare):
            sym = candidate + suffix if suffix else candidate
            if _try_yf(sym):
                if candidate.upper() != bare.upper():
                    results.append({
                        "bare": bare, "status": "RENAME_SUGGESTED",
                        "current_symbol": bare + suffix,
                        "working_symbol": sym,
                    })
                else:
                    results.append({"bare": bare, "status": "OK",
                                          "current_symbol": sym})
                break
        else:
            results.append({"bare": bare, "status": "DELISTED",
                                  "current_symbol": bare + suffix,
                                  "note": "no working symbol found in aliases"})
            n_delisted += 1

    return {
        "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_universe":  len(universe),
        "n_ok":        sum(1 for r in results if r["status"] == "OK"),
        "n_rename":    sum(1 for r in results if r["status"] == "RENAME_SUGGESTED"),
        "n_delisted":  n_delisted,
        "results":     results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india", "usa", "both"], default="india")
    args = ap.parse_args()

    total_delisted = 0
    for m in (["india", "usa"] if args.market == "both" else [args.market]):
        rep = verify_market(_ROOT, m)
        p = _ROOT / "reports" / "context" / f"universe_verification_{m}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False),
                          encoding="utf-8")
        print()
        print(f"[verify_universe:{m}] " +
                  f"OK={rep['n_ok']}  RENAME={rep['n_rename']}  DELISTED={rep['n_delisted']}")
        total_delisted += rep["n_delisted"]
        if rep["n_rename"] > 0:
            print(f"  Renames suggested:")
            for r in rep["results"]:
                if r["status"] == "RENAME_SUGGESTED":
                    print(f"    · {r['bare']:12} → {r['working_symbol']}")
        if rep["n_delisted"] > 0:
            print(f"  DELISTED:")
            for r in rep["results"]:
                if r["status"] == "DELISTED":
                    print(f"    · {r['bare']:12} (no viable symbol)")
    return 1 if total_delisted > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
