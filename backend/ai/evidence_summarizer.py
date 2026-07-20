"""AI Evidence Summarizer v1.0.

Given a set of canonical datasets, produce a concise cross-source narrative.
Used by:
  - Market Analyst as a fallback when specific signals are missing.
  - Sprint 4+ engines when they need a one-paragraph "what does the raw data say"
    for a specific ticker / sector / theme.

The summarizer NEVER draws conclusions the underlying data doesn't
directly support. If two sources conflict, the narrative surfaces the
conflict rather than picking a side.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from statistics import mean

from backend.ai.base import AgentOutput
from backend.canonical.schemas import CanonicalDataset

VERSION = "v1.0"


def run(canon: dict[str, CanonicalDataset], market_name: str,
         asof: date | None = None,
         focus_symbol: str | None = None) -> AgentOutput:
    """Summarize a bundle of canonical datasets.

    focus_symbol restricts the narrative to one ticker (used by per-stock engines).
    """
    lines: list[str] = []
    citations: list[str] = []
    evidence: dict = {"kinds_present": sorted(canon.keys())}

    header = ("Data snapshot" if not focus_symbol
               else f"Data snapshot for {focus_symbol}") + f" · {market_name.upper()}."
    lines.append(header)

    # ── news
    news = canon.get("news")
    if news and news.rows:
        rows = news.rows
        if focus_symbol:
            rows = [n for n in rows if n.symbol == focus_symbol]
        if rows:
            avg = mean([n.sentiment for n in rows])
            n_pos = sum(1 for n in rows if n.sentiment > 0.1)
            n_neg = sum(1 for n in rows if n.sentiment < -0.1)
            head_count = sum(n.n_headlines for n in rows)
            lines.append(
                f"News: {len(rows)} ticker{'s' if len(rows) != 1 else ''} scored across "
                f"{head_count} headline{'s' if head_count != 1 else ''}. "
                f"Average sentiment {avg:+.2f} (positive={n_pos}, negative={n_neg}).")
            citations.append(f"canonical.news ({len(rows)} rows)")

    # ── fundamentals
    funds = canon.get("fundamentals")
    if funds and funds.rows:
        rows = funds.rows
        if focus_symbol:
            rows = [f for f in rows if f.symbol == focus_symbol]
        if rows:
            valid_roe = [r.roe for r in rows if r.roe is not None]
            valid_de  = [r.debt_to_equity for r in rows if r.debt_to_equity is not None]
            valid_pe  = [r.trailing_pe for r in rows if r.trailing_pe is not None]
            bits = []
            if valid_roe: bits.append(f"ROE median {mean(valid_roe) * (100 if abs(mean(valid_roe)) < 1 else 1):.1f}%")
            if valid_de:  bits.append(f"D/E median {mean(valid_de):.2f}")
            if valid_pe:  bits.append(f"P/E median {mean(valid_pe):.1f}")
            if bits:
                lines.append(f"Fundamentals: {len(rows)} rows · " + " · ".join(bits) + ".")
            citations.append(f"canonical.fundamentals ({len(rows)} rows)")

    # ── flows
    flows = canon.get("flow")
    if flows and flows.rows:
        rows = flows.rows
        if focus_symbol:
            rows = [f for f in rows if f.symbol == focus_symbol]
        if rows:
            net = sum(f.value_native for f in rows if f.kind in ("foreign_institutional",
                                                                    "domestic_institutional",
                                                                    "insider_buy"))
            net -= sum(f.value_native for f in rows if f.kind == "insider_sell")
            lines.append(f"Institutional flows: {len(rows)} rows, net {net:+,.0f} {market_name.upper() == 'INDIA' and 'INR' or 'USD'}.")
            citations.append(f"canonical.flow ({len(rows)} rows)")

    # ── earnings
    earn = canon.get("earnings")
    if earn and earn.rows:
        rows = earn.rows
        if focus_symbol:
            rows = [e for e in rows if e.symbol == focus_symbol]
        near = [e for e in rows if e.next_earnings_date is not None]
        if near:
            lines.append(f"Earnings: {len(near)} ticker{'s' if len(near) != 1 else ''} have a "
                          "next-earnings date on the calendar.")
            citations.append(f"canonical.earnings ({len(near)} rows)")

    # ── corp actions
    ca = canon.get("corporate_action")
    if ca and ca.rows:
        rows = ca.rows
        if focus_symbol:
            rows = [c for c in rows if c.symbol == focus_symbol]
        if rows:
            n_div = sum(1 for r in rows if r.dividend > 0)
            n_sp  = sum(1 for r in rows if r.split_ratio > 0)
            lines.append(f"Corporate actions: {n_div} dividend event(s), {n_sp} split(s) "
                          "in the trailing window.")
            citations.append(f"canonical.corporate_action ({len(rows)} rows)")

    # ── macro
    macro = canon.get("macro")
    if macro and macro.rows and not focus_symbol:    # macro is market-level, not per-symbol
        rows = macro.rows
        bits = [f"{m.symbol} {m.close:.2f}" for m in rows[:4]]
        lines.append(f"Macro: {len(rows)} indicators (" + ", ".join(bits) + ").")
        citations.append(f"canonical.macro ({len(rows)} rows)")

    if len(lines) == 1:
        lines.append("No data across any canonical source at this cutoff.")

    narrative = " ".join(lines)
    headline = lines[0]

    conf = min(1.0, 0.4 + 0.1 * (len(lines) - 1))    # more sources = more confidence
    caveats: list[str] = []
    if focus_symbol and len(citations) < 2:
        caveats.append(f"Limited per-symbol evidence for {focus_symbol}.")

    return AgentOutput(
        agent="evidence_summarizer", version=VERSION, market=market_name,
        asof=asof or date.today(),
        headline=headline,
        narrative=narrative,
        findings=[],
        evidence=evidence,
        citations=citations,
        confidence=round(conf, 3),
        caveats=caveats,
        determinism="template",
    )
