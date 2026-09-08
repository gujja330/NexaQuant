"""AEGIS · SECTOR SUBSTRATE · CEO 2026-09-08.

> "USA: identify why `sector` contains 'Large-Cap' · separate cap_bucket
>  from sector · locate authoritative historical sector source ·
>  reconstruct PIT sector by prediction date · never reinterpret
>  'Large-Cap' as a real sector."

DIAGNOSIS THAT LED HERE
-----------------------
The corruption is not in the delivery layer. Traced to source:

  usa/reports/universe.json   sector == "Unknown" for ALL 516 tickers
  usa/research/recommendations/run.py:88   sector = spec.get("sector") or "?"

so every USA recommendation inherits "Unknown"/"?" and the workbook's
Sector column has never held a sector. The historical "Large-Cap" values
(995 rows) came from an older universe build that wrote a CAP label into
the sector field - which is why `cap_bucket` and `sector` were reporting
the same thing and any "cap effect" was uncontrolled for sector.

India is different: its sectors are real (FMCG, Pharma, Power, Financials,
Metal) but present on only ~34.5% of rows.

WHAT THIS PRODUCES · AND WHAT IT DELIBERATELY DOES NOT CLAIM
------------------------------------------------------------
A sector cache keyed by ticker, stamped with the date it was ACQUIRED.

It does NOT reconstruct point-in-time sector, and it does not pretend to.
The directive is explicit - "do not backfill today's sector into
historical rows · preserve PIT correctness" - and no historical sector
snapshot exists anywhere in this repository to reconstruct from. Inventing
one would be fabrication.

So this follows the precedent the feature enricher already set for
fundamentals: acquire the current value, stamp it `sector_asof`, and label
it as a CURRENT-TIME attribute so every downstream consumer can see that
it is not PIT. A cap-versus-sector control built on it is valid only to
the extent that GICS sector assignment is stable over the cohort window -
a limitation that must be stated in any study that uses it, not buried.

Nothing here touches an engine, a threshold, or a universe definition.
It writes one cache file.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.sector_substrate.v1"

# A cap label is NOT a sector. These must never be accepted as one.
CAP_LABELS = {"LARGE-CAP", "LARGECAP", "LARGE CAP", "MID-CAP", "MIDCAP",
              "MID CAP", "SMALL-CAP", "SMALLCAP", "SMALL CAP", "LARGE",
              "MID", "SMALL"}
NULL_LABELS = {"", "?", "NONE", "UNKNOWN", "N/A", "NAN"}


def is_valid_sector(v) -> bool:
    """Reject cap labels and null-ish placeholders."""
    s = str(v or "").strip().upper()
    return bool(s) and s not in NULL_LABELS and s not in CAP_LABELS


def cache_path(root: Path) -> Path:
    return root / "reports" / "context" / "sector_substrate.json"


def load(root: Path) -> dict:
    p = cache_path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sector_for(root: Path, ticker: str, cache: dict | None = None) -> Optional[str]:
    c = cache if cache is not None else load(root)
    e = (c.get("sectors") or {}).get(str(ticker).upper().split(".", 1)[0])
    return (e or {}).get("sector")


def _universe(root: Path, market: str) -> list:
    if market == "usa":
        p = root / "usa" / "reports" / "universe.json"
    else:
        p = root / "reports" / "india_universe.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for t in (d.get("tickers") or []):
        sym = t.get("symbol") if isinstance(t, dict) else t
        if sym:
            out.append(str(sym).upper())
    return out


def _cohort_tickers(root: Path, market: str) -> list:
    """Tickers the prediction cohort actually contains · the study needs
    sector for THESE, not only for today's universe."""
    p = (root / "reports" / "research"
         / f"mr_prediction_autopsy_{market}_enriched.jsonl")
    if not p.exists():
        return []
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.add(str(json.loads(line).get("ticker") or "").upper()
                    .split(".", 1)[0])
        except Exception:
            continue
    return sorted(t for t in out if t)


def build(root: Path, markets=("india", "usa"),
          limit: int | None = None) -> dict:
    """Acquire sector/industry per ticker. Resumes from the existing cache."""
    import yfinance as yf

    cache = load(root)
    sectors = dict(cache.get("sectors") or {})
    today = date.today().isoformat()

    wanted = {}
    for m in markets:
        for t in set(_universe(root, m)) | set(_cohort_tickers(root, m)):
            wanted.setdefault(t, m)

    todo = [t for t in sorted(wanted) if t not in sectors]
    if limit:
        todo = todo[:limit]

    n_ok = n_fail = 0
    for i, t in enumerate(todo, 1):
        m = wanted[t]
        yq = f"{t}.NS" if m == "india" else t
        sec = ind = None
        try:
            info = yf.Ticker(yq).info or {}
            sec, ind = info.get("sector"), info.get("industry")
        except Exception:
            pass
        if is_valid_sector(sec):
            n_ok += 1
        else:
            sec, ind = None, None
            n_fail += 1
        sectors[t] = {"sector": sec, "industry": ind, "market": m,
                      "sector_asof": today, "query_symbol": yq}
        if i % 50 == 0:
            print(f"  [{i}/{len(todo)}] resolved={n_ok} unresolved={n_fail}")
            _write(root, sectors, today)      # checkpoint · resumable

    return _write(root, sectors, today, n_ok=n_ok, n_fail=n_fail,
                  n_attempted=len(todo))


def _write(root: Path, sectors: dict, today: str, **extra) -> dict:
    resolved = {k: v for k, v in sectors.items() if v.get("sector")}
    by_sec = {}
    for v in resolved.values():
        by_sec[v["sector"]] = by_sec.get(v["sector"], 0) + 1
    rep = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sector_asof": today,
        "pit_status": (
            "CURRENT-TIME ATTRIBUTE, NOT POINT-IN-TIME. No historical "
            "sector snapshot exists in this repository, so sector is "
            "acquired as of the stamp above and applied to the whole "
            "cohort. Valid only insofar as GICS sector assignment is "
            "stable across the cohort window · any study using it MUST "
            "state this limitation."),
        "n_tickers": len(sectors),
        "n_resolved": len(resolved),
        "coverage_pct": round(len(resolved) / max(1, len(sectors)) * 100, 1),
        "distinct_sectors": len(by_sec),
        "by_sector": dict(sorted(by_sec.items(), key=lambda kv: -kv[1])),
        "sectors": sectors,
        **extra,
    }
    p = cache_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return rep


def summary_line(rep: dict) -> str:
    return (f"sector_substrate · {rep['n_resolved']}/{rep['n_tickers']} "
            f"resolved ({rep['coverage_pct']}%) · {rep['distinct_sectors']} "
            f"distinct sectors · asof {rep['sector_asof']}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS sector substrate builder")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    mk = ("india", "usa") if a.market == "both" else (a.market,)
    rep = build(root, mk, a.limit)
    print(summary_line(rep))
    for k, v in list(rep["by_sector"].items())[:12]:
        print(f"    {k:<28} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
