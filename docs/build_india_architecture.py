# docs/build_india_architecture.py
"""
Builds docs/Arjuna_Architecture.pdf — a colorful architecture/results deck for the
INDIA equity engine (parallel to the gold/BTC deck). Charts are drawn from the REAL backtest.

Run: python docs/build_india_architecture.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.equity_engine import load, composite_score
from india.picker_pro import backtest, SECTOR

INK = "#10243e"; BLUE = "#2563eb"; GREEN = "#16a34a"; AMBER = "#d97706"
RED = "#dc2626"; SLATE = "#334155"; SUB = "#64748b"; CARD = "#eef2f7"; TEAL = "#0d9488"


def box(ax, x, y, w, h, text, fc, tc="white", fs=11, bold=True, ec=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.03",
                                fc=fc, ec=ec or fc, lw=1.5))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc,
                fontsize=fs, fontweight="bold" if bold else "normal", zorder=5)


def arrow(ax, x1, y1, x2, y2, color=SLATE):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16, lw=2, color=color))


def base(fig, title, subtitle, page):
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 8.5), 16, 0.5, color=INK))
    ax.text(0.4, 8.75, title, color="white", fontsize=18, fontweight="bold", va="center")
    ax.text(15.6, 8.82, "ARJUNA", color="#fbbf24", fontsize=13, fontweight="bold", va="center", ha="right")
    ax.text(15.6, 8.58, "NSE equity engine", color="#9fc3e8", fontsize=8, va="center", ha="right")
    if subtitle:
        ax.text(0.4, 8.2, subtitle, color=SUB, fontsize=11, va="center")
    ax.text(8, 0.18, page, color=SUB, fontsize=8, ha="center")
    return ax


# ---- real backtest data (HARDENED: pure momentum on the broad ~49-stock universe) ----
net = backtest(vix_derisk=False)
eq = (1 + net).cumprod() * 100000.0
yearly = [(y, 100 * ((1 + g).prod() - 1)) for y, g in net.groupby(net.index.year) if len(g) > 30]
closes, _ = load(); score = composite_score(closes, {"momentum": 1.0})
picks = score.iloc[-1].dropna().sort_values(ascending=False).head(5)


def p_cover(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 16, 9, color=INK))
    ax.add_patch(plt.Rectangle((0, 5.2), 16, 0.06, color=TEAL))
    ax.text(8, 6.85, "ARJUNA", color="#fbbf24", fontsize=58, fontweight="bold", ha="center")
    ax.text(8, 6.05, "NSE Equity Engine", color="white", fontsize=16, ha="center")
    ax.text(8, 5.6, "The focused stock picker — sees only the target: momentum, top-5, weekly",
            color="#cfe0f0", fontsize=13, ha="center")
    for i, (lbl, val, c) in enumerate([("BACKTEST", "Rs 1L -> Rs 2.64L", GREEN),
                                       ("RETURN", "+164% / ~6y", TEAL),
                                       ("SHARPE", "0.79", BLUE),
                                       ("PROFIT YEARS", "6 / 7", AMBER)]):
        x = 1.2 + i * 3.6
        box(ax, x, 3.0, 3.2, 1.5, "", "#16314f", ec=c)
        ax.text(x + 1.6, 4.05, val, color="white", fontsize=16, fontweight="bold", ha="center")
        ax.text(x + 1.6, 3.35, lbl, color=c, fontsize=10, fontweight="bold", ha="center")
    ax.text(8, 1.7, "Evidence-first - net of Indian costs - parallel to the gold/BTC system",
            color=SUB, fontsize=11, ha="center")
    ax.text(8, 1.2, "Honest: survivorship-light universe - 2026 a down year - paper-test before capital",
            color="#7f93a8", fontsize=9, ha="center")
    pdf.savefig(fig); plt.close(fig)


def p_flow(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "How a Stock Gets Picked", "Systematic, rule-based — rank the universe, hold the best, de-risk on fear", "2")
    steps = [("UNIVERSE\n~49 liquid\nNSE stocks", BLUE),
             ("SCORE each\nby 6-month\nMOMENTUM", TEAL),
             ("RANK &\nHOLD TOP 5\nequal weight", GREEN),
             ("VIX DE-RISK\n(optional: lower\ndrawdown)", AMBER),
             ("REBALANCE\nweekly -> sell\nif drops out", SLATE)]
    for i, (t, c) in enumerate(steps):
        x = 0.5 + i * 3.15
        box(ax, x, 5.4, 2.7, 1.9, t, c, fs=10.5)
        if i < 4:
            arrow(ax, x + 2.7, 6.35, x + 3.15, 6.35)
    box(ax, 0.5, 3.0, 15.0, 1.7, "", CARD, ec=BLUE)
    ax.text(0.8, 4.4, "WHY THIS WORKS", color=BLUE, fontsize=11, fontweight="bold", va="top")
    ax.text(0.8, 4.0,
            "Momentum rewards strength (winners keep winning) — the most robust factor across markets.\n"
            "The edge is the BASKET, not any single stock — across many holds, winners' payoff beats losers' cost.\n"
            "Validated on a BROAD ~49-stock universe (the narrow 23-stock blend with low-vol was overfit).",
            color=SLATE, fontsize=9.5, va="top")
    box(ax, 0.5, 0.7, 15.0, 1.9, "", "#eafaf0", ec=GREEN)
    ax.text(0.8, 2.35, "EXIT RULE (no stops — proven to whipsaw)", color=GREEN, fontsize=11, fontweight="bold", va="top")
    ax.text(0.8, 1.95,
            "A name is SOLD only when it drops out of the weekly top-5 (rotation). No per-stock stop-loss,\n"
            "no fixed target. Tested stops/exits ALL reduced returns — momentum needs room to breathe.",
            color=SLATE, fontsize=9.5, va="top")
    pdf.savefig(fig); plt.close(fig)


def p_results(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "Backtest Results", "Rs1,00,000 compounded, net of cost — the money view", "3")
    # equity curve
    c1 = fig.add_axes([0.07, 0.12, 0.52, 0.62])
    c1.plot(eq.index, eq.values, color=GREEN, lw=2)
    c1.fill_between(eq.index, 100000, eq.values, color=GREEN, alpha=0.12)
    c1.axhline(100000, color=SUB, lw=0.8, ls="--")
    c1.set_title("Portfolio value (Rs)", fontsize=11, color=INK)
    c1.grid(alpha=0.25); c1.tick_params(labelsize=8)
    # yearly bars
    c2 = fig.add_axes([0.66, 0.12, 0.3, 0.62])
    yrs = [str(y) for y, _ in yearly]; vals = [v for _, v in yearly]
    c2.bar(yrs, vals, color=[GREEN if v > 0 else RED for v in vals])
    c2.axhline(0, color=INK, lw=0.8); c2.set_title("Yearly return %", fontsize=11, color=INK)
    c2.tick_params(labelsize=8); plt.setp(c2.get_xticklabels(), rotation=45)
    for i, (lbl, val, c) in enumerate([("Total", "+164%", GREEN), ("Sharpe", "0.79", BLUE),
                                       ("Max DD", "~25%", AMBER), ("CAGR", "~15%", TEAL)]):
        x = 0.5 + i * 3.85
        box(ax, x, 0.6, 3.5, 1.0, "", CARD, ec=c)
        ax.text(x + 1.75, 1.25, val, color=INK, fontsize=15, fontweight="bold", ha="center")
        ax.text(x + 1.75, 0.85, lbl, color=c, fontsize=10, fontweight="bold", ha="center")
    pdf.savefig(fig); plt.close(fig)


def p_evidence(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "What Works vs What We Rejected", "Every idea tested honestly — kept only what the data proved", "4")
    ax.text(0.5, 8.0, "KEPT (validated)", color=GREEN, fontsize=13, fontweight="bold", va="top")
    keep = [("Pure-momentum picker", "the robust core — Sharpe 0.79"),
            ("Broad ~49-stock universe", "hardened (narrow set was overfit)"),
            ("Top-5 diversified basket", "systematic, not stock-picking")]
    y = 7.4
    for n, w in keep:
        box(ax, 0.5, y - 0.2, 7.2, 0.62, "", "#eafaf0", ec=GREEN)
        ax.text(0.75, y + 0.16, n, color=INK, fontsize=10, fontweight="bold", va="center")
        ax.text(0.75, y - 0.1, w, color=SLATE, fontsize=8.3, va="center"); y -= 0.78
    ax.text(8.3, 8.0, "REJECTED (tested, failed)", color=RED, fontsize=13, fontweight="bold", va="top")
    rej = [("Intraday (ORB+VWAP)", "loses every yr, -0.09%/trade"),
           ("Stops / trailing / mom-break exit", "whipsaw momentum -> cut returns"),
           ("Avoid-losers selection filter", "winners=losers at entry (AUC 0.47)"),
           ("Sector cap / regime filter", "too restrictive -> lower return")]
    y = 7.4
    for n, w in rej:
        box(ax, 8.3, y - 0.2, 7.2, 0.62, "", "#fdeeee", ec=RED)
        ax.text(8.55, y + 0.16, n, color=INK, fontsize=10, fontweight="bold", va="center")
        ax.text(8.55, y - 0.1, w, color=SLATE, fontsize=8.3, va="center"); y -= 0.78
    box(ax, 0.5, 0.7, 15.0, 1.7, "", CARD, ec=BLUE)
    ax.text(0.8, 2.05, "THE DEEP FINDING", color=BLUE, fontsize=11, fontweight="bold", va="top")
    ax.text(0.8, 1.65,
            "Future winners and losers look IDENTICAL at entry (AI AUC 0.47, worse than random). So you can't\n"
            "dodge the losers without dodging the winners — the losses are the necessary cost of the edge.\n"
            "This is why it's a SYSTEMATIC BASKET, and why stops/filters all fail. Open frontier: point-in-time fundamentals.",
            color=SLATE, fontsize=9.3, va="top")
    pdf.savefig(fig); plt.close(fig)


def p_influences(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "What Moves Indian Stocks", "Drivers we embed (react to footprint, never predict headlines)", "5")
    cats = [("GLOBAL", BLUE, ["US S&P / Nasdaq (overnight)", "China -> metals/commodities",
                              "GIFT Nifty gap", "US/India VIX (fear)"]),
            ("MACRO / FLOWS", TEAL, ["US Fed / 10y yield", "Dollar (DXY), USD/INR",
                                     "Crude oil (imports)", "FII / DII flows"]),
            ("SECTORS", AMBER, ["Metals <- China/LME", "IT <- US spend/USDINR",
                                "Auto/EV <- demand/fuel", "Banks <- rates/credit"]),
            ("STOCK-SPECIFIC", GREEN, ["Earnings / PEAD drift", "Estimate revisions",
                                       "Index rejig", "News -> via VIX+price"])]
    for i, (title, c, items) in enumerate(cats):
        x = 0.4 + (i % 2) * 7.9; yb = 4.6 - (i // 2) * 3.5
        box(ax, x, yb, 7.4, 3.0, "", CARD, ec=c)
        ax.text(x + 0.3, yb + 2.65, title, color=c, fontsize=12, fontweight="bold", va="top")
        for k, it in enumerate(items):
            ax.text(x + 0.4, yb + 2.15 - k * 0.5, "- " + it, color=SLATE, fontsize=9.5, va="top")
    pdf.savefig(fig); plt.close(fig)


def p_roadmap(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "Status & Roadmap", "Honest scorecard + the path to live", "6")
    box(ax, 0.5, 6.4, 15.0, 1.8, "", "#eafaf0", ec=GREEN)
    ax.text(0.8, 8.0, "TODAY  (~6 / 10, honest after hardening)", color=GREEN, fontsize=12, fontweight="bold", va="top")
    ax.text(0.8, 7.6,
            "Pure-momentum engine on a broad universe: +164% / CAGR ~15% / Sharpe 0.79 / 6-of-7 years.\n"
            "Hardening cut the inflated 1.23 to a trustworthy 0.79. Decent, not spectacular — every\n"
            "alternative tested & rejected. Current picks printed by india/picks_report.py.",
            color=SLATE, fontsize=9.5, va="top")
    steps = [("1. HARDEN", "survivorship-safe\nNifty 200/500 +\nwalk-forward gate", BLUE),
             ("2. FUNDAMENTALS", "point-in-time data ->\nseparate winners/losers\n(the open frontier)", TEAL),
             ("3. GO LIVE", "Angel One / Upstox\nfree API, paper on PC\nduring market hours", GREEN),
             ("4. SCALE", "grow capital +\ncompounding over\nyears", AMBER)]
    for i, (t, d, c) in enumerate(steps):
        x = 0.5 + i * 3.85
        box(ax, x, 3.4, 3.5, 2.2, "", "#ffffff", ec=c)
        ax.text(x + 1.75, 5.2, t, color=c, fontsize=12, fontweight="bold", ha="center")
        ax.text(x + 1.75, 4.3, d, color=SLATE, fontsize=9, ha="center", va="center")
        if i < 3:
            arrow(ax, x + 3.5, 4.5, x + 3.85, 4.5)
    box(ax, 0.5, 0.7, 15.0, 2.2, "", "#fff8ec", ec=AMBER)
    ax.text(0.8, 2.7, "HONEST CAVEATS", color=AMBER, fontsize=11, fontweight="bold", va="top")
    ax.text(0.8, 2.3,
            "- +145% is on CURRENT large-caps (survivorship-light) -> true number is lower; harden before trusting.\n"
            "- Rs1,000 is tiny vs Indian costs/STT -> a grow-into-it plan; F&O is last + capital-gated (90% retail lose).\n"
            "- AI is a modest filter, not an oracle. We react to news via volatility, never predict it.\n"
            "- Paper-trade before any real capital. The edge is real but lumpy (2026 was -10%).",
            color=SLATE, fontsize=9.3, va="top")
    pdf.savefig(fig); plt.close(fig)


def p_insights(pdf):
    fig = plt.figure(figsize=(16, 9)); ax = base(fig, "Key Insights — What the Data Taught Us",
                                                 "Hard-won, evidence-based — the lessons behind ARJUNA", "7")
    cards = [
        ("THE EDGE IS THE BASKET", GREEN,
         "Future winners & losers look identical at entry\n(AI AUC 0.47). You can't cherry-pick —\nhold the top-5, the math wins in aggregate."),
        ("STOPS WHIPSAW MOMENTUM", RED,
         "Every stop / trailing / exit filter CUT returns\n(mom-break: 145%->49%). The losers are the\nnecessary cost of the winners."),
        ("HARDEN ON A BROAD UNIVERSE", BLUE,
         "On 23 stocks mom+low-vol showed Sharpe 1.23 —\nbut it COLLAPSED to 0.42 on 49 stocks. It was\noverfit. Pure momentum held at 0.79. Always\nvalidate broad before trusting a number."),
        ("VIX DE-RISK = OPTIONAL", TEAL,
         "VIX de-risk lowers drawdown (24.7%->21.8%) but\nslightly trims return on the broad universe.\nA risk dial, not a free lunch."),
        ("INTRADAY IS NOISE + COST", AMBER,
         "11,695 intraday trades: -0.09%/trade, losing\nevery year. Same lesson as fast-TF crypto.\nLong-term/positional is the real edge."),
        ("RETURNS ARE LUMPY, NOT SMOOTH", SLATE,
         "2021 (+49%) flatters the headline; factor decay\nis real and 2026 was -10%. Expect lumpy years\n- it's a compounder, not an annuity."),
    ]
    for i, (t, c, body) in enumerate(cards):
        x = 0.5 + (i % 3) * 5.15; y = 5.0 - (i // 3) * 3.6
        ax.add_patch(FancyBboxPatch((x, y), 4.8, 3.0, boxstyle="round,pad=0.02,rounding_size=0.05",
                                    fc="#ffffff", ec=c, lw=2.2))
        ax.add_patch(plt.Rectangle((x, y + 2.55), 4.8, 0.45, color=c))
        ax.text(x + 2.4, y + 2.77, t, color="white", fontsize=10.5, fontweight="bold", ha="center", va="center")
        ax.text(x + 0.25, y + 2.2, body, color=SLATE, fontsize=9.2, va="top")
    pdf.savefig(fig); plt.close(fig)


out = ROOT / "docs" / "Arjuna_Architecture.pdf"
with PdfPages(out) as pdf:
    p_cover(pdf); p_flow(pdf); p_results(pdf); p_evidence(pdf); p_insights(pdf); p_influences(pdf); p_roadmap(pdf)
print(f"PDF written: {out}")
