"""Market Breadth · daily A/D + sector breadth from existing bar parquets.

For each ticker with a _D1.parquet:
    · advancer = today_close > yesterday_close
    · above_50dma = today_close > mean(last 50 closes)

Aggregates to:
    · overall market breadth (advancers/total · % above 50DMA)
    · per-sector breadth (via ticker→sector map from rec archive)

Output: reports/context/market_breadth.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _sector_map(root: Path, market: str) -> dict:
    """Ticker → sector map · India: uses india/sectors.py SECTORS dict as
    the authoritative source (~100 tickers) + supplements from R2 archive.
    USA: uses universe.yaml + R2 archive."""
    reports = root / ("usa/reports" if market == "usa" else "reports")
    mapping = {}

    # India · load authoritative dict from india/sectors.py
    if market == "india":
        try:
            import sys as _sys
            _sys.path.insert(0, str(root))
            from india.sectors import SECTORS as _S
            mapping.update({k.upper(): v for k, v in _S.items()})
        except Exception:
            pass

    # Supplement from R2 archive (fills tickers not in the seed dict)
    hist_dir = reports / "recommendations_history" / market
    if hist_dir.exists():
        for p in sorted(hist_dir.glob("*.json"))[-30:]:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                for r in d.get("recommendations") or []:
                    t = (r.get("ticker") or "").replace(".NS", "").replace(".BO", "")
                    s = r.get("sector") or ""
                    if t and s: mapping.setdefault(t.upper(), s)
            except Exception:
                continue

    # USA universe.yaml fallback
    if market == "usa":
        uni = root / "usa" / "configs" / "universe.yaml"
        if uni.exists():
            try:
                import yaml
                d = yaml.safe_load(uni.read_text(encoding="utf-8"))
                for uni_name, cfg in (d.get("universes") or {}).items():
                    for entry in cfg.get("tickers") or []:
                        if isinstance(entry, dict):
                            sym = (entry.get("symbol") or "").upper()
                            sec = entry.get("sector")
                            if sym and sec: mapping.setdefault(sym, sec)
            except Exception:
                pass
    return mapping


def _bars_dir(root: Path, market: str) -> Path:
    if market == "usa":
        return root / "usa" / "data" / "raw" / "us"
    return root / "data" / "raw" / "india"


def compute_breadth(root: Path, market: str, asof: str) -> dict:
    try:
        import pandas as pd
    except ImportError:
        return {"available": False, "reason": "pandas not installed"}

    bars = _bars_dir(root, market)
    if not bars.exists():
        return {"available": False, "reason": f"no bars dir at {bars}"}

    sector_map = _sector_map(root, market)
    stats = {"total": 0, "advancers": 0, "decliners": 0, "above_50dma": 0}
    per_sector: dict[str, dict] = {}

    for pq in bars.glob("*_D1.parquet"):
        if pq.name.startswith("_IDX_"): continue
        ticker = pq.stem.replace("_D1", "").replace(".NS", "").replace(".BO", "")
        try:
            df = pd.read_parquet(pq)
            if len(df) < 51: continue
            # Handle both 'Close' and 'close' column casing
            close_col = "Close" if "Close" in df.columns else \
                             ("close" if "close" in df.columns else None)
            if close_col is None: continue
            df = df.tail(60)
            last = float(df[close_col].iloc[-1])
            prev = float(df[close_col].iloc[-2])
            sma50 = float(df[close_col].tail(50).mean())
        except Exception:
            continue
        advancing = last > prev
        above_50 = last > sma50
        stats["total"] += 1
        stats["advancers" if advancing else "decliners"] += 1
        if above_50: stats["above_50dma"] += 1
        sector = sector_map.get(ticker.upper(), "Unknown")
        per_sector.setdefault(sector, {"total": 0, "advancers": 0, "above_50dma": 0})
        per_sector[sector]["total"] += 1
        if advancing: per_sector[sector]["advancers"] += 1
        if above_50: per_sector[sector]["above_50dma"] += 1

    if stats["total"] == 0:
        return {"available": False, "reason": "no bar files with sufficient history"}

    # Sector breadth scores
    sector_scores = {}
    for sector, s in per_sector.items():
        ad_ratio = s["advancers"] / s["total"] if s["total"] else 0
        pct_above = s["above_50dma"] / s["total"] if s["total"] else 0
        # Combined score: [-1, +1] · +1 = all advancing + all above 50 · -1 = opposite
        score = round((ad_ratio - 0.5) + (pct_above - 0.5), 3)
        sector_scores[sector] = {
            "n":            s["total"],
            "advancers":    s["advancers"],
            "ad_ratio_pct": round(ad_ratio * 100, 1),
            "above_50dma_pct": round(pct_above * 100, 1),
            "score":        score,
        }

    return {
        "engine":            "aegis.context.market_breadth.v0.1",
        "asof":              asof, "market": market,
        "generated_utc":     datetime.now(timezone.utc).isoformat(),
        "available":         True,
        "total_tickers":     stats["total"],
        "overall_ad_ratio_pct": round(stats["advancers"] / stats["total"] * 100, 1),
        "overall_above_50dma_pct": round(stats["above_50dma"] / stats["total"] * 100, 1),
        "per_sector":        sector_scores,
    }


def emit(root: Path, payload: dict) -> Path:
    p = root / "reports" / "context" / "market_breadth.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return p
