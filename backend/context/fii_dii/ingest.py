"""FII/DII daily flow ingest.

Primary: NSE archived FII/DII bulletin (JSON via nseindia.com/api).
Fallback 1: yfinance market-wide flow proxy from index turnover.
Fallback 2: skeleton payload with data_available=False (safe · never crashes).

Output shape:
    {
      "asof": "2026-08-05",
      "fii_net_crore": -420.5,
      "dii_net_crore": 812.3,
      "net_crore": 391.8,
      "source": "nse|yfinance_proxy|skeleton",
      "history_days": 5,
      "trailing_5d_avg_fii": -180.2,
      "trailing_5d_avg_dii": 620.1,
      "flow_direction": "net_positive",
      "data_available": true
    }
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path


NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"


def _fetch_nse() -> dict | None:
    """Attempt NSE endpoint · returns None on any failure."""
    try:
        import urllib.request
        req = urllib.request.Request(
            NSE_FII_DII_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Expected shape: [{"category":"FII/FPI","netValue":-XXX,...}, {"category":"DII",...}]
        out = {"fii": 0.0, "dii": 0.0}
        for row in data if isinstance(data, list) else []:
            cat = str(row.get("category", "")).upper()
            net = float(row.get("netValue") or 0)
            if "FII" in cat or "FPI" in cat:
                out["fii"] = net
            elif "DII" in cat:
                out["dii"] = net
        return out if out["fii"] or out["dii"] else None
    except Exception:
        return None


def _yf_proxy() -> dict | None:
    """Weak proxy · derive from Nifty turnover vs price move if NSE is blocked."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^NSEI").history(period="5d", interval="1d")
        if len(hist) < 2: return None
        # Very rough: net = volume_pct_change × close_pct_change · not real FII/DII
        # but at least produces a signed number the adapter can consume as fallback.
        vol_delta = float(hist["Volume"].iloc[-1]) - float(hist["Volume"].mean())
        px_delta = float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[-2])
        proxy = round(vol_delta * (1 if px_delta > 0 else -1) / 1e7, 2)
        # Split 60/40 as FII/DII placeholder
        return {"fii": round(proxy * 0.6, 2), "dii": round(proxy * 0.4, 2)}
    except Exception:
        return None


def _load_history(root: Path) -> list[dict]:
    p = root / "reports" / "context" / "fii_dii_history.jsonl"
    if not p.exists(): return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: continue
    return sorted(rows, key=lambda r: r.get("asof") or "")


def _append_history(root: Path, entry: dict) -> None:
    p = root / "reports" / "context" / "fii_dii_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    # Idempotent per asof
    existing = _load_history(root)
    if any(e.get("asof") == entry.get("asof") for e in existing): return
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


def ingest_daily(root: Path, asof: str) -> dict:
    """Try NSE → yfinance proxy → skeleton. Always writes reports/fii_dii_flow.json."""
    source = "skeleton"
    fii = dii = 0.0
    data_available = False

    fetched = _fetch_nse()
    if fetched:
        source = "nse"; fii = fetched["fii"]; dii = fetched["dii"]
        data_available = True
    else:
        proxy = _yf_proxy()
        if proxy:
            source = "yfinance_proxy"; fii = proxy["fii"]; dii = proxy["dii"]
            data_available = True

    net = fii + dii
    direction = "net_positive" if net > 100 else ("net_negative" if net < -100 else "neutral")

    entry = {
        "asof":          asof,
        "fii_net_crore": round(fii, 2),
        "dii_net_crore": round(dii, 2),
        "net_crore":     round(net, 2),
        "source":        source,
        "flow_direction": direction,
        "data_available": data_available,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    _append_history(root, entry)

    # Compute 5d rolling avg
    hist = _load_history(root)
    last5 = hist[-5:]
    if len(last5) >= 2:
        entry["history_days"] = len(last5)
        entry["trailing_5d_avg_fii"] = round(
            sum(e.get("fii_net_crore") or 0 for e in last5) / len(last5), 2)
        entry["trailing_5d_avg_dii"] = round(
            sum(e.get("dii_net_crore") or 0 for e in last5) / len(last5), 2)
    else:
        entry["history_days"] = len(last5)

    entry["engine"] = "aegis.context.fii_dii.v0.1"
    p = root / "reports" / "fii_dii_flow.json"
    p.write_text(json.dumps(entry, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return entry
