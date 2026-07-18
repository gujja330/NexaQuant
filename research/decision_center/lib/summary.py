"""Decision Center · overnight summary paragraph.

Deterministic templated sentence generator — no LLM. Produces the
one-paragraph "what changed overnight" text the operator sees at
the top of the dashboard."""
from __future__ import annotations


def build_paragraph(diff: dict) -> str:
    """One-paragraph human summary. Every sentence is a rule."""
    if diff.get("first_run"):
        n = diff.get("action_counts", {})
        return (
            "First day of tracking. "
            f"Baseline captured with {sum(n.values())} recommendations "
            f"(action mix: {_action_mix_short(n)}). "
            "Change tracking begins tomorrow."
        )

    counts = diff.get("counts_by_kind", {})
    n_new = counts.get("NEW", 0)
    n_removed = counts.get("REMOVED", 0)
    n_up = counts.get("UPGRADED", 0)
    n_down = counts.get("DOWNGRADED", 0)
    n_intel_up = counts.get("INTELLIGENCE_UP", 0)
    n_intel_down = counts.get("INTELLIGENCE_DOWN", 0)
    n_conf_up = counts.get("CONFIDENCE_UP", 0)
    n_conf_down = counts.get("CONFIDENCE_DOWN", 0)
    n_target = counts.get("TARGET_HIT", 0)
    n_stop = counts.get("STOP_HIT", 0)
    n_new_held = counts.get("NEW_HELD", 0)
    n_exited = counts.get("EXITED", 0)
    n_sizing = counts.get("SIZING_WARNING", 0)

    sentences = []

    # Sentence 1 — headline change count
    total = diff.get("n_changes", 0)
    if total == 0:
        sentences.append("No material changes overnight — recommendation set is stable.")
    else:
        sentences.append(f"{total} material changes overnight.")

    # Sentence 2 — new opportunities + removed
    if n_new or n_removed:
        parts = []
        if n_new:     parts.append(f"{n_new} new opportunit{'y' if n_new==1 else 'ies'}")
        if n_removed: parts.append(f"{n_removed} removed")
        sentences.append(" · ".join(parts) + ".")

    # Sentence 3 — rank changes
    if n_up or n_down:
        parts = []
        if n_up:   parts.append(f"{n_up} upgraded")
        if n_down: parts.append(f"{n_down} downgraded")
        sentences.append(" · ".join(parts) + ".")

    # Sentence 4 — intelligence + confidence drift
    if n_intel_up or n_intel_down:
        sentences.append(
            f"Intelligence score changed materially on {n_intel_up + n_intel_down} recs "
            f"({n_intel_up} up · {n_intel_down} down)."
        )
    if n_conf_up or n_conf_down:
        sentences.append(
            f"Confidence changed on {n_conf_up + n_conf_down} recs "
            f"({n_conf_up} up · {n_conf_down} down)."
        )

    # Sentence 5 — portfolio-level events
    portfolio_events = []
    if n_target: portfolio_events.append(f"{n_target} target hit")
    if n_stop:   portfolio_events.append(f"{n_stop} stop hit")
    if n_new_held: portfolio_events.append(f"{n_new_held} newly held")
    if n_exited:   portfolio_events.append(f"{n_exited} exited")
    if n_sizing:   portfolio_events.append(f"{n_sizing} sizing warning{'s' if n_sizing != 1 else ''}")
    if portfolio_events:
        sentences.append("Portfolio: " + " · ".join(portfolio_events) + ".")

    # Sentence 6 — verdict
    if n_stop or n_target:
        sentences.append("Action required on flagged positions.")
    elif n_new or (n_up > 0):
        sentences.append("New evidence supports at least one action today.")
    else:
        sentences.append("No portfolio rebalance required.")

    return " ".join(sentences)


def _action_mix_short(counts: dict) -> str:
    """Compact one-line action distribution: 'Buy 44 · Hold 19 · Avoid 127'."""
    if not counts:
        return "none"
    return " · ".join(f"{a} {n}" for a, n in list(counts.items())[:6])
