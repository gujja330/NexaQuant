"""Adaptive Rec Engine v2.1 · conflict detection.

Rules-based conflict detector that inspects the 10 dimension scores +
the DEV023 raw recommendation type + the fusion decision, and fires
CRITICAL / MEDIUM / MINOR conflict alerts when engines disagree.

Every rule is deterministic and named — the operator can trace which
rule fired on which recommendation."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Conflict:
    severity:   str       # CRITICAL · MEDIUM · MINOR
    rule:       str
    detail:     str


# ────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────
def _dim(dims: list, name: str):
    for d in dims:
        if d.name == name:
            return d.score
    return None


# ────────────────────────────────────────────────────────────────
# RULES
# ────────────────────────────────────────────────────────────────
def detect_conflicts(rec: dict, dims: list, fusion: dict) -> list[dict]:
    """Return the list of conflicts fired on this rec.

    dims  : list[DimensionScore]
    fusion: fuse() output dict"""
    conflicts: list[Conflict] = []

    research = _dim(dims, "research")
    historical = _dim(dims, "historical")
    validation = _dim(dims, "validation")
    risk = _dim(dims, "risk")
    dna = _dim(dims, "dna")
    portfolio_fit = _dim(dims, "portfolio_fit")

    fused_score = fusion.get("intelligence_score")
    fusion_decision = fusion.get("decision")
    raw_rec = rec.get("recommendation")

    # CRITICAL — Research says buy but Risk blocks it
    if research is not None and risk is not None:
        if research >= 75 and risk <= 40:
            conflicts.append(Conflict(
                "CRITICAL", "research_high_risk_low",
                f"Research={research:.0f} suggests buy but Risk={risk:.0f} "
                f"blocks — investigate before sizing.",
            ))

    # CRITICAL — DNA pattern says buy but Validation harness says weak
    if dna is not None and validation is not None:
        if dna >= 75 and validation <= 40:
            conflicts.append(Conflict(
                "CRITICAL", "dna_high_validation_low",
                f"DNA pattern strength={dna:.0f} but live validation={validation:.0f}"
                f" — historical pattern may not be repeating.",
            ))

    # CRITICAL — Fusion decision disagrees with raw DEV023 recommendation
    if raw_rec and fusion_decision:
        strong = {"Strong-Buy", "Buy", "Accumulate"}
        weak = {"Sell", "Reduce", "Avoid"}
        if raw_rec in strong and fusion_decision in weak:
            conflicts.append(Conflict(
                "CRITICAL", "raw_buy_fusion_sell",
                f"DEV023 says {raw_rec} but fused Intelligence={fusion_decision}"
                f" (score {fused_score:.1f}) — do not act until reconciled.",
            ))
        elif raw_rec in weak and fusion_decision in strong:
            conflicts.append(Conflict(
                "CRITICAL", "raw_sell_fusion_buy",
                f"DEV023 says {raw_rec} but fused Intelligence={fusion_decision}"
                f" — check whether fusion is picking up new evidence.",
            ))

    # MEDIUM — Research strong but Validation weak
    if research is not None and validation is not None:
        if research >= 75 and validation <= 60 and validation > 40:
            conflicts.append(Conflict(
                "MEDIUM", "research_strong_validation_weak",
                f"Research={research:.0f} but Validation={validation:.0f}"
                f" — live results not (yet) confirming the research call.",
            ))

    # MEDIUM — Historical says loser but rec is buy
    if historical is not None and raw_rec in ("Strong-Buy", "Buy", "Accumulate"):
        if historical <= 35:
            conflicts.append(Conflict(
                "MEDIUM", "buy_but_historical_loser",
                f"Historical={historical:.0f} indicates this ticker has lost more"
                f" than won; {raw_rec} deserves review.",
            ))

    # MEDIUM — Very few portfolio inclusions but Strong-Buy
    if portfolio_fit is not None and raw_rec == "Strong-Buy" and portfolio_fit <= 30:
        conflicts.append(Conflict(
            "MEDIUM", "strong_buy_thin_portfolio_fit",
            f"Strong-Buy but portfolio_fit={portfolio_fit:.0f} — only a few of "
            f"the 99 DEV022 constructions include this ticker.",
        ))

    # MINOR — Wide dimension spread (any pair-wise gap > 40)
    named = [(d.name, d.score) for d in dims if d.score is not None]
    if len(named) >= 2:
        scores = [s for _, s in named]
        spread = max(scores) - min(scores)
        if spread > 40:
            hi = max(named, key=lambda kv: kv[1])
            lo = min(named, key=lambda kv: kv[1])
            conflicts.append(Conflict(
                "MINOR", "wide_dimension_spread",
                f"Wide spread: {hi[0]}={hi[1]:.0f} vs {lo[0]}={lo[1]:.0f}"
                f" (gap {spread:.0f}) — check evidence quality per dimension.",
            ))

    # MINOR — Many missing dimensions
    if fusion.get("n_dimensions_missing", 0) >= 4:
        conflicts.append(Conflict(
            "MINOR", "many_missing_dimensions",
            f"{fusion['n_dimensions_missing']} of 10 dimensions are missing:"
            f" {', '.join(fusion.get('missing_dimensions', []))}.",
        ))

    return [asdict(c) for c in conflicts]


def aggregate_conflicts(all_conflicts_by_ticker: dict[str, list[dict]]) -> dict:
    """Aggregate the per-ticker conflicts into a portfolio-level summary."""
    by_severity: dict[str, list] = {"CRITICAL": [], "MEDIUM": [], "MINOR": []}
    by_rule: dict[str, int] = {}
    tickers_with_critical: set[str] = set()

    for ticker, cs in all_conflicts_by_ticker.items():
        for c in cs:
            sev = c.get("severity", "MINOR")
            by_severity.setdefault(sev, []).append({**c, "ticker": ticker})
            rule = c.get("rule", "unknown")
            by_rule[rule] = by_rule.get(rule, 0) + 1
            if sev == "CRITICAL":
                tickers_with_critical.add(ticker)

    return {
        "n_conflicts_total":     sum(len(v) for v in by_severity.values()),
        "n_critical":            len(by_severity["CRITICAL"]),
        "n_medium":              len(by_severity["MEDIUM"]),
        "n_minor":               len(by_severity["MINOR"]),
        "n_tickers_with_critical": len(tickers_with_critical),
        "by_rule":               dict(sorted(by_rule.items(), key=lambda kv: -kv[1])),
        "top_criticals":         by_severity["CRITICAL"][:20],
        "top_medium":            by_severity["MEDIUM"][:20],
    }
