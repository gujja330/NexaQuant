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
    # India · CEO 2026-11-04
    #
    # This inverted SECTORS, which is a FLAT ticker->sector map, and so
    # iterated the CHARACTERS of each sector name - producing 30 entries
    # keyed by single letters and a 0-of-228 join. One shared resolver
    # now owns the shape and refuses a malformed map rather than
    # returning a plausible wrong one.
    try:
        from backend.shared.sector_map import india_ticker_sector
        return india_ticker_sector(repo_root)
    except Exception as e:
        print("    | WARN sector map unavailable: %s: %s"
              % (type(e).__name__, e))
        return {}


def _index_aliases(repo_root) -> dict:
    """sector-name -> sector-INDEX-label, from validated config.

    Only `aliases` is honoured. `proposed_aliases` is deliberately NOT
    read: each one is a modelling claim awaiting approval, and reading
    it here would enable it silently.
    """
    if repo_root is None:
        return {}
    from pathlib import Path as _P
    p = _P(repo_root) / "configs" / "india_sector_index_aliases.yaml"
    if not p.exists():
        return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out = cfg.get("aliases") or {}
        if not isinstance(out, dict):
            return {}
        return {str(k): str(v) for k, v in out.items()
                if isinstance(v, (str, int, float))}
    except Exception as e:
        print("    | WARN sector alias config unreadable: %s: %s"
              % (type(e).__name__, e))
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

    # 2026-07-27 fix: normalize ticker lookup. `ticker_sector` from india/sectors.py
    # keys are BARE symbols (RELIANCE), but universe may include NSE-suffix form
    # (RELIANCE.NS). Try both.
    def _lookup_sector(t: str) -> str:
        s = ticker_sector.get(t, "")
        if s: return s
        bare = t.split(".")[0] if "." in t else t
        return ticker_sector.get(bare, "")

    # CEO 2026-11-04 · the ticker classification and the sector-index
    # labels are two vocabularies that only agree on 7 of 17 names, so a
    # correctly classified ticker can still have no sector return. The
    # alias table encodes label variance ONLY; a sector with no
    # defensible index stays unmapped and its features stay null.
    alias = _index_aliases(repo_root)

    out: dict[str, dict] = {}
    for t in universe:
        sec = _lookup_sector(t)
        idx = alias.get(sec, sec) if sec else None
        ret = sec_return.get(idx) if idx else None
        rank = sec_rank.get(idx) if idx else None
        # An unknown rank is NOT "not a leader". Returning 0 here claimed
        # 133 of 228 India tickers were measured and found ordinary, when
        # no sector return existed for them at all. Missing and weak are
        # different answers and must not share an encoding.
        if rank is None:
            is_leader = None
            is_lag = None
        else:
            is_leader = 1 if rank <= 3 else 0
            is_lag    = 1 if (n_sec > 0 and rank > n_sec - 3) else 0
        out[t] = {
            "sector":                 sec or None,
            "sector_return_1m_pct":   ret,
            "sector_rank":            rank,
            "sector_is_leader":       is_leader if rank is not None else None,
            "sector_is_laggard":      is_lag if rank is not None else None,
        }
    return out
