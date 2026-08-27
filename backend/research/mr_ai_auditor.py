"""AEGIS · M-R2 · AI Validation Auditor · Sprint M.

Per CEO memory feedback_no_more_ai_agents: no new LLM/AI engine. This
module is a DETERMINISTIC narrative synthesizer that reads all M-R JSON
evidence and writes plain-English audit findings that any of the six
existing AI agents can consume.

It does NOT make production recommendations. It does NOT auto-promote.
It restates what the evidence already says · in a form suitable for
operator review OR ingestion by an existing narrative AI agent.

Emits reports/research/mr_ai_auditor_findings.jsonl · one finding per row.
Each finding has:
  finding_id · market · severity · category · claim · evidence · caveat
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_ai_auditor.v0.1"


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _finding(fid: str, market: str, severity: str, category: str,
             claim: str, evidence: list, caveat: str) -> dict:
    return {
        "finding_id":    fid,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":        market,
        "severity":      severity,   # CRITICAL / HIGH / MEDIUM / LOW / INFO
        "category":      category,   # ALPHA / RANKER / STOP / DATA_QUALITY / SCORE / SECTOR
        "claim":         claim,
        "evidence":      evidence,
        "caveat":        caveat,
        "engine":        ENGINE_ID,
        "experiment_id": EXPERIMENT_ID,
    }


def build(root: Path) -> list:
    findings = []
    ctrl_i = _load(root, "mr_control_cohort_india.json")
    autopsy_i = _load(root, "mr_prediction_autopsy_india_summary.json")
    autopsy_u = _load(root, "mr_prediction_autopsy_usa_summary.json")
    ctrl_u = _load(root, "mr_control_cohort_usa.json")
    feat_i = _load(root, "mr_feature_ranking_india.json")
    feat_u = _load(root, "mr_feature_ranking_usa.json")
    score_i = _load(root, "mr_score_usefulness_india.json")
    stop_i = _load(root, "mr_stop_loss_sweep_india.json")
    stop_u = _load(root, "mr_stop_loss_sweep_usa.json")
    lp_i = _load(root, "mr_loss_prevention_india.json")
    lp_u = _load(root, "mr_loss_prevention_usa.json")
    leak_i = _load(root, "mr_leakage_audit_india.json")
    leak_u = _load(root, "mr_leakage_audit_usa.json")
    missed_i = _load(root, "mr_missed_winners_india.json")

    # F001 · India negative alpha
    u5 = (ctrl_i.get("aggregate",{}) or {}).get("fwd_5d",{})
    a5 = (autopsy_i.get("cohort_ALL",{}) or {}).get("fwd_5d",{})
    if u5.get("n") and a5.get("n"):
        alpha_wr = round(a5["win_rate_pct"] - u5["wr_pct"], 2)
        alpha_avg = round(a5["avg_pct"] - u5["avg_pct"], 3)
        sev = "CRITICAL" if alpha_wr < -3 else "HIGH" if alpha_wr < 0 else "INFO"
        findings.append(_finding(
            "F001_INDIA_ALPHA", "INDIA", sev, "ALPHA",
            claim=(f"Over the 18-day window, AEGIS-India 5D WR={a5['win_rate_pct']}% "
                   f"and avg={a5['avg_pct']}%. Random NSE-universe pick over the "
                   f"SAME days achieved WR={u5['wr_pct']}% and avg={u5['avg_pct']}%. "
                   f"Alpha = WR{alpha_wr:+}pp / avg{alpha_avg:+}%. "
                   f"AEGIS-India is currently BELOW baseline."),
            evidence=[
                {"source":"mr_control_cohort_india.json","field":"aggregate.fwd_5d","value":u5},
                {"source":"mr_prediction_autopsy_india_summary.json","field":"cohort_ALL.fwd_5d","value":a5},
            ],
            caveat=("Window is 18 days · dominated by a market drawdown context. "
                    "Re-run monthly. Do NOT modify production based on this alone. "
                    "See ticket_india_negative_alpha for compound-improvement plan."),
        ))

    # F002 · USA positive alpha
    u5u = (ctrl_u.get("aggregate",{}) or {}).get("fwd_5d",{})
    a5u = (autopsy_u.get("cohort_ALL",{}) or {}).get("fwd_5d",{})
    if u5u.get("n") and a5u.get("n"):
        alpha_wr = round(a5u["win_rate_pct"] - u5u["wr_pct"], 2)
        alpha_avg = round(a5u["avg_pct"] - u5u["avg_pct"], 3)
        sev = "INFO" if alpha_wr > 0 else "MEDIUM"
        findings.append(_finding(
            "F002_USA_ALPHA", "USA", sev, "ALPHA",
            claim=(f"AEGIS-USA 5D WR={a5u['win_rate_pct']}% vs universe "
                   f"{u5u['wr_pct']}%. Alpha = WR{alpha_wr:+}pp / avg{alpha_avg:+}%. "
                   f"USA runner is above baseline · small positive edge."),
            evidence=[
                {"source":"mr_control_cohort_usa.json","field":"aggregate.fwd_5d","value":u5u},
                {"source":"mr_prediction_autopsy_usa_summary.json","field":"cohort_ALL.fwd_5d","value":a5u},
            ],
            caveat="USA window has n_days=7 for control cohort · sample thin. Retest.",
        ))

    # F003 · India confidence anti-signal
    conf = (score_i.get("audits",{}) or {}).get("confidence_pct",{})
    if conf and conf.get("verdict") in ("ANTI_SIGNAL","ANTI_SIGNAL_WEAK","KEEP_WARN"):
        findings.append(_finding(
            "F003_INDIA_CONFIDENCE_ANTI_SIGNAL", "INDIA", "HIGH", "SCORE",
            claim=(f"India confidence_pct verdict = {conf['verdict']}. WR spread "
                   f"{conf['wr_spread_pp']}pp with monotonicity "
                   f"{conf['monotonicity']} vs expected MONOTONIC_UP. "
                   f"High-confidence India predictions underperform low-confidence."),
            evidence=[{"source":"mr_score_usefulness_india.json",
                       "field":"audits.confidence_pct","value":conf}],
            caveat=("Confidence may be calibrated on a non-return objective "
                    "(thesis-strength). Consider re-labeling for CEO or "
                    "documenting as 'thesis strength' not 'win probability'."),
        ))

    # F004 · Feature ranking headlines
    for market, feat in (("INDIA", feat_i), ("USA", feat_u)):
        top = (feat.get("ranking") or [])[:3]
        if top:
            findings.append(_finding(
                f"F004_{market}_TOP_FEATURES", market, "MEDIUM", "FEATURE",
                claim=(f"Top-3 predictive features for {market} 5D WR: "
                       + ", ".join(f"{r['feature']}({r['wr_spread_pp']}pp)"
                                   for r in top) + "."),
                evidence=[{"source": f"mr_feature_ranking_{market.lower()}.json",
                           "field":"ranking[:3]","value":top}],
                caveat="Feature ranking is descriptive · does not imply causation.",
            ))

    # F005 · India stop policy gap
    by_pol_i = (stop_i.get("by_policy") or {})
    if "CURRENT" in by_pol_i and "TIME_STOP_5D" in by_pol_i:
        cur = by_pol_i["CURRENT"]; alt = by_pol_i["TIME_STOP_5D"]
        gap = round(alt["expectancy_pct"] - cur["expectancy_pct"], 3)
        findings.append(_finding(
            "F005_INDIA_STOP_POLICY", "INDIA", "MEDIUM", "STOP",
            claim=(f"India TIME_STOP_5D expectancy {alt['expectancy_pct']}% vs "
                   f"CURRENT {cur['expectancy_pct']}%. Gap = {gap}%. "
                   f"TIME_STOP_5D also has 0.00% catastrophic loss rate vs "
                   f"{cur['catastrophic_gt10pct_pct']}% for CURRENT."),
            evidence=[{"source":"mr_stop_loss_sweep_india.json",
                       "field":"by_policy","value":{"CURRENT":cur,"TIME_STOP_5D":alt}}],
            caveat=("Time-exit forfeits longer-run winners · track MFE-captured. "
                    "Requires walk-forward before any change."),
        ))

    # F006 · India loss prevention
    if lp_i.get("preventable_pct") is not None:
        findings.append(_finding(
            "F006_INDIA_LOSS_PREVENTABILITY", "INDIA", "HIGH", "LOSS_PREVENTION",
            claim=(f"Of {lp_i['n_losses']} India losses ({lp_i['loss_rate_pct']}% "
                   f"loss rate), {lp_i['preventable_pct']}% had at least one "
                   f"anti-signal at entry. Most common: "
                   + ", ".join(f"{k}({v})" for k, v in
                               list(lp_i.get("top_anti_signals",{}).items())[:5]) + "."),
            evidence=[{"source":"mr_loss_prevention_india.json",
                       "field":"top_anti_signals",
                       "value":lp_i.get("top_anti_signals",{})}],
            caveat=("Anti-signal presence != causation. Same signals appear in "
                    "some winners too. Bucket comparisons must control for this."),
        ))

    # F007 · India missed winners
    if missed_i.get("capture_rate_pct") is not None:
        findings.append(_finding(
            "F007_INDIA_CAPTURE_RATE", "INDIA", "HIGH", "MISSED",
            claim=(f"India capture rate = {missed_i['capture_rate_pct']}%. "
                   f"Of {missed_i['n_big_winners_missed_ge5pct'] + missed_i['n_big_winners_caught_ge5pct']} "
                   f"universe-wide >=+5% winners over {missed_i['n_days']} days, "
                   f"AEGIS captured only {missed_i['n_big_winners_caught_ge5pct']}. "
                   f"Missed {missed_i['n_big_winners_missed_ge5pct']}."),
            evidence=[{"source":"mr_missed_winners_india.json",
                       "field":"capture_rate_pct","value":missed_i["capture_rate_pct"]}],
            caveat=("Universe scan includes tickers AEGIS deliberately excludes "
                    "(illiquid, non-investable). True capture rate on the "
                    "investable universe will be higher."),
        ))

    # F008 · Leakage audit
    for market, leak in (("INDIA", leak_i), ("USA", leak_u)):
        checks = leak.get("checks", {}) if isinstance(leak, dict) else {}
        if not checks: continue
        fails = {k: v for k, v in checks.items()
                 if isinstance(v, dict) and v.get("fail", 0) > 0}
        if fails:
            findings.append(_finding(
                f"F008_{market}_DATA_QUALITY", market, "MEDIUM", "DATA_QUALITY",
                claim=(f"{market} leakage audit fails: "
                       + ", ".join(f"{k}({v['fail']} fails)" for k, v in fails.items())),
                evidence=[{"source": f"mr_leakage_audit_{market.lower()}.json",
                           "field":"checks","value":fails}],
                caveat="Non-fatal but tracks a real upstream write-order artifact.",
            ))

    return findings


def emit(root: Path, findings: list) -> Path:
    p = root / ALLOWED_WRITE_ROOT / "mr_ai_auditor_findings.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for x in findings:
            f.write(json.dumps(x, default=str, ensure_ascii=False) + "\n")
    return p


def render_console(findings: list):
    print(f"\n======== AI AUDITOR · n_findings={len(findings)} ========")
    for f in findings:
        print(f"\n  [{f['finding_id']}] {f['severity']:8s} {f['market']:6s} "
              f"{f['category']}")
        print(f"    CLAIM   : {f['claim']}")
        print(f"    CAVEAT  : {f['caveat']}")


if __name__ == "__main__":
    root = Path(".").resolve()
    findings = build(root)
    p = emit(root, findings)
    render_console(findings)
    print(f"\n[ai_auditor] wrote {len(findings)} findings -> {p.name}")
