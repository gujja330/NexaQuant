# tools/feature_library.py
"""
AEGIS Feature Library + Cross-Market Promotion Matrix — the catalogue of everything AEGIS has LEARNED,
across USA and India. NOT new framework; a generated rollup of accumulated evidence (the leaderboard).

Each row is a CONCEPT (not a raw column) mapped to its domain and its status in each market, so the question
"does this work in BOTH markets?" is answerable at a glance. Cross-market lift is the strongest evidence and
the basis for promoting a concept into the shared library -> the other market's lab -> production.

Run:  python tools/feature_library.py   ->  markets/research/FEATURE_LIBRARY.md
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
LB = list(csv.DictReader((RES / "LEADERBOARD.csv").open()))

# concept -> (domain, {factor_or_experiment aliases}). Concepts group raw factors across markets.
CONCEPTS = [
    ("Low-volatility selection", "Risk", {"t_vol_ann"}),
    ("Regime timing overlay", "Timing", {"regime_overlay"}),
    ("HRP weighting", "Risk", {"hrp_weighting"}),
    ("Stock selection", "Portfolio", {"stock_selection"}),
    ("Momentum", "Technical", {"pure_momentum_top5", "t_mom_3m"}),
    ("Relative strength", "Technical", {"t_rel_str_3m"}),
    ("Universe sizing", "Portfolio", {"dynamic_top_n"}),
    ("Fundamental ratios (ROE/margin/growth/debt)", "Fundamental",
     {"f_roe", "f_net_margin", "f_rev_growth_yoy", "f_debt_to_equity", "composite_equal_weight"}),
    ("Fundamental learned blend", "Fundamental/ML", {"lgbm_learned_blend_purged"}),
    ("PEAD (earnings surprise)", "Event", {"earnings_surprise_yoy"}),
    ("Insider buying (Form 4)", "Alternative", {"insider_net_buy_90d"}),
]
# concepts wired into the LIVE engine (shared core) for the listed markets
PRODUCTION = {"Low-volatility selection": {"USA", "INDIA"}, "Regime timing overlay": {"INDIA"},
              "Momentum": {"USA"}, "Relative strength": {"USA"}}        # USA technicals power sector intel
RANK = {"kept": 4, "promoted": 4, "investigate": 2}                     # everything else = rejected (1)


def market_status(concept, aliases, mkt):
    best = 0
    for r in LB:
        if r["market"] == mkt and r["factor_or_experiment"] in aliases:
            best = max(best, RANK.get(r["status"], 1))
    prod = mkt in PRODUCTION.get(concept, set())
    if prod:
        return "✅ production"
    if best == 4:
        return "✅ promoted"
    if best == 2:
        return "🟡 research"
    if best == 1:
        return "❌ rejected"
    return "—"


def scope(usa, ind):
    g = lambda s: s.startswith("✅")
    if g(usa) and g(ind):
        return "🌐 Global"
    if g(usa):
        return "USA-only"
    if g(ind):
        return "India-only"
    if "🟡" in (usa + ind):
        return "Research"
    if "❌" in (usa + ind):
        return "Rejected"
    return "Untested"


def main():
    rows = []
    for concept, domain, aliases in CONCEPTS:
        usa, ind = market_status(concept, aliases, "USA"), market_status(concept, aliases, "INDIA")
        rows.append((concept, domain, usa, ind, scope(usa, ind)))
    L = ["# AEGIS Feature Library & Cross-Market Promotion Matrix", "",
         "Everything AEGIS has learned, by concept and market. Auto-generated from `LEADERBOARD.csv` "
         "(`python tools/feature_library.py`). Cross-market lift (✅ in BOTH) is the strongest evidence and "
         "the path to production.", "",
         "| Concept | Domain | USA | India | Scope |", "|---|---|---|---|---|"]
    for c, d, u, i, s in rows:
        L.append(f"| {c} | {d} | {u} | {i} | {s} |")
    L += ["",
          "**Legend:** ✅ production (live engine) / promoted · 🟡 research lead · ❌ rejected (tested, no "
          "edge) · — untested · 🌐 Global (works in both markets).", "",
          "## Reading it today",
          "- **Validated alpha:** only the **regime timing overlay (India)** — the rest of India's stack "
          "(HRP, selection, momentum) adds ~nothing over equal-weight; low-vol selection is the shared "
          "production base in both markets.",
          "- **USA:** every tested concept (fundamental ratios, learned blend, PEAD) is **rejected** on "
          "expanded data; insider (Form 4) is in research (deep ingest running).",
          "- **Cross-market gap:** no concept is yet ✅ in BOTH markets by *research evidence* (low-vol is "
          "production-shared but not separately gated as alpha). Closing this — e.g. testing the India "
          "regime overlay on USA — is the highest-value cross-market experiment.",
          "- **Planned domains (⏳):** analyst revisions, 13F, ETF flows, options, macro, news — each enters "
          "as its own concept once acquired."]
    out = RES / "FEATURE_LIBRARY.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(ROOT)} ({len(rows)} concepts)")


if __name__ == "__main__":
    main()
