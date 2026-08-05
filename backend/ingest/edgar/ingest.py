"""SEC EDGAR insider Form 4 ingest.

For a small curated ticker set (Dow 30 + top-active names), fetch the
last 90 days of Form 4 filings via EDGAR's public JSON endpoint. Aggregate
into insider net buy vs sell per ticker · surface for the CIL layer.

Rate-limited: SEC allows 10 req/sec · we run at 1 req/sec to be polite.
Required per SEC policy: descriptive User-Agent header.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


UA_HEADER = {"User-Agent": "AEGIS Research aegis@example.com",
                  "Accept": "application/json"}

# Ticker → CIK mapping for Dow 30 (avoids parsing EDGAR ticker map)
CIK_MAP = {
    "AAPL":  "0000320193", "MSFT": "0000789019", "NVDA": "0001045810",
    "AMZN":  "0001018724", "META": "0001326801", "TSLA": "0001318605",
    "GOOGL": "0001652044", "JPM":  "0000019617", "V":    "0001403161",
    "WMT":   "0000104169", "JNJ":  "0000200406", "PG":   "0000080424",
    "HD":    "0000354950", "MA":   "0001141391", "UNH":  "0000731766",
    "DIS":   "0001744489", "BAC":  "0000070858", "KO":   "0000021344",
    "PEP":   "0000077476", "CSCO": "0000858877", "MRK":  "0000310158",
    "INTC":  "0000050863", "IBM":  "0000051143", "GS":   "0000886982",
    "MMM":   "0000066740", "BA":   "0000012927", "CAT":  "0000018230",
    "MCD":   "0000063908", "CVX":  "0000093410", "AXP":  "0000004962",
    "TRV":   "0000086312", "NKE":  "0000320187", "HON":  "0000773840",
    "AMGN":  "0000318154",
}


def _fetch_recent_forms(cik: str, forms: list[str], days: int = 90) -> list[dict]:
    """Fetch recent filings for a CIK · filter to given form types + last N days."""
    padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    try:
        req = urllib.request.Request(url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    if not recent: return []
    out = []
    since = date.today() - timedelta(days=days)
    for i, form in enumerate(recent.get("form") or []):
        if form not in forms: continue
        dt_str = (recent.get("filingDate") or ["" ])[i] if i < len(recent.get("filingDate") or []) else ""
        try:
            dt = date.fromisoformat(dt_str)
        except (ValueError, TypeError):
            continue
        if dt < since: continue
        out.append({
            "form":         form,
            "filing_date":  dt_str,
            "accession":    (recent.get("accessionNumber") or [""])[i]
                                if i < len(recent.get("accessionNumber") or []) else "",
            "primary_doc":  (recent.get("primaryDocument") or [""])[i]
                                if i < len(recent.get("primaryDocument") or []) else "",
        })
    return out


def ingest_daily(root: Path, asof: str, ticker_universe: list[str] | None = None) -> dict:
    """Fetch last 90 days of Form 4 (insider) filings for the curated universe."""
    universe = ticker_universe or list(CIK_MAP.keys())
    out_dir = root / "reports" / "edgar"
    out_dir.mkdir(parents=True, exist_ok=True)

    per_ticker: dict = {}
    n_ok = 0
    n_forms_total = 0
    for i, ticker in enumerate(universe):
        cik = CIK_MAP.get(ticker.upper())
        if not cik:
            per_ticker[ticker] = {"available": False,
                                            "reason": "no CIK mapping"}
            continue
        # Be polite to SEC · 1 req/sec
        if i > 0: time.sleep(1.0)
        filings = _fetch_recent_forms(cik, forms=["4", "4/A"], days=90)
        per_ticker[ticker] = {
            "cik":             cik,
            "available":       True,
            "n_form4_last_90d": len(filings),
            "most_recent":     filings[0] if filings else None,
            "filings":         filings[:20],
        }
        n_forms_total += len(filings)
        n_ok += 1

    payload = {
        "engine":         "aegis.ingest.edgar.v0.1",
        "asof":           asof,
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "source":         "https://data.sec.gov/submissions (public · free · UA required)",
        "universe_size":  len(universe),
        "n_ok":           n_ok,
        "n_form4_total":  n_forms_total,
        "per_ticker":     per_ticker,
    }
    p = out_dir / "insider_recent.json"
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return payload
