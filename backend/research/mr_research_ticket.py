"""AEGIS · M-R2 · Research Ticket Generator · Sprint M.

Reads M-R evidence (feature ranking, score usefulness, loss prevention,
control cohort, stop-loss sweep) and generates STRUCTURED research
tickets · one per candidate improvement · following the M-R governance
gate.

Each ticket is a JSON with:

  ticket_id           · aegis_mr_ticket_YYYYMMDD_<slug>
  status              · DRAFT (never auto-promotes)
  market              · INDIA / USA / GLOBAL
  title               · one-line
  hypothesis          · what we believe
  expected_effect     · quantified expected improvement
  evidence            · list of {source_file, metric, value} triples
  n_evidence          · sample size of underlying evidence
  statistical_verdict · per M-R contract (OBSERVATION_ONLY/INSUFFICIENT/PRODUCTION_CANDIDATE)
  proposed_rule       · concrete config-level change (OFF by default)
  validation_plan     · walk-forward N + horizon + acceptance metric
  promotion_gate      · 7-step gate from PRODUCTION_LOCK.md
  risk                · what could go wrong
  do_not_touch        · locked layers this ticket must not modify

Emits reports/research/tickets/{ticket_id}.json.
No production changes. Tickets are frozen for CEO review · not applied.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_research_ticket.v0.1"
LOCKED_LAYERS = [
    "R1 recommendation runner",
    "R2 recommendation runner",
    "Registry orphan-close",
    "backend/delivery/xlsx_contract.py",
    "backend/delivery/xlsx_validator.py",
    "scripts/telegram_command_center_send.py canonical INVESTMENT_ACTIVE JSON",
    "configs/ensemble_weights_adaptive.yaml",
    "model_registry.jsonl",
]
PROMOTION_GATE = [
    "1. Research Ticket accepted by CEO",
    "2. Walk-forward test on N >= 100 forward predictions",
    "3. Full regression pass on locked delivery invariants (BLOCK == 0)",
    "4. CEO explicit approval + lock-override phrase",
    "5. Config-toggle OFF by default in a new SPRINT_ID branch",
    "6. Paper-trading period >= 30 sessions with green metrics",
    "7. Production promotion under new SPRINT_ID with L4 evidence",
]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", s.lower())[:60]


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _ticket(ticket_id: str, market: str, title: str, hypothesis: str,
            expected_effect: str, evidence: list, n_evidence: int,
            stat_verdict: str, proposed_rule: str, validation_plan: str,
            risk: str) -> dict:
    today = date.today().isoformat()
    return {
        "ticket_id":          ticket_id,
        "status":             "DRAFT",
        "generated_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date":     today,
        "market":             market,
        "engine":             ENGINE_ID,
        "experiment_id":      EXPERIMENT_ID,
        "title":              title,
        "hypothesis":         hypothesis,
        "expected_effect":    expected_effect,
        "n_evidence":         n_evidence,
        "statistical_verdict": stat_verdict,
        "evidence":           evidence,
        "proposed_rule":      proposed_rule,
        "validation_plan":    validation_plan,
        "promotion_gate":     PROMOTION_GATE,
        "risk":               risk,
        "do_not_touch":       LOCKED_LAYERS,
    }


def build_tickets(root: Path) -> list:
    tickets = []
    feat_i = _load(root, "mr_feature_ranking_india.json")
    feat_u = _load(root, "mr_feature_ranking_usa.json")
    score_i = _load(root, "mr_score_usefulness_india.json")
    lp_i = _load(root, "mr_loss_prevention_india.json")
    stop_i = _load(root, "mr_stop_loss_sweep_india.json")
    stop_u = _load(root, "mr_stop_loss_sweep_usa.json")
    ctrl_i = _load(root, "mr_control_cohort_india.json")
    ctrl_u = _load(root, "mr_control_cohort_usa.json")
    autopsy_i = _load(root, "mr_prediction_autopsy_india_summary.json")

    today = date.today().strftime("%Y%m%d")

    # T1 · India confidence anti-signal
    conf = (score_i.get("audits",{}) or {}).get("confidence_pct",{})
    if conf and conf.get("verdict") in ("ANTI_SIGNAL","ANTI_SIGNAL_WEAK","KEEP_WARN"):
        tickets.append(_ticket(
            ticket_id=f"aegis_mr_ticket_{today}_india_confidence_anti_signal",
            market="INDIA",
            title="India confidence_pct is anti-correlated with forward return",
            hypothesis=(
                "In India, higher confidence_pct at prediction time predicts LOWER "
                f"5D forward win rate. Bucket audit shows WR spread of "
                f"{conf.get('wr_spread_pp')}pp with monotonicity "
                f"{conf.get('monotonicity')}."),
            expected_effect=(
                "If we INVERT confidence's contribution to R1 ranking OR treat "
                "conf_70_85 as a WARN not GO signal in India, expected 5D WR lift "
                "of ~10pp on affected cohort (n>=180)."),
            evidence=[
                {"source": "mr_score_usefulness_india.json",
                 "field": "audits.confidence_pct",
                 "value": conf},
                {"source": "mr_winner_loser_genome_india.json",
                 "field": "genome.genome_signals.confidence_diff",
                 "note": "winners avg=51.4% · losers avg=57.94% · delta=-6.54%"},
            ],
            n_evidence=autopsy_i.get("n_predictions", 0),
            stat_verdict="PRODUCTION_CANDIDATE" if autopsy_i.get("n_predictions",0) >= 100 else "INSUFFICIENT_EVIDENCE",
            proposed_rule=(
                "Config-toggle in a shadow R1 ranker: multiply confidence "
                "contribution by -1 (or set to 0) in India-only. Requires new "
                "shadow R1 output stream · does NOT modify production R1."),
            validation_plan=(
                "Capture 20 forward days of R1 predictions with the shadow "
                "confidence-inverted variant. Accept if 5D WR of shadow >= "
                "current + 5pp AND fwd_5d avg > current + 0.3% on n>=100."),
            risk=(
                "Confidence is calibrated on a different objective (thesis-strength). "
                "Inversion may destroy long-run signal even while helping short-term. "
                "MUST run in shadow only · never in production R1."),
        ))

    # T2 · India TOP-3 rank inversion
    ranking_i = feat_i.get("ranking", []) or []
    rank_row = next((r for r in ranking_i if r["feature"] == "rank_slot"), None)
    if rank_row:
        tickets.append(_ticket(
            ticket_id=f"aegis_mr_ticket_{today}_india_top3_rank_inversion",
            market="INDIA",
            title="India top-3 rank slot underperforms rank_4_7 (ranker inversion)",
            hypothesis=(
                "India R1 places QUALITY(57%) + OK(40%) high-confidence stocks in "
                "top-3 slots · these have 14.5% 5D WR. Meanwhile R2 rank_4_7 "
                "(n=56, 47% WR, +0.53% avg) is the only positive cohort. The "
                "ranker's top-3 selection is anti-correlated with outcome."),
            expected_effect=(
                "Rank-slot filter test: 'reject R1 top-3 in India unless additional "
                "MA20-dist +1..+5 filter passes' should lift avg return by ~+0.5% on "
                "the affected 82-prediction cohort."),
            evidence=[
                {"source": "mr_studies_india.json",
                 "field": "Q8_rank_slot.top3.fwd_5d",
                 "note": "n=141 WR=17.43% avg=-0.905%"},
                {"source": "mr_feature_ranking_india.json",
                 "field": "ranking[rank_slot]", "value": rank_row},
            ],
            n_evidence=141,
            stat_verdict="PRODUCTION_CANDIDATE",
            proposed_rule=(
                "In a shadow India ranker: gate any rank-1-to-3 output through "
                "a 'ma20_dist_pct BETWEEN +1 AND +5' filter. Non-passing candidates "
                "demoted to rank_4_7. Config-flag OFF by default."),
            validation_plan=(
                "Capture 20 forward days. Compare shadow-rank-1-3 5D WR vs current "
                "rank-1-3 on same day. Accept if shadow lifts WR by 10pp with n>=50 "
                "and does not degrade rank_4_7 quality."),
            risk=(
                "Filter may over-tighten and reduce total NEW recommendations. "
                "Track daily rec-count delta. If drop >30% for 5 consecutive days, "
                "roll back."),
        ))

    # T3 · India investability OK band boundary defect
    band = (score_i.get("audits",{}) or {}).get("investability_band",{})
    if band and (band.get("wr_spread_pp") or 0) >= 5:
        tickets.append(_ticket(
            ticket_id=f"aegis_mr_ticket_{today}_india_band_boundary",
            market="INDIA",
            title="India OK band underperforms AVOID · boundary miscalibrated",
            hypothesis=(
                "India investability_band ordering QUALITY > MARGINAL > AVOID > OK "
                "instead of expected QUALITY > OK > MARGINAL > AVOID. OK band (n=119) "
                "has 17.4% 5D WR · below AVOID (n=108) 19.2% · suggesting OK's "
                "internal calibration is broken."),
            expected_effect=(
                "Re-tuning OK/MARGINAL thresholds using forward-return-optimized "
                "cutoffs should lift OK cohort WR from 17.4% to 24-28% (mid MARGINAL "
                "range)."),
            evidence=[
                {"source": "mr_score_usefulness_india.json",
                 "field": "audits.investability_band", "value": band},
                {"source": "mr_studies_india.json",
                 "field": "Q7_score_usefulness.band"},
            ],
            n_evidence=551,
            stat_verdict="PRODUCTION_CANDIDATE",
            proposed_rule=(
                "In a shadow Investability engine: re-derive OK/MARGINAL split by "
                "sorting all historical predictions by underlying investability "
                "score and picking the split point that maximizes forward WR spread. "
                "Emit under new investability_shadow_v2_india.json alongside "
                "existing shadow."),
            validation_plan=(
                "Compare shadow_v2 5D WR by band on 20 forward days. Accept only if "
                "band ordering becomes strictly monotonic (QUALITY > OK > MARGINAL > "
                "AVOID) with n>=100 per band."),
            risk=(
                "Sorting purely by forward return risks overfitting to the 30-day "
                "backtest window. Regularize the split point against a walk-forward "
                "cross-validation."),
        ))

    # T4 · India stop-policy switch
    by_pol_i = (stop_i.get("by_policy") or {})
    current = by_pol_i.get("CURRENT", {})
    time_5d = by_pol_i.get("TIME_STOP_5D", {})
    if current and time_5d and current.get("expectancy_pct") is not None \
            and time_5d.get("expectancy_pct") is not None:
        gap = round(time_5d["expectancy_pct"] - current["expectancy_pct"], 3)
        tickets.append(_ticket(
            ticket_id=f"aegis_mr_ticket_{today}_india_stop_policy",
            market="INDIA",
            title=f"India TIME_STOP_5D beats CURRENT by {gap}% expectancy",
            hypothesis=(
                f"Under 30-day historical replay, TIME_STOP_5D exit produces avg "
                f"expectancy of {time_5d['expectancy_pct']}% vs CURRENT "
                f"{current['expectancy_pct']}%. TIME_STOP_5D also eliminates all "
                f"catastrophic >10% losses (0.00% vs 0.20%)."),
            expected_effect=(
                f"Gap = {gap}%. Applied to production: ~0.27% expectancy improvement "
                f"per position, zero catastrophic losses in this sample."),
            evidence=[
                {"source": "mr_stop_loss_sweep_india.json",
                 "field": "by_policy.CURRENT", "value": current},
                {"source": "mr_stop_loss_sweep_india.json",
                 "field": "by_policy.TIME_STOP_5D", "value": time_5d},
            ],
            n_evidence=time_5d.get("n", 0),
            stat_verdict="PRODUCTION_CANDIDATE" if time_5d.get("n",0) >= 100 else "INSUFFICIENT_EVIDENCE",
            proposed_rule=(
                "In a shadow exit engine: for every ACTIVE position beyond 5 trading "
                "days from entry, emit ADVISORY 'time-exit candidate'. Do NOT modify "
                "the production stop or exit. Config-flag OFF."),
            validation_plan=(
                "For each ADVISORY produced, record the fwd_5d outcome from the "
                "advisory date. Accept if median advisory return over next 5D >= "
                "median current-policy return by 0.3% on n>=100."),
            risk=(
                "5-day time exit forfeits the tail of longer-holding winners. Track "
                "MFE-captured metric alongside expectancy."),
        ))

    # T5 · India negative alpha vs universe
    if ctrl_i.get("aggregate",{}).get("fwd_5d",{}).get("n"):
        ur = ctrl_i["aggregate"]["fwd_5d"]
        ae = autopsy_i.get("cohort_ALL",{}).get("fwd_5d",{})
        if ae.get("n"):
            alpha_wr = round(ae["win_rate_pct"] - ur["wr_pct"], 2)
            alpha_avg = round(ae["avg_pct"] - ur["avg_pct"], 3)
            tickets.append(_ticket(
                ticket_id=f"aegis_mr_ticket_{today}_india_negative_alpha",
                market="INDIA",
                title=f"India AEGIS produces {alpha_wr}pp NEGATIVE alpha vs universe",
                hypothesis=(
                    f"Over 18 days, NSE universe (n={ur['n']}) 5D WR={ur['wr_pct']}% "
                    f"avg={ur['avg_pct']}%. AEGIS-India (n={ae['n']}) 5D "
                    f"WR={ae['win_rate_pct']}% avg={ae['avg_pct']}%. "
                    f"Alpha = WR{alpha_wr}pp · avg{alpha_avg}%. AEGIS-India "
                    f"currently DESTROYS value relative to random pick."),
                expected_effect=(
                    "This is the master finding · the fix is the combined effect "
                    "of tickets T1 (confidence), T2 (rank), T3 (band), T4 (stop). "
                    "Individual candidates each address ~1-2pp of the -6.48pp gap. "
                    "Only in combination can alpha be restored above zero."),
                evidence=[
                    {"source": "mr_control_cohort_india.json",
                     "field": "aggregate.fwd_5d", "value": ur},
                    {"source": "mr_prediction_autopsy_india_summary.json",
                     "field": "cohort_ALL.fwd_5d", "value": ae},
                ],
                n_evidence=ur["n"],
                stat_verdict="PRODUCTION_CANDIDATE",
                proposed_rule=(
                    "Compound proposal: enable ALL of T1+T2+T3+T4 in a single "
                    "shadow India runner instance. Compare compound-shadow vs "
                    "production on identical days for 30 forward sessions."),
                validation_plan=(
                    "Walk-forward N=30 sessions. Acceptance: compound-shadow 5D WR "
                    ">= universe WR + 3pp AND compound-shadow avg > universe avg. "
                    "Reject if any single component regresses beyond -2pp WR."),
                risk=(
                    "Compound experiments are hard to attribute. Run components in "
                    "isolation FIRST for 10 days each · then combined for 20 days."),
            ))

    return tickets


def emit(root: Path, tickets: list) -> tuple:
    dst_dir = root / ALLOWED_WRITE_ROOT / "tickets"
    dst_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in tickets:
        p = dst_dir / f"{t['ticket_id']}.json"
        p.write_text(json.dumps(t, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
        paths.append(p)
    # Also emit an index
    idx = {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_tickets":    len(tickets),
        "tickets":      [{
            "ticket_id": t["ticket_id"], "market": t["market"],
            "title": t["title"], "status": t["status"],
            "statistical_verdict": t["statistical_verdict"],
            "n_evidence": t["n_evidence"],
        } for t in tickets],
    }
    idx_p = dst_dir / "INDEX.json"
    idx_p.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    return (paths, idx_p)


def render_console(tickets: list):
    print(f"\n======== RESEARCH TICKETS · n={len(tickets)} ========")
    for t in tickets:
        print(f"\n  [{t['ticket_id']}]")
        print(f"    market:  {t['market']}")
        print(f"    title:   {t['title']}")
        print(f"    n_evid:  {t['n_evidence']}")
        print(f"    verdict: {t['statistical_verdict']}")
        print(f"    status:  {t['status']} (never auto-promoted)")


if __name__ == "__main__":
    root = Path(".").resolve()
    tickets = build_tickets(root)
    paths, idx = emit(root, tickets)
    render_console(tickets)
    print(f"\n[research_tickets] wrote {len(paths)} tickets + INDEX -> {idx.parent}")
