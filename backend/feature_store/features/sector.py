"""Sector features from CanonicalFlowProxy + universe sector metadata.

USA universe carries per-ticker sector in usa/reports/universe.json.
India universe carries sector via `india/sectors.py` — we import lazily.
Sector return proxy comes from ETF (USA) or sector_context (India).
"""
from __future__ import annotations

from datetime import date

from backend.canonical.schemas import CanonicalDataset


# USA sector → sector-ETF ticker used as the proxy
_USA_SECTOR_TO_ETF = {
    "Technology":                "XLK",
    "Financials":                "XLF",
    "Healthcare":                "XLV",
    "Energy":                    "XLE",
    "Industrials":               "XLI",
    "Consumer Discretionary":    "XLY",
    "Consumer Staples":          "XLP",
    "Utilities":                 "XLU",
    "Materials":                 "XLB",
    "Real Estate":               "XLRE",
    "Communication Services":    "XLC",
}


def _ticker_sector_map(repo_root, market_name: str) -> dict[str, str]:
    """Return {ticker: sector} using each market's authoritative source."""
    import json
    from pathlib import Path
    if market_name == "usa":
        p = Path(repo_root) / "usa" / "reports" / "universe.json"
        if not p.exists(): return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return {t["symbol"]: t.get("sector", "") for t in data.get("tickers", [])}
    # India
    try:
        import sys
        sys.path.insert(0, str(repo_root))
        from india.sectors import SECTORS  # type: ignore
        m: dict[str, str] = {}
        for sec, syms in SECTORS.items():
            for s in syms:
                m[s] = sec
        return m
    except Exception:
        return {}


def compute(canon: dict[str, CanonicalDataset], universe: list[str],
             asof: date, market_name: str,
             repo_root=None) -> dict[str, dict]:
    ticker_sector = _ticker_sector_map(repo_root, market_name) if repo_root else {}

    # Build sector -> return_pct map from flow_proxy (USA: ETF ticker; India: sector name)
    sec_return: dict[str, float] = {}
    fp = canon.get("flow_proxy")
    if fp and fp.rows:
        if market_name == "usa":
            # USA flow_proxy is keyed by ETF ticker; invert via _USA_SECTOR_TO_ETF
            etf_to_return = {r.symbol: r.return_pct for r in fp.rows}
            for sec, etf in _USA_SECTOR_TO_ETF.items():
                if etf in etf_to_return:
                    sec_return[sec] = etf_to_return[etf]
        else:
            # India: sector name directly
            for r in fp.rows:
                sec_return[r.label or r.symbol] = r.return_pct

    # Rank sectors (1 = leader)
    ranked = sorted(sec_return.items(), key=lambda kv: kv[1], reverse=True)
    sec_rank: dict[str, int] = {s: i + 1 for i, (s, _) in enumerate(ranked)}
    n_sec = len(ranked)

    out: dict[str, dict] = {}
    for t in universe:
        sec = ticker_sector.get(t, "")
        ret = sec_return.get(sec) if sec else None
        rank = sec_rank.get(sec) if sec else None
        is_leader = 1 if (rank is not None and rank <= 3) else 0
        is_lag    = 1 if (rank is not None and n_sec > 0 and rank > n_sec - 3) else 0
        out[t] = {
            "sector":                 sec or None,
            "sector_return_1m_pct":   ret,
            "sector_rank":            rank,
            "sector_is_leader":       is_leader if rank is not None else None,
            "sector_is_laggard":      is_lag if rank is not None else None,
        }
    return out
