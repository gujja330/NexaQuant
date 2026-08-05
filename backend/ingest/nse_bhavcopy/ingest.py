"""NSE bhavcopy ingest · daily equity market snapshot from NSE archives.

Fetches sec_bhavdata_full_DDMMYYYY.csv for the given asof · parses ·
persists to reports/nse_bhavcopy/{asof}.parquet for downstream engines.

Idempotent per asof. Falls back gracefully when NSE archive is blocked
(some networks · rate limits · weekend/holidays no file exists).
"""
from __future__ import annotations

import io
import json
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path


NSE_URL_TMPL = ("https://archives.nseindia.com/products/content/"
                     "sec_bhavdata_full_{dd}{mm}{yyyy}.csv")
UA_HEADER = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"}


def _fetch_bhavcopy(asof: str) -> bytes | None:
    try:
        d = date.fromisoformat(asof)
    except (ValueError, TypeError):
        return None
    url = NSE_URL_TMPL.format(dd=f"{d.day:02d}", mm=f"{d.month:02d}", yyyy=d.year)
    try:
        req = urllib.request.Request(url, headers=UA_HEADER)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception:
        return None


def ingest_daily(root: Path, asof: str) -> dict:
    out_dir = root / "reports" / "nse_bhavcopy"
    out_dir.mkdir(parents=True, exist_ok=True)

    body = _fetch_bhavcopy(asof)
    if body is None:
        # Try prior business day · NSE archives may lag
        from datetime import timedelta
        for offset in [1, 2, 3]:
            prev = (date.fromisoformat(asof) - timedelta(days=offset)).isoformat()
            body = _fetch_bhavcopy(prev)
            if body:
                asof = prev
                break

    if body is None:
        payload = {"engine": "aegis.ingest.nse_bhavcopy.v0.1",
                        "asof": asof, "available": False,
                        "reason": "archive fetch failed for asof and 3 prior days"}
        (out_dir / "latest_status.json").write_text(json.dumps(payload, indent=2))
        return payload

    # Parse CSV lightly · save raw + summary
    raw_path = out_dir / f"{asof}.csv"
    raw_path.write_bytes(body)

    try:
        import pandas as pd
        df = pd.read_csv(io.BytesIO(body))
        df.columns = [c.strip() for c in df.columns]
        pq_path = out_dir / f"{asof}.parquet"
        df.to_parquet(pq_path, index=False)
        n_rows = len(df)
        n_series = df["SERIES"].str.strip().value_counts().to_dict() \
                        if "SERIES" in df.columns else {}
        total_traded = float(df["TTL_TRD_QNTY"].sum()) if "TTL_TRD_QNTY" in df.columns else None
        total_value = float(df["TURNOVER_LACS"].sum()) if "TURNOVER_LACS" in df.columns else None
    except Exception as e:
        payload = {"engine": "aegis.ingest.nse_bhavcopy.v0.1",
                        "asof": asof, "available": False,
                        "reason": f"parse failed: {type(e).__name__}: {e}"}
        (out_dir / "latest_status.json").write_text(json.dumps(payload, indent=2))
        return payload

    payload = {
        "engine":              "aegis.ingest.nse_bhavcopy.v0.1",
        "asof":                asof,
        "generated_utc":       datetime.now(timezone.utc).isoformat(),
        "source":              "https://archives.nseindia.com (public archive)",
        "available":           True,
        "raw_csv":             str(raw_path.relative_to(root)),
        "parquet":             str(pq_path.relative_to(root)),
        "n_rows":              n_rows,
        "series_breakdown":    n_series,
        "total_traded_qty":    total_traded,
        "total_turnover_lacs": total_value,
    }
    (out_dir / "latest_status.json").write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8")
    return payload
