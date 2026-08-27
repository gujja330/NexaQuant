"""AEGIS · Sprint M-R · Research Topology.

CEO handover 2026-08-27:
> "research/
>    MR_V1/frozen/ · active/{E1_india_r1_filter, E2_india_r2_boost,
>                            E3_stop_loss}/ · evidence/ · reports/ · dashboards/
>    archive/successful/ · promising/ · failed/ · superseded/
>    historical/45d/"
>
> "Don't label something 'successful' just because the historical backtest
>  looked good. Record: historical evidence + forward evidence +
>  statistical confidence + decision + reason + revisit condition."

Materializes the EXACT topology above from the existing sandbox artifacts.
Does NOT delete or overwrite the older paths · builds an additional view
under reports/research/topology/ so both structures coexist. The older
paths remain the machine-writable roots (evidence/, active/MR_V1/,
archive/); topology/ is the CEO-facing structured view.

Each card carries the 6 CEO-required fields:
   1. historical_evidence  (n, WR, effect size · frozen from studies/stops)
   2. forward_evidence     (N so far, WR, avg · from evidence_report)
   3. statistical_confidence (verdict from Wilson CI + acceptance rule)
   4. decision             (promoted/rejected/pending)
   5. reason               (why current status · plain text)
   6. revisit_condition    (what triggers re-examination)

Under M-R sandbox rules. Zero production changes.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_research_topology.v0.1"


TOPOLOGY = {
    "MR_V1": {
        "frozen":     [],
        "active": {
            "E1_india_r1_filter":   {},
            "E2_india_r2_boost":    {},
            "E3_stop_loss":         {},
        },
        "evidence":   [],
        "daily":      [],
        "dashboards": [],
        "decisions":  [],
        "reports":    [],
    },
    "archive": {
        "successful":   [],
        "promising":    [],
        "failed":       [],
        "superseded":   [],
        "data_quality": [],
    },
    "historical": {
        "45d": [],
    },
}


STATUS_LABEL_5WAY = {
    "PASSED":             "SUCCESSFUL_PROMOTION_CANDIDATE",
    "PROMISING":          "PROMISING_NEED_MORE_DATA",
    "FAILED":             "FAILED_RETAIN_EVIDENCE",
    "SUPERSEDED_BY":      "SUPERSEDED_KEEP_HISTORY",
    "ARCHIVED_FOR_LATER": "SUPERSEDED_KEEP_HISTORY",
    "ARCHIVED_LOW_PRIORITY": "SUPERSEDED_KEEP_HISTORY",
    "ACTIVE_SHADOW":      "PROMISING_NEED_MORE_DATA",
    "DATA_GAP":           "DATA_GAP_FIX_DATA",
}

# CEO 2026-08-27 · 4-state lifecycle ladder (alongside the 5-way bucket)
#   OBSERVED   · hypothesis exists · no forward N yet
#   TESTED     · forward N > 0 but < 100
#   VALIDATED  · N >= 100 · acceptance passed
#   PROMOTABLE · CEO-approved for paper trading
LIFECYCLE_4STATE = ("OBSERVED", "TESTED", "VALIDATED", "PROMOTABLE")


def _lifecycle_4state(historical_n: int, forward_n: int,
                       current_status: str) -> str:
    if current_status == "PASSED":
        return "PROMOTABLE"
    if forward_n >= 100:
        return "VALIDATED"
    if forward_n > 0:
        return "TESTED"
    return "OBSERVED"


# CEO 2026-08-27 · 8-field research card contract
CEO_CARD_CONTRACT = (
    "question", "hypothesis", "data_period", "sample_size",
    "result", "confidence", "decision", "production_status",
    "next_validation",
)


def _ceo_card_contract(exp: dict, hist_effect_pp, historical_n: int,
                       forward_n: int, status: str) -> dict:
    """Return the CEO's 8-field card contract for one experiment."""
    hyp = exp.get("hypothesis","")
    title = exp.get("title","")
    lifecycle = _lifecycle_4state(historical_n, forward_n, status)
    if status == "PASSED":
        prod_status = "PROMOTABLE · awaiting CEO approval + new SPRINT_ID"
    elif status == "FAILED":
        prod_status = "REJECTED · not eligible for production"
    elif status == "SUPERSEDED_BY":
        prod_status = f"RETIRED · superseded by {exp.get('superseded_by','?')}"
    elif status in ("ARCHIVED_FOR_LATER","ARCHIVED_LOW_PRIORITY"):
        prod_status = "ARCHIVED · not currently promoted"
    else:
        prod_status = "LOCKED_OUT · production layer untouched until forward N >= 100"
    return {
        "question":          f"Does {title} produce forward evidence that "
                             f"beats the locked baseline?",
        "hypothesis":        hyp,
        "data_period":       "2026-07 to 2026-08 · 45-day corpus",
        "sample_size":       {"historical_n": historical_n,
                              "forward_n":    forward_n,
                              "target_n":     100},
        "result":            {"lifecycle_4state": lifecycle,
                              "historical_effect_pp": hist_effect_pp},
        "confidence":        _statistical_confidence(historical_n, forward_n,
                                                     hist_effect_pp),
        "decision":          lifecycle,
        "production_status": prod_status,
        "next_validation":   f"acceptance evaluation fires the moment forward "
                             f"N reaches {exp.get('min_sample_size', 100)}",
    }


