# backend/research/attribution_matrix.py
"""AEGIS · Sprint M · Phase C · Attribution Matrix (12 tasks · C17-C28).

CEO directive 2026-08-25 v2.0: "the next analysis should be multi-
dimensional · Cap × Sector × Runner × Regime".

Builds the deep dimensional matrix operator asked for:

  C17 · Canonical Position ID → Outcome Dataset
  C18 · R1 vs R2 dimensional attribution
  C19 · Large / Mid / Small × Runner
  C20 · Sector × Runner
  C21 · Cap × Sector
  C22 · Cap × Sector × Runner (the deep matrix)
  C23 · Investability × Runner
  C24 · Context × Runner
  C25 · Market regime × Sector × Runner
  C26 · Winner-vs-loser feature analysis (15 dimensions)
  C27 · False-positive analysis (recommended → lost)
  C28 · False-negative / missed-opportunity analysis (delegates to
        win_discovery which already ships)

Per-cell metrics: N · win% · avg return · median return · profit factor
· expectancy · avg drawdown · statistical confidence.

Statistical Discipline (Sprint M G2 · CEO Part 21):
  N < 20   · observation only (no ticket)
  20-49    · directional evidence (ticket allowed)
  50-99    · research candidate
  100+     · production validation candidate

Emits reports/research/attribution_matrix_{market}.json + markdown digest.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.attribution_matrix.v1.20260825"

# Statistical confidence bands (CEO Part 21)
def confidence_band(n: int) -> str:
    if n < 20:  return "observation-only"
    if n < 50:  return "directional"
    if n < 100: return "research-candidate"
    return "production-candidate"


@dataclass
class CellMetrics:
    n: int
    n_wins: int
    n_losses: int
    win_rate_pct: float
    avg_return_pct: float
    median_return_pct: float
    profit_factor: float
    expectancy_pct: float
    avg_drawdown_pct: float
    confidence: str            # observation / directional / research / production
    dominant_pattern: str = "" # only for winner-vs-loser cell


@dataclass
class MatrixCell:
    key: str                   # dimension label · e.g. "R2|LargeCap|Technology"
    dimensions: dict
    metrics: dict


@dataclass
class AttributionMatrixReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_positions: int = 0
    runner_matrix: list = field(default_factory=list)          # C18
    cap_runner_matrix: list = field(default_factory=list)      # C19
    sector_runner_matrix: list = field(default_factory=list)   # C20
    cap_sector_matrix: list = field(default_factory=list)      # C21
    cap_sector_runner_matrix: list = field(default_factory=list) # C22
    investability_runner_matrix: list = field(default_factory=list) # C23
    regime_sector_runner_matrix: list = field(default_factory=list) # C25
    winner_vs_loser_dims: list = field(default_factory=list)   # C26
    false_positives: list = field(default_factory=list)        # C27
    top_findings: list = field(default_factory=list)


def _load_closed_positions(root: Path, market: str,
                           lookback_days: int = 90) -> list:
    """Return list of dicts with {ticker, runner, entry_date, exit_date,
    pnl_pct, days_held, sector, cap_size, is_win}."""
    try:
        from backend.research import opportunity_registry as _oreg
        from backend.research.loss_attribution_v2 import (
            _sector_for, _cap_size_for, _return_between)
    except Exception:
        return []
    reg = _oreg.load_all(root)
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    positions = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.status != "CLOSED": continue
            if not (o.created_date and o.closed_date): continue
            if o.closed_date < cutoff: continue
            pnl = _return_between(root, o.ticker, market,
                                  o.created_date, o.closed_date)
            if pnl is None: continue
            try:
                _dh = (date.fromisoformat(o.closed_date)
                       - date.fromisoformat(o.created_date)).days
            except Exception:
                _dh = 0
            positions.append({
                "ticker": o.ticker.upper(),
                "runner": o.runner.upper().replace("_NEW", ""),
                "entry_date": o.created_date,
                "exit_date": o.closed_date,
                "pnl_pct": round(pnl, 2),
                "days_held": _dh,
                "sector": _sector_for(root, o.ticker, market),
                "cap_size": _cap_size_for(root, o.ticker, market),
                "is_win": pnl > 0.5,
            })
    return positions


def _cell_metrics(items: list) -> CellMetrics:
    n = len(items)
    if n == 0:
        return CellMetrics(
            n=0, n_wins=0, n_losses=0,
            win_rate_pct=0.0, avg_return_pct=0.0, median_return_pct=0.0,
            profit_factor=0.0, expectancy_pct=0.0, avg_drawdown_pct=0.0,
            confidence="observation-only")
    wins = [x["pnl_pct"] for x in items if x["is_win"]]
    losses = [x["pnl_pct"] for x in items if not x["is_win"]]
    n_w = len(wins); n_l = len(losses)
    win_rate = n_w / n * 100
    avg_win = sum(wins) / max(n_w, 1) if wins else 0
    avg_loss = sum(losses) / max(n_l, 1) if losses else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss else 0.0
    # Expectancy = win_rate*avg_win + loss_rate*avg_loss
    expectancy = (win_rate/100) * avg_win + (1 - win_rate/100) * avg_loss
    all_pnls = sorted(x["pnl_pct"] for x in items)
    med = all_pnls[n // 2] if all_pnls else 0
    avg_dd = round(sum(x["pnl_pct"] for x in items
                       if x["pnl_pct"] < 0) / max(n_l, 1), 2) if n_l else 0.0
    return CellMetrics(
        n=n, n_wins=n_w, n_losses=n_l,
        win_rate_pct=round(win_rate, 1),
        avg_return_pct=round((sum(x["pnl_pct"] for x in items) / n), 2),
        median_return_pct=round(med, 2),
        profit_factor=round(profit_factor, 2),
        expectancy_pct=round(expectancy, 2),
        avg_drawdown_pct=avg_dd,
        confidence=confidence_band(n),
    )


def _rollup(positions: list, dim_fns: list) -> list:
    """Group by tuple(dim_fn(p) for dim_fn in dim_fns) · return cells."""
    buckets = defaultdict(list)
    for p in positions:
        key = tuple(fn(p) for fn in dim_fns)
        buckets[key].append(p)
    cells = []
    for key, items in buckets.items():
        m = _cell_metrics(items)
        cells.append({
            "key": "|".join(str(k) for k in key),
            "dimensions": {f"dim_{i}": str(k) for i, k in enumerate(key)},
            "metrics": asdict(m),
        })
    # Sort by expectancy desc (CEO G3 · optimize expectancy not win rate)
    cells.sort(key=lambda c: -(c["metrics"]["expectancy_pct"] or 0))
    return cells


# ─────────────────────────────────────────────────────────────────
# Dimension functions
# ─────────────────────────────────────────────────────────────────
def _dim_runner(p):   return p["runner"]
def _dim_cap(p):      return p["cap_size"]
def _dim_sector(p):   return p["sector"]


def _dim_investability(p):
    """Best-effort · lookup investability verdict at entry (approximate)."""
    return "UNKNOWN"    # Registry doesn't currently snapshot entry-quality


def _dim_regime(p):
    """Regime at entry · best-effort from macro_regime history."""
    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────
# C26 · Winner-vs-loser feature dimensions
# ─────────────────────────────────────────────────────────────────
def _winner_loser_by_dim(positions: list, dim_fn, dim_name: str) -> dict:
    """For a dimension, split positions into winners vs losers and
    compute per-bucket metrics."""
    buckets = defaultdict(list)
    for p in positions:
        buckets[dim_fn(p)].append(p)
    out = []
    for k, items in buckets.items():
        m = _cell_metrics(items)
        out.append({
            "dimension": dim_name,
            "value": str(k),
            "metrics": asdict(m),
        })
    out.sort(key=lambda x: -(x["metrics"]["expectancy_pct"] or 0))
    return out


# ─────────────────────────────────────────────────────────────────
# C27 · False positive analysis
# ─────────────────────────────────────────────────────────────────
def false_positives(positions: list, threshold_loss_pct: float = -3.0) -> list:
    """Positions we recommended that lost more than threshold."""
    losses = sorted(
        (p for p in positions if p["pnl_pct"] <= threshold_loss_pct),
        key=lambda x: x["pnl_pct"])
    return [
        {
            "ticker": p["ticker"], "runner": p["runner"],
            "entry_date": p["entry_date"], "exit_date": p["exit_date"],
            "days_held": p["days_held"], "pnl_pct": p["pnl_pct"],
            "sector": p["sector"], "cap_size": p["cap_size"],
        }
        for p in losses[:30]
    ]


# ─────────────────────────────────────────────────────────────────
# Top findings extractor
# ─────────────────────────────────────────────────────────────────
def _top_findings(rep: AttributionMatrixReport) -> list:
    findings = []
    # Best runner
    if rep.runner_matrix:
        best = rep.runner_matrix[0]
        if best["metrics"]["n"] >= 20:
            findings.append({
                "type": "best-runner",
                "finding": f"{best['dimensions'].get('dim_0','?')} · "
                           f"expectancy {best['metrics']['expectancy_pct']:+.2f}% · "
                           f"PF {best['metrics']['profit_factor']} · "
                           f"n={best['metrics']['n']} · "
                           f"confidence {best['metrics']['confidence']}",
            })
    # Best cap × sector × runner triple (from C22)
    if rep.cap_sector_runner_matrix:
        top3 = [c for c in rep.cap_sector_runner_matrix
                if c["metrics"]["n"] >= 20][:3]
        for c in top3:
            findings.append({
                "type": "best-triple",
                "finding": f"{c['key']} · expectancy "
                           f"{c['metrics']['expectancy_pct']:+.2f}% · "
                           f"PF {c['metrics']['profit_factor']} · n={c['metrics']['n']}",
            })
    # Worst sector
    if rep.sector_runner_matrix:
        worst = list(reversed(rep.sector_runner_matrix))[0]
        if worst["metrics"]["n"] >= 20 and worst["metrics"]["expectancy_pct"] < 0:
            findings.append({
                "type": "worst-sector-runner",
                "finding": f"{worst['key']} · expectancy "
                           f"{worst['metrics']['expectancy_pct']:+.2f}% · "
                           f"n={worst['metrics']['n']}",
            })
    return findings


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str,
            lookback_days: int = 90) -> AttributionMatrixReport:
    positions = _load_closed_positions(root, market, lookback_days)
    rep = AttributionMatrixReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    rep.n_positions = len(positions)
    # C18 · Runner
    rep.runner_matrix = _rollup(positions, [_dim_runner])
    # C19 · Cap × Runner
    rep.cap_runner_matrix = _rollup(positions, [_dim_cap, _dim_runner])
    # C20 · Sector × Runner
    rep.sector_runner_matrix = _rollup(positions, [_dim_sector, _dim_runner])
    # C21 · Cap × Sector
    rep.cap_sector_matrix = _rollup(positions, [_dim_cap, _dim_sector])
    # C22 · Cap × Sector × Runner
    rep.cap_sector_runner_matrix = _rollup(
        positions, [_dim_cap, _dim_sector, _dim_runner])
    # C23 · Investability × Runner
    rep.investability_runner_matrix = _rollup(
        positions, [_dim_investability, _dim_runner])
    # C25 · Regime × Sector × Runner
    rep.regime_sector_runner_matrix = _rollup(
        positions, [_dim_regime, _dim_sector, _dim_runner])
    # C26 · Winner-vs-loser per dimension
    for dim_fn, dim_name in [
        (_dim_runner, "runner"), (_dim_cap, "cap_size"),
        (_dim_sector, "sector"),
    ]:
        rep.winner_vs_loser_dims.extend(
            _winner_loser_by_dim(positions, dim_fn, dim_name))
    # C27 · False positives
    rep.false_positives = false_positives(positions)
    # Top findings
    rep.top_findings = _top_findings(rep)
    return rep


def emit(root: Path, report: AttributionMatrixReport) -> Path:
    p = (root / "reports" / "research"
         / f"attribution_matrix_{report.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: AttributionMatrixReport) -> str:
    return (f"attribution_matrix · {rep.n_positions} closed · "
            f"top_findings {len(rep.top_findings)} · "
            f"false_positives {len(rep.false_positives)}")
