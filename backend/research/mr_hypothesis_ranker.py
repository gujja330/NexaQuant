"""AEGIS · Sprint M-R · Hypothesis Ranker · Sprint M.

Consumes all M-R draft tickets and AI-auditor findings and produces a
SINGLE ranked shortlist of the top hypotheses that deserve forward
walk-forward validation next.

Ranking score (deterministic):
    priority_score = severity_pts * 3
                   + verdict_pts * 2
                   + evidence_pts * 1
                   + preventability_pts * 2

where
    severity_pts     = 5 CRITICAL / 4 HIGH / 3 MEDIUM / 2 LOW / 1 INFO
    verdict_pts      = 3 PRODUCTION_CANDIDATE / 2 INSUFFICIENT / 1 else
    evidence_pts     = 3 n>=500 / 2 n>=100 / 1 n>=20 / 0 else
    preventability_pts = 2 if the ticket touches a preventable-loss
                         mechanism (bumps compound value)

Emits reports/research/mr_hypothesis_shortlist.json with:
    ranked      · sorted list of hypotheses
    top_n       · configurable N (default 5)
    rationale   · why each survived / was dropped

Under M-R sandbox rules. No production changes.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_hypothesis_ranker.v0.1"
DEFAULT_TOP_N = 5

SEVERITY_PTS = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}
VERDICT_PTS = {
    "PRODUCTION_CANDIDATE":   3,
    "INSUFFICIENT_EVIDENCE":  2,
    "OBSERVATION_ONLY":       1,
}

PREVENTABILITY_KEYS = (
    "anti_signal", "top3_rank_inversion", "band_boundary",
    "confidence", "stop_policy", "loss_preventability",
    "regime",
)


def _load(root: Path, name: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _load_jsonl(root: Path, name: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / name
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _evidence_pts(n: int) -> int:
    if n >= 500: return 3
    if n >= 100: return 2
    if n >= 20:  return 1
    return 0


def _preventability_pts(ticket_id: str) -> int:
    lower = ticket_id.lower()
    return 2 if any(k in lower for k in PREVENTABILITY_KEYS) else 0


def _fetch_finding_severity(findings: list, ticket_id: str) -> str:
    """Best-effort map from ticket_id to AI Auditor severity."""
    lower = ticket_id.lower()
    for f in findings:
        fid_low = f.get("finding_id","").lower()
        if fid_low == lower: return f.get("severity", "MEDIUM")
    # Heuristic mapping
    if "negative_alpha" in lower: return "CRITICAL"
    if "confidence_anti_signal" in lower: return "HIGH"
    if "top3_rank_inversion" in lower: return "HIGH"
    if "loss_prevent" in lower: return "HIGH"
    if "capture_rate" in lower: return "HIGH"
    if "band_boundary" in lower: return "MEDIUM"
    if "stop_policy" in lower: return "MEDIUM"
    if "data_quality" in lower: return "MEDIUM"
    return "LOW"


def _load_tickets(root: Path) -> list:
    idx = _load(root, "tickets/INDEX.json")
    if not idx: return []
    tickets = idx.get("tickets", [])
    full = []
    for t in tickets:
        detail = _load(root, f"tickets/{t['ticket_id']}.json")
        if detail:
            full.append(detail)
        else:
            full.append(t)
    return full


def rank(root: Path, top_n: int = DEFAULT_TOP_N) -> dict:
    tickets = _load_tickets(root)
    findings = _load_jsonl(root, "mr_ai_auditor_findings.jsonl")

    if not tickets:
        return {
            "engine": ENGINE_ID, "generated_utc":
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "NO_TICKETS", "ranked": [], "top_n": top_n,
        }

    scored = []
    for t in tickets:
        tid = t.get("ticket_id","")
        market = t.get("market","")
        verdict = t.get("statistical_verdict") or ""
        n_ev = int(t.get("n_evidence") or 0)
        sev = _fetch_finding_severity(findings, tid)
        sev_pts = SEVERITY_PTS.get(sev, 1)
        ver_pts = VERDICT_PTS.get(verdict, 0)
        ev_pts = _evidence_pts(n_ev)
        pv_pts = _preventability_pts(tid)
        score = sev_pts * 3 + ver_pts * 2 + ev_pts * 1 + pv_pts * 2
        scored.append({
            "ticket_id":    tid,
            "market":       market,
            "title":        t.get("title",""),
            "n_evidence":   n_ev,
            "severity":     sev,
            "verdict":      verdict,
            "sev_pts":      sev_pts,
            "verdict_pts":  ver_pts,
            "evidence_pts": ev_pts,
            "preventability_pts": pv_pts,
            "score":        score,
            "hypothesis":   t.get("hypothesis",""),
            "expected_effect": t.get("expected_effect",""),
            "proposed_rule":  t.get("proposed_rule",""),
            "risk":           t.get("risk",""),
        })
    scored.sort(key=lambda r: -r["score"])
    for i, r in enumerate(scored, start=1):
        r["rank"] = i

    result = {
        "engine":         ENGINE_ID,
        "experiment_id":  EXPERIMENT_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_date": date.today().isoformat(),
        "top_n":          top_n,
        "n_tickets_considered": len(tickets),
        "ranked":         scored,
        "shortlist":      scored[:top_n],
        "rationale":      (
            "Score = severity*3 + verdict*2 + evidence*1 + preventability*2. "
            "Preventability bumps mechanisms that reduce future losses. "
            "n>=500 gets max evidence points. Never breaks a tie by title or "
            "market · ties keep original order."),
    }
    return result


def emit(root: Path, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / "mr_hypothesis_shortlist.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if res.get("status") == "NO_TICKETS":
        print("[hypothesis_ranker] no draft tickets found · run mr_research_ticket first")
        return
    print(f"\n======== HYPOTHESIS SHORTLIST · top-{res['top_n']} of "
          f"{res['n_tickets_considered']} ========")
    print(f"  {'rk':>2s}  {'score':>5s}  {'market':6s} {'severity':8s} "
          f"{'verdict':22s} {'n_evid':>6s}  title")
    for r in res["shortlist"]:
        print(f"  {r['rank']:>2d}  {r['score']:>5d}  {r['market']:6s} "
              f"{r['severity']:8s} {r['verdict']:22s} {r['n_evidence']:>6d}  "
              f"{r['title']}")
    print(f"\n  Rationale: {res['rationale']}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = ap.parse_args()
    root = Path(".").resolve()
    res = rank(root, args.top_n)
    p = emit(root, res)
    render_console(res)
    print(f"\n[hypothesis_ranker] wrote -> {p.name}")
