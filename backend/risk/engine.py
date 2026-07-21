"""RiskEngine — composes sizing + caps + vol adjustment + VaR/CVaR.

Reads recommendations_v3.json + feature snapshot + market_intelligence_summary.
Produces sized_positions.json + risk_report.json + AI narrative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from backend.risk.types           import (
    SizedPosition, RiskBudget, RiskReport, CapReason,
)
from backend.risk.sizing          import kelly_fractional_size, confidence_tier_multiplier
from backend.risk.vol_adjustment  import vol_adjusted_size, vix_regime_dampener
from backend.risk.exposure_caps   import (
    apply_per_ticker_cap, apply_per_sector_cap, choose_cap_reason,
)
from backend.risk.concentration   import herfindahl_hirschman, top_k_concentration_pct
from backend.risk.var_cvar        import parametric_var_cvar


CONFIDENCE_GATE = 0.30    # positions with regime_adjusted_confidence < this are dropped


class RiskEngine:
    ENGINE_ID       = "aegis.risk.v1"
    ENGINE_VERSION  = "1.0.0"

    def __init__(self, repo_root: Path, market: str, budget: RiskBudget,
                    regime: str = "unknown", vix_level: float | None = None,
                    schema_fingerprint: str = "",
                    feature_set_version: str = "",
                    model_stamp: dict | None = None):
        self.repo_root = Path(repo_root)
        self.market = market
        self.budget = budget
        self.regime = regime
        self.vix_level = vix_level
        self.schema_fingerprint = schema_fingerprint
        self.feature_set_version = feature_set_version
        self.model_stamp = dict(model_stamp) if model_stamp else {}

    def run(self, recommendations: list[dict], features_df: pd.DataFrame,
              asof: date | None = None) -> tuple[list[SizedPosition], RiskReport]:
        """Turn a list of Recommendation dicts into SizedPosition + RiskReport."""
        asof = asof or date.today()
        vix_mult = vix_regime_dampener(self.regime, self.vix_level)

        # Index features by ticker for fast lookup
        feats = features_df.set_index("ticker") if "ticker" in features_df.columns else features_df
        sector_map = {}                # populated as we size

        sized: list[SizedPosition] = []
        # Track running sector exposure as we allocate (greedy — good enough for Sprint 4 baseline;
        # a joint optimizer is Sprint 5 Portfolio Engine's job)
        sector_exposure: dict[str, float] = {}

        # Order recs by confidence descending — highest-conviction gets first crack at budget
        ordered = sorted(recommendations,
                            key=lambda r: (r.get("regime_adjusted_confidence") or 0.0),
                            reverse=True)

        for rec in ordered:
            action = str(rec.get("action") or "HOLD")
            ticker = str(rec.get("ticker") or "")
            score  = float(rec.get("ensemble_score") or 0.0)
            conf   = float(rec.get("regime_adjusted_confidence") or 0.0)
            disagreement = bool(rec.get("disagreement_flag"))

            # HOLD is dropped — nothing to size
            if action == "HOLD":
                continue

            # Confidence gate
            if conf < CONFIDENCE_GATE:
                sized.append(self._make_position(
                    ticker, action, score, conf, 0.0, 0.0, 0.0, 0.0,
                    CapReason.CONFIDENCE_GATE, feats,
                ))
                continue

            # Disagreement handled upstream (Sprint 3 collapses to HOLD), but re-guard here
            if disagreement:
                sized.append(self._make_position(
                    ticker, action, score, conf, 0.0, 0.0, 0.0, 0.0,
                    CapReason.DISAGREEMENT, feats,
                ))
                continue

            # Short handling
            is_short = action in ("SELL", "STRONG_SELL")
            if is_short and not self.budget.enable_shorts:
                sized.append(self._make_position(
                    ticker, action, score, conf, 0.0, 0.0, 0.0, 0.0,
                    CapReason.SHORT_DISABLED, feats,
                ))
                continue

            # Pull volatility from features
            row = feats.loc[ticker].to_dict() if ticker in feats.index else {}
            vol_ann = self._extract_vol(row)

            # Edge = confidence × score × direction sign × VIX multiplier
            direction  = -1.0 if is_short else 1.0
            edge       = conf * abs(score) * direction * vix_mult

            # Kelly baseline
            kelly = kelly_fractional_size(edge, vol_ann, self.budget.max_kelly_fraction)

            # Confidence-tier multiplier
            tier_mult = confidence_tier_multiplier(action, self.budget.confidence_tier_mult)
            size_by_conf = kelly * abs(tier_mult) * (1.0 if kelly >= 0 else -1.0)

            # Vol-adjusted (inverse-vol targeting)
            size_by_vol = vol_adjusted_size(size_by_conf, vol_ann,
                                              self.budget.target_portfolio_vol)

            kelly_hit  = abs(kelly) >= self.budget.max_kelly_fraction - 1e-9
            vol_hit    = abs(size_by_vol) < abs(size_by_conf) - 1e-9

            # Per-ticker cap
            clipped, ticker_hit = apply_per_ticker_cap(size_by_vol, self.budget.per_ticker_cap)

            # Per-sector cap
            sector = self._extract_sector(row)
            clipped, sector_hit = apply_per_sector_cap(
                clipped, sector, sector_exposure, self.budget.per_sector_cap)

            # Record final position
            reason = choose_cap_reason(kelly_hit, ticker_hit, sector_hit,
                                          vol_hit, False, False, False)
            entry_ref = self._extract_price(row)
            pos = self._make_position(
                ticker, action, score, conf,
                target_weight=clipped,
                kelly=kelly, vol_ann=vol_ann,
                risk_budget_bps=abs(clipped) * vol_ann * 10000,
                cap_reason=reason, feats=feats,
                entry_ref=entry_ref,
            )
            sized.append(pos)

            # Update running sector exposure (only when non-zero)
            if abs(clipped) > 1e-9 and sector:
                sector_exposure[sector] = sector_exposure.get(sector, 0.0) + clipped

        # ── Build portfolio-level report ────────────────────
        report = self._build_report(sized, sector_exposure, asof)
        return sized, report

    # ─── Helpers ─────────────────────────────────────────────
    def _extract_vol(self, row: dict) -> float:
        """Prefer 20d, fall back to 60d, else a conservative 40% default."""
        for key in ("volatility_20d", "volatility_60d"):
            v = row.get(key)
            if v is not None and v > 0:
                # Feature stored as stdev of daily returns → annualise
                return float(v) * (252 ** 0.5)
        return 0.40   # 40% annualised default when data missing

    def _extract_sector(self, row: dict) -> str:
        s = row.get("sector")
        return str(s) if s is not None else ""

    def _extract_price(self, row: dict) -> float | None:
        p = row.get("close")
        return float(p) if p is not None else None

    def _make_position(self, ticker: str, action: str, score: float, conf: float,
                          target_weight: float, kelly: float, vol_ann: float,
                          risk_budget_bps: float, cap_reason: CapReason,
                          feats: pd.DataFrame,
                          entry_ref: float | None = None) -> SizedPosition:
        return SizedPosition(
            market=self.market, ticker=ticker, action=action,
            ensemble_score=round(score, 4),
            confidence=round(conf, 4),
            target_weight=round(target_weight, 5),
            target_notional=0.0,                       # populated by Portfolio Engine given AUM
            risk_budget_bps=round(risk_budget_bps, 2),
            stop_loss_pct=self.budget.default_stop_loss_pct,
            take_profit_pct=None,
            vol_20d_annualised=round(vol_ann, 4),
            kelly_fraction=round(kelly, 5),
            cap_reason=cap_reason,
            entry_reference=entry_ref,
            model_stamp=self.model_stamp,
            schema_fingerprint=self.schema_fingerprint,
            feature_set_version=self.feature_set_version,
        )

    def _build_report(self, sized: list[SizedPosition],
                        sector_exposure: dict[str, float],
                        asof: date) -> RiskReport:
        r = RiskReport(market=self.market, asof=asof,
                          engine_version=self.ENGINE_VERSION, regime=self.regime)

        # Only positions with non-zero target_weight count as active
        active = [p for p in sized if abs(p.target_weight) > 1e-9]
        r.n_positions = len(active)
        r.n_long  = sum(1 for p in active if p.target_weight > 0)
        r.n_short = sum(1 for p in active if p.target_weight < 0)

        r.total_long_exposure_pct  = round(sum(p.target_weight for p in active if p.target_weight > 0), 4)
        r.total_short_exposure_pct = round(sum(p.target_weight for p in active if p.target_weight < 0), 4)
        r.gross_exposure_pct       = round(sum(abs(p.target_weight) for p in active), 4)
        r.net_exposure_pct         = round(r.total_long_exposure_pct + r.total_short_exposure_pct, 4)
        r.cash_pct                 = round(max(0.0, 1.0 - r.gross_exposure_pct), 4)

        weights = [p.target_weight for p in active]
        vols    = [p.vol_20d_annualised for p in active]
        r.hhi_concentration      = round(herfindahl_hirschman(weights), 4)
        r.top_5_concentration_pct = round(top_k_concentration_pct(weights, 5), 4)
        r.per_sector_exposure_pct = {s: round(v, 4) for s, v in sector_exposure.items()}

        var_pct, cvar_pct, port_vol_ann = parametric_var_cvar(weights, vols, horizon_days=1)
        r.portfolio_var_95_1d_pct   = round(var_pct, 4)
        r.portfolio_cvar_95_1d_pct  = round(cvar_pct, 4)
        r.portfolio_vol_annualised  = round(port_vol_ann, 4)

        # Verdict + breaches
        for s, expo in r.per_sector_exposure_pct.items():
            if abs(expo) > self.budget.per_sector_cap + 1e-6:
                r.breaches.append({
                    "kind": "per_sector_cap", "sector": s,
                    "exposure_pct": expo, "cap_pct": self.budget.per_sector_cap})
        for p in active:
            if abs(p.target_weight) > self.budget.per_ticker_cap + 1e-6:
                r.breaches.append({
                    "kind": "per_ticker_cap", "ticker": p.ticker,
                    "weight": p.target_weight, "cap": self.budget.per_ticker_cap})
        if r.portfolio_vol_annualised > self.budget.target_portfolio_vol + 0.05:
            r.breaches.append({
                "kind": "portfolio_vol_cap",
                "portfolio_vol_annualised": r.portfolio_vol_annualised,
                "target": self.budget.target_portfolio_vol})

        if r.breaches:
            r.verdict = "FAIL" if len(r.breaches) > 3 else "WARNING"
        else:
            r.verdict = "PASS"

        r.notes.append(f"engine v{r.engine_version} · regime={r.regime} · "
                          f"vix_mult={vix_regime_dampener(self.regime, self.vix_level):.2f}")
        return r
