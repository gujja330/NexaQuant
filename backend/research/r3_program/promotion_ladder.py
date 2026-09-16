"""R3 PROMOTION LADDER — the path from discovery to production, as machinery.

WHY THIS IS CODE AND NOT A DOCUMENT
-----------------------------------
"When does a discovery become part of the pipeline" has been a conversation.
A conversation cannot be failed. This module turns the ladder into an artifact
that returns a verdict, so a discovery's status is computed from its evidence
rather than argued for.

    DISCOVERY -> REPEATABILITY -> TEMPORAL -> ROBUSTNESS -> INCREMENTAL
    -> DECISION -> ECONOMICS -> SHADOW -> AUTHORIZATION -> INTEGRATION

Two properties matter more than the list itself.

FIRST, the ladder is STRICTLY SEQUENTIAL. Gate n is not evaluated unless gate
n-1 passed. This is deliberate: it is exactly how the market-memory wave nearly
went wrong. India's twin residual passed robustness and looked promising, but
the twins it was computed over had failed the stability gate underneath it. A
scorecard would have shown "4 of 7 green" and invited a judgement call. A ladder
shows HALTED AT REPEATABILITY and there is nothing to argue about.

SECOND, gates 9 and 10 are NOT computable. AUTHORIZATION is a human act and
INTEGRATION follows from it. No evidence, however strong, can set them - the
ladder can only ever conclude READY_FOR_AUTHORIZATION and stop. That boundary
is the whole governance model, so it is enforced in code rather than remembered.

A defect fix (CANON-1/2/3, SECTOR-1/2) does NOT travel this ladder. It is an
engineering authorization, not a discovery, and mixing the two queues would let
a bug fix borrow the credibility of a research result or vice versa.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Callable, Optional

SCHEMA_VERSION = "aegis.r3.promotion_ladder.v1"

# Gate 9 and 10 are human acts. Nothing in this module may set them.
HUMAN_GATES = ("AUTHORIZATION", "INTEGRATION")

GATES = (
    ("DISCOVERY", "Did AI discover non-random structure?"),
    ("REPEATABILITY", "Does it recur across historical periods?"),
    ("TEMPORAL", "Does it survive chronological / OOS testing?"),
    ("ROBUSTNESS", "Does it survive ticker / date / regime perturbation?"),
    ("INCREMENTAL", "Does it add information beyond R2?"),
    ("DECISION", "Does it improve actual R2 decisions?"),
    ("ECONOMICS", "Does the improvement survive costs and turnover?"),
    ("SHADOW", "Does it behave correctly beside live R2 without controlling it?"),
    ("AUTHORIZATION", "Explicit human approval"),
    ("INTEGRATION", "Entry into the major pipeline"),
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NOT_REACHED = "NOT_REACHED"
STATUS_BLOCKED = "BLOCKED_INSUFFICIENT_EVIDENCE"
STATUS_HUMAN = "REQUIRES_HUMAN_ACT"


@dataclass
class GateResult:
    gate: str
    question: str
    status: str
    evidence: Optional[dict] = None
    reason: str = ""


@dataclass
class LadderResult:
    schema_version: str
    discovery_id: str
    market: str
    evaluated_utc: str
    gates: list
    highest_gate_passed: Optional[str]
    halted_at: Optional[str]
    verdict: str
    can_enter_pipeline: bool = False
    queue: str = "RESEARCH_DISCOVERY"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gates"] = [asdict(g) if not isinstance(g, dict) else g for g in self.gates]
        return d


def evaluate(discovery_id: str, market: str, checks: dict) -> LadderResult:
    """Walk the ladder in order and stop at the first gate that is not passed.

    `checks` maps a gate name to either a bool, or a dict carrying at least
    {"passed": bool} plus whatever evidence supports it. A gate with no entry is
    BLOCKED_INSUFFICIENT_EVIDENCE rather than a silent pass - the absence of a
    measurement is never evidence of one.
    """
    results: list[GateResult] = []
    halted: Optional[str] = None
    highest: Optional[str] = None

    for name, question in GATES:
        if halted is not None:
            results.append(GateResult(name, question, STATUS_NOT_REACHED))
            continue

        if name in HUMAN_GATES:
            results.append(GateResult(
                name, question, STATUS_HUMAN,
                reason=("This gate is a human act. No computed evidence can set "
                        "it, and this module will never report it as passed.")))
            halted = name
            continue

        raw = checks.get(name)
        if raw is None:
            results.append(GateResult(
                name, question, STATUS_BLOCKED,
                reason="No measurement was supplied for this gate."))
            halted = name
            continue

        if isinstance(raw, bool):
            passed, evidence, reason = raw, None, ""
        else:
            passed = bool(raw.get("passed"))
            evidence = {k: v for k, v in raw.items() if k not in ("passed", "reason")}
            reason = str(raw.get("reason", ""))

        if passed:
            results.append(GateResult(name, question, STATUS_PASS, evidence, reason))
            highest = name
        else:
            results.append(GateResult(name, question, STATUS_FAIL, evidence, reason))
            halted = name

    if halted in HUMAN_GATES:
        verdict = "READY_FOR_AUTHORIZATION"
    elif halted is None:
        # unreachable by construction; the human gates always halt the walk
        verdict = "READY_FOR_AUTHORIZATION"
    else:
        verdict = "HALTED_AT_%s" % halted

    return LadderResult(
        schema_version=SCHEMA_VERSION, discovery_id=discovery_id, market=market,
        evaluated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        gates=results, highest_gate_passed=highest, halted_at=halted,
        verdict=verdict,
        # Only a human act can flip this. The ladder never sets it True.
        can_enter_pipeline=False,
        queue="RESEARCH_DISCOVERY")


def engineering_fix(fix_id: str, summary: str, changes_r2_inputs: bool,
                    diagnosis_ref: str) -> dict:
    """A defect fix travels a DIFFERENT queue and is recorded as such.

    CANON-1/2/3 and SECTOR-1/2 are bugs degrading R2's inputs today. They are
    not discoveries, they carry no evidence tier, and they must never appear in
    a research ledger where they could borrow a discovery's credibility - or
    lend it.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "queue": "ENGINEERING_AUTHORIZATION",
        "fix_id": fix_id,
        "summary": summary,
        "changes_r2_inputs": changes_r2_inputs,
        "diagnosis_ref": diagnosis_ref,
        "requires": ("explicit CEO authorization; a before/after decision diff "
                     "if R2 inputs change"),
        "evidence_tier": None,
        "note": ("Not a research discovery. This queue exists so a defect fix is "
                 "never counted as a positive research outcome, and a research "
                 "result is never smuggled in as a bug fix."),
    }


def summarise(results: list) -> dict:
    """Programme-level view: where everything actually stands."""
    from collections import Counter
    verd = Counter(r["verdict"] if isinstance(r, dict) else r.verdict for r in results)
    halted = Counter((r["halted_at"] if isinstance(r, dict) else r.halted_at) or "-"
                     for r in results)
    ready = [(r["discovery_id"] if isinstance(r, dict) else r.discovery_id)
             for r in results
             if (r["verdict"] if isinstance(r, dict) else r.verdict)
             == "READY_FOR_AUTHORIZATION"]
    return {"n_discoveries": len(results),
            "verdicts": dict(verd),
            "halted_at": dict(halted),
            "ready_for_authorization": ready,
            "in_pipeline": [],
            "note": ("`in_pipeline` can only become non-empty through a human "
                     "authorization act recorded outside this module.")}
