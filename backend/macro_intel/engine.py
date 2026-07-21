"""MacroIntelligenceEngine — composes all macro readers into one result."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.macro_intel.types            import MacroIntelligenceResult, VolatilityReading
from backend.macro_intel.commodities      import read_commodities
from backend.macro_intel.currencies       import read_currencies
from backend.macro_intel.bonds            import read_bonds, compute_yield_curve
from backend.macro_intel.central_bank     import infer_central_bank_state
from backend.macro_intel.volatility       import classify_volatility_regime
from backend.macro_intel.sector_rotation  import compute_sector_rotation
from backend.macro_intel.macro_regime     import classify_macro_regime
from backend.macro_intel.impact_matrix    import apply_impact_matrix
from backend.macro_intel.knowledge_graph  import build_macro_knowledge_graph


class MacroIntelligenceEngine:
    ENGINE_ID       = "aegis.macro_intel.v1"
    ENGINE_VERSION  = "1.0.0"

    def __init__(self, repo_root: Path, market: str,
                    schema_fingerprint: str = "",
                    feature_set_version: str = "",
                    model_stamp: dict | None = None):
        self.repo_root = Path(repo_root)
        self.market = market
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version
        self.model_stamp = dict(model_stamp) if model_stamp else {}

    def _load_json(self, path: Path) -> dict | None:
        if not path.exists(): return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def run(self, asof: date | None = None) -> MacroIntelligenceResult:
        asof = asof or date.today()
        r = MacroIntelligenceResult(
            market=self.market, asof=asof,
            engine_version=self.ENGINE_VERSION,
            schema_fingerprint=self.schema_fingerprint,
            feature_set_version=self.feature_set_version,
            model_stamp=self.model_stamp,
        )

        # ── Load Sprint 1B artefacts ──────────────────────────
        if self.market == "usa":
            macro_summary_p = self.repo_root / "usa" / "reports" / "macro_summary.json"
            etf_flows_p     = self.repo_root / "usa" / "reports" / "etf_flows_summary.json"
            sector_ctx_p    = None
        else:
            macro_summary_p = self.repo_root / "reports" / "macro_summary.json"    # may not exist for India
            etf_flows_p     = None
            sector_ctx_p    = self.repo_root / "reports" / "sector_context.json"

        macro_summary   = self._load_json(macro_summary_p) if macro_summary_p else None
        etf_flows       = self._load_json(etf_flows_p)     if etf_flows_p     else None
        sector_context  = self._load_json(sector_ctx_p)    if sector_ctx_p    else None

        # ── Read commodity, currency, bond blocks ─────────────
        r.commodities = read_commodities(macro_summary)
        r.currencies  = read_currencies(macro_summary)
        r.bonds       = read_bonds(macro_summary)

        # ── Volatility ───────────────────────────────────────
        vix_level: float | None = None
        vix_1m_pct: float | None = None
        if macro_summary:
            for row in macro_summary.get("per_symbol", []):
                if str(row.get("symbol") or "") == "^VIX":
                    vix_level = float(row.get("last")) if row.get("last") is not None else None
                    vix_1m_pct = row.get("chg_1m_pct")
                    break
        # India VIX fallback
        if self.market == "india" and vix_level is None:
            p = self.repo_root / "data" / "raw" / "india" / "INDIAVIX_D1.parquet"
            if p.exists():
                try:
                    import pandas as pd
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns and len(df) > 0:
                        vix_level = float(df["close"].iloc[-1])
                except Exception: pass
        r.volatility = classify_volatility_regime(self.market, vix_level, vix_1m_pct)

        # ── Yield curve + central bank ───────────────────────
        curve_slope, inversion = compute_yield_curve(r.bonds)
        r.central_bank = infer_central_bank_state(self.market, r.bonds, curve_slope, inversion)

        # ── Sector rotation ──────────────────────────────────
        r.sector_rotation = compute_sector_rotation(
            self.market, asof, etf_flows_summary=etf_flows, sector_context=sector_context,
        )

        # ── Impact matrix ────────────────────────────────────
        r.active_impacts = apply_impact_matrix(r.commodities, threshold_pct=3.0)

        # ── Composite macro regime ───────────────────────────
        r.macro_regime = classify_macro_regime(
            self.market, asof,
            commodities=r.commodities,
            currencies=r.currencies,
            bonds=r.bonds,
            volatility=r.volatility,
            yield_curve_inversion=inversion,
        )

        # ── Knowledge graph ──────────────────────────────────
        r.knowledge_graph = build_macro_knowledge_graph(
            r.commodities, r.currencies, r.bonds, r.volatility, r.active_impacts,
        )

        # ── Notes ────────────────────────────────────────────
        r.notes.append(f"engine v{r.engine_version} · "
                          f"n_commodities={len(r.commodities)} · "
                          f"n_currencies={len(r.currencies)} · "
                          f"n_bonds={len(r.bonds)} · "
                          f"n_active_impacts={len(r.active_impacts)} · "
                          f"n_kg_entries={len(r.knowledge_graph)}")
        return r
