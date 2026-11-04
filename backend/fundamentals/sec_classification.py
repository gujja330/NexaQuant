"""SEC SIC classification ingest · the source side of the USA sector resolver.

CEO 2026-11-04 · Phase 1B.

WHY A SEPARATE MODULE
---------------------
`backend/fundamentals/sec_adapter.py` ingests XBRL *facts* - financial
line items from companyfacts. SIC lives somewhere else entirely, in the
`submissions` endpoint, alongside the company's name, exchanges and
former names. Different endpoint, different cadence (a classification
changes rarely; facts change quarterly), different cache. So this is a
sibling of the facts adapter, sharing its politeness policy and its
cache conventions, not an extension of it.

WHAT SEC GIVES, AND THE ONE THING IT DOES NOT
---------------------------------------------
Measured on AAPL, JPM, XOM, SPG and NEE before this module was written:

    sic             4-digit code, present on all five
    sicDescription  the regulatory description
    name            current registrant name
    tickers         ALL listed securities, preferred shares included -
                    JPM returns 9, of which only "JPM" is the common
    exchanges       parallel array to `tickers`
    formerNames     name changes with from/to dates

There is NO `sicHistory` field. SEC publishes only the CURRENT
classification, and `formerNames` dates name changes, not SIC changes -
a company can be reclassified without renaming.

So this module can honestly record WHEN AEGIS FIRST SAW a
classification, and nothing about what it was before that. The resolver
exposes that as `first_observed_date`, deliberately distinct from a true
`effective_from`, and historical queries before it return UNAVAILABLE
rather than today's answer backdated. Filling that gap needs a licensed
point-in-time provider; the interface is shaped to accept one.

SCOPE
-----
Read-only against SEC. Writes only under data/classification/. No
production caller. Rate-limited well under SEC's published 10 req/sec,
with the descriptive User-Agent their policy requires.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

#: SEC requires a descriptive User-Agent identifying the requester.
UA_HEADER = {"User-Agent": "AEGIS Research aegis@example.com",
             "Accept": "application/json"}

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK%010d.json"

#: SEC permits 10 req/sec. One is ample and courteous for a daily job.
REQUEST_INTERVAL_S = 1.0

DATA_DIR = ("data", "classification")
SOURCE_ID = "SEC:submissions"


@dataclass(frozen=True)
class SecClassification:
    """One company's current SEC classification, as observed."""
    ticker: str
    cik: int
    source: str
    sic_code: Optional[str]
    sic_description: Optional[str]
    registrant_name: str
    exchanges: tuple
    all_tickers: tuple
    retrieved_at_utc: str
    #: The first date AEGIS observed this classification. NOT the date
    #: the classification became true - SEC does not publish that.
    first_observed_date: str

    def as_dict(self) -> dict:
        return asdict(self)


def classification_dir(repo_root: Path) -> Path:
    return Path(repo_root).joinpath(*DATA_DIR)


def store_path(repo_root: Path) -> Path:
    return classification_dir(repo_root) / "sec_sic.json"


def _get_json(url: str, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers=UA_HEADER)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def fetch_ticker_map(cache: Optional[Path] = None) -> dict:
    """ticker (upper) -> (cik, title) for every SEC registrant."""
    if cache is not None and cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
    else:
        raw = _get_json(TICKER_MAP_URL, timeout=90)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw), encoding="utf-8")
    rows = list(raw.values()) if isinstance(raw, dict) else raw
    out = {}
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if t:
            out[t] = (int(r["cik_str"]), str(r.get("title") or ""))
    return out


def symbol_variants(symbol: str) -> list:
    """`BRK.B` also appears as `BRK-B` and `BRKB` across sources."""
    s = str(symbol or "").upper().strip()
    out = [s]
    if "." in s:
        out += [s.replace(".", "-"), s.replace(".", "")]
    if "-" in s:
        out += [s.replace("-", "."), s.replace("-", "")]
    seen, uniq = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def resolve_ciks(symbols: Iterable[str], ticker_map: dict) -> tuple:
    """(resolved {symbol: cik}, unresolved [symbol])."""
    resolved, unresolved = {}, []
    for s in symbols:
        for v in symbol_variants(s):
            if v in ticker_map:
                resolved[s] = ticker_map[v][0]
                break
        else:
            unresolved.append(s)
    return resolved, sorted(unresolved)