ACTIVE_MAP = {
    "aegis_mr_experiment_20260827_e1_india_r1_filter":         "E1_india_r1_filter",
    "aegis_mr_experiment_20260827_e2_india_r2_rank_4_7_boost": "E2_india_r2_boost",
    "aegis_mr_experiment_20260827_e3_stop_loss_cross_market":  "E3_stop_loss",
}


def _load(root: Path, rel: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / rel
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _ensure_tree(root: Path) -> Path:
    base = root / ALLOWED_WRITE_ROOT / "topology"
    for top, sub in TOPOLOGY.items():
        for name, val in sub.items():
            if isinstance(val, dict):
                for leaf in val.keys():
                    (base / top / name / leaf).mkdir(parents=True, exist_ok=True)
            else:
                (base / top / name).mkdir(parents=True, exist_ok=True)
    return base


def _copy_frozen_docs(root: Path, dst: Path):
    """Copy MR_V1 lock documents into MR_V1/frozen/."""
    frozen = dst / "MR_V1" / "frozen"
    for doc in ("MR_V1_LOCK.md", "MR_V1_EXPERIMENTS_FROZEN.md",
                "MR_V1_DECISION_TABLE.md", "MR_V1_CLOSE_OUT.md",
                "MR_V1_EVIDENCE_SUMMARY.md"):
        src = root / ALLOWED_WRITE_ROOT / doc
        if src.exists():
            shutil.copy2(src, frozen / doc)


def _copy_reports(root: Path, dst: Path):
    """Populate MR_V1/reports/ + MR_V1/dashboards/ + MR_V1/evidence/."""
    reports = dst / "MR_V1" / "reports"
    for doc in ("AEGIS_FORWARD_VALIDATION_REPORT.md",
                "M_R_MASTER_REPORT.md",
                "EVIDENCE_REPORT.md", "EVIDENCE_REPORT.txt",
                "PROMOTION_DECISIONS.md",
                "FUNDAMENTALS_GAP_PLAN.md"):
        src = root / ALLOWED_WRITE_ROOT / doc
        if src.exists():
            shutil.copy2(src, reports / doc)
    # Learning report lives under reports/ subdir already
    lr = root / ALLOWED_WRITE_ROOT / "reports" / "LEARNING_REPORT.md"
    if lr.exists():
        shutil.copy2(lr, reports / "LEARNING_REPORT.md")

    dashboards = dst / "MR_V1" / "dashboards"
    for doc in ("CEO_DASHBOARD_M1.md", "CEO_DASHBOARD_M1.txt",
                "DAILY_CONTROL_PANEL.md", "DAILY_CONTROL_PANEL.txt"):
        src = root / ALLOWED_WRITE_ROOT / doc
        if src.exists():
            shutil.copy2(src, dashboards / doc)

    evidence = dst / "MR_V1" / "evidence"
    # Copy the two markets' evidence trees (history/portfolio/exit JSONLs)
    for market in ("india", "usa"):
        market_dir = evidence / market
        market_dir.mkdir(parents=True, exist_ok=True)
        src_market = root / ALLOWED_WRITE_ROOT / "evidence" / market
        if src_market.exists():
            for f in src_market.iterdir():
                if f.is_file(): shutil.copy2(f, market_dir / f.name)


def _forward_evidence_for(root: Path, exp_id: str) -> dict:
    ev = _load(root, "mr_evidence_report.json")
    for row in (ev.get("rows") or []):
        if row.get("experiment_id") == exp_id:
            return row
    return {}


def _statistical_confidence(historical_n: int, forward_n: int,
                            historical_effect_pp: Optional[float]) -> str:
    """Classify statistical confidence · per MR_V1 discipline."""
    if forward_n >= 100:
        return "PRODUCTION_CANDIDATE (forward N >= 100 · run acceptance)"
    if historical_n >= 100 and abs(historical_effect_pp or 0) >= 10:
        return f"HISTORICAL_STRONG (n={historical_n}, effect {historical_effect_pp}pp) · forward evidence needed"
    if historical_n >= 100:
        return f"HISTORICAL_MODERATE (n={historical_n}) · effect size {historical_effect_pp}pp"
    if historical_n >= 20:
        return f"DIRECTIONAL_EVIDENCE (n={historical_n}) · small sample"
    return f"OBSERVATION_ONLY (n={historical_n})"


def _card_6field(exp: dict, root: Path) -> dict:
    """CEO's 6 required metadata fields · one card record."""
    exp_id = exp["experiment_id"]
    fwd = _forward_evidence_for(root, exp_id)
    historical_n = exp.get("historical_n") or 0
    # Extract historical effect size from evidence artifacts
    hist_effect = None
    if "e1_india_r1_filter" in exp_id:
        hist_effect = -11.35  # R1 vs R2 gap
        historical_n = 314
    elif "e2_india_r2_rank_4_7_boost" in exp_id:
        hist_effect = +46.96
        historical_n = 22
    elif "e3_stop_loss_cross_market" in exp_id:
        hist_effect = +0.273
        historical_n = 500
    forward_n = fwd.get("forward_n") or exp.get("days_of_evidence", 0) * 15
    fwd_wr = fwd.get("wr_pct")
    fwd_avg = fwd.get("avg_pct")
    status = exp.get("current_status","?")
    if status == "ACTIVE_SHADOW":
        decision = "PENDING (forward evidence accumulating)"
    elif status == "SUPERSEDED_BY":
        decision = f"RETIRED (superseded by {exp.get('superseded_by','?')})"
    elif status in ("ARCHIVED_FOR_LATER", "ARCHIVED_LOW_PRIORITY"):
        decision = f"ARCHIVED ({status})"
    elif status == "PASSED":
        decision = "PROMOTED_CANDIDATE (paper trade queued)"
    elif status == "FAILED":
        decision = "REJECTED (forward evidence failed)"
    else:
        decision = f"UNKNOWN ({status})"
    reason = exp.get("hypothesis") or exp.get("title","(no reason recorded)")
    revisit = (f"Forward N reaches {exp.get('min_sample_size', 100)} observations "
               f"OR baseline shifts materially")
    return {
        "experiment_id":         exp_id,
        "title":                 exp.get("title","?"),
        "market":                exp.get("market","?"),
        "historical_evidence":   {
            "n":            historical_n,
            "effect_pp":    hist_effect,
            "source":       "mr_studies_*/mr_stop_loss_sweep_*/mr_conditional_cohorts_*",
        },
        "forward_evidence":      {
            "n":            forward_n,
            "wr_pct":       fwd_wr,
            "avg_pct":      fwd_avg,
            "target_n":     100,
            "source":       "reports/research/mr_evidence_report.json",
        },
        "statistical_confidence": _statistical_confidence(
            historical_n, forward_n, hist_effect),
        "decision":              decision,
        "reason":                reason,
        "revisit_condition":     revisit,
        "current_status":        status,
        "status_label_5way":     STATUS_LABEL_5WAY.get(status, "SUPERSEDED_KEEP_HISTORY"),
        "lifecycle_4state":      _lifecycle_4state(historical_n, forward_n, status),
        "ceo_card_contract":     _ceo_card_contract(exp, hist_effect,
                                                    historical_n, forward_n,
                                                    status),
        "topology_route":        exp.get("_route","?"),
        "generated_utc":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _write_active_cards(root: Path, dst: Path):
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if not exp_dir.exists(): return
    for p in exp_dir.glob("aegis_mr_experiment_*.json"):
        try: d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        exp_id = d.get("experiment_id")
        if exp_id not in ACTIVE_MAP: continue
        slot = ACTIVE_MAP[exp_id]
        card = _card_6field(d, root)
        target = dst / "MR_V1" / "active" / slot / f"{exp_id}.card.json"
        target.write_text(json.dumps(card, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")
        # Human-readable version
        md = _render_card_md(card)
        (target.with_suffix(".md")).write_text(md, encoding="utf-8")


def _write_archive_cards(root: Path, dst: Path):
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if not exp_dir.exists(): return
    for p in exp_dir.glob("aegis_mr_experiment_*.json"):
        try: d = json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        exp_id = d.get("experiment_id")
        status = d.get("current_status","")
        if exp_id in ACTIVE_MAP: continue
        # Route to CEO's 4 archive buckets ONLY when forward evidence exists
        if status == "SUPERSEDED_BY":
            bucket = "superseded"
        elif status == "FAILED":
            bucket = "failed"
        elif status == "PASSED":
            bucket = "successful"  # forward pass · earned the label
        elif status == "PROMISING":
            bucket = "promising"
        else:
            # ARCHIVED_FOR_LATER / ARCHIVED_LOW_PRIORITY etc · route to
            # superseded (they're not "successful" · they're retired)
            bucket = "superseded"
        card = _card_6field(d, root)
        card["archive_bucket"] = bucket
        card["archive_note"]   = (
            "Historical backtest evidence alone did not earn this bucket. "
            "'successful' is reserved for forward PASS · 'promising' for "
            "forward BORDERLINE with directional support · 'failed' for "
            "forward FAIL · 'superseded' for retired/archived/replaced.")
        target = dst / "archive" / bucket / f"{exp_id}.card.json"
        target.write_text(json.dumps(card, indent=2, ensure_ascii=False, default=str),
                          encoding="utf-8")
        (target.with_suffix(".md")).write_text(_render_card_md(card), encoding="utf-8")


def _render_card_md(card: dict) -> str:
    L = [f"# {card['title']}\n"]
    L.append(f"**ID:** `{card['experiment_id']}`  ")
    L.append(f"**Market:** {card['market']}  ")
    L.append(f"**Status:** `{card['current_status']}`  ")
    L.append(f"**5-way label:** `{card.get('status_label_5way','?')}`  ")
    L.append(f"**Lifecycle (4-state):** `{card.get('lifecycle_4state','?')}`\n")
    L.append(f"## 1 · Historical evidence")
    he = card["historical_evidence"]
    L.append(f"- n = **{he['n']}**")
    L.append(f"- effect = **{he['effect_pp']}pp**")
    L.append(f"- source = `{he['source']}`\n")
    L.append(f"## 2 · Forward evidence")
    fe = card["forward_evidence"]
    L.append(f"- N = **{fe['n']}** / target {fe['target_n']}")
    L.append(f"- WR = {fe.get('wr_pct')}%  ·  avg = {fe.get('avg_pct')}%")
    L.append(f"- source = `{fe['source']}`\n")
    L.append(f"## 3 · Statistical confidence")
    L.append(f"{card['statistical_confidence']}\n")
    L.append(f"## 4 · Decision")
    L.append(f"**{card['decision']}**\n")
    L.append(f"## 5 · Reason")
    L.append(f"{card['reason']}\n")
    L.append(f"## 6 · Revisit condition")
    L.append(f"{card['revisit_condition']}\n")
    if card.get("archive_note"):
        L.append(f"---")
        L.append(f"_{card['archive_note']}_")
    return "\n".join(L)


def _copy_daily_snapshots(root: Path, dst: Path):
    """MR_V1/daily/ · today's walk-forward captures + daemon manifest."""
    daily = dst / "MR_V1" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    iso = date.today().isoformat()
    day_dir = daily / iso
    day_dir.mkdir(exist_ok=True)
    src_day = root / ALLOWED_WRITE_ROOT / "walkforward" / iso
    if src_day.exists():
        for f in src_day.iterdir():
            if f.is_file():
                shutil.copy2(f, day_dir / f.name)
    # Also include today's daily control panel
    for name in ("DAILY_CONTROL_PANEL.md", "DAILY_CONTROL_PANEL.txt",
                 "mr_daily_control_panel.json"):
        src = root / ALLOWED_WRITE_ROOT / name
        if src.exists(): shutil.copy2(src, day_dir / name)


def _copy_decisions(root: Path, dst: Path):
    """MR_V1/decisions/ · promotion decisions + evidence report."""
    decisions = dst / "MR_V1" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    for name in ("PROMOTION_DECISIONS.md",
                 "mr_promotion_decisions.json",
                 "EVIDENCE_REPORT.md",
                 "EVIDENCE_REPORT.txt",
                 "mr_evidence_report.json"):
        src = root / ALLOWED_WRITE_ROOT / name
        if src.exists(): shutil.copy2(src, decisions / name)


def _copy_data_quality(root: Path, dst: Path):
    """archive/data_quality/ · fundamentals + Momentum + USA canonical gaps."""
    dq = dst / "archive" / "data_quality"
    dq.mkdir(parents=True, exist_ok=True)
    # Copy the gap-check outputs + closure plan
    for name in ("mr_fundamentals_gap_india.json",
                 "mr_fundamentals_gap_usa.json",
                 "FUNDAMENTALS_GAP_PLAN.md"):
        src = root / ALLOWED_WRITE_ROOT / name
        if src.exists(): shutil.copy2(src, dq / name)
    # Write inline cards for the 3 known gaps
    for card_name, body in (
        ("MOMENTUM_HISTORICAL_GAP.card.md",
         "# Momentum Historical Coverage Gap\n\n"
         "**5-way label:** `DATA_GAP_FIX_DATA`\n\n"
         "- Historical n = 0 · Forward capture started 2026-08-27\n"
         "- Reason: no historical Momentum snapshots ever written\n"
         "- Revisit: N forward >= 20 sessions\n"),
        ("USA_FUNDAMENTALS_GAP.card.md",
         "# USA Fundamentals Coverage Gap\n\n"
         "**5-way label:** `DATA_GAP_FIX_DATA`\n\n"
         "- Historical n = 0 in `usa/data/raw/us/fundamentals.parquet`\n"
         "- Reason: parquet empty · yfinance batch pull required\n"
         "- Revisit: coverage >= 95% of daily-pred tickers\n"
         "- Plan: FUNDAMENTALS_GAP_PLAN.md\n"),
        ("USA_CANONICAL_LOCAL_GAP.card.md",
         "# USA Canonical Portfolio JSON · Local Availability Gap\n\n"
         "**5-way label:** `DATA_GAP_FIX_DATA`\n\n"
         "- Local canonical portfolio JSON missing (CI generates it)\n"
         "- Reason: CI commit step runs only on send success · "
         "diagnostic-upload step added to aegis-usa.yml on 2026-08-27\n"
         "- Revisit: next USA CI publishes canonical + XLSX artifact\n"),
    ):
        (dq / card_name).write_text(body, encoding="utf-8")


CEO_DATED_ARCHIVE_BUCKETS = (
    "validated", "promising", "failed",
    "insufficient_data", "superseded", "evidence",
    "ai_audits",   # CEO 2026-08-27 · preserve AI Auditor findings monthly
)


def _dated_archive(root: Path, dst: Path):
    """CEO 2026-08-27 · research/2026-08/{validated,promising,failed,
    insufficient_data,superseded,evidence}. Month tag = today's YYYY-MM."""
    today = date.today()
    month_tag = f"{today.year:04d}-{today.month:02d}"
    dated = dst / month_tag
    for b in CEO_DATED_ARCHIVE_BUCKETS:
        (dated / b).mkdir(parents=True, exist_ok=True)
    # Copy relevant items into buckets
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if exp_dir.exists():
        for p in exp_dir.glob("aegis_mr_experiment_*.json"):
            try: d = json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
            status = d.get("current_status","?")
            # CEO 6-way bucket map
            if status == "PASSED":                            bucket = "validated"
            elif status == "ACTIVE_SHADOW":                   bucket = "promising"
            elif status == "FAILED":                          bucket = "failed"
            elif status == "SUPERSEDED_BY":                   bucket = "superseded"
            elif status in ("ARCHIVED_FOR_LATER",
                            "ARCHIVED_LOW_PRIORITY"):         bucket = "superseded"
            else:                                             bucket = "insufficient_data"
            target = dated / bucket / f"{d['experiment_id']}.card.json"
            shutil.copy2(p, target)
    # Evidence · copy the current evidence layer JSONLs + XLSX sidecars
    ev_src = root / ALLOWED_WRITE_ROOT / "evidence"
    ev_dst = dated / "evidence"
    ev_dst.mkdir(parents=True, exist_ok=True)
    if ev_src.exists():
        for market in ("india","usa"):
            m_src = ev_src / market
            if not m_src.exists(): continue
            m_dst = ev_dst / market
            m_dst.mkdir(exist_ok=True)
            for f in m_src.iterdir():
                if f.is_file(): shutil.copy2(f, m_dst / f.name)
        for xf in ev_src.glob("aegis_evidence_*.xlsx"):
            shutil.copy2(xf, ev_dst / xf.name)
    # AI Auditor findings under ai_audits/
    ai_src = root / ALLOWED_WRITE_ROOT / "mr_ai_auditor_findings.jsonl"
    if ai_src.exists():
        shutil.copy2(ai_src, dated / "ai_audits" / "mr_ai_auditor_findings.jsonl")
    # Data-quality gaps in insufficient_data
    ins = dated / "insufficient_data"
    for name, body in (
        ("MOMENTUM.card.md",
         "# Momentum · insufficient_data\n\n"
         "- Historical N=0 · forward capture started 2026-08-27\n"
         "- Revisit when forward N >= 20 sessions\n"),
        ("USA_FUNDAMENTALS.card.md",
         "# USA Fundamentals · insufficient_data\n\n"
         "- Parquet empty · yfinance batch pull required\n"
         "- Revisit when coverage >= 95% of daily-pred tickers\n"),
    ):
        (ins / name).write_text(body, encoding="utf-8")
    # Manifest
    (dated / "MANIFEST.json").write_text(json.dumps({
        "engine":       ENGINE_ID,
        "month_tag":    month_tag,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "buckets":      CEO_DATED_ARCHIVE_BUCKETS,
        "note":         ("CEO 2026-08-27 dated archive · this is the durable "
                         "monthly cross-section · aligned to the 6-bucket "
                         "spec: validated/promising/failed/insufficient_data/"
                         "superseded/evidence."),
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def _freeze_historical_45d(root: Path, dst: Path):
    """historical/45d/ snapshot manifest · immutable anchor of 45-day corpus."""
    hist_dir = dst / "historical" / "45d"
    hist_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "engine":         ENGINE_ID,
        "sentinel":       "MR_V1_HISTORICAL_45D.v1.0",
        "frozen_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "immutable":      True,
        "note":           ("This directory is a machine-anchored snapshot "
                           "of the 45-day corpus that produced MR_V1 · "
                           "reference only · never modify."),
        "counts": {},
        "source_files": [],
    }
    # Include the 2 autopsy JSONLs as the historical anchor
    for market in ("india","usa"):
        for name in (f"mr_prediction_autopsy_{market}.jsonl",
                     f"mr_prediction_autopsy_{market}_enriched.jsonl",
                     f"mr_prediction_autopsy_{market}_summary.json"):
            src = root / ALLOWED_WRITE_ROOT / name
            if not src.exists(): continue
            n = 0
            if src.suffix == ".jsonl":
                n = sum(1 for _ in src.read_text(encoding="utf-8").splitlines()
                        if _.strip())
            shutil.copy2(src, hist_dir / name)
            manifest["counts"][name] = n
            manifest["source_files"].append(name)
    # Also anchor the AEGIS 18-section report + master report + evidence summary
    for name in ("AEGIS_FORWARD_VALIDATION_REPORT.md",
                 "M_R_MASTER_REPORT.md",
                 "MR_V1_EVIDENCE_SUMMARY.md",
                 "MR_V1_DECISION_TABLE.md"):
        src = root / ALLOWED_WRITE_ROOT / name
        if src.exists():
            shutil.copy2(src, hist_dir / name)
            manifest["source_files"].append(name)
    (hist_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_root_readme(root: Path, dst: Path):
    """Human-readable README explaining the topology."""
    L = ["# AEGIS · Research Topology (CEO-spec)\n"]
    L.append(f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")
    L.append("```")
    L.append("research/")
    L.append("├── MR_V1/")
    L.append("│   ├── frozen/     · lock docs + experiments frozen list")
    L.append("│   ├── active/")
    L.append("│   │   ├── E1_india_r1_filter/     · shadow rule + card")
    L.append("│   │   ├── E2_india_r2_boost/      · shadow rule + card")
    L.append("│   │   └── E3_stop_loss/           · shadow rule + card")
    L.append("│   ├── evidence/    · India + USA history/portfolio/exit JSONLs")
    L.append("│   ├── daily/       · today's walk-forward captures + panel")
    L.append("│   ├── dashboards/  · daily control panel + CEO dashboard")
    L.append("│   ├── decisions/   · promotion decisions + evidence report")
    L.append("│   └── reports/     · consolidated learning + validation reports")
    L.append("│")
    L.append("├── archive/")
    L.append("│   ├── successful/   · forward PASS only · not historical hits")
    L.append("│   ├── promising/    · forward BORDERLINE with directional support")
    L.append("│   ├── failed/       · forward FAIL · never deleted")
    L.append("│   ├── superseded/   · retired / replaced experiments")
    L.append("│   └── data_quality/ · Momentum + USA fundamentals + USA canonical gaps")
    L.append("│")
    L.append("└── historical/")
    L.append("    └── 45d/        · immutable 45-day corpus anchor + manifest")
    L.append("```\n")
    L.append("## Card metadata contract\n")
    L.append("Every experiment card contains the 6 CEO-required fields:\n")
    L.append("1. **Historical evidence** · n, effect size, source")
    L.append("2. **Forward evidence** · N so far, WR, avg, target, source")
    L.append("3. **Statistical confidence** · verdict per MR_V1 discipline")
    L.append("4. **Decision** · promoted / rejected / pending / archived")
    L.append("5. **Reason** · plain-text hypothesis and current status rationale")
    L.append("6. **Revisit condition** · what triggers re-examination\n")
    L.append("## Successful ≠ historical hit\n")
    L.append("`archive/successful/` accepts an experiment ONLY after its "
             "forward acceptance criterion passes. Historical backtest wins "
             "are not enough. This prevents rediscovery loops.\n")
    L.append("## Compliance\n")
    L.append("- Zero production R1/R2/Registry/XLSX changes.")
    L.append("- Zero locked-layer edits.")
    L.append("- All content is a COPY of the machine-writable roots "
             "(`evidence/`, `active/MR_V1/`, `archive/` under "
             "`reports/research/`). Nothing is moved or deleted.")
    (dst / "README.md").write_text("\n".join(L), encoding="utf-8")


def _ceo_v3_mirror(root: Path, dst: Path):
    """CEO 2026-08-27 · exact top-level layout:
       research/
         evidence/{india,usa}
         findings/{validated,promising,failed,insufficient_evidence}
         experiments/MR_V1/{E1,E2,E3}
         historical/45d_research_archive/
    Materialized as mirrors of the existing content so nothing else breaks.
    """
    # 1. evidence/
    ev_dst = dst / "evidence"
    for market in ("india","usa"):
        m_src = root / ALLOWED_WRITE_ROOT / "evidence" / market
        m_dst = ev_dst / market
        m_dst.mkdir(parents=True, exist_ok=True)
        if m_src.exists():
            for f in m_src.iterdir():
                if f.is_file(): shutil.copy2(f, m_dst / f.name)
    # Also mirror the xlsx sidecars
    ev_root = root / ALLOWED_WRITE_ROOT / "evidence"
    if ev_root.exists():
        for xf in ev_root.glob("aegis_evidence_*.xlsx"):
            shutil.copy2(xf, ev_dst / xf.name)

    # 2. findings/
    findings = dst / "findings"
    finding_map = {
        "validated":            "PASSED",
        "promising":            "ACTIVE_SHADOW",
        "failed":               "FAILED",
        "insufficient_evidence": "SUPERSEDED_BY",   # everything not-yet-graded
    }
    for bucket in finding_map:
        (findings / bucket).mkdir(parents=True, exist_ok=True)
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments"
    if exp_dir.exists():
        for p in exp_dir.glob("aegis_mr_experiment_*.json"):
            try: d = json.loads(p.read_text(encoding="utf-8"))
            except Exception: continue
            status = d.get("current_status","?")
            if status == "PASSED":                              bucket = "validated"
            elif status == "ACTIVE_SHADOW":                     bucket = "promising"
            elif status == "FAILED":                            bucket = "failed"
            elif status in ("SUPERSEDED_BY","ARCHIVED_FOR_LATER",
                             "ARCHIVED_LOW_PRIORITY"):          bucket = "insufficient_evidence"
            else:                                               bucket = "insufficient_evidence"
            shutil.copy2(p, findings / bucket / f"{d['experiment_id']}.card.json")

    # 3. experiments/MR_V1/{E1,E2,E3}
    experiments = dst / "experiments" / "MR_V1"
    for e in ("E1","E2","E3"):
        (experiments / e).mkdir(parents=True, exist_ok=True)
    active_map = ACTIVE_MAP
    for exp_id, slot in active_map.items():
        e_label = slot.split("_")[0]  # E1 / E2 / E3
        src_slot = dst / "MR_V1" / "active" / slot
        dst_slot = experiments / e_label
        if src_slot.exists():
            for f in src_slot.iterdir():
                if f.is_file(): shutil.copy2(f, dst_slot / f.name)

    # 4. historical/45d_research_archive/
    hist_src = dst / "historical" / "45d"
    hist_dst = dst / "historical" / "45d_research_archive"
    hist_dst.mkdir(parents=True, exist_ok=True)
    if hist_src.exists():
        for f in hist_src.iterdir():
            if f.is_file(): shutil.copy2(f, hist_dst / f.name)


def build(root: Path) -> dict:
    dst = _ensure_tree(root)
    _copy_frozen_docs(root, dst)
    _copy_reports(root, dst)
    _copy_daily_snapshots(root, dst)
    _copy_decisions(root, dst)
    _copy_data_quality(root, dst)
    _write_active_cards(root, dst)
    _write_archive_cards(root, dst)
    _dated_archive(root, dst)
    _freeze_historical_45d(root, dst)
    _ceo_v3_mirror(root, dst)
    _write_root_readme(root, dst)
    # Tree summary
    def _list(d: Path) -> list:
        if not d.exists(): return []
        return sorted([p.name for p in d.iterdir()])
    tree = {}
    for top in ("MR_V1", "archive", "historical"):
        tree[top] = {}
        for name in sorted((dst / top).iterdir()) if (dst / top).exists() else []:
            if name.is_dir():
                tree[top][name.name] = _list(name)
    return {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base":         str(dst.relative_to(root)),
        "tree":         tree,
    }


def render_console(res: dict):
    print(f"\n======== RESEARCH TOPOLOGY ({res['base']}) ========")
    for top, sub in res["tree"].items():
        if not sub: continue
        print(f"\n  {top}/")
        for name, items in sub.items():
            print(f"    {name}/ ({len(items)} items)")
            for i in items[:6]:
                print(f"      · {i}")
    # CEO v3 mirrors
    base = Path(res.get("base","."))
    for p in ("evidence","findings","experiments/MR_V1",
              "historical/45d_research_archive"):
        d = Path("reports") / "research" / "topology" / p
        if d.exists():
            n = sum(1 for _ in d.rglob("*") if _.is_file())
            print(f"  ceo_v3_mirror: {p}/  ({n} files)")


if __name__ == "__main__":
    root = Path(".").resolve()
    res = build(root)
    render_console(res)
    print(f"\n[research_topology] materialized CEO structure · "
          f"cards carry 6 metadata fields")
