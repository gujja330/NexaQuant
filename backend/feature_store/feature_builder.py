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
    """`pit_mode` is OFF by default and production never enables it.

    With pit_mode=False every code path below is byte-identical to the
    pre-remediation builder: universe and sector come from today's files.

    With pit_mode=True (research replay only) universe and sector are
    resolved from git provenance at `asof`, and a date with no committed
    record raises instead of silently borrowing today's membership.
    """

    def __init__(self, repo_root: Path, market: MarketProfile,
                 pit_mode: bool = False):
        self.repo_root = Path(repo_root)
        self.market = market
        self.pit_mode = bool(pit_mode)
        self.pit_provenance: dict = {}

    # ── Load the market's universe symbols ──────────────────────
    def _universe(self, asof: "date | None" = None) -> list[str]:
        if self.pit_mode and asof is not None:
            from backend.canonical.pit_provenance import universe_asof, PIT_UNAVAILABLE
            members, prov = universe_asof(self.repo_root, self.market.name, asof)
            self.pit_provenance["universe"] = prov
            if members is PIT_UNAVAILABLE or members == PIT_UNAVAILABLE:
                raise ValueError(
                    "PIT_UNAVAILABLE: no committed universe for %s on or before %s (%s)"
                    % (self.market.name, asof, prov.get("reason")))
            return sorted(members)
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
    def _ticker_sector(self, asof: "date | None" = None) -> dict[str, str]:
        if self.pit_mode and asof is not None:
            from backend.canonical.pit_provenance import sector_asof, PIT_UNAVAILABLE
            mapping, prov = sector_asof(self.repo_root, self.market.name, asof)
            self.pit_provenance["sector"] = prov
            if mapping is PIT_UNAVAILABLE or mapping == PIT_UNAVAILABLE:
                raise ValueError(
                    "PIT_UNAVAILABLE: no committed sector map for %s on or before %s (%s)"
                    % (self.market.name, asof, prov.get("reason")))
            return mapping
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
        universe = self._universe(asof)
        if not universe:
            return pd.DataFrame()

        canon = adapt_all(self.repo_root, self.market, cutoff=cutoff)

        # Phase A fix (2026-07-27): India universe uses ".NS" suffix but the
        # canonical bars/fundamentals/etc. use bare symbols (AARTIIND). Every
        # compute function does `if sym not in universe: continue` which
        # silently dropped ALL tickers → 64/81 empty columns. Fix: pass a
        # suffix-tolerant universe (union of bare + suffixed forms) and map
        # bare-form output keys back to suffix-form for row storage.
        def _bare(t: str) -> str:
            return t.split(".")[0] if "." in t else t
        universe_bare = [_bare(t) for t in universe]
        inverse_map = dict(zip(universe_bare, universe))   # bare → suffixed
        universe_tolerant = list(dict.fromkeys(list(universe) + universe_bare))

        # Identity columns (always filled)
        sec_map = self._ticker_sector(asof)
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
            ("technical",         lambda: technical.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("fundamental",       lambda: fundamental.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("news",              lambda: news.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("earnings",          lambda: earnings.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("macro",             lambda: macro.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("sector",            lambda: sector.compute(canon, universe_tolerant, asof or date.today(), self.market.name,
                                                            repo_root=self.repo_root)),
            ("institutional",     lambda: institutional.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("corporate_actions", lambda: corporate_actions.compute(canon, universe_tolerant, asof or date.today(), self.market.name)),
            ("market_intel",      lambda: market_intel.compute(canon, universe_tolerant, asof or date.today(), self.market.name,
                                                                  repo_root=self.repo_root)),
            ("historical",        lambda: historical.compute(canon, universe_tolerant, asof or date.today(), self.market.name,
                                                                 repo_root=self.repo_root)),
        ]
        for name, fn in computers:
            try:
                per_ticker = fn()
            except Exception as e:
                print(f"    | WARN computer '{name}' raised {type(e).__name__}: {e}")
                continue
            for t, feats in per_ticker.items():
                if not feats: continue
                # Try direct match (compute returned suffixed form)
                if t in rows:
                    rows[t].update(feats)
                    continue
                # Else translate bare → suffixed via inverse_map
                mapped = inverse_map.get(t)
                if mapped and mapped in rows:
                    rows[mapped].update(feats)

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
