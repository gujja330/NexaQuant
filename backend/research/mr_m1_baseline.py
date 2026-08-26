"""AEGIS · M-R · M1 baseline measurement (Sprint M research phase).

M1 · Baseline Measurement · reads locked canonical production inputs
(Opportunity Registry + aegis_history.xlsx EXIT rows) and reports
realized outcomes per runner, lifecycle, holding period, and market.

CEO handover 2026-08-26 · post-lock research phase. Measurement-only.
DOES NOT modify production. DOES NOT touch R1/R2. India + USA parallel
per feedback_dual_market_parallel rule.

Output:
  reports/research/mr_m1_baseline_{market}.json  (per-market metrics)
  reports/research/mr_m1_baseline_global.json     (India vs USA compare)

Wilson-95 CIs on win-rate. n<20 = OBSERVATION_ONLY, n<100 = INSUFFICIENT_EVIDENCE,
n>=100 = PRODUCTION_CANDIDATE (per Statistical Discipline).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, SCHEMA_FINGERPRINT, \
    ALLOWED_WRITE_ROOT


M1_SCHEMA_FINGERPRINT = "aegis.mr_m1_baseline.v0.1.20260826"


# ─────────────────────────────────────────────────────────────────
# Statistical thresholds (per aegis_sprint_m_research_phase memory)
# ─────────────────────────────────────────────────────────────────
def _statistical_verdict(n: int) -> str:
    if n < 20:   return "OBSERVATION_ONLY"
    if n < 100:  return "INSUFFICIENT_EVIDENCE"
    return "PRODUCTION_CANDIDATE"


def _wilson_95(k: int, n: int) -> tuple:
    """Wilson-95 CI for k successes in n trials · returns (low, high) in %.
    Returns (None, None) when n == 0."""
    if n <= 0: return (None, None)
    z = 1.96
    p = k / n
    denom = 1 + z*z/n
    centre = p + z*z/(2*n)
    margin = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n)
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return (round(lo*100, 2), round(hi*100, 2))


# ─────────────────────────────────────────────────────────────────
# Locked canonical readers (read-only)
# ─────────────────────────────────────────────────────────────────
def _load_closed_from_registry(root: Path, market: str) -> list:
    """Read CLOSED opportunities from Registry · single canonical source."""
    from backend.research import opportunity_registry as _oreg
    reg = _oreg.load_all(root)
    closed = []
    for opps in reg.values():
        for o in opps:
            if o.market.lower() != market.lower(): continue
            if o.status != "CLOSED": continue
            closed.append(o)
    return closed


def _parquet_close(root: Path, ticker: str, market: str,
                   iso_date: str) -> Optional[float]:
    try:
        import pandas as pd
        clean = ticker.upper().replace(".NS","").replace(".BO","")
        base = "usa/data/raw/us" if market.lower()=="usa" else "data/raw/india"
        p = root / base / f"{clean}_D1.parquet"
        if not p.exists(): return None
        d = pd.read_parquet(p)
        col = "close" if "close" in d.columns else "Close"
        d.index = pd.to_datetime(d.index).strftime("%Y-%m-%d")
        if iso_date in d.index: return float(d.loc[iso_date, col])
        earlier = [dt for dt in d.index if dt <= iso_date]
        return float(d.loc[earlier[-1], col]) if earlier else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# M1 metrics
# ─────────────────────────────────────────────────────────────────
@dataclass
class CohortMetrics:
    label:                 str
    n:                     int
    n_win:                 int
    n_loss:                int
    n_flat:                int
    win_rate_pct:          Optional[float]
    win_rate_ci_low_pct:   Optional[float]
    win_rate_ci_high_pct:  Optional[float]
    avg_return_pct:        Optional[float]
    median_return_pct:     Optional[float]
    best_return_pct:       Optional[float]
    worst_return_pct:      Optional[float]
    avg_hold_days:         Optional[float]
    profit_factor:         Optional[float]
    statistical_verdict:   str


def _metrics(label: str, trades: list) -> CohortMetrics:
    n = len(trades)
    if n == 0:
        return CohortMetrics(label=label, n=0, n_win=0, n_loss=0, n_flat=0,
            win_rate_pct=None, win_rate_ci_low_pct=None,
            win_rate_ci_high_pct=None, avg_return_pct=None,
            median_return_pct=None, best_return_pct=None,
            worst_return_pct=None, avg_hold_days=None, profit_factor=None,
            statistical_verdict=_statistical_verdict(0))
    pnls   = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
    days   = [t["hold_days"] for t in trades if t.get("hold_days") is not None]
    wins   = [p for p in pnls if p > 0.5]
    losses = [p for p in pnls if p < -0.5]
    flats  = [p for p in pnls if -0.5 <= p <= 0.5]
    n_pnl = len(pnls)
    if n_pnl == 0:
        return CohortMetrics(label=label, n=n, n_win=0, n_loss=0, n_flat=0,
            win_rate_pct=None, win_rate_ci_low_pct=None,
            win_rate_ci_high_pct=None, avg_return_pct=None,
            median_return_pct=None, best_return_pct=None,
            worst_return_pct=None,
            avg_hold_days=(round(sum(days)/len(days),1) if days else None),
            profit_factor=None,
            statistical_verdict=_statistical_verdict(n))
    wr = round(len(wins)/n_pnl*100, 2)
    lo, hi = _wilson_95(len(wins), n_pnl)
    avg = round(sum(pnls)/n_pnl, 3)
    srt = sorted(pnls)
    med = round(srt[n_pnl//2], 3)
    win_sum  = sum(wins)
    loss_sum = abs(sum(losses))
    pf = round(win_sum / loss_sum, 3) if loss_sum > 0 else None
    return CohortMetrics(
        label=label, n=n, n_win=len(wins), n_loss=len(losses), n_flat=len(flats),
        win_rate_pct=wr, win_rate_ci_low_pct=lo, win_rate_ci_high_pct=hi,
        avg_return_pct=avg, median_return_pct=med,
        best_return_pct=round(max(pnls),3), worst_return_pct=round(min(pnls),3),
        avg_hold_days=(round(sum(days)/len(days),1) if days else None),
        profit_factor=pf,
        statistical_verdict=_statistical_verdict(n),
    )


def compute(root: Path, market: str) -> dict:
    """Build the M1 baseline report for one market. Pure read · never writes."""
    from datetime import date as _d
    closed = _load_closed_from_registry(root, market)
    trades = []
    for o in closed:
        cd = str(o.created_date or "")[:10]
        xd = str(o.closed_date or "")[:10]
        if not (cd and xd): continue
        ep = _parquet_close(root, o.ticker, market, cd)
        xp = _parquet_close(root, o.ticker, market, xd)
        if not (isinstance(ep,(int,float)) and ep > 0
                and isinstance(xp,(int,float)) and xp > 0):
            continue
        try:
            hd = (_d.fromisoformat(xd) - _d.fromisoformat(cd)).days
        except Exception:
            hd = None
        trades.append({
            "ticker": o.ticker.upper().replace(".NS","").replace(".BO",""),
            "runner": o.runner.upper().replace("_NEW",""),
            "entry_date": cd,
            "exit_date":  xd,
            "entry_price": round(ep,2),
            "exit_price":  round(xp,2),
            "pnl_pct":    round((xp - ep) / ep * 100, 3),
            "hold_days":  hd,
            "same_day":   cd == xd,
        })
    trades_no_artifact = [t for t in trades if not t["same_day"]]
    by_runner = defaultdict(list)
    for t in trades_no_artifact:
        by_runner[t["runner"]].append(t)
    cohorts = {}
    cohorts["ALL"]  = asdict(_metrics("ALL", trades_no_artifact))
    for run in sorted(by_runner):
        cohorts[run] = asdict(_metrics(run, by_runner[run]))
    return {
        "engine":                  "aegis.mr_m1_baseline.v0.1",
        "experiment_id":           EXPERIMENT_ID,
        "schema_fingerprint":      M1_SCHEMA_FINGERPRINT,
        "generated_utc":           datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":                  market.lower(),
        "n_total_closed":          len(trades),
        "n_same_day_artifact":     sum(1 for t in trades if t["same_day"]),
        "n_measured":              len(trades_no_artifact),
        "cohorts":                 cohorts,
    }


def emit(root: Path, market: str, report: dict) -> Path:
    out = root / ALLOWED_WRITE_ROOT / f"mr_m1_baseline_{market.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return out


def emit_global(root: Path, per_market_reports: dict) -> Path:
    """Emit the global India-vs-USA comparison artifact (mandatory per
    feedback_dual_market_parallel · every Phase 3 sprint ships both markets
    plus reports/global/<engine>_comparison.json)."""
    out = root / "reports" / "global" / "mr_m1_baseline_comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    comp = {
        "engine":             "aegis.mr_m1_baseline.v0.1",
        "experiment_id":      EXPERIMENT_ID,
        "generated_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets":            list(per_market_reports.keys()),
        "per_market_summary": {},
        "verdict_by_market":  {},
    }
    for mkt, rep in per_market_reports.items():
        all_c = rep["cohorts"].get("ALL", {})
        comp["per_market_summary"][mkt] = {
            "n_measured":          all_c.get("n"),
            "win_rate_pct":        all_c.get("win_rate_pct"),
            "win_rate_ci":         (all_c.get("win_rate_ci_low_pct"),
                                    all_c.get("win_rate_ci_high_pct")),
            "avg_return_pct":      all_c.get("avg_return_pct"),
            "profit_factor":       all_c.get("profit_factor"),
            "statistical_verdict": all_c.get("statistical_verdict"),
        }
        comp["verdict_by_market"][mkt] = all_c.get("statistical_verdict")
    out.write_text(json.dumps(comp, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def render_console(reports: dict):
    """Human-readable console dump · exactly what CEO asked for."""
    print("=" * 72)
    print("M1 · BASELINE MEASUREMENT · Sprint M Research Runner (M-R.v0.1)")
    print("=" * 72)
    for mkt, rep in reports.items():
        print(f"\n[{mkt.upper()}] · n_measured={rep['n_measured']} · "
              f"same-day-artifacts excluded={rep['n_same_day_artifact']}")
        for label, c in rep["cohorts"].items():
            if c["n"] == 0:
                print(f"  · {label:6s} · n=0"); continue
            print(f"  · {label:6s} · n={c['n']:3d} · "
                  f"W/L/F={c['n_win']}/{c['n_loss']}/{c['n_flat']} · "
                  f"WR={c['win_rate_pct']}% [{c['win_rate_ci_low_pct']}, {c['win_rate_ci_high_pct']}] · "
                  f"avg={c['avg_return_pct']}% · med={c['median_return_pct']}% · "
                  f"hold={c['avg_hold_days']}d · PF={c['profit_factor']} · "
                  f"[{c['statistical_verdict']}]")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    _root = Path(args.root).resolve()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    reports = {}
    for m in markets:
        rep = compute(_root, m)
        p   = emit(_root, m, rep)
        reports[m] = rep
        print(f"[mr_m1:{m}] emitted · {p.relative_to(_root)}")
    if len(reports) > 1:
        g = emit_global(_root, reports)
        print(f"[mr_m1:global] comparison · {g.relative_to(_root)}")
    render_console(reports)
