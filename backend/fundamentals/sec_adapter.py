"""SEC XBRL adapter — PIT-verified historical fundamentals for the USA.

WHY THIS EXISTS
---------------
The existing fundamental substrate is 5-8 quarters deep with a 45-day ASSUMED
filing lag. That is why every long-horizon R3 hypothesis came back
BLOCKED - INSUFFICIENT HISTORY: a 1Y growth feature needs 4 prior quarters and a
forward outcome needs 126 sessions after, and on 8 quarters those two windows do
not overlap at all.

SEC XBRL carries a real `filed` date on every fact. Measured on AAPL before this
module was written: 74 quarterly periods spanning 2007-2026, first-filing lag
median 32 days. That converts PIT_ASSUMED_LAG into PIT_VERIFIED and multiplies
depth roughly ninefold.

THE TWO TRAPS, BOTH MEASURED NOT ASSUMED
----------------------------------------
1. TAXONOMY DRIFT. The same economic quantity changes concept name mid-history.
   AAPL revenue lives under `Revenues` for 2016-2018 and under
   `RevenueFromContractWithCustomerExcludingAssessedTax` for 2017-2026. An
   adapter that picks one concept silently produces a series with a hole in it.

2. RESTATEMENTS. 71 of 74 AAPL periods are filed more than once. Consuming rows
   as returned inflates the apparent filing lag to a median of 401 days, because
   later filings restate older comparatives. Taking MIN(filed) per period gives
   the true 32. Without that rule an adapter looks PIT-correct while leaking
   restated figures backward into earlier simulation dates - the exact failure
   this whole programme exists to prevent.

So every fact is resolved to a FIRST_KNOWN value, and later filings are kept
separately as revisions rather than discarded or merged.

SCOPE
-----
Read-only. Writes only under data/fundamentals/. No production caller.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = "aegis.fundamentals.sec.v1"
SEC_BASE = "https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"

# SEC asks for a descriptive UA with contact. Rate limit is 10 req/s; we stay
# far below that deliberately.
USER_AGENT = "AEGIS-research rajkiran.killamsetty@gmail.com"
REQUEST_SPACING_S = 0.34

PIT_VERIFIED = "PIT_VERIFIED"
PIT_UNVERIFIED = "PIT_UNVERIFIED"

# Only forms that constitute a public financial report.
ACCEPTED_FORMS = {"10-K", "10-Q", "20-F", "40-F", "10-K/A", "10-Q/A"}


# ── concept mapping · the answer to taxonomy drift ────────────────────
#
# Order matters: earlier entries are preferred when several concepts cover the
# same period. Never merge concepts that mean different things - `Revenues` and
# `RevenueFromContractWithCustomer...` are both top-line revenue; `GrossProfit`
# is NOT, and so lives under its own canonical metric.
CONCEPT_MAP: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "gross_profit": ["GrossProfit"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "interest_expense": ["InterestExpense", "InterestIncomeExpenseNet"],
    "shares_outstanding": ["CommonStockSharesOutstanding",
                           "WeightedAverageNumberOfDilutedSharesOutstanding"],
    "eps_diluted": ["EarningsPerShareDiluted"],
}


@dataclass
class Fact:
    """One normalized observation. Mirrors the PIT data model."""
    company_id: str
    ticker: Optional[str]
    cik: int
    market: str
    metric: str
    value: float
    unit: str
    period_start: Optional[str]
    period_end: str
    filed_date: str
    available_from: str
    form: str
    accession_number: Optional[str]
    fiscal_year: Optional[int]
    fiscal_period: Optional[str]
    source: str
    source_concept: str
    source_version: str
    is_first_filing: bool
    revision_sequence: int
    pit_status: str
    data_quality: str = "OK"


def _get(url: str, retries: int = 3) -> Optional[dict]:
    """Fetch with backoff. Returns None rather than raising: a missing company
    must not abort a whole run."""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            time.sleep(REQUEST_SPACING_S)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def fetch_companyfacts(cik: int, cache_dir: Path) -> Optional[dict]:
    """Raw companyfacts, cached. §18 forbids re-downloading every run."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / ("CIK%010d.json" % cik)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    d = _get(SEC_BASE % cik)
    if d is None:
        return None
    p.write_text(json.dumps(d), encoding="utf-8")
    return d


def _period_key(f: dict) -> Optional[tuple]:
    """Identity of the reported period. `start` distinguishes a quarter from a
    year-to-date figure ending on the same date - collapsing them would merge
    incompatible quantities."""
    end = f.get("end")
    if not end:
        return None
    return (f.get("start"), end)


