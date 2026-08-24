"""Part 10 (Context Engine) + Part 13 (Sector Engine) · active gates.

Both engines already emit signals · previously informational only.
This module reads their outputs and returns a per-ticker gate verdict:

  ALLOW   · fine to keep at rec-emitted decision
  DOWNGRADE · force ACTIVE (not ACTIVE+ · not NEW) · context/sector weak
  BLOCK   · force EXIT · sector break or hostile macro regime

Consumers (sender + guard) call `evaluate(ticker, sector, decision)` and
apply the returned action. Non-invasive to R1/R2 engines · this is a
post-recommender gate layer.

Config knobs live in configs/opportunity_registry.yaml under `gates`.
Sources consumed (all already emitted by existing engines):
  reports/macro_regime.json         · primary_regime + confidence
  reports/market_intelligence_summary.json · composite_score + regime_label
  reports/sector_rotation.json      · leaders / laggards / rotation_strength
  reports/sector_context.json       · per-sector state
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


HOSTILE_REGIMES = {
    "risk-off", "risk_off", "bear", "bearish", "crisis", "panic",
    "distribution", "correction",
}


@dataclass
class GateVerdict:
    ticker:       str = ""
    sector:       str = ""
    action:       str = "ALLOW"    # ALLOW | DOWNGRADE | BLOCK
    reason:       str = ""
    macro_regime: str = ""
    sector_state: str = ""


@dataclass
class GateReport:
    engine:       str = "aegis.context_sector_gate.v1"
    generated_utc: str = ""
    market:       str = ""
    asof:         str = ""
    n_allow:      int = 0
    n_downgrade:  int = 0
    n_block:      int = 0
    macro_regime: str = ""
    verdicts:     list = field(default_factory=list)


def _load_json(p: Path) -> dict:
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_config(root: Path) -> dict:
    p = root / "configs" / "opportunity_registry.yaml"
    if not p.exists(): return {}
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cfg.get("gates", {}) or {}
    except Exception:
        return {}


class ContextSectorGate:
    """Evaluate one ticker at a time · state pre-loaded once per market."""

    def __init__(self, root: Path, market: str):
        self.root = Path(root)
        self.market = market.lower()
        self.cfg = _load_config(root)
        self._macro = _load_json(root / "reports" / "macro_regime.json")
        self._mkt   = _load_json(root / "reports" / "market_intelligence_summary.json")
        self._sec_rot = _load_json(root / "reports" / "sector_rotation.json")
        self._sec_ctx = _load_json(root / "reports" / "sector_context.json")
        # Per-sector state map · normalize sector names to upper-case keys
        self._laggards = {str(s).upper()
                                for s in (self._sec_rot.get("laggards") or [])}
        self._leaders  = {str(s).upper()
                                for s in (self._sec_rot.get("leaders") or [])}
        self._per_sector = {}
        _ctx = self._sec_ctx.get("sectors") or self._sec_ctx.get("per_sector") or {}
        if isinstance(_ctx, dict):
            for k, v in _ctx.items():
                self._per_sector[str(k).upper()] = v
        elif isinstance(_ctx, list):
            for row in _ctx:
                if isinstance(row, dict) and row.get("sector"):
                    self._per_sector[str(row["sector"]).upper()] = row

    def _macro_verdict(self) -> tuple:
        """Returns (severity, regime, reason). severity in {NONE, DOWNGRADE, BLOCK}."""
        reg = str(self._macro.get("primary_regime", "")).strip().lower()
        if not reg: return ("NONE", "", "")
        conf = float(self._macro.get("confidence") or 0.0)
        if reg in HOSTILE_REGIMES and conf >= 0.60:
            return ("BLOCK", reg, f"hostile macro regime={reg} · conf={conf:.2f}")
        if reg in HOSTILE_REGIMES:
            return ("DOWNGRADE", reg, f"hostile macro regime={reg} · low conf {conf:.2f}")
        return ("NONE", reg, "")

    def _sector_verdict(self, sector: str) -> tuple:
        """Returns (severity, state, reason)."""
        sec = str(sector or "").upper()
        if not sec: return ("NONE", "", "")
        if sec in self._laggards:
            # If sector context confirms deterioration → block
            _row = self._per_sector.get(sec) or {}
            _state = str(_row.get("state") or _row.get("trend") or "").lower()
            if _state in ("bearish", "breakdown", "distribution"):
                return ("BLOCK", _state, f"sector={sec} · laggard + state={_state}")
            return ("DOWNGRADE", "laggard",
                        f"sector={sec} · in laggards (sector_rotation.json)")
        return ("NONE", "", "")

    def evaluate(self, ticker: str, sector: str) -> GateVerdict:
        v = GateVerdict(ticker=str(ticker or ""),
                              sector=str(sector or ""))
        # Macro check
        m_sev, m_reg, m_reason = self._macro_verdict()
        v.macro_regime = m_reg
        # Sector check
        s_sev, s_state, s_reason = self._sector_verdict(sector)
        v.sector_state = s_state
        # Combine · BLOCK dominates DOWNGRADE dominates NONE
        levels = {"BLOCK": 3, "DOWNGRADE": 2, "NONE": 1}
        m_lvl = levels.get(m_sev, 1)
        s_lvl = levels.get(s_sev, 1)
        best_lvl = max(m_lvl, s_lvl)
        if best_lvl == 3:
            v.action = "BLOCK"
            v.reason = m_reason if m_lvl >= s_lvl else s_reason
        elif best_lvl == 2:
            v.action = "DOWNGRADE"
            v.reason = m_reason if m_lvl >= s_lvl else s_reason
        else:
            v.action = "ALLOW"
        return v


def compute_report(root: Path, market: str, asof: str,
                            ticker_sector_pairs: list) -> GateReport:
    """Batch evaluate + emit report. `ticker_sector_pairs` is [(ticker, sector), ...]."""
    gate = ContextSectorGate(root, market)
    rep = GateReport(
        market=market.lower(), asof=asof[:10],
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        macro_regime=str(gate._macro.get("primary_regime", "")),
    )
    for tk, sec in ticker_sector_pairs:
        v = gate.evaluate(tk, sec)
        rep.verdicts.append(asdict(v))
        if v.action == "BLOCK":     rep.n_block += 1
        elif v.action == "DOWNGRADE": rep.n_downgrade += 1
        else:                         rep.n_allow += 1
    return rep


def emit(root: Path, rep: GateReport) -> Path:
    p = (root / "reports" / "context"
             / f"context_sector_gate_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def summary_line(rep: GateReport) -> str:
    return (f"gate · macro={rep.macro_regime or 'n/a'} · "
                f"allow={rep.n_allow} · downgrade={rep.n_downgrade} · "
                f"block={rep.n_block}")
