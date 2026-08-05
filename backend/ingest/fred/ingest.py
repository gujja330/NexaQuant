"""FRED daily ingest · fetches curated macro series to reports/fred/*.csv
+ writes a rolled-up snapshot at reports/fred/fred_snapshot.json.

Series curated for MAX signal:
    · DGS10       · 10-year Treasury yield
    · DGS2        · 2-year Treasury yield  (curve slope)
    · DFF         · Federal Funds Rate
    · CPIAUCSL    · CPI-U all urban
    · UNRATE      · Unemployment rate
    · PAYEMS      · Non-farm payrolls
    · UMCSENT     · Univ of Michigan sentiment
    · DEXINUS     · India/USD exchange rate
    · DCOILWTICO  · WTI crude oil
    · VIXCLS      · CBOE VIX
    · WM2NS       · M2 money supply
    · T10Y2Y      · 10y-2y yield spread (recession indicator)

Output: reports/fred/fred_snapshot.json with per-series latest value +
30d change + 1y change + percentile. Consumers: bond_adapter,
currency_adapter, commodity_adapter, vol_adapter (Phase 2B).
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


FRED_SERIES = [
    ("DGS10",       "10Y_treasury_yield",       "%",     "rates"),
    ("DGS2",        "2Y_treasury_yield",        "%",     "rates"),
    ("DFF",         "fed_funds_rate",           "%",     "rates"),
    ("T10Y2Y",      "10y_2y_spread",            "%",     "recession_signal"),
    ("CPIAUCSL",    "cpi_all_urban",            "index", "inflation"),
    ("UNRATE",      "unemployment_rate",        "%",     "labor"),
    ("PAYEMS",      "nonfarm_payrolls",         "k",     "labor"),
    ("UMCSENT",     "consumer_sentiment",       "index", "sentiment"),
    ("DEXINUS",     "usd_inr",                  "INR",   "currency"),
    ("DCOILWTICO",  "wti_crude",                "$/bbl", "commodity"),
    ("VIXCLS",      "vix",                      "index", "volatility"),
    ("WM2NS",       "m2_money_supply",          "$B",    "monetary"),
]


def _fetch_series(series_id: str) -> list[tuple[str, float]]:
    """Fetch (date, value) tuples from FRED CSV endpoint.

    2026-08-05: FRED's old public CSV endpoint returns 403 · need to use
    the observations JSON endpoint. Falls back to pandas_datareader if
    installed (uses same underlying FRED service).
    """
    # Method 1: try pandas_datareader (uses FRED's structured API)
    try:
        import pandas_datareader.data as pdr
        from datetime import datetime, timedelta
        end = datetime.now()
        start = end - timedelta(days=800)
        df = pdr.DataReader(series_id, "fred", start, end)
        if df is not None and not df.empty:
            rows = []
            for idx, val in df[series_id].items():
                try:
                    rows.append((idx.strftime("%Y-%m-%d"), float(val)))
                except (ValueError, TypeError):
                    continue
            if rows: return rows
    except Exception:
        pass

    # Method 2: fallback to public CSV endpoint (may be blocked in some networks)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; aegis-research/1.0)",
            "Accept": "text/csv,text/plain,*/*",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except Exception:
        return []
    rows = []
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    for row in reader:
        if len(row) < 2: continue
        try:
            v = float(row[1])
            rows.append((row[0], v))
        except (ValueError, TypeError):
            continue
    return rows


def _percentile_rank(values: list[float], v: float) -> float:
    if not values: return 50.0
    n_below = sum(1 for x in values if x < v)
    return round(n_below / len(values) * 100.0, 1)


def ingest_daily(root: Path, asof: str) -> dict:
    out_dir = root / "reports" / "fred"
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot: dict = {}
    n_ok = 0
    n_fail = 0

    for series_id, label, unit, category in FRED_SERIES:
        rows = _fetch_series(series_id)
        if not rows:
            snapshot[series_id] = {"label": label, "available": False,
                                              "reason": "fetch failed"}
            n_fail += 1
            continue
        # Persist CSV for audit
        with (out_dir / f"{series_id}.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "value"])
            w.writerows(rows[-500:])   # last ~2y

        values = [v for _, v in rows]
        last = values[-1]
        # 30d ago (approx 22 business days)
        val_30d = values[-22] if len(values) >= 22 else None
        val_1y = values[-252] if len(values) >= 252 else None
        change_30d = round((last - val_30d) / val_30d * 100, 2) if val_30d else None
        change_1y = round((last - val_1y) / val_1y * 100, 2) if val_1y else None
        # Percentile vs last 2y
        pctile = _percentile_rank(values[-500:], last)

        snapshot[series_id] = {
            "label":       label,
            "unit":        unit,
            "category":    category,
            "available":   True,
            "latest_date": rows[-1][0],
            "latest_value": round(last, 4),
            "change_30d_pct": change_30d,
            "change_1y_pct": change_1y,
            "percentile_2y": pctile,
        }
        n_ok += 1

    payload = {
        "engine":         "aegis.ingest.fred.v0.1",
        "asof":           asof,
        "generated_utc":  datetime.now(timezone.utc).isoformat(),
        "source":         "https://fred.stlouisfed.org (public · free · no auth)",
        "n_series":       len(FRED_SERIES),
        "n_available":    n_ok,
        "n_failed":       n_fail,
        "series":         snapshot,
    }
    p = out_dir / "fred_snapshot.json"
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return payload
