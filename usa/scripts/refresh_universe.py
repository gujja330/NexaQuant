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

import hashlib
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
_USA = _ROOT / "usa"
OUT_DIR = _USA / "configs" / "universes"
sys.path.insert(0, str(_ROOT))

from backend.ingest.security_master import normalize, update
from backend.shared.atomic_io import write_text_atomic


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


class _ConstituentTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and (self.depth or dict(attrs).get("id") == "constituents"):
            self.depth += 1
        if self.depth != 1:
            return
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.depth == 1 and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.depth == 1 and tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1


def _extract_tickers(html: str) -> list[str]:
    parser = _ConstituentTable()
    parser.feed(html)
    if not parser.rows or parser.rows[0][0].lower() not in {"symbol", "ticker", "ticker symbol"}:
        raise ValueError("constituents table has no recognizable ticker column")
    return [row[0] for row in parser.rows[1:]]


def refresh_reference(root, key, seed):
    spec = INDEX_SOURCES[key]

    def fetch():
        members = _extract_tickers(_fetch_html(spec["url"]))
        return {"market": "usa", "index": key, "members": members,
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "source": spec["url"], "source_type": "PUBLIC_SECONDARY",
                "source_revision": hashlib.sha256("\n".join(members).encode()).hexdigest()}

    return update(root / "usa/reports/security_master", "usa", key, seed, fetch,
                  bounds=(spec["min"], spec["expected"] + 50))


def fetch_index(key: str, spec: dict) -> dict:
    print(f"[{key}] fetching {spec['url']}")
    html = _fetch_html(spec["url"])
    tickers = normalize(_extract_tickers(html))
    n = len(tickers)
    status = "ok" if spec["min"] <= n <= spec["expected"] + 50 else "insufficient"
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
            if data["status"] != "ok":
                all_ok = False
                continue
            old = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            before, after = set(old.get("tickers") or ()), set(data["tickers"])
            if before and len(before ^ after) > 0.12 * len(before):
                print(f"[{key}] change exceeds review threshold; retained previous file")
                all_ok = False
                continue
            write_text_atomic(out, json.dumps(data, indent=2))
            print(f"[{key}] wrote {out.relative_to(_ROOT)}  ({data['n_tickers']} tickers)")
        except Exception as e:
            print(f"[{key}] FAILED: {type(e).__name__}: {e}")
            all_ok = False

    # Also emit a combined universe file (union of both, deduplicated)
    if not all_ok:
        return 1
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
        if combined_data["status"] != "ok":
            return 1
        write_text_atomic(OUT_DIR / "sp500_plus_midcap400.json", json.dumps(combined_data, indent=2))
        print(f"[combined] {len(combined)} unique tickers (union) · wrote "
              f"{(OUT_DIR / 'sp500_plus_midcap400.json').relative_to(_ROOT)}")
    except Exception as e:
        print(f"[combined] FAILED: {type(e).__name__}: {e}")
        all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
