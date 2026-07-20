"""Feature Builder — orchestrates one feature snapshot per (market, asof).

Reads canonical data via adapt_all() then invokes every registered
category computer. Joins the per-category dicts into one row per ticker.
Returns a pandas DataFrame with columns aligned to FEATURE_REGISTRY.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from backend.canonical.model import MarketProfile
from backend.canonical.adapters import adapt_all
from backend.canonical.schemas import CanonicalDataset
from backend.feature_store.feature_registry import FEATURE_REGISTRY, list_features, FeatureCategory
from backend.feature_store.features import (
    technical, fundamental, news, earnings, macro, sector,
    institutional, corporate_actions, market_intel, historical,
)


class FeatureBuilder:
    def __init__(self, repo_root: Path, market: MarketProfile):
        self.repo_root = Path(repo_root)
        self.market = market

    # ── Load the market's universe symbols ──────────────────────
    def _universe(self) -> list[str]:
        if self.market.name == "usa":
            import json
            p = self.repo_root / "usa" / "reports" / "universe.json"
            if not p.exists(): return []
            data = json.loads(p.read_text(encoding="utf-8"))
            return sorted({t["symbol"] for t in data.get("tickers", []) if t.get("symbol")})
        # India — read from india.data_nse.UNIVERSE
        import sys
        sys.path.insert(0, str(self.repo_root))
        try:
            from india.data_nse import UNIVERSE  # type: ignore
            return sorted([s for s in UNIVERSE if not s.startswith("^")])
        except Exception:
            return []

    # ── Ticker → sector lookup, used to fill identity.sector ────
    def _ticker_sector(self) -> dict[str, str]:
        import json
        if self.market.name == "usa":
            p = self.repo_root / "usa" / "reports" / "universe.json"
            if not p.exists(): return {}
            data = json.loads(p.read_text(encoding="utf-8"))
            return {t["symbol"]: t.get("sector", "") for t in data.get("tickers", [])}
        try:
            import sys
            sys.path.insert(0, str(self.repo_root))
            from india.sectors import SECTORS  # type: ignore
            m: dict[str, str] = {}
            for sec, syms in SECTORS.items():
                for s in syms:
                    m[s] = sec
            return m
        except Exception:
            return {}

    # ── The main call ───────────────────────────────────────────
    def build(self, asof: date | None = None) -> pd.DataFrame:
        cutoff = asof                  # walk-forward: asof is the freeze date
        universe = self._universe()
        if not universe:
            return pd.DataFrame()

        canon = adapt_all(self.repo_root, self.market, cutoff=cutoff)

        # Identity columns (always filled)
        sec_map = self._ticker_sector()
        as_iso = (asof or date.today()).isoformat()
        rows: dict[str, dict] = {}
        for t in universe:
            rows[t] = {
                "market":   self.market.name,
                "ticker":   t,
                "asof":     as_iso,
                "sector":   sec_map.get(t) or None,
                "currency": self.market.currency,
            }

        # Category computers — each returns {ticker: {feature: value}}
        computers = [
            ("technical",         lambda: technical.compute(canon, universe, asof or date.today(), self.market.name)),
            ("fundamental",       lambda: fundamental.compute(canon, universe, asof or date.today(), self.market.name)),
            ("news",              lambda: news.compute(canon, universe, asof or date.today(), self.market.name)),
            ("earnings",          lambda: earnings.compute(canon, universe, asof or date.today(), self.market.name)),
            ("macro",             lambda: macro.compute(canon, universe, asof or date.today(), self.market.name)),
            ("sector",            lambda: sector.compute(canon, universe, asof or date.today(), self.market.name,
                                                            repo_root=self.repo_root)),
            ("institutional",     lambda: institutional.compute(canon, universe, asof or date.today(), self.market.name)),
            ("corporate_actions", lambda: corporate_actions.compute(canon, universe, asof or date.today(), self.market.name)),
            ("market_intel",      lambda: market_intel.compute(canon, universe, asof or date.today(), self.market.name,
                                                                  repo_root=self.repo_root)),
            ("historical",        lambda: historical.compute(canon, universe, asof or date.today(), self.market.name,
                                                                 repo_root=self.repo_root)),
        ]
        for name, fn in computers:
            try:
                per_ticker = fn()
            except Exception as e:
                print(f"    | WARN computer '{name}' raised {type(e).__name__}: {e}")
                continue
            for t, feats in per_ticker.items():
                if t in rows and feats:
                    rows[t].update(feats)

        # Align to registry columns
        registered_cols = [f.name for f in FEATURE_REGISTRY]
        # ensure sector identity is present (may have been overwritten by sector computer)
        for t in universe:
            if "sector" not in rows[t] or rows[t]["sector"] is None:
                rows[t]["sector"] = sec_map.get(t) or None

        df = pd.DataFrame([rows[t] for t in universe])

        # Fill missing registered columns with None, drop unregistered ones
        for c in registered_cols:
            if c not in df.columns:
                df[c] = None
        df = df[registered_cols]
        return df