def normalize(cik: int, facts: dict, market: str = "usa",
              ticker: Optional[str] = None) -> list[Fact]:
    """companyfacts -> Fact rows, with first-filing resolution per period.

    For each (metric, period) the FIRST filing becomes the PIT value and later
    filings are retained as revisions with increasing revision_sequence.
    """
    out: list[Fact] = []
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    company_id = "SEC:%010d" % cik
    for metric, concepts in CONCEPT_MAP.items():
        # period -> list of candidate rows across ALL mapped concepts
        buckets: dict[tuple, list[tuple]] = {}
        for concept in concepts:
            units = gaap.get(concept, {}).get("units", {})
            for unit, rows in units.items():
                for f in rows:
                    if f.get("form") not in ACCEPTED_FORMS:
                        continue
                    if f.get("val") is None or not f.get("filed"):
                        continue
                    k = _period_key(f)
                    if k is None:
                        continue
                    buckets.setdefault(k, []).append((concept, unit, f))
        for k, cands in buckets.items():
            # earliest filing first; ties broken by CONCEPT_MAP preference
            cands.sort(key=lambda c: (c[2]["filed"], concepts.index(c[0])))
            for seq, (concept, unit, f) in enumerate(cands):
                # CHRONOLOGY GUARD. A value for a period that had not finished
                # when the filing was made is not a historical observation.
                # Measured on the 12-company validation set: 1 row in 13,620
                # (a WMT cash fact with end 2012-12-31 filed 2012-03-27). Rare,
                # but it must never be labelled PIT_VERIFIED.
                try:
                    _lag = (date.fromisoformat(f["filed"])
                            - date.fromisoformat(f["end"])).days
                except Exception:
                    _lag = None
                _bad = (_lag is not None and _lag < 0)
                out.append(Fact(
                    company_id=company_id, ticker=ticker, cik=cik, market=market,
                    metric=metric, value=float(f["val"]), unit=unit,
                    period_start=f.get("start"), period_end=f["end"],
                    filed_date=f["filed"],
                    # A filing is knowable the day it is filed. No assumed lag
                    # is added on top of an observed date.
                    available_from=f["filed"],
                    form=f.get("form", ""), accession_number=f.get("accn"),
                    fiscal_year=f.get("fy"), fiscal_period=f.get("fp"),
                    source="SEC", source_concept=concept,
                    source_version=SCHEMA_VERSION,
                    is_first_filing=(seq == 0), revision_sequence=seq,
                    pit_status=(PIT_UNVERIFIED if _bad else PIT_VERIFIED),
                    data_quality=("IMPOSSIBLE_CHRONOLOGY" if _bad else "OK")))
    return out


def first_known(facts: Iterable[Fact]) -> list[Fact]:
    """FIRST_KNOWN_PIT_VALUE — what research must consume."""
    return [f for f in facts if f.is_first_filing]


def revisions(facts: Iterable[Fact]) -> list[Fact]:
    """LATEST_REPORTED_VALUE lineage — kept, never silently merged."""
    return [f for f in facts if not f.is_first_filing]


def visible_at(facts: Iterable[Fact], asof: date) -> list[Fact]:
    """THE PIT RULE. Nothing filed after `asof` may be visible.

    This is the function the leakage test targets.
    """
    a = asof.isoformat()
    return [f for f in facts if f.available_from <= a]


def to_frame(facts: Iterable[Fact]):
    import pandas as pd
    return pd.DataFrame([asdict(f) for f in facts])


def manifest(facts: list[Fact], run_id: str) -> dict:
    """§19 evidence ledger row."""
    firsts = [f for f in facts if f.is_first_filing]
    periods = {(f.metric, f.period_end) for f in facts}
    lags = []
    for f in firsts:
        try:
            lags.append((date.fromisoformat(f.filed_date)
                         - date.fromisoformat(f.period_end)).days)
        except Exception:
            pass
    lags.sort()
    body = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "SEC XBRL companyfacts",
        "companies": len({f.cik for f in facts}),
        "facts_total": len(facts),
        "facts_first_filing": len(firsts),
        "facts_revisions": len(facts) - len(firsts),
        "metrics": sorted({f.metric for f in facts}),
        "distinct_periods": len(periods),
        "pit_verified": sum(1 for f in facts if f.pit_status == PIT_VERIFIED),
        "pit_unverified": sum(1 for f in facts if f.pit_status != PIT_VERIFIED),
        "first_filing_lag_days": {
            "min": lags[0] if lags else None,
            "median": lags[len(lags) // 2] if lags else None,
            "max": lags[-1] if lags else None,
        },
        "concept_map_version": hashlib.sha256(
            json.dumps(CONCEPT_MAP, sort_keys=True).encode()).hexdigest()[:12],
    }
    body["manifest_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return body
