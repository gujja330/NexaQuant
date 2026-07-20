"""AI Market Analyst v1.0.

Reads Market Intelligence Engine output → prose narrative.

Structure:
  1. Regime headline
  2. Breadth + benchmark momentum evidence
  3. Volatility state
  4. Macro summary (USA) / VIX-only summary (India)
  5. Sector rotation
  6. News + flow pulses
  7. Constructive vs cautionary balance
  8. Two-sided watch-list

**Does NOT compute** — everything cited comes from the engine's signals.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.ai.base import AgentOutput
from backend.market_intelligence.engine import MarketIntelligenceResult

VERSION = "v1.0"


def _line_or_empty(label: str, value: str | None) -> str:
    return f"{label}: {value}" if value else ""


def run(result: MarketIntelligenceResult) -> AgentOutput:
    sigs = result.signals

    # ── Regime headline ─────────────────────────────────────────
    regime_headline = (f"{result.regime_label} · Composite Market Health "
                        f"{result.composite_score:.1f}/100.")

    # ── Section 1: breadth ──────────────────────────────────────
    b20 = sigs.get("breadth_above_20ma")
    b52 = sigs.get("breadth_at_52w_high")
    if b20 and b52:
        breadth_para = (f"Breadth: {b20.label}. {b52.label}. "
                         + _interpret_breadth(b20.value, b52.value))
    else:
        breadth_para = "Breadth data unavailable (universe too thin)."

    # ── Section 2: benchmark momentum ───────────────────────────
    b1m = sigs.get("benchmark_1m_pct"); b5d = sigs.get("benchmark_5d_pct")
    if b1m and b5d:
        bench_para = (f"{b5d.label}; {b1m.label}. "
                       + _interpret_bench(float(b5d.value), float(b1m.value)))
    else:
        bench_para = ""

    # ── Section 3: volatility ────────────────────────────────────
    vix = sigs.get("vix"); move = sigs.get("move")
    if vix:
        vol_para = f"Volatility: {vix.label}."
        if move:
            vol_para += f" Bond-market vol: {move.label}."
        vol_para += " " + _interpret_vix(float(vix.value))
    else:
        vol_para = ""

    # ── Section 4: macro (USA-only) ─────────────────────────────
    macro_para = ""
    if result.market == "usa":
        macro = sigs.get("macro")
        if macro:
            ev = macro.evidence
            tnx = ev.get("^TNX", {}).get("last") if isinstance(ev, dict) else None
            uup = ev.get("UUP", {}).get("last") if isinstance(ev, dict) else None
            gld = ev.get("GC=F", {}).get("last") if isinstance(ev, dict) else None
            oil = ev.get("CL=F", {}).get("last") if isinstance(ev, dict) else None
            bits = []
            if tnx is not None: bits.append(f"10Y {tnx:.2f}%")
            if uup is not None: bits.append(f"UUP {uup:.2f}")
            if gld is not None: bits.append(f"Gold ${gld:,.0f}")
            if oil is not None: bits.append(f"WTI ${oil:.2f}")
            if bits:
                macro_para = "Macro: " + " · ".join(bits) + "."

    # ── Section 5: sector rotation ──────────────────────────────
    rot = sigs.get("sector_rotation")
    rot_para = ""
    if rot and rot.evidence:
        top = rot.evidence.get("top_3", [])
        bot = rot.evidence.get("bottom_3", [])
        if top and bot:
            rot_para = (f"Sector rotation: leaders — " +
                         ", ".join(f"{t['label']} ({t['return_pct']:+.1f}%)" for t in top[:3]) +
                         "; laggards — " +
                         ", ".join(f"{b['label']} ({b['return_pct']:+.1f}%)" for b in bot[:3]) +
                         ".")

    # ── Section 6: news + flow ──────────────────────────────────
    news = sigs.get("news_pulse")
    flow = sigs.get("flow_pulse")
    news_flow_para = ""
    if news or flow:
        bits = []
        if news: bits.append(news.label)
        if flow: bits.append(flow.label)
        news_flow_para = "Pulse: " + " · ".join(bits) + "."

    # ── Section 7: balance ──────────────────────────────────────
    supportive: list[str] = []
    cautionary: list[str] = []
    for key, sig in sigs.items():
        if key in ("breadth_above_20ma",) and isinstance(sig.value, (int, float)) and float(sig.value) > 55:
            supportive.append(f"{sig.label}")
        if key in ("breadth_above_20ma",) and isinstance(sig.value, (int, float)) and float(sig.value) < 40:
            cautionary.append(f"{sig.label}")
        if key == "benchmark_1m_pct" and isinstance(sig.value, (int, float)):
            if float(sig.value) > 2:   supportive.append(sig.label)
            if float(sig.value) < -2:  cautionary.append(sig.label)
        if key == "vix" and isinstance(sig.value, (int, float)) and float(sig.value) > 25:
            cautionary.append(sig.label)
        if key == "news_pulse" and isinstance(sig.value, (int, float)):
            if float(sig.value) > 0.15:  supportive.append(sig.label)
            if float(sig.value) < -0.15: cautionary.append(sig.label)

    balance_bits: list[str] = []
    if supportive:
        balance_bits.append("Supportive: " + " · ".join(supportive))
    if cautionary:
        balance_bits.append("Cautionary: " + " · ".join(cautionary))
    balance_para = "\n".join(balance_bits) if balance_bits else ""

    paragraphs = [regime_headline, breadth_para, bench_para, vol_para,
                    macro_para, rot_para, news_flow_para, balance_para]
    narrative = "\n\n".join(p for p in paragraphs if p.strip())

    # ── Structured findings ─────────────────────────────────────
    findings: list[dict] = []
    for key, sig in sigs.items():
        findings.append({
            "signal": key, "value": sig.value, "label": sig.label,
            "evidence": sig.evidence,
        })

    citations = [f"backend/market_intelligence/engine.py (v{result.engine_version})"]
    for key in sigs:
        citations.append(f"market_intelligence.signals.{key}")

    caveats: list[str] = []
    if len(sigs) < 5:
        caveats.append("Fewer than 5 signals available — narrative confidence reduced.")
    if not b20:
        caveats.append("Breadth signal missing — regime classification may be biased toward the benchmark move.")

    confidence = min(1.0, 0.5 + 0.05 * len(sigs))

    return AgentOutput(
        agent="market_analyst", version=VERSION, market=result.market,
        asof=result.asof,
        headline=regime_headline,
        narrative=narrative,
        findings=findings,
        evidence={"n_signals": len(sigs), "composite_score": result.composite_score,
                    "regime": result.regime},
        citations=citations,
        confidence=round(confidence, 3),
        caveats=caveats,
        determinism="template",
    )


# ── Interpretation helpers (deterministic; no LLM) ─────────────
def _interpret_breadth(pct_above: float, pct_at_high: float) -> str:
    if pct_above > 65:  return "Broad participation — this is not a narrow rally."
    if pct_above < 35:  return "Narrow tape — most of the universe is weakening."
    return "Mixed participation — bulls have not yet won the tape."


def _interpret_bench(b5: float, b1m: float) -> str:
    if b5 > 0 and b1m > 0:     return "Positive short-term and monthly momentum."
    if b5 < 0 and b1m < 0:     return "Negative on both windows — a downtrend, not just a dip."
    if b5 < 0 and b1m > 0:     return "Monthly gain but short-term pullback — watch the retest."
    return "Short-term bounce inside a broader downtrend — regime not confirmed."


def _interpret_vix(v: float) -> str:
    if v > 30:   return "Stress-level vol; historically a buying window ONLY after it starts falling."
    if v > 25:   return "Elevated vol; sizing should be reduced until it normalises."
    if v > 18:   return "Moderate vol; normal operating range."
    return "Calm tape; complacency risk is the classic setup for a downside surprise."
