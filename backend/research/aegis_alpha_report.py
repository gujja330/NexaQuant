# backend/research/aegis_alpha_report.py
"""AEGIS · Sprint M · Part 22 · Consolidated Alpha Report.

CEO directive 2026-08-25: "After implementation/research, produce one
consolidated report" with 25 metrics + top-10 Research Tickets.

Aggregates every engine already running into ONE artifact:

  Winner side:
    win_attribution         · patterns + sector + cap rollups
    win_discovery           · capture rate + missed winners
    new_opportunity_outcomes · forward P&L per cohort

  Loss side:
    loss_attribution_v2     · 6-cat loss classifier
    loss_avoidance_guard    · current-loser verdicts
    loss_guard_backtest     · historical hit rate

  Ranking / segmentation:
    attribution_matrix      · multi-dim rollups
    ranking_effectiveness   · per-rank forward returns

  Discovery / discipline:
    emerging_leader_engine  · small-cap candidates
    missed_opportunity_v2   · successful reject vs missed winner
    research_ticket         · top 10 by impact
    lifecycle_stabilization · 10 audits

  Data health:
    opportunity_engine      · data_state (VALID / STALE / etc.)
    price_integrity_guard   · price alignment

Outputs:
  reports/research/aegis_alpha_report_{market}.json
  reports/research/aegis_alpha_report_{market}.md   (CEO-readable)

Locks preserved · every read pure · zero writes to Excel or R1/R2.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_FINGERPRINT = "aegis.alpha_report.v1.20260825"

# CEO's exact 25 metrics from Part 22
METRIC_KEYS = [
    "top_winning_patterns", "top_losing_patterns",
    "best_sectors", "worst_sectors",
    "best_cap_segments", "worst_cap_segments",
    "best_r1_combinations", "best_r2_combinations",
    "best_sector_cap_combos", "best_regime_combos",
    "small_cap_emerging_leaders", "worst_recurring_losses",
    "stop_loss_findings", "exit_quality_findings",
    "timing_failures", "ranking_effectiveness",
    "new_opportunity_refresh_rate", "stale_recommendation_rate",
    "re_entry_rate", "profit_factor",
    "expectancy", "max_drawdown",
    "win_rate", "average_winner", "average_loser",
]


@dataclass
class AlphaReport:
    market: str
    asof: str
    generated_utc: str
    engine: str = SCHEMA_FINGERPRINT
    metrics: dict = field(default_factory=dict)
    top_research_tickets: list = field(default_factory=list)
    data_state: str = "UNKNOWN"
    lifecycle_verdict: str = "UNKNOWN"
    capture_rate_pct: float = 0.0
    successful_reject_rate_pct: float = 0.0


# ─────────────────────────────────────────────────────────────────
# Helpers · load JSON with graceful fallback
# ─────────────────────────────────────────────────────────────────
def _load(root: Path, subpath: str) -> dict:
    p = root / subpath
    if not p.exists(): return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _first_or(items: list, default=None):
    return items[0] if items else default


def _last_or(items: list, default=None):
    return items[-1] if items else default


# ─────────────────────────────────────────────────────────────────
# Metric extractors (one per CEO Part 22 key)
# ─────────────────────────────────────────────────────────────────
def _top_winning_patterns(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/win_patterns_{mkt}.json")
    cnts = d.get("pattern_counts", {})
    out = [{"pattern": k, "n": v} for k, v in
           sorted(cnts.items(), key=lambda x: -x[1])[:5]]
    return out


def _top_losing_patterns(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    cnts = d.get("category_counts", {})
    out = [{"category": k, "n": v} for k, v in
           sorted(cnts.items(), key=lambda x: -x[1])[:5]
           if k != "WINNER"]
    return out


def _sector_rollups(root: Path, mkt: str, kind: str) -> list:
    d = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    rollups = d.get("sector_rollup", [])
    if kind == "best":
        rollups = sorted(rollups, key=lambda x: -(x.get("total_pnl_pct", 0)))
    else:
        rollups = sorted(rollups, key=lambda x: (x.get("total_pnl_pct", 0)))
    return rollups[:3]


def _cap_rollups(root: Path, mkt: str, kind: str) -> list:
    d = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    rollups = d.get("cap_size_rollup", [])
    if kind == "best":
        rollups = sorted(rollups, key=lambda x: -(x.get("profit_factor", 0)))
    else:
        rollups = sorted(rollups, key=lambda x: (x.get("profit_factor", 0)))
    return rollups[:3]


def _runner_combos(root: Path, mkt: str, runner: str) -> list:
    d = _load(root, f"reports/research/attribution_matrix_{mkt}.json")
    cells = d.get("cap_sector_runner_matrix", [])
    filt = [c for c in cells if runner in c.get("key", "")]
    filt.sort(key=lambda c: -c.get("metrics", {}).get("expectancy_pct", 0))
    return filt[:5]


def _sector_cap_combos(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/attribution_matrix_{mkt}.json")
    cells = d.get("cap_sector_matrix", [])
    cells.sort(key=lambda c: -c.get("metrics", {}).get("expectancy_pct", 0))
    return cells[:5]


def _regime_combos(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/attribution_matrix_{mkt}.json")
    cells = d.get("regime_sector_runner_matrix", [])
    cells.sort(key=lambda c: -c.get("metrics", {}).get("expectancy_pct", 0))
    return cells[:5]


def _emerging_leaders(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/emerging_leader_{mkt}.json")
    return [{"ticker": c.get("ticker"),
             "sector": c.get("sector"),
             "n_positive": c.get("n_positive"),
             "overall_score": c.get("overall_score")}
            for c in d.get("emerging", [])[:10]]


def _worst_recurring_losses(root: Path, mkt: str) -> list:
    d = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    exits = d.get("exits", [])
    losses = [e for e in exits if not e.get("is_win")]
    losses.sort(key=lambda e: e.get("pnl_pct", 0))
    return [{"ticker": e.get("ticker"), "pnl_pct": e.get("pnl_pct"),
             "category": e.get("category"), "days_held": e.get("days_held")}
            for e in losses[:10]]


def _stop_loss_findings(root: Path, mkt: str) -> dict:
    d = _load(root, f"reports/research/loss_guard_backtest_{mkt}.json")
    return {
        "n_losses_analyzed": d.get("n_losses_analyzed", 0),
        "n_losses_caught": d.get("n_losses_caught", 0),
        "hit_rate_pct": d.get("hit_rate_pct", 0.0),
        "total_loss_avoided_pct": d.get("total_loss_avoided_pct", 0.0),
    }


def _exit_quality(root: Path, mkt: str) -> dict:
    d = _load(root, f"reports/research/new_opportunity_outcomes_{mkt}.json")
    metrics_by_cohort = {c["cohort"]: c for c in d.get("cohort_metrics", [])}
    return {
        cohort: {k: v for k, v in m.items()
                 if k in ("n_observations", "win_rate_20d",
                          "expectancy_20d_pct", "avg_max_dd_pct")}
        for cohort, m in metrics_by_cohort.items()
    }


def _timing_failures(root: Path, mkt: str) -> list:
    """Timing failures = quick-in quick-out losers · MACRO_SHOCK category."""
    d = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    exits = d.get("exits", [])
    shocks = [e for e in exits if e.get("category") == "MACRO_SHOCK"]
    return [{"ticker": e.get("ticker"), "days_held": e.get("days_held"),
             "pnl_pct": e.get("pnl_pct")}
            for e in shocks[:5]]


def _ranking_effectiveness(root: Path, mkt: str) -> dict:
    d = _load(root, f"reports/research/ranking_effectiveness_{mkt}.json")
    return {
        "monotonicity": d.get("monotonicity_test", {}).get("status", "?"),
        "best_rank": d.get("monotonicity_test", {}).get("best_rank_by_20d"),
        "n_observations": d.get("n_positions", 0),
        "finding": d.get("finding", ""),
    }


def _refresh_rate(root: Path, mkt: str) -> dict:
    d = _load(root, f"reports/context/opportunity_engine_{mkt}.json")
    return {
        "freshness_ratio_pct": d.get("freshness_ratio", 0.0),
        "n_new_today": d.get("n_new", 0),
        "n_reentry_today": d.get("n_reentry", 0),
        "n_existing_today": d.get("n_existing", 0),
        "data_state": d.get("data_state", "?"),
    }


def _stale_recommendation_rate(root: Path, mkt: str) -> float:
    d = _load(root, f"reports/context/opportunity_engine_{mkt}.json")
    total = d.get("n_total_today", 0)
    existing = d.get("n_existing", 0)
    if total == 0: return 0.0
    return round(existing / total * 100, 1)


def _reentry_rate(root: Path, mkt: str) -> float:
    d = _load(root, f"reports/context/opportunity_engine_{mkt}.json")
    total = d.get("n_total_today", 0)
    reentry = d.get("n_reentry", 0)
    if total == 0: return 0.0
    return round(reentry / total * 100, 1)


def _overall_metrics(root: Path, mkt: str) -> dict:
    d_loss = _load(root, f"reports/research/loss_patterns_{mkt}.json")
    d_win = _load(root, f"reports/research/win_patterns_{mkt}.json")
    n_exits = d_loss.get("n_positions", 0)
    n_wins = d_win.get("n_wins", 0)
    n_losses = n_exits - n_wins
    win_rate = round(n_wins / max(n_exits, 1) * 100, 1)
    all_pnl_wins = sum(w.get("pnl_pct", 0)
                       for w in d_win.get("winners", []))
    all_pnl_losses = sum(e.get("pnl_pct", 0)
                         for e in d_loss.get("exits", [])
                         if not e.get("is_win"))
    avg_win = round(all_pnl_wins / max(n_wins, 1), 2)
    avg_loss = round(all_pnl_losses / max(n_losses, 1), 2)
    pf = round(abs(avg_win / avg_loss), 2) if avg_loss else 0.0
    expectancy = round((win_rate / 100) * avg_win
                        + (1 - win_rate / 100) * avg_loss, 2)
    max_dd = round(min([e.get("pnl_pct", 0)
                       for e in d_loss.get("exits", [])],
                      default=0), 2)
    return {
        "n_closed": n_exits,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "expectancy_pct": expectancy,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "max_drawdown_pct": max_dd,
    }


def _capture_rate(root: Path, mkt: str) -> float:
    d = _load(root, f"reports/research/missed_winners_{mkt}.json")
    return d.get("capture_rate_pct", 0.0)


def _successful_reject_rate(root: Path, mkt: str) -> float:
    d = _load(root, f"reports/research/rejection_analysis_{mkt}.json")
    return d.get("successful_reject_rate_pct", 0.0)


def _data_state(root: Path, mkt: str) -> str:
    d = _load(root, f"reports/context/opportunity_engine_{mkt}.json")
    return d.get("data_state", "UNKNOWN")


def _lifecycle_verdict(root: Path, mkt: str) -> str:
    d = _load(root, f"reports/context/lifecycle_stabilization_{mkt}.json")
    return d.get("verdict", "UNKNOWN")


def _top_tickets(root: Path) -> list:
    try:
        from backend.research.research_ticket import load_top_tickets
        return load_top_tickets(root, n=10)
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────
# PUBLIC · compute + emit + markdown render
# ─────────────────────────────────────────────────────────────────
def compute(root: Path, market: str) -> AlphaReport:
    mkt = market.lower()
    rep = AlphaReport(
        market=mkt,
        asof=date.today().isoformat(),
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    overall = _overall_metrics(root, mkt)
    rep.metrics = {
        # 1
        "top_winning_patterns":       _top_winning_patterns(root, mkt),
        # 2
        "top_losing_patterns":        _top_losing_patterns(root, mkt),
        # 3
        "best_sectors":               _sector_rollups(root, mkt, "best"),
        # 4
        "worst_sectors":              _sector_rollups(root, mkt, "worst"),
        # 5
        "best_cap_segments":          _cap_rollups(root, mkt, "best"),
        # 6
        "worst_cap_segments":         _cap_rollups(root, mkt, "worst"),
        # 7 · R1 combos
        "best_r1_combinations":       _runner_combos(root, mkt, "R1"),
        # 8 · R2 combos
        "best_r2_combinations":       _runner_combos(root, mkt, "R2"),
        # 9
        "best_sector_cap_combos":     _sector_cap_combos(root, mkt),
        # 10
        "best_regime_combos":         _regime_combos(root, mkt),
        # 11
        "small_cap_emerging_leaders": _emerging_leaders(root, mkt),
        # 12
        "worst_recurring_losses":     _worst_recurring_losses(root, mkt),
        # 13
        "stop_loss_findings":         _stop_loss_findings(root, mkt),
        # 14
        "exit_quality_findings":      _exit_quality(root, mkt),
        # 15
        "timing_failures":            _timing_failures(root, mkt),
        # 16
        "ranking_effectiveness":      _ranking_effectiveness(root, mkt),
        # 17
        "new_opportunity_refresh_rate": _refresh_rate(root, mkt),
        # 18
        "stale_recommendation_rate":  _stale_recommendation_rate(root, mkt),
        # 19
        "re_entry_rate":              _reentry_rate(root, mkt),
        # 20-25 · overall
        "profit_factor":              overall["profit_factor"],
        "expectancy":                 overall["expectancy_pct"],
        "max_drawdown":               overall["max_drawdown_pct"],
        "win_rate":                   overall["win_rate_pct"],
        "average_winner":             overall["avg_win_pct"],
        "average_loser":              overall["avg_loss_pct"],
        # extras · headline flags
        "n_closed":                   overall["n_closed"],
        "capture_rate_pct":           _capture_rate(root, mkt),
        "successful_reject_rate_pct": _successful_reject_rate(root, mkt),
    }
    rep.top_research_tickets = _top_tickets(root)
    rep.data_state = _data_state(root, mkt)
    rep.lifecycle_verdict = _lifecycle_verdict(root, mkt)
    rep.capture_rate_pct = rep.metrics["capture_rate_pct"]
    rep.successful_reject_rate_pct = rep.metrics["successful_reject_rate_pct"]
    return rep


def emit(root: Path, rep: AlphaReport) -> Path:
    p = (root / "reports" / "research"
         / f"aegis_alpha_report_{rep.market}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(rep), indent=2, default=str,
                            ensure_ascii=False), encoding="utf-8")
    return p


def render_markdown(rep: AlphaReport) -> str:
    m = rep.metrics
    lines = [
        f"# AEGIS Alpha Report · {rep.market.upper()} · asof {rep.asof}",
        "",
        f"**Data state**: {rep.data_state} · **Lifecycle**: {rep.lifecycle_verdict}",
        f"**Capture rate** (universe winners we caught): {rep.capture_rate_pct}%",
        f"**Successful-reject rate**: {rep.successful_reject_rate_pct}%",
        "",
        "## Headline metrics (25 CEO)",
        f"- **Win rate**: {m['win_rate']}%",
        f"- **Profit factor**: {m['profit_factor']}",
        f"- **Expectancy**: {m['expectancy']}%",
        f"- **Avg winner**: {m['average_winner']}%",
        f"- **Avg loser**: {m['average_loser']}%",
        f"- **Max drawdown (worst single exit)**: {m['max_drawdown']}%",
        f"- **N closed positions**: {m['n_closed']}",
        "",
        "## Refresh + selectivity",
        f"- Refresh rate today: NEW={m['new_opportunity_refresh_rate']['n_new_today']} · "
        f"RE-ENTRY={m['new_opportunity_refresh_rate']['n_reentry_today']} · "
        f"EXISTING={m['new_opportunity_refresh_rate']['n_existing_today']} · "
        f"freshness={m['new_opportunity_refresh_rate']['freshness_ratio_pct']}%",
        f"- Stale-recommendation rate: {m['stale_recommendation_rate']}%",
        f"- Re-entry rate: {m['re_entry_rate']}%",
        "",
        "## Top winning patterns",
    ]
    for p in m["top_winning_patterns"]:
        lines.append(f"- {p.get('pattern')} · n={p.get('n')}")
    lines.append("")
    lines.append("## Top losing patterns")
    for p in m["top_losing_patterns"]:
        lines.append(f"- {p.get('category')} · n={p.get('n')}")
    lines.append("")
    lines.append("## Sectors (best → worst)")
    for s in m["best_sectors"]:
        lines.append(f"- BEST · {s.get('sector')} · "
                     f"{s.get('n_positions')}pos · P&L {s.get('total_pnl_pct')}%")
    for s in m["worst_sectors"]:
        lines.append(f"- WORST · {s.get('sector')} · "
                     f"{s.get('n_positions')}pos · P&L {s.get('total_pnl_pct')}%")
    lines.append("")
    lines.append("## Cap segments (best → worst)")
    for c in m["best_cap_segments"]:
        lines.append(f"- BEST · {c.get('cap_size')} · PF {c.get('profit_factor')} · n={c.get('n_positions')}")
    for c in m["worst_cap_segments"]:
        lines.append(f"- WORST · {c.get('cap_size')} · PF {c.get('profit_factor')} · n={c.get('n_positions')}")
    lines.append("")
    lines.append("## Ranking effectiveness")
    _r = m["ranking_effectiveness"]
    lines.append(f"- Monotonicity: {_r.get('monotonicity')} · "
                 f"best rank {_r.get('best_rank','?')} · {_r.get('finding','')}")
    lines.append("")
    lines.append("## Small-cap emerging leaders")
    if not m["small_cap_emerging_leaders"]:
        lines.append("- (none surfaced today)")
    for e in m["small_cap_emerging_leaders"]:
        lines.append(f"- {e.get('ticker')} · {e.get('sector')} · "
                     f"score {e.get('overall_score')} · "
                     f"{e.get('n_positive')}/6 positive")
    lines.append("")
    lines.append("## Worst recurring losses")
    for w in m["worst_recurring_losses"][:5]:
        lines.append(f"- {w.get('ticker')} · {w.get('pnl_pct')}% · "
                     f"{w.get('category')} · {w.get('days_held')}d held")
    lines.append("")
    lines.append("## Stop-loss backtest")
    _s = m["stop_loss_findings"]
    lines.append(f"- Analyzed {_s.get('n_losses_analyzed')} losses · "
                 f"caught {_s.get('n_losses_caught')} · "
                 f"hit rate {_s.get('hit_rate_pct')}% · "
                 f"saved {_s.get('total_loss_avoided_pct')}%")
    lines.append("")
    lines.append("## Top-10 Research Tickets (ranked by impact)")
    if not rep.top_research_tickets:
        lines.append("- (no tickets filed · attribution below N-threshold)")
    for t in rep.top_research_tickets:
        lines.append(f"- {t.get('id')} · impact {t.get('impact_score')} · "
                     f"{t.get('status')} · {t.get('market')}")
    return "\n".join(lines)


def emit_markdown(root: Path, rep: AlphaReport) -> Path:
    md = render_markdown(rep)
    p = (root / "reports" / "research"
         / f"aegis_alpha_report_{rep.market}.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md, encoding="utf-8")
    return p


def summary_line(rep: AlphaReport) -> str:
    m = rep.metrics
    return (f"alpha_report · state={rep.data_state} · "
            f"n_closed={m['n_closed']} · win_rate={m['win_rate']}% · "
            f"PF={m['profit_factor']} · exp={m['expectancy']}% · "
            f"capture={rep.capture_rate_pct}% · "
            f"reject={rep.successful_reject_rate_pct}%")
