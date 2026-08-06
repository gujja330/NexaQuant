"""Daily runner for the Recommendation SSoT bridge.

Publishes `reports/recommendations.json` (or `usa/reports/recommendations.json`)
from the fresh Runner 2 v3 output. Slots into the daily orchestrator
IMMEDIATELY after `recommendation_intelligence` (Runner 2) — before every
downstream consumer.

Usage:
    python -m backend.recommendation.ssot.run --market india
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Cycle 4: force UTF-8 stdout so ceo_summary/lifecycle prints don't crash
# the pipeline on Windows cp1252 consoles or CI with mismatched LANG.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

import json  # noqa: E402
from backend.recommendation.ssot.bridge import publish_ssot  # noqa: E402
from backend.recommendation.investor_actionable import (  # noqa: E402
    enrich_batch, summarize_batch, build_ceo_summary,
)
from backend.recommendation.snapshot import (  # noqa: E402
    archive_snapshot, load_previous_snapshot, list_snapshot_dates,
    load_snapshot_for_date,
)
from backend.recommendation.snapshot.store import snapshot_to_ticker_map  # noqa: E402
from backend.portfolio.position_store import (  # noqa: E402
    update_from_recs, load_all_positions,
)
# v2.4 trust-surface modules (Article 101.2 · pure attribution)
from backend.analytics.scorecard import run_scorecard  # noqa: E402
from backend.analytics.attribution import (  # noqa: E402
    enrich_recs_with_attribution, summarize_attribution,
)
from backend.analytics.backtrack import build_market_backtrack  # noqa: E402
# Evidence Cycle 1 · Phases 1.1 / 1.2 / 2 / 3 · pure measurement, zero features
from backend.analytics.evidence import (  # noqa: E402
    run_calibration, run_alpha_validation, run_yoy, run_rolling_ic,
)
# AEGIS Research Platform · permanent evaluation framework
# (Article IX Research Lifecycle · Article X Evidence-First Promotion)
# 60-day minimum / 90-day target · canonical UNDECIDED during evaluation
from backend.research import (  # noqa: E402
    ingest_runner1_picks_for_date, ingest_runner2_picks_for_date,
    ingest_runner2_picks_usa_for_date,
    ingest_runner1_intraday_picks_for_date, ingest_runner2_intraday_picks_for_date,
    log_daily_disagreements, compute_disagreement_verdict,
    compute_daily_explainability,
    run_intraday_delivery_correlation,
    run_reduced_backtest, run_historical_per_year,
    build_research_platform,
)
from backend.research.disagreement_store import mark_forward_outcomes  # noqa: E402
# R006 · Portfolio State Machine · rebuilds R2 from Top-N-screener → stateful
# portfolio manager. Zero coupling to R1 (SEALED) or delivery engine.
from backend.portfolio.portfolio_manager import (  # noqa: E402
    run_daily_cycle as _r006_run_daily_cycle,
    emit_snapshot as _r006_emit_snapshot,
)
# NOTE: Intraday HOURLY (real yfinance bars) runs as a SEPARATE parallel job
# via scripts/intraday_hourly_run.py · NEVER clubbed with the main daily
# pipeline (external fetch + rate-limit risk would block advisory delivery).
# v3.0 Option D: Runner 1 demoted to validation layer (not competing recommender)
from backend.recommendation.validation_layer import (  # noqa: E402
    build_validation_report,
)
from backend.recommendation.validation_layer.engine import (  # noqa: E402
    enrich_recs_with_validation,
)


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT.joinpath("usa", "reports")
    return _ROOT / "reports"


def _stamp_canonical(pub: dict, market: str, root: Path) -> None:
    """Read Research Platform SSoT and stamp canonical status onto ceo_summary
    + every rotation_intelligence block. Silent no-op if delivery_platform.json
    missing (never breaks the daily pipeline)."""
    dp_path = root / "reports" / "research" / "delivery_platform.json"
    if not dp_path.exists():
        return
    try:
        dp = json.loads(dp_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return
    program = dp.get("program") or {}
    status = dp.get("status") or {}
    canonical = program.get("canonical") or "UNDECIDED"
    canonical_reason = program.get("canonical_reason") or ""
    day_of_program = program.get("day_of_program") or 0
    window_target = program.get("window_days_target") or 90
    window_min = program.get("window_days_minimum") or 60
    leader = status.get("leader") or "TIE"
    leader_edge_pct = status.get("leader_edge_pct") or 0.0
    confidence = status.get("confidence") or "insufficient"

    # Every rotation in the daily payload today is a Runner 2 v3 proposal
    # (v3 is the sole source of recommendations_v3.json). When a canonical
    # winner is declared post-90-day evaluation, this attribution updates.
    proposed_by = "RUNNER_2"

    canonical_block = {
        "canonical":            canonical,
        "canonical_reason":     canonical_reason,
        "leader":               leader,
        "leader_edge_pct":      leader_edge_pct,
        "day_of_program":       day_of_program,
        "window_days_minimum":  window_min,
        "window_days_target":   window_target,
        "confidence":           confidence,
        "proposed_by":          proposed_by,
        "governance":           "Article IX (Research Lifecycle) + Article X (Evidence-First Promotion)",
        "source_ssot":          "reports/research/delivery_platform.json",
    }

    # Stamp top-level for consumers reading pub["canonical"] directly
    pub["canonical"] = canonical_block
    # Stamp inside ceo_summary for consumers reading ceo_summary alone
    ceo = pub.get("ceo_summary") or {}
    ceo["canonical_engine"]  = canonical
    ceo["canonical_status"]  = canonical
    ceo["canonical_leader"]  = leader
    ceo["canonical_edge_pct"] = leader_edge_pct
    ceo["proposed_by"]       = proposed_by
    ceo["evaluation_day"]    = f"{day_of_program} · min {window_min}d · target {window_target}d"
    pub["ceo_summary"] = ceo
    # Stamp every rotation_intelligence with proposer + canonical marker
    for r in pub.get("recommendations") or []:
        rot = r.get("rotation_intelligence")
        if not isinstance(rot, dict):
            continue
        rot["proposed_by"]      = proposed_by
        rot["canonical_status"] = canonical
        rot["canonical_leader"] = leader
        rot["evaluation_day"]   = f"{day_of_program} · min {window_min}d · target {window_target}d"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    ap.add_argument("--force", action="store_true",
                       help="DESTRUCTIVE · overwrite existing snapshot for asof · "
                            "required when the pipeline was already run for this date")
    args = ap.parse_args()

    reports = _reports_dir(args.market)
    v3 = reports / "recommendations_v3.json"
    out = reports / "recommendations.json"
    asof_run = args.asof or date.today().isoformat()

    # ── Guard 1 · same-day idempotency lock (Article: never destroy today's picks) ──
    # Post-mortem 2026-07-30: re-running ssot on the same date silently overwrote
    # morning-good state (LUPIN/HEROMOTOCO/CHAMBLFERT demoted to HOLD by evolution
    # enricher). Prevention: refuse rerun unless --force is passed explicitly.
    # Display-layer changes should use scripts/stamp_only.py which is non-destructive.
    snap_existing = (reports / "recommendations_history" / args.market
                        / f"{asof_run}.json")
    if snap_existing.exists() and not args.force:
        print(f"[recommendation_ssot:{args.market}] REFUSED · snapshot for "
                f"{asof_run} already exists at {snap_existing.relative_to(_ROOT)}.")
        print(f"  · Use 'scripts/stamp_only.py --market {args.market}' for display "
                f"or canonical stamp updates (non-destructive).")
        print(f"  · Pass --force to this script only if you truly need to REGENERATE "
                f"today's picks (destroys the current snapshot).")
        return 2

    payload = publish_ssot(v3, out, market=args.market,
                             asof=asof_run,
                             run_utc=datetime.now(timezone.utc).isoformat())
    print(f"[recommendation_ssot:{args.market}] "
          f"n={payload['n']} (source: {payload['source']}) -> {out.name}")

    # Investor-Actionable enrichment · adds investor_action + position_plan + why
    # + rotation_intelligence + lifecycle_state + evolution to every rec, plus
    # a ceo_summary block at top-level. Also archives today's snapshot to the
    # per-market history directory so future runs can compute deltas.
    # Article 101.2 · pure enrichment · CEO cycles 2-4.
    try:
        pub = json.loads(out.read_text(encoding="utf-8"))
        recs = pub.get("recommendations", [])
        if recs:
            lifecycle_records, dynamic_holding_decisions = _load_context(reports)
            # Cycle 4: load previous snapshot for evolution deltas.
            # Cycle 5-Cmd: real first_seen dates from position_store.
            asof_str = pub.get("asof") or ""
            prev_snap = load_previous_snapshot(reports, args.market, asof_str) if asof_str else None
            previous_ticker_map = snapshot_to_ticker_map(prev_snap)
            # Pre-load ANY existing positions so the enricher can compute
            # days_recommended from first_seen_date. Then enrich, then
            # update position store with the ENRICHED prices.
            positions = load_all_positions(reports, args.market)
            history_asof_map = {t: pr.first_seen_date for t, pr in positions.items()}

            enrich_batch(recs,
                            lifecycle_records=lifecycle_records,
                            dynamic_holding_decisions=dynamic_holding_decisions,
                            previous_ticker_map=previous_ticker_map,
                            asof=asof_str,
                            history_asof_map=history_asof_map)

            # Update position store AFTER enrichment so entry_zone.current_price
            # is populated. Position store is idempotent per (ticker, asof).
            try:
                update_from_recs(reports, args.market, recs, asof=asof_str or "")
            except Exception as _e:
                print(f"[position_store:{args.market}] update failed · {type(_e).__name__}: {_e}")

            # Cycle 4: CEO executive summary block at the top of payload
            ceo_summary = build_ceo_summary(recs,
                                               market=args.market,
                                               macro_regime=_read_macro_regime(reports),
                                               portfolio_cash_pct=_read_cash_pct(reports),
                                               portfolio_health_score=_read_portfolio_health(reports))
            pub["ceo_summary"] = ceo_summary
            pub["recommendations"] = recs
            pub["investor_actionable_engine"] = "aegis.recommendation.investor_actionable.v1"

            # Article IX/X · stamp canonical status on ceo_summary + every
            # rotation_intelligence block · reads from the Research Platform
            # SSoT (delivery_platform.json). This makes it explicit in every
            # downstream consumer (Telegram, dashboards, APIs) that every
            # rotation shown is a PROPOSAL from Runner 2 v3 while canonical
            # designation is UNDECIDED pending 60/90-day evaluation.
            _stamp_canonical(pub, args.market, _ROOT)

            out.write_text(json.dumps(pub, indent=2, default=str, ensure_ascii=False),
                            encoding="utf-8")
            summ = summarize_batch(recs)
            (reports / "investor_actionable_summary.json").write_text(
                json.dumps(summ, indent=2, ensure_ascii=False), encoding="utf-8")

            # v2.4: Sector/Decision Attribution — decompose ensemble score
            # into per-model contributions. Runs BEFORE snapshot archive so
            # the attribution block is preserved in history.
            try:
                enrich_recs_with_attribution(recs, reports, _ROOT)
                pub["recommendations"] = recs
                pub["attribution_summary"] = summarize_attribution(recs)
                (reports / "attribution_summary.json").write_text(
                    json.dumps(pub["attribution_summary"], indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
            except Exception as _e:
                print(f"[attribution:{args.market}] failed · {type(_e).__name__}: {_e}")

            # v2.4: AI Scorecard from learning.parquet (India only — closed
            # trades ledger is India-side; will extend to USA when learning
            # corpus grows there).
            if args.market == "india":
                try:
                    scorecard = run_scorecard(_ROOT)
                    pub["ai_scorecard"] = {
                        "overall_score":  scorecard.get("overall_score"),
                        "overall_stars":  scorecard.get("overall_stars"),
                        "verdict":        scorecard.get("verdict"),
                        "n_trades":       scorecard.get("n_trades"),
                        "period_start":   scorecard.get("period_start"),
                        "period_end":     scorecard.get("period_end"),
                    }
                    print(f"[ai_scorecard] {scorecard.get('overall_score')}/100 · "
                          f"{scorecard.get('verdict')} · {scorecard.get('n_trades')} trades")
                except Exception as _e:
                    print(f"[ai_scorecard] failed · {type(_e).__name__}: {_e}")

                # Evidence Cycle 1 · 4 measurement engines · India-only for now
                try:
                    cal = run_calibration(_ROOT)
                    pub.setdefault("ai_scorecard", {})["calibration_verdict"] = cal.get("verdict_short")
                    pub["ai_scorecard"]["calibration_slope"] = cal.get("calibration_slope")
                    pub["ai_scorecard"]["brier_score"] = cal.get("brier_score")
                    print(f"[evidence.calibration] {cal.get('verdict_short')} · "
                          f"slope={cal.get('calibration_slope')} · brier={cal.get('brier_score')}")
                except Exception as _e:
                    print(f"[evidence.calibration] failed · {type(_e).__name__}: {_e}")
                try:
                    av = run_alpha_validation(_ROOT)
                    print(f"[evidence.alpha_validation] {av.get('verdict')} · "
                          f"pearson_r={av.get('pearson_r')} · "
                          f"directional={av.get('directional_accuracy')}")
                except Exception as _e:
                    print(f"[evidence.alpha_validation] failed · {type(_e).__name__}: {_e}")
                try:
                    yoy = run_yoy(_ROOT)
                    print(f"[evidence.yoy] {yoy.get('verdict')} · "
                          f"win_rate_trend={yoy.get('win_rate_trend')} · "
                          f"median_return_trend={yoy.get('median_return_trend')}")
                except Exception as _e:
                    print(f"[evidence.yoy] failed · {type(_e).__name__}: {_e}")
                try:
                    ric = run_rolling_ic(_ROOT)
                    n_retire = sum(1 for d in ric.get("per_dim_summary") or []
                                        if "retire" in d.get("verdict", ""))
                    print(f"[evidence.rolling_ic] {ric.get('verdict')} · "
                          f"{n_retire} retire-candidates")
                except Exception as _e:
                    print(f"[evidence.rolling_ic] failed · {type(_e).__name__}: {_e}")

            # v3.0 Option D: Runner 1 validation layer (India-only · Runner 1
            # runs against India universe; USA has no legacy Runner 1 today).
            if args.market == "india":
                try:
                    r1_csv = _ROOT / "data" / "aegis_today.csv"
                    enrich_recs_with_validation(recs, r1_csv)
                    validation_report = build_validation_report(recs, r1_csv)
                    pub["recommendations"] = recs
                    pub["runner1_validation"] = {
                        k: v for k, v in validation_report.items()
                        if k != "per_rec_validation"
                    }
                    (reports / "runner1_validation.json").write_text(
                        json.dumps(validation_report, indent=2, default=str,
                                     ensure_ascii=False),
                        encoding="utf-8")
                    ac = validation_report.get("agreement_counts", {})
                    print(f"[runner1_validation:india] "
                          f"consensus={validation_report.get('consensus_pct')}% · "
                          f"agree={ac.get('AGREE', 0)} · disagree={ac.get('DISAGREE', 0)} · "
                          f"orphans={len(validation_report.get('runner1_orphans', []))}")
                except Exception as _e:
                    print(f"[runner1_validation:india] failed · {type(_e).__name__}: {_e}")

            # Persist enrichment updates before snapshot archive
            out.write_text(json.dumps(pub, indent=2, default=str, ensure_ascii=False),
                            encoding="utf-8")

            # Cycle 4: archive today's snapshot for tomorrow's evolution deltas
            snap_path = archive_snapshot(pub, reports, args.market, asof=asof_str or None)

            # v2.4: Backtrack Engine — regenerate per-ticker timelines from
            # the accumulated snapshot + position_store history. Runs AFTER
            # snapshot archive so today's data is included.
            try:
                bt = build_market_backtrack(reports, args.market)
                print(f"[backtrack:{args.market}] tracked {bt['n_tickers_tracked']} tickers "
                      f"across {len(bt['snapshot_dates'])} snapshot dates")
            except Exception as _e:
                print(f"[backtrack:{args.market}] failed · {type(_e).__name__}: {_e}")

            print(f"[investor_actionable:{args.market}] "
                  f"entry_dist={summ['entry_decision_dist']} "
                  f"if_holding_dist={summ['if_holding_decision_dist']} "
                  f"actionable_entries={len(summ['actionable_entries'])} "
                  f"actionable_exits={len(summ['actionable_exits'])} "
                  f"rotations={summ.get('n_rotation_suggestions', 0)} "
                  f"lifecycle={summ.get('lifecycle_state_dist', {})}")
            print(f"[ceo_summary:{args.market}] {ceo_summary.get('recommended_action')} "
                  f"· regime={ceo_summary.get('market_regime')} "
                  f"· actionable={ceo_summary.get('actionable_count')} "
                  f"· rotations={ceo_summary.get('rotations_count')}")
            print(f"[snapshot:{args.market}] archived -> {snap_path.relative_to(reports.parent)}")
    except Exception as exc:
        # Enrichment failure must NEVER break the SSoT pipeline · log and continue
        print(f"[investor_actionable:{args.market}] enrichment failed · {type(exc).__name__}: {exc}")

    # ── AEGIS Research Platform (Article IX + X) ──
    # Runs AFTER investor-actionable enrichment so it has today's fresh
    # recommendations file. India-run is authoritative (has both runners);
    # USA-run refreshes only its USA-scoped slice. Failures must never
    # break the SSoT pipeline.
    try:
        asof_str_rp = payload.get("asof") or date.today().isoformat()
        if args.market == "usa":
            # USA delivery paper portfolio (Runner 2 only · R1 doesn't cover USA)
            ingest_runner2_picks_usa_for_date(_ROOT, asof=asof_str_rp)
        if args.market == "india":
            # Delivery paper portfolios (both runners)
            ingest_runner1_picks_for_date(_ROOT, asof=asof_str_rp)
            ingest_runner2_picks_for_date(_ROOT, asof=asof_str_rp)
            # Intraday ingest REMOVED 2026-07-30 · shadow-of-delivery approach
            # rejected. Real intraday engine spec in
            # docs/AEGIS_INTRADAY_ARCHITECTURE.md (ticket R004 · not built).
            # Disagreement store + forward-outcome marking + verdict rollup
            dis = log_daily_disagreements(_ROOT, as_of=asof_str_rp)
            mark_forward_outcomes(_ROOT)
            compute_disagreement_verdict(_ROOT)
            # Explainability
            compute_daily_explainability(_ROOT, as_of=asof_str_rp)
            # Historical per-year (both markets refreshed from India run)
            run_reduced_backtest(_ROOT)
            run_historical_per_year(_ROOT, "india")
            run_historical_per_year(_ROOT, "usa")
            print(f"[research_platform:india] agreement={dis.get('agreement_pct')}% "
                    f"disagreement={dis.get('disagreement_pct')}% "
                    f"new_ledger_rows={dis.get('new_rows_appended')}")
        # Both markets emit the unified SSoT.
        # experiment_start = first day the research platform was activated.
        # Read it from a lightweight config file · falls back to today on
        # first-ever run (bootstrap). Never hardcoded (guardrail-friendly).
        cfg_path = _ROOT / "configs" / "research_program.json"
        exp_start = None
        try:
            if cfg_path.exists():
                exp_start = json.loads(cfg_path.read_text(encoding="utf-8")).get("experiment_start")
        except Exception:
            exp_start = None
        if not exp_start:
            exp_start = asof_str_rp
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps({"experiment_start": exp_start,
                                                     "note": "Locked at first activation of the Research Platform"},
                                                indent=2), encoding="utf-8")
        rp = build_research_platform(_ROOT, experiment_start=exp_start)
        prog = rp.get("program", {})
        status = rp.get("status", {})
        print(f"[research_platform:{args.market}] "
                f"day={prog.get('day_of_program')}/{prog.get('window_days_target')} "
                f"canonical={status.get('canonical')} "
                f"leader={status.get('leader')} "
                f"edge={status.get('leader_edge_pct')}pp "
                f"confidence={status.get('confidence')}")
    except Exception as exc:
        print(f"[research_platform:{args.market}] failed · {type(exc).__name__}: {exc}")

    # ── R006 · Portfolio State Machine (stateful R2 cycle) ──
    # Post-mortem 2026-07-31: R2 behaved as Top-N daily screener · this hook
    # runs the R006 state machine AFTER enrichment · producing:
    #   · portfolio_ledger.jsonl events (OPEN/HOLD/EXIT/ROTATE)
    #   · rotation_ledger.jsonl audit trail
    #   · portfolio_snapshot_{market}.json (Telegram-consumable)
    # Zero coupling to Runner 1 (SEALED) or delivery enricher · additive only.
    try:
        r006_recs = pub.get("recommendations") or []
        if r006_recs:
            snap_r006 = _r006_run_daily_cycle(_ROOT, market=args.market,
                                                     runner="runner2",
                                                     asof=asof_str_rp,
                                                     recs=r006_recs)
            _r006_emit_snapshot(_ROOT, snap_r006)
            print(f"[r006:{args.market}] cycle done · "
                    f"opens={len(snap_r006.opens_today)} "
                    f"holds={len(snap_r006.holds_today)} "
                    f"exits={len(snap_r006.exits_today)} "
                    f"rotations={len(snap_r006.rotations_today)} "
                    f"rejected={len(snap_r006.rejected_proposals)} "
                    f"horizon_check={snap_r006.horizon_check.get('verdict')}")
    except Exception as exc:
        print(f"[r006:{args.market}] failed · {type(exc).__name__}: {exc}")

    return 0


def _read_macro_regime(reports: Path) -> str | None:
    """Read market regime from whichever source has a valid label.
    v3.0 fix: `macro_regime.json` uses `primary_regime` (not `regime`) ·
    also fall back to `market_intelligence.json` which always has a value ·
    NEVER return None to CEO summary (Article: never show "unknown")."""
    for name, keys in [
        ("macro_regime.json",       ["primary_regime", "regime", "current_regime", "regime_label"]),
        ("market_intelligence.json", ["regime", "current_regime", "market_regime"]),
        ("macro_intelligence.json", ["regime", "current_regime", "regime_label"]),
    ]:
        p = reports / name
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in keys:
                v = d.get(k)
                if v and str(v).strip().lower() not in ("unknown", "n/a", "none"):
                    return str(v)
        except Exception:
            continue
    # Article compliance: rather than "unknown", surface an actionable label.
    return "not_available"


def _read_cash_pct(reports: Path) -> float | None:
    for name in ("portfolio_v3.json", "portfolio.json"):
        p = reports / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return d.get("cash_pct") or d.get("cash_weight_pct") or d.get("cash")
            except Exception:
                continue
    return None


def _read_portfolio_health(reports: Path) -> int | None:
    p = reports / "portfolio_health.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            v = d.get("score") or d.get("health_score")
            return int(v) if v is not None else None
        except Exception:
            return None
    return None


def _build_history_asof_map(reports: Path, market: str, current_asof: str) -> dict:
    """Return {ticker: earliest_asof_string} across ALL prior snapshots.

    Used by the enricher to compute `days_recommended` accurately. Only
    counts tickers present in a contiguous streak ending at current_asof
    OR just returns the earliest date seen — we take the simpler earliest-
    seen semantic and rely on lifecycle_state to signal breaks.
    """
    from datetime import date as _date
    dates = list_snapshot_dates(reports, market)
    if not dates:
        return {}
    ticker_first: dict[str, str] = {}
    for d in dates:
        snap = load_snapshot_for_date(reports, market, d)
        if not snap:
            continue
        for r in (snap.get("recommendations") or []):
            t = str(r.get("ticker") or "")
            if t and t not in ticker_first:
                ticker_first[t] = d.isoformat()
    return ticker_first


def _load_context(reports: Path) -> tuple[dict | None, dict | None]:
    """Load lifecycle records + dynamic_holding decisions if available.

    Both are optional — enricher degrades gracefully when missing.
    """
    lifecycle_records = None
    dynamic_holding_decisions = None
    try:
        lp = reports / "recommendation_lifecycle.json"
        if lp.exists():
            payload = json.loads(lp.read_text(encoding="utf-8"))
            lifecycle_records = payload.get("records") or {}
    except Exception:
        pass
    try:
        dhp = reports / "dynamic_holding.json"
        if dhp.exists():
            payload = json.loads(dhp.read_text(encoding="utf-8"))
            decisions = payload.get("decisions") or []
            if isinstance(decisions, list):
                dynamic_holding_decisions = {
                    str(d.get("ticker") or ""): d for d in decisions if d.get("ticker")
                }
    except Exception:
        pass
    return lifecycle_records, dynamic_holding_decisions


if __name__ == "__main__":
    sys.exit(main())
