# core/usa_fundamentals.py
"""
SEC EDGAR FUNDAMENTALS (USA Phase 5) — free, official, POINT-IN-TIME.

Pipeline: ticker -> CIK -> CompanyFacts JSON (raw, cached) -> normalize using the 'filed' date (never
the period end -> no look-ahead) -> derive PIT fundamentals -> upsert into the feature store.

Derived features (latest values known as-of today):
  f_roe = NetIncome(FY) / StockholdersEquity   ·  f_net_margin = NetIncome(FY) / Revenues(FY)
  f_debt_to_equity = Liabilities / StockholdersEquity  ·  f_rev_growth_yoy  ·  f_eps_diluted

Raw JSON is kept locally (git-ignored, regenerable); the normalized table + feature store are committed.

Run:  python -m core.usa_fundamentals --fetch [--max N]    # download raw CompanyFacts for the universe
      python -m core.usa_fundamentals --build              # normalize raw -> feature store
"""
import sys, json, time, re, urllib.request, warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from core.feature_store import FeatureStore, FeatureProvider

UA = {"User-Agent": "AEGIS Research aegis-research@example.com"}      # SEC requires a User-Agent
RAW = ROOT / "markets" / "usa" / "raw" / "fundamentals"
CIK_MAP = RAW / "cik_map.json"
PROCESSED = ROOT / "markets" / "usa" / "processed" / "fundamentals.parquet"
TODAY = str(date.today())


def _get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())


def cik_map():
    if CIK_MAP.exists():
        return json.loads(CIK_MAP.read_text())
    m = _get("https://www.sec.gov/files/company_tickers.json")
    tm = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in m.values()}
    RAW.mkdir(parents=True, exist_ok=True); CIK_MAP.write_text(json.dumps(tm))
    return tm


def fetch_raw(symbols, max_n=None):
    tm = cik_map(); got = 0
    for s in (symbols[:max_n] if max_n else symbols):
        cik = tm.get(s)
        if not cik:
            continue
        try:
            cf = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
            (RAW / f"{s}.json").write_text(json.dumps(cf)); got += 1
            time.sleep(0.12)                                  # ~8 req/s, under SEC's 10/s limit
        except Exception:
            pass
    return got


def _annual(items, today):
    """Annual (full-year) flow facts filed on/before today, newest first (frame like CY2024, no Qn)."""
    out = [x for x in items if x.get("filed", "9") <= today and re.fullmatch(r"CY\d{4}", str(x.get("frame", "")))]
    return sorted(out, key=lambda x: x["end"], reverse=True)


def _latest(items, today):
    out = [x for x in items if x.get("filed", "9") <= today]
    return max(out, key=lambda x: x["filed"]) if out else None


def normalize_one(ticker, today=TODAY):
    p = RAW / f"{ticker}.json"
    if not p.exists():
        return None
    g = json.loads(p.read_text()).get("facts", {}).get("us-gaap", {})

    def units(concept, unit="USD"):
        return g.get(concept, {}).get("units", {}).get(unit, [])
    rev = _annual(units("Revenues") or units("RevenueFromContractWithCustomerExcludingAssessedTax"), today)
    ni = _annual(units("NetIncomeLoss"), today)
    eq = _latest(units("StockholdersEquity"), today)
    li = _latest(units("Liabilities"), today)
    eps = _annual(units("EarningsPerShareDiluted", "USD/shares"), today)
    row = {"symbol": ticker, "date": today}
    if ni and eq and eq["val"]:
        row["f_roe"] = round(100 * ni[0]["val"] / eq["val"], 1)
    if ni and rev and rev[0]["val"]:
        row["f_net_margin"] = round(100 * ni[0]["val"] / rev[0]["val"], 1)
    if li and eq and eq["val"]:
        row["f_debt_to_equity"] = round(li["val"] / eq["val"], 2)
    if len(rev) >= 2 and rev[1]["val"]:
        row["f_rev_growth_yoy"] = round(100 * (rev[0]["val"] / rev[1]["val"] - 1), 1)
    if eps:
        row["f_eps_diluted"] = round(eps[0]["val"], 2)
    return row if len(row) > 2 else None


def build(symbols):
    rows = [r for s in symbols if (r := normalize_one(s))]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    PROCESSED.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED)
    FeatureStore("usa").upsert(df)        # merge fundamentals into the shared feature store
    return df


class FundamentalProvider(FeatureProvider):
    name, category, source, point_in_time = "fundamentals", "Fundamental", "SEC EDGAR", True

    def compute(self, adapter):
        return build([c for c in adapter.get_universe()])


def main():
    from core.market_adapter import USAAdapter
    syms = USAAdapter().symbols
    if "--fetch" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else None
        print(f"  fetching SEC CompanyFacts for {mx or len(syms)} symbols (raw -> {RAW.relative_to(ROOT)}/)...")
        print(f"  fetched {fetch_raw(syms, mx)} raw filings.")
    elif "--build" in sys.argv:
        df = build(syms)
        print(f"  normalized {len(df)} symbols -> feature store + {PROCESSED.relative_to(ROOT)}")
        if not df.empty:
            cols = [c for c in df.columns if c.startswith("f_")]
            print(f"  fundamental features: {cols}")
            print(df.head(8).to_string(index=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
