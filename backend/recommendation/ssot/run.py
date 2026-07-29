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


def _reports_dir(market: str) -> Path:
    if market == "usa":
        return _ROOT.joinpath("usa", "reports")
    return _ROOT / "reports"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["india", "usa"])
    ap.add_argument("--asof", default=None)
    args = ap.parse_args()

    reports = _reports_dir(args.market)
    v3 = reports / "recommendations_v3.json"
    out = reports / "recommendations.json"

    payload = publish_ssot(v3, out, market=args.market,
                             asof=(args.asof or date.today().isoformat()),
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
            # Update position store BEFORE enrichment so the enricher sees
            # today's first-seen dates for newly-recommended tickers.
            try:
                update_from_recs(reports, args.market, recs, asof=asof_str or "")
            except Exception as _e:
                print(f"[position_store:{args.market}] update failed · {type(_e).__name__}: {_e}")
            positions = load_all_positions(reports, args.market)
            history_asof_map = {t: pr.first_seen_date for t, pr in positions.items()}

            enrich_batch(recs,
                            lifecycle_records=lifecycle_records,
                            dynamic_holding_decisions=dynamic_holding_decisions,
                            previous_ticker_map=previous_ticker_map,
                            asof=asof_str,
                            history_asof_map=history_asof_map)

            # Cycle 4: CEO executive summary block at the top of payload
            ceo_summary = build_ceo_summary(recs,
                                               market=args.market,
                                               macro_regime=_read_macro_regime(reports),
                                               portfolio_cash_pct=_read_cash_pct(reports),
                                               portfolio_health_score=_read_portfolio_health(reports))
            pub["ceo_summary"] = ceo_summary
            pub["recommendations"] = recs
            pub["investor_actionable_engine"] = "aegis.recommendation.investor_actionable.v1"
            out.write_text(json.dumps(pub, indent=2, default=str, ensure_ascii=False),
                            encoding="utf-8")
            summ = summarize_batch(recs)
            (reports / "investor_actionable_summary.json").write_text(
                json.dumps(summ, indent=2, ensure_ascii=False), encoding="utf-8")

            # Cycle 4: archive today's snapshot for tomorrow's evolution deltas
            snap_path = archive_snapshot(pub, reports, args.market, asof=asof_str or None)

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

    return 0


def _read_macro_regime(reports: Path) -> str | None:
    for name in ("macro_regime.json", "macro_intelligence.json"):
        p = reports / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return d.get("regime") or d.get("current_regime") or d.get("regime_label")
            except Exception:
                continue
    return None


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
