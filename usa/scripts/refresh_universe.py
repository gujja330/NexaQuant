"""Refresh USA universe · fetches S&P 500 + S&P MidCap 400 constituents.

Writes to `usa/configs/universes/sp500.json` and `sp500_midcap400.json`.
Universe.yaml references those files via `tickers_from_json:` — so
switching between Dow 30 / S&P 500 / MidCap 400 / combined-large-mid is
a pure CONFIG change.

Sources:
  S&P 500  — Wikipedia canonical list (public, weekly-updated)
  MidCap 400 — Wikipedia canonical list

Run:
  python usa/scripts/refresh_universe.py
    (fetches both · writes JSON files · quiet on success)

Article 3 of AEGIS v3.0 Constitutional Directive:
  "no hardcoded ticker universes remain · future universe changes should
   require only updating configuration, not code."
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
_USA = _ROOT / "usa"
OUT_DIR = _USA / "configs" / "universes"
OUT_DIR.mkdir(parents=True, exist_ok=True)


UA = "Mozilla/5.0 (compatible; AEGIS-universe-fetcher/1.0)"

INDEX_SOURCES = {
    "sp500": {
        "url":       "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "expected":  500,
        "min":       450,   # tolerate index membership drift
        "description": "S&P 500 · US large-cap · Wikipedia canonical",
    },
    "sp400_midcap": {
        "url":       "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "expected":  400,
        "min":       350,
        "description": "S&P MidCap 400 · US mid-cap · Wikipedia canonical",
    },
}


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_tickers(html: str) -> list[str]:
    """Wikipedia S&P constituent tables have ticker as first-column <a>Ticker</a>.
    Regex is intentionally loose to survive minor markup changes."""
    hits = re.findall(r'<td[^>]*><a[^>]*>([A-Z][A-Z0-9\.\-]{0,5})</a>', html)
    # Filter obvious noise (page section anchors etc.)
    tickers = []
    seen = set()
    for t in hits:
        if len(t) > 6 or "." in t and len(t) > 5:
            continue
        if t in seen:
            continue
        seen.add(t)
        tickers.append(t)
    return tickers


def fetch_index(key: str, spec: dict) -> dict:
    print(f"[{key}] fetching {spec['url']}")
    html = _fetch_html(spec["url"])
    tickers = _extract_tickers(html)
    n = len(tickers)
    status = "ok" if n >= spec["min"] else "insufficient"
    print(f"[{key}] extracted {n} tickers · expected ~{spec['expected']} · status={status}")
    return {
        "engine":       "aegis.usa.universe.fetcher.v1",
        "index_key":    key,
        "description":  spec["description"],
        "source_url":   spec["url"],
        "fetched_utc":  datetime.now(timezone.utc).isoformat(),
        "n_tickers":    n,
        "expected":     spec["expected"],
        "min_threshold": spec["min"],
        "status":       status,
        "tickers":      sorted(tickers),
    }


def main() -> int:
    all_ok = True
    for key, spec in INDEX_SOURCES.items():
        try:
            data = fetch_index(key, spec)
            out = OUT_DIR / f"{key}.json"
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[{key}] wrote {out.relative_to(_ROOT)}  ({data['n_tickers']} tickers)")
            if data["status"] != "ok":
                all_ok = False
        except Exception as e:
            print(f"[{key}] FAILED: {type(e).__name__}: {e}")
            all_ok = False

    # Also emit a combined universe file (union of both, deduplicated)
    try:
        sp500 = json.loads((OUT_DIR / "sp500.json").read_text(encoding="utf-8")).get("tickers", [])
        sp400 = json.loads((OUT_DIR / "sp400_midcap.json").read_text(encoding="utf-8")).get("tickers", [])
        combined = sorted(set(sp500) | set(sp400))
        combined_data = {
            "engine":       "aegis.usa.universe.fetcher.v1",
            "index_key":    "sp500_plus_midcap400",
            "description":  "S&P 500 + S&P MidCap 400 combined · US large + mid cap",
            "fetched_utc":  datetime.now(timezone.utc).isoformat(),
            "n_tickers":    len(combined),
            "component_indices": {"sp500": len(sp500), "sp400_midcap": len(sp400)},
            "status":       "ok" if len(combined) >= 800 else "insufficient",
            "tickers":      combined,
        }
        (OUT_DIR / "sp500_plus_midcap400.json").write_text(
            json.dumps(combined_data, indent=2), encoding="utf-8")
        print(f"[combined] {len(combined)} unique tickers (union) · wrote "
              f"{(OUT_DIR / 'sp500_plus_midcap400.json').relative_to(_ROOT)}")
    except Exception as e:
        print(f"[combined] FAILED: {type(e).__name__}: {e}")
        all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
