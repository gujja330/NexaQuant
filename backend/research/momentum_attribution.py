# backend/research/momentum_attribution.py
"""AEGIS · Sprint M.1 · Momentum × Runner/Cap/Sector/Regime attribution.

CEO directive 2026-08-25: "produce Momentum × Runner · Momentum × Cap ·
Momentum × Sector · Momentum × Investability · Momentum × Market Regime
· Momentum × Sector Regime · at 1D / 3D / 5D / 10D / 20D".

Reads short_term_momentum_backtest walk-forward samples · joins with
Registry entries for cohort tagging · produces multi-dim rollups with
N · win rate · avg return · median · profit factor · expectancy ·
max drawdown · statistical confidence.

Constitutional invariant · READ ONLY · never mutates R1/R2.
Statistical Discipline (CEO Part 21) · confidence bands per N.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.momentum_attribution.v1.20260825"

FORWARD_HORIZONS = [1, 3, 5, 10, 20]


def _confidence_band(n: int) -> str:
    if n < 20: return "observation-only"
    if n < 50: return "directional"
    if n < 100: return "research-candidate"
    return "production-candidate"


@dataclass
class Cell:
    key: str
    dimensions: dict
    n: int = 0
    horizon_metrics: dict = field(default_factory=dict)   # per-horizon dict
    confidence: str = "observation-only"


@dataclass
class MomentumAttributionReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    n_samples: int = 0
    momentum_x_runner: list = field(default_factory=list)
    momentum_x_cap: list = field(default_factory=list)
    momentum_x_sector: list = field(default_factory=list)
    momentum_x_investability: list = field(default_factory=list)
    momentum_x_market_regime: list = field(default_factory=list)
    momentum_x_sector_regime: list = field(default_factory=list)
    top_findings: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
# Helpers · reuse loss/win attribution primitives
# ─────────────────────────────────────────────────────────────────
def _sector_for(root: Path, ticker: str, market: str) -> str:
    p = root / "reports" / "sector_cache.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get(market.lower(), {}).get(ticker.upper()) or "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _cap_size(root: Path, ticker: str, market: str) -> str:
    if market.lower() == "india":
        try:
            from india.data_nse import NIFTY100
            tk = str(ticker).upper()
            if tk in NIFTY100: return "LARGE"
            return "MID"
        except Exception:
            return "UNKNOWN"
    return "UNKNOWN"


def _regime_at(root: Path, market: str, at_date: str) -> str:
    p = root / "reports" / "context" / f"macro_regime_{market.lower()}.json"
    if not p.exists(): return "UNKNOWN"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        _l = str(d.get("regime") or d.get("label") or "").upper()
        if "BULL" in _l: return "BULL"
        if "BEAR" in _l: return "BEAR"
        return "NEUTRAL"
    except Exception:
        return "UNKNOWN"


def _horizon_metrics(samples: list) -> dict:
    """For a set of samples · compute per-horizon metrics."""
    out = {}
    for h in FORWARD_HORIZONS:
        field_name = f"fwd_{h}d_pct"
        vals = [s.get(field_name) for s in samples
                if s.get(field_name) is not None]
        if not vals:
            out[str(h)] = None
            continue
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v < 0]
        avg_w = sum(wins) / len(wins) if wins else 0
        avg_l = sum(losses) / len(losses) if losses else 0
        pf = round(abs(avg_w / avg_l), 2) if avg_l else 0.0
        wr = round(len(wins) / len(vals) * 100, 1)
        avg = round(sum(vals) / len(vals), 2)
        exp = round((wr / 100) * avg_w + (1 - wr / 100) * avg_l, 2)
        max_dd = round(min(vals), 2)
        _sorted = sorted(vals)
        med = round(_sorted[len(_sorted) // 2], 2)
        out[str(h)] = {
            "n": len(vals),
            "win_rate_pct": wr,
            "avg_pct": avg,
            "median_pct": med,
            "profit_factor": pf,
            "expectancy_pct": exp,
            "max_dd_pct": max_dd,
        }
    return out


def _rollup_by(root: Path, market: str, samples: list,
               dim_fn) -> list:
    """Group samples by dim_fn(sample) tuple · produce Cell per bucket."""
    buckets = defaultdict(list)
    for s in samples:
        _k = dim_fn(root, market, s)
        buckets[_k].append(s)
    cells = []
    for k, items in buckets.items():
        c = Cell(
            key="|".join(str(x) for x in k),
            dimensions={f"dim_{i}": str(x) for i, x in enumerate(k)},
            n=len(items),
            horizon_metrics=_horizon_metrics(items),
            confidence=_confidence_band(len(items)),
        )
        cells.append(asdict(c))
    # Sort by 20d expectancy desc
    cells.sort(key=lambda c: -((c["horizon_metrics"].get("20") or {})
                                .get("expectancy_pct") or -999))
    return cells


# Dimension functions
def _dim_mom(root, market, s): return (s.get("verdict","IGNORE"),)
def _dim_mom_runner(root, market, s):
    return (s.get("verdict","IGNORE"), s.get("runner","?"))
def _dim_mom_cap(root, market, s):
    return (s.get("verdict","IGNORE"), _cap_size(root, s.get("ticker",""), market))
def _dim_mom_sector(root, market, s):
    return (s.get("verdict","IGNORE"), _sector_for(root, s.get("ticker",""), market))
def _dim_mom_investability(root, market, s):
    return (s.get("verdict","IGNORE"), s.get("quality_band","UNKNOWN"))
def _dim_mom_market_regime(root, market, s):
    return (s.get("verdict","IGNORE"), _regime_at(root, market, s.get("as_of","")))
def _dim_mom_sector_regime(root, market, s):
    # sector_regime not in backtest samples yet · use "UNKNOWN"
    return (s.get("verdict","IGNORE"), "UNKNOWN")


def _top_findings(rep: MomentumAttributionReport) -> list:
    findings = []
    # Highest-expectancy momentum × investability cell with N ≥ 20
    if rep.momentum_x_investability:
        best = None
        for c in rep.momentum_x_investability:
            if c["n"] < 20: continue
            _exp = (c["horizon_metrics"].get("20") or {}).get("expectancy_pct") or 0
            if best is None or _exp > best[1]:
                best = (c, _exp)
        if best:
            _c, _e = best
            findings.append({
                "type": "best-momentum-quality",
                "finding": f"{_c['key']} · 20d expectancy {_e:+.2f}% · n={_c['n']} · {_c['confidence']}",
            })
    # Worst-expectancy momentum × runner
    if rep.momentum_x_runner:
        for c in rep.momentum_x_runner:
            if c["n"] < 20: continue
            _exp = (c["horizon_metrics"].get("20") or {}).get("expectancy_pct") or 0
            if _exp < -1:
                findings.append({
                    "type": "loss-making-momentum-runner",
                    "finding": f"{c['key']} · 20d expectancy {_exp:+.2f}% · n={c['n']} · investigate",
                })
                break
    return findings


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str) -> MomentumAttributionReport:
    """Read short_term_momentum_backtest samples · build attribution matrices."""
    rep = MomentumAttributionReport(
        market=market.lower(),
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _bt_p = (root / "reports" / "research"
             / f"short_term_momentum_backtest_{market.lower()}.json")
    if not _bt_p.exists():
        return rep
    try:
        _bt = json.loads(_bt_p.read_text(encoding="utf-8"))
    except Exception:
        return rep
    samples = _bt.get("top_winners", []) + _bt.get("worst_losers", [])
    # Also aggregate from per_verdict.n_samples where possible
    # (top/worst are subsamples · richer roll-ups need full sample list)
    if not samples: return rep
    # Best-effort · runner tag not in samples · put "?"
    for s in samples:
        s.setdefault("runner", "?")
    rep.n_samples = len(samples)
    rep.momentum_x_runner       = _rollup_by(root, market, samples, _dim_mom_runner)
    rep.momentum_x_cap          = _rollup_by(root, market, samples, _dim_mom_cap)
    rep.momentum_x_sector       = _rollup_by(root, market, samples, _dim_mom_sector)
    rep.momentum_x_investability = _rollup_by(root, market, samples, _dim_mom_investability)
    rep.momentum_x_market_regime = _rollup_by(root, market, samples, _dim_mom_market_regime)
    rep.momentum_x_sector_regime = _rollup_by(root, market, samples, _dim_mom_sector_regime)
    rep.top_findings = _top_findings(rep)
    return rep


def emit(root: Path, rep: MomentumAttributionReport) -> Path:
    p = (root / "reports" / "research"
         / f"momentum_attribution_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def summary_line(rep: MomentumAttributionReport) -> str:
    return (f"momentum_attribution · {rep.n_samples} samples · "
            f"{len(rep.momentum_x_runner)} runner-cells · "
            f"{len(rep.top_findings)} top-findings")
