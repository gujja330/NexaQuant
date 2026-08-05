"""Runner 3 · Daily 3-runner comparison report.

Produces reports/research/runner3/three_runner_comparison_{market}.json
+ .md so the operator can inspect R1 vs R2 vs R3 side-by-side on identical
metrics. Feeds the CEO Day-90 decision.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from .shadow_ledger import load_all, count_distinct_asofs
from .day30_gate import _compute_shadow_returns, _sharpe, _brier


def _r1_metrics(root: Path, market: str) -> dict:
    """Pull R1 (adaptive_rec_v2 · SEALED) metrics from ai_scorecard."""
    p = root / "reports" / "ai_scorecard.json"
    if not p.exists():
        return {"available": False, "reason": "ai_scorecard.json missing"}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {
            "available":    True,
            "sharpe":       d.get("runner1_sharpe") or d.get("sharpe"),
            "win_rate":     d.get("runner1_win_rate") or d.get("win_rate"),
            "max_dd":       d.get("runner1_max_dd") or d.get("max_dd"),
            "n_closed":     d.get("n_closed_trades") or d.get("runner1_closed"),
        }
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}


def _r2_metrics(root: Path, market: str) -> dict:
    """Pull R2 metrics from benchmark_runner2 or ai_scorecard."""
    for pth in [root / "reports" / "benchmark_runner2_india.json",
                    root / "reports" / "ai_scorecard.json"]:
        if not pth.exists(): continue
        try:
            d = json.loads(pth.read_text(encoding="utf-8"))
            return {
                "available":    True,
                "sharpe":       d.get("runner2_sharpe") or d.get("sharpe"),
                "win_rate":     d.get("runner2_win_rate") or d.get("win_rate"),
                "max_dd":       d.get("runner2_max_dd") or d.get("max_dd"),
                "n_positions":  d.get("runner2_positions") or d.get("n_positions"),
            }
        except Exception:
            continue
    return {"available": False, "reason": "no R2 metrics source found"}


def _r3_metrics(root: Path, market: str) -> dict:
    n_days = count_distinct_asofs(root, market)
    entries = load_all(root, market=market)
    if not entries:
        return {"available": False, "reason": "no shadow ledger entries yet",
                    "n_days": n_days, "n_positions": 0}
    returns = _compute_shadow_returns(root, market)
    outcomes = [1 if r > 0 else 0 for r in returns]
    probs = [float(e.get("calibrated_confidence") or 0.5)
                 for e in entries[:len(outcomes)]]
    win_rate = round(sum(outcomes) / len(outcomes) * 100.0, 1) if outcomes else None
    return {
        "available":    True,
        "n_days":       n_days,
        "n_positions":  len(entries),
        "n_closed":     len(returns),
        "sharpe":       _sharpe(returns),
        "brier":        _brier(probs, outcomes),
        "win_rate":     win_rate,
        "mean_return_pct": round(sum(returns) / len(returns) * 100.0, 2) if returns else None,
    }


def build(root: Path, market: str, asof: str | None = None) -> dict:
    asof = asof or date.today().isoformat()
    return {
        "engine":        "aegis.runner3.three_runner_comparison.v1",
        "asof":          asof, "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runners": {
            "runner1_sealed":   _r1_metrics(root, market),
            "runner2_canonical": _r2_metrics(root, market),
            "runner3_shadow":   _r3_metrics(root, market),
        },
        "note": "Runner 3 is SHADOW · not visible in Telegram · "
                    "promotion decision at Day 90 per RL-Runner3 plan.",
    }


def render_md(rep: dict) -> str:
    r1 = rep["runners"]["runner1_sealed"]
    r2 = rep["runners"]["runner2_canonical"]
    r3 = rep["runners"]["runner3_shadow"]
    def _cell(v):
        return "—" if v is None else str(v)
    lines = [f"# 3-Runner Comparison · {rep['market'].upper()} · {rep['asof']}",
                "",
                "| Metric | R1 (SEALED) | R2 (canonical) | R3 (shadow) |",
                "|---|---|---|---|",
                f"| Available | {_cell(r1.get('available'))} | {_cell(r2.get('available'))} | {_cell(r3.get('available'))} |",
                f"| Sharpe | {_cell(r1.get('sharpe'))} | {_cell(r2.get('sharpe'))} | {_cell(r3.get('sharpe'))} |",
                f"| Win rate % | {_cell(r1.get('win_rate'))} | {_cell(r2.get('win_rate'))} | {_cell(r3.get('win_rate'))} |",
                f"| Max DD | {_cell(r1.get('max_dd'))} | {_cell(r2.get('max_dd'))} | — |",
                f"| Brier score | — | — | {_cell(r3.get('brier'))} |",
                f"| n days | — | — | {_cell(r3.get('n_days'))} |",
                f"| n positions | {_cell(r1.get('n_closed'))} | {_cell(r2.get('n_positions'))} | {_cell(r3.get('n_positions'))} |",
                "",
                f"> {rep['note']}"]
    return "\n".join(lines) + "\n"


def emit(root: Path, market: str, rep: dict) -> tuple[Path, Path]:
    j = root / "reports" / "research" / "runner3" / f"three_runner_comparison_{market}.json"
    m = root / "reports" / "research" / "runner3" / f"three_runner_comparison_{market}.md"
    j.parent.mkdir(parents=True, exist_ok=True)
    j.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    m.write_text(render_md(rep), encoding="utf-8")
    return j, m