def fetch_classification(ticker: str, cik: int, cache_dir: Optional[Path] = None,
                         first_observed: Optional[str] = None
                         ) -> Optional[SecClassification]:
    """One company's submissions record · cached by CIK."""
    raw = None
    p = (cache_dir / ("CIK%010d.json" % cik)) if cache_dir else None
    if p is not None and p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raw = None
    if raw is None:
        try:
            raw = _get_json(SUBMISSIONS_URL % cik)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return None
        if p is not None:
            p.parent.mkdir(parents=True, exist_ok=True)
            # keep only the fields we use · the full record is ~MBs of filings
            slim = {k: raw.get(k) for k in
                    ("cik", "name", "sic", "sicDescription", "tickers",
                     "exchanges", "formerNames")}
            p.write_text(json.dumps(slim), encoding="utf-8")
    now = datetime.now(timezone.utc)
    return SecClassification(
        ticker=str(ticker).upper(),
        cik=int(cik),
        source=SOURCE_ID,
        sic_code=(str(raw.get("sic")).strip() or None) if raw.get("sic") else None,
        sic_description=(str(raw.get("sicDescription")).strip() or None
                         if raw.get("sicDescription") else None),
        registrant_name=str(raw.get("name") or ""),
        exchanges=tuple(raw.get("exchanges") or ()),
        all_tickers=tuple(raw.get("tickers") or ()),
        retrieved_at_utc=now.isoformat(timespec="seconds"),
        first_observed_date=first_observed or now.date().isoformat(),
    )


def load_store(repo_root: Path) -> dict:
    """{ticker: record}. Preserves the EARLIEST first_observed_date."""
    p = store_path(repo_root)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("companies") or {}
    except Exception:
        return {}


def save_store(repo_root: Path, companies: dict, unresolved: list) -> Path:
    p = store_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "aegis.classification.sec_sic.v1",
        "source": SOURCE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("SEC publishes only the CURRENT classification. "
                 "first_observed_date is when AEGIS first saw it, NOT when "
                 "it became true · there is no sicHistory field."),
        "n_companies": len(companies),
        "n_unresolved": len(unresolved),
        "unresolved": unresolved,
        "companies": companies,
    }, indent=1, default=str), encoding="utf-8")
    return p


def ingest(repo_root: Path, symbols: Iterable[str],
           limit: Optional[int] = None, verbose: bool = True) -> dict:
    """Fetch SIC for each symbol, preserving earlier first-observations."""
    root = Path(repo_root)
    cache_dir = classification_dir(root) / "raw" / "sec"
    prior = load_store(root)
    tmap = fetch_ticker_map(classification_dir(root) / "company_tickers.json")
    syms = sorted({str(s).upper() for s in symbols})
    resolved, unresolved = resolve_ciks(syms, tmap)

    todo = [s for s in syms if s in resolved]
    if limit:
        todo = todo[:limit]

    out = dict(prior)
    n_new, n_fail = 0, []
    for i, s in enumerate(todo):
        was = prior.get(s) or {}
        # Decide BEFORE the call whether this will hit the network, so
        # the rate limit applies to requests and a warm cache runs at
        # full speed.
        cached = (cache_dir / ("CIK%010d.json" % resolved[s])).exists()
        rec = fetch_classification(
            s, resolved[s], cache_dir,
            first_observed=was.get("first_observed_date"))
        if rec is None:
            n_fail.append(s)
        else:
            out[s] = rec.as_dict()
            n_new += 1
        if verbose and (i + 1) % 50 == 0:
            print("    ... %d/%d" % (i + 1, len(todo)), flush=True)
        if not cached:
            time.sleep(REQUEST_INTERVAL_S)

    save_store(root, out, unresolved)
    n_sic = sum(1 for r in out.values() if r.get("sic_code"))
    return {
        "n_symbols": len(syms),
        "n_cik_resolved": len(resolved),
        "n_unresolved": len(unresolved),
        "unresolved": unresolved,
        "n_fetched": n_new,
        "n_failed": len(n_fail),
        "failed": n_fail,
        "n_with_sic": n_sic,
        "store": str(store_path(root)),
    }
