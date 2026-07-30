"""Research Platform · unified SSoT emitter.

Compiles the entire Research Platform state into ONE canonical file
that Telegram / dashboard / APIs all read:

    reports/research/research_platform.json

Structure:
{
  engine, schema_fingerprint, run_utc,
  program: {
    experiment_start, day_of_program, window_days_minimum, window_days_target,
    decision_checkpoints, canonical, canonical_reason,
  },
  tickets: [{ticket_id, title, lifecycle_state, days_live, canonical_candidate}, ...],
  layers: {
    live_evaluation: {
      india_delivery: {runner1, runner2, leader, leader_edge_pct, overlaps},
      usa_delivery:   {runner2 only},
      india_intraday: {runner1, runner2, leader, leader_edge_pct, mode},
    },
    historical: {
      india: {years[], overall_winner},
      usa:   {years[], overall_winner},
    },
    correlation_lab: {intraday_vs_delivery, top_refinement_levers},
    explainability: {narrative, biggest_edge, biggest_miss, sector_attribution},
    disagreements: {n_total, buckets, latest_verdict},
  },
  status: {
    canonical:  "UNDECIDED",
    leader:     "RUNNER_2" | "RUNNER_1" | "TIE",
    confidence: "growing" | "stable" | "flipping" | "insufficient",
  },
}
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from .metrics import compute_runner_metrics, RunnerMetrics
from .disagreement_store import compute_overlap_metrics
from .ticket import load_all_tickets, bootstrap_starter_tickets

SCHEMA_FINGERPRINT = "aegis.research.platform.v1.20260731"
ENGINE_ID = "aegis.research.platform.v1"

WINDOW_DAYS_MIN = 60
WINDOW_DAYS_TARGET = 90
DECISION_CHECKPOINTS = {
    "day_30": "informational_only",
    "day_60": "first_decision_checkpoint",
    "day_90": "final_production_decision",
}
LEADER_EDGE_THRESHOLD_PP = 2.0


def _leader(r1: dict | None, r2: dict | None,
              threshold_pp: float = LEADER_EDGE_THRESHOLD_PP) -> tuple[str, float]:
    r1_ret = (r1 or {}).get("total_return_pct")
    r2_ret = (r2 or {}).get("total_return_pct")
    if r1_ret is None and r2_ret is None:
        return "NO_DATA", 0.0
    if r1_ret is None:
        return "RUNNER_2_ONLY", r2_ret or 0.0
    if r2_ret is None:
        return "RUNNER_1_ONLY", r1_ret or 0.0
    edge = r2_ret - r1_ret
    if abs(edge) < threshold_pp:
        return "TIE", round(edge, 3)
    if edge > 0:
        return "RUNNER_2", round(edge, 3)
    return "RUNNER_1", round(edge, 3)


def _read_json_safe(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_research_platform(root: Path,
                                experiment_start: str | None = "2026-07-30") -> dict:
    """Compile the full Research Platform SSoT and write to
    reports/research/research_platform.json."""
    now = datetime.now(timezone.utc)
    day_of_program = 0
    if experiment_start:
        try:
            start_dt = date.fromisoformat(experiment_start)
            day_of_program = (date.today() - start_dt).days + 1
        except ValueError:
            pass

    # ── Overlap / agreement / disagreement (live) ──
    overlap = compute_overlap_metrics(root)

    # ── Delivery layer ──
    r1_india = compute_runner_metrics(root, "runner1", "india", "delivery",
                                            experiment_start=experiment_start)
    r2_india = compute_runner_metrics(root, "runner2", "india", "delivery",
                                            experiment_start=experiment_start)
    r1_india.agreement_pct = overlap.get("agreement_pct")
    r1_india.disagreement_pct = overlap.get("disagreement_pct")
    r1_india.buy_overlap_pct = overlap.get("buy_overlap_pct")
    r2_india.agreement_pct = overlap.get("agreement_pct")
    r2_india.disagreement_pct = overlap.get("disagreement_pct")
    r2_india.buy_overlap_pct = overlap.get("buy_overlap_pct")
    india_leader, india_edge = _leader(asdict(r1_india), asdict(r2_india))

    # USA delivery: Runner 2 only (Runner 1 doesn't cover USA)
    r2_usa = None
    usa_r2_pos = root / "usa" / "reports" / "position_store" / "usa" / "positions.json"
    if usa_r2_pos.exists():
        r2_usa_m = RunnerMetrics(runner="runner2", market="usa", mode="delivery")
        try:
            payload = json.loads(usa_r2_pos.read_text(encoding="utf-8"))
            positions = payload.get("positions") or {}
            r2_usa_m.n_positions = len(positions)
            r2_usa_m.n_open = sum(1 for p in positions.values() if p.get("is_active"))
            r2_usa_m.n_closed = r2_usa_m.n_positions - r2_usa_m.n_open
            rets = [(p.get("last_seen_price", 0) / (p.get("first_seen_price") or 1) - 1) * 100
                    for p in positions.values() if p.get("first_seen_price")]
            if rets:
                winners = [r for r in rets if r > 0]
                r2_usa_m.n_winners = len(winners)
                r2_usa_m.n_losers = len(rets) - len(winners)
                r2_usa_m.win_rate = round(len(winners) / len(rets), 4)
                r2_usa_m.total_return_pct = round(sum(rets) / len(rets), 3)
                r2_usa_m.median_return_pct = round(sorted(rets)[len(rets) // 2], 3)
                r2_usa_m.mtd_return_pct = r2_usa_m.total_return_pct
        except Exception:
            pass
        r2_usa = asdict(r2_usa_m)

    # ── Intraday layer (daily-proxy + hourly if present) ──
    r1_it = compute_runner_metrics(root, "runner1_intraday", "india",
                                        mode="intraday_shadow",
                                        experiment_start=experiment_start)
    r2_it = compute_runner_metrics(root, "runner2_intraday", "india",
                                        mode="intraday_shadow",
                                        experiment_start=experiment_start)
    it_leader, it_edge = _leader(asdict(r1_it), asdict(r2_it))

    r1_ith = compute_runner_metrics(root, "runner1_intraday_h1", "india",
                                          mode="intraday_shadow_hourly",
                                          experiment_start=experiment_start)
    r2_ith = compute_runner_metrics(root, "runner2_intraday_h1", "india",
                                          mode="intraday_shadow_hourly",
                                          experiment_start=experiment_start)

    intraday_india = {
        "mode":                "shadow · measurement only · no user-facing recs · no orders",
        "daily_proxy": {
            "runner1":            asdict(r1_it),
            "runner2":            asdict(r2_it),
            "leader":             it_leader,
            "leader_edge_pct":    it_edge,
        },
        "hourly": {
            "runner1":            asdict(r1_ith),
            "runner2":            asdict(r2_ith),
            "note":               ("Real intraday from yfinance hourly bars · "
                                     "populated when data cache has today's session"),
        },
    }

    # Attach historical intraday-signal report if present
    it_hist_path = root / "reports" / "research" / "intraday_shadow_backtest.json"
    it_hist = _read_json_safe(it_hist_path)
    if it_hist:
        intraday_india["historical_correlation"] = {
            "verdict":         it_hist.get("overall_verdict"),
            "recommendation":  it_hist.get("ceo_recommendation"),
            "n_trades":        it_hist.get("n_trades_evaluated"),
        }

    # ── Historical per-year layers ──
    hist_india = _read_json_safe(root / "reports" / "research" / "historical_per_year_india.json")
    hist_usa = _read_json_safe(root / "reports" / "research" / "historical_per_year_usa.json")
    reduced = _read_json_safe(root / "reports" / "research" / "backtest_2y.json")

    # ── Correlation lab ──
    corr = _read_json_safe(root / "reports" / "research" / "intraday_delivery_correlation.json")
    correlation_summary = None
    if corr:
        correlation_summary = {
            "pearson":                    corr.get("pearson_intraday_vs_swing"),
            "spearman":                   corr.get("spearman_intraday_vs_swing"),
            "interpretation":             corr.get("interpretation"),
            "best_filter":                corr.get("best_filter"),
            "recommendation":             corr.get("hybrid_strategy_recommendation"),
            "top_refinement_levers":      corr.get("top_refinement_levers", [])[:5],
            "n_slice_dims": {
                "sector":       len(corr.get("by_sector", [])),
                "industry":     len(corr.get("by_industry", [])),
                "dimension":    len(corr.get("by_dimension_score", [])),
                "execution":    len(corr.get("by_execution_flags", [])),
                "confidence":   len(corr.get("by_confidence_bucket", [])),
                "holding":      len(corr.get("by_holding_period_bucket", [])),
            },
        }

    # ── Explainability (latest) ──
    today_expl = _read_json_safe(root / "reports" / "research"
                                       / f"explainability_{date.today().isoformat()}.json")
    expl_summary = None
    if today_expl:
        expl_summary = {
            "narrative":            today_expl.get("narrative"),
            "leader_today":         today_expl.get("leader_today"),
            "edge_pp":              today_expl.get("edge_pp"),
            "biggest_edge":         today_expl.get("biggest_edge"),
            "biggest_miss":         today_expl.get("biggest_miss"),
            "sector_attribution":   today_expl.get("sector_attribution", [])[:5],
        }

    # ── Disagreement verdict ──
    dis_verdict = _read_json_safe(root / "reports" / "research"
                                        / "disagreements" / "verdict.json")
    disagreement_summary = None
    if dis_verdict:
        # Show only buckets with a decisive winner
        decisive = {k: v for k, v in (dis_verdict.get("buckets") or {}).items()
                        if v.get("winner") not in (None, "INSUFFICIENT_SAMPLE")}
        disagreement_summary = {
            "n_total":              dis_verdict.get("n_total_disagreements"),
            "n_scorable":           dis_verdict.get("n_scorable"),
            "horizon_days":         dis_verdict.get("horizon_days"),
            "sample_size_note":     dis_verdict.get("sample_size_note"),
            "decisive_buckets":     decisive,
            "all_buckets":          dis_verdict.get("buckets"),
        }

    # ── Tickets ──
    bootstrap_starter_tickets(root)      # idempotent
    tickets = [
        {
            "ticket_id":            t.ticket_id,
            "title":                t.title,
            "market_scope":         t.market_scope,
            "mode":                 t.mode,
            "lifecycle_state":      t.lifecycle_state,
            "canonical_candidate":  t.canonical_candidate,
            "opened_at":            t.opened_at,
            "updated_at":           t.updated_at,
            "tags":                 t.tags,
        }
        for t in load_all_tickets(root)
    ]

    # ── Program status ──
    canonical = "UNDECIDED"
    canonical_reason = f"evaluation program in progress · day {day_of_program} of {WINDOW_DAYS_TARGET}"
    if day_of_program >= WINDOW_DAYS_MIN and india_leader in ("RUNNER_1", "RUNNER_2"):
        if day_of_program >= WINDOW_DAYS_TARGET:
            canonical = india_leader
            canonical_reason = f"sustained superiority over {WINDOW_DAYS_TARGET}-day target window"
        else:
            canonical_reason = (f"day-60 first-decision checkpoint · {india_leader} leading by "
                                    f"{abs(india_edge):.2f}pp · monitoring through day-90")

    # Confidence tag
    if day_of_program < 15:
        confidence = "insufficient"
    elif india_leader == "TIE":
        confidence = "flipping"
    elif abs(india_edge) < 1.0:
        confidence = "flipping"
    elif abs(india_edge) < 3.0:
        confidence = "growing"
    else:
        confidence = "stable"

    payload = {
        "engine":               ENGINE_ID,
        "schema_fingerprint":   SCHEMA_FINGERPRINT,
        "run_utc":              now.isoformat(),
        "program": {
            "experiment_start":     experiment_start,
            "day_of_program":       day_of_program,
            "window_days_minimum":  WINDOW_DAYS_MIN,
            "window_days_target":   WINDOW_DAYS_TARGET,
            "decision_checkpoints": DECISION_CHECKPOINTS,
            "canonical":            canonical,
            "canonical_reason":     canonical_reason,
        },
        "tickets":              tickets,
        "layers": {
            "live_evaluation": {
                "india_delivery": {
                    "runner1":          asdict(r1_india),
                    "runner2":          asdict(r2_india),
                    "leader":           india_leader,
                    "leader_edge_pct":  india_edge,
                    "overlap":          overlap,
                },
                "usa_delivery": {
                    "runner1":       None,
                    "runner1_note":  "Runner 1 (adaptive_rec_v2) does not cover USA universe",
                    "runner2":       r2_usa,
                    "leader":        "RUNNER_2_ONLY" if r2_usa else "NO_DATA",
                },
                "india_intraday":    intraday_india,
            },
            "historical": {
                "india":                hist_india,
                "usa":                  hist_usa,
                "reduced_2y_backtest":  reduced,
            },
            "correlation_lab":        correlation_summary or {"note": "run correlation lab to populate"},
            "explainability":         expl_summary or {"note": "run explainability layer"},
            "disagreements":          disagreement_summary or {"note": "run disagreement store"},
        },
        "status": {
            "canonical":     canonical,
            "leader":        india_leader,
            "leader_edge_pct": india_edge,
            "confidence":    confidence,
        },
        "note": ("Both runners are CANDIDATES · neither is canonical during evaluation. "
                    "Article IX (Research Lifecycle) + Article X (Evidence-First Promotion) "
                    "govern any state transition."),
    }

    out = root / "reports" / "research" / "research_platform.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")

    # Also emit an alias at the legacy path for anything still reading it
    alias = root / "reports" / "runner_metrics.json"
    alias.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                        encoding="utf-8")
    return payload
