# docs/build_arjuna_v2_pdf.py
"""
Build the ARJUNA v2 architecture deck — clean, colorful, one idea per page.
Pulls real backtest numbers for the charts. Output: docs/ARJUNA_v2_Architecture.pdf
Run: python docs/build_arjuna_v2_pdf.py
"""
import sys, warnings
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---- palette ----
NAVY = "#16213e"; INDIGO = "#1f4068"; GOLD = "#f4a259"; TEAL = "#2ec4b6"
CORAL = "#e76f51"; GREEN = "#43aa8b"; RED = "#d62246"; LIGHT = "#f6f8fb"; GREY = "#5c6b7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})


def newpage(pdf, bg=LIGHT):
    fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor(bg)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return fig, ax


def header(ax, kicker, title, color=NAVY):
    ax.add_patch(FancyBboxPatch((0, 0.9), 1, 0.1, boxstyle="square,pad=0", color=color, lw=0))
    ax.add_patch(FancyBboxPatch((0, 0.888), 1, 0.012, boxstyle="square,pad=0", color=GOLD, lw=0))
    ax.text(0.06, 0.955, kicker, color=GOLD, fontsize=11, weight="bold")
    ax.text(0.06, 0.918, title, color="white", fontsize=20, weight="bold")


def box(ax, x, y, w, h, text, fc, tc="white", fs=11, weight="normal", align="center"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                fc=fc, ec="none"))
    ax.text(x + w / 2 if align == "center" else x + 0.015, y + h / 2, text, color=tc, fontsize=fs,
            ha=align, va="center", weight=weight, wrap=True)


def arrow(ax, x, y0, y1, color=GREY):
    ax.add_patch(FancyArrowPatch((x, y0), (x, y1), arrowstyle="-|>", mutation_scale=16,
                                 color=color, lw=2))


# ---------- equity data (real backtest) ----------
def equity_curves():
    from india.arjuna_v2 import backtest
    champ, idx = backtest("hrp", regime="global")
    ew, _ = backtest("ew")
    nifty = idx.pct_change().fillna(0.0).reindex(champ.index).fillna(0.0)
    e = lambda r: (1 + r).cumprod() * 1e5
    return champ.index, e(champ), e(ew), e(nifty)


def main():
    print("  computing backtest curves...")
    dts, champ, ew, nifty = equity_curves()
    pdf_path = ROOT / "docs" / "ARJUNA_v2_Architecture.pdf"
    with PdfPages(pdf_path) as pdf:

        # ---------- PAGE 1 — cover ----------
        fig, ax = newpage(pdf, NAVY)
        ax.text(0.5, 0.76, "ARJUNA", color="white", fontsize=60, weight="bold", ha="center")
        ax.add_patch(Rectangle((0.34, 0.722), 0.32, 0.005, color=GOLD, lw=0))
        ax.text(0.5, 0.665, "v2  ·  Adaptive Risk & Regime Allocation System", color=TEAL,
                fontsize=15, ha="center", weight="bold")
        ax.text(0.5, 0.60, "AQR / Bridgewater-style risk investing — for retail Indian equities",
                color="#c7d0db", fontsize=11.5, ha="center")
        for i, (k, v, c) in enumerate([("Sharpe", "2.04", TEAL), ("max DD", "12.8%", GOLD),
                                       ("Defl. Sharpe", "0.996", GREEN), ("PBO", "0.00", CORAL)]):
            x = 0.08 + i * 0.225
            box(ax, x, 0.40, 0.20, 0.12, "", "#22335c")
            ax.text(x + 0.10, 0.47, v, color="white", fontsize=20, weight="bold", ha="center")
            ax.text(x + 0.10, 0.425, k, color="#9fb3c8", fontsize=10, ha="center")
        ax.text(0.5, 0.30, "NOT a stock-picking bot.  A risk-allocation & regime-management bot.",
                color="white", fontsize=12.5, ha="center", weight="bold")
        ax.text(0.5, 0.06, "Validated on clean Angel One data · Nifty-200 · net of cost\n"
                "Returns are unpredictable. Risk is. ARJUNA forecasts risk, not winners.",
                color="#8b9bb0", fontsize=9.5, ha="center")
        pdf.savefig(fig, facecolor=fig.get_facecolor()); plt.close(fig)

        # ---------- PAGE 2 — the principle ----------
        fig, ax = newpage(pdf)
        header(ax, "THE CORE PRINCIPLE", "Returns are noise. Risk has structure.")
        ax.text(0.06, 0.83, "We tested 13 AI model families on 'will the stock go up?'  Every one\n"
                "scored ~0.50 (a coin flip). Then we changed the TARGET — and the same\n"
                "model suddenly had real skill at predicting RISK.", fontsize=12, color=NAVY)
        # bar chart of AUC by target
        axb = fig.add_axes([0.12, 0.40, 0.76, 0.32])
        tg = ["Return\n(up/down)", "Sharpe", "Drawdown", "Volatility"]
        au = [0.51, 0.50, 0.62, 0.76]; cols = [RED, RED, GREEN, GREEN]
        axb.bar(tg, au, color=cols); axb.axhline(0.5, color=GREY, ls="--", lw=1)
        axb.set_ylim(0.45, 0.80); axb.set_ylabel("AUC (skill)  ·  0.50 = none")
        for i, v in enumerate(au):
            axb.text(i, v + 0.005, f"{v:.2f}", ha="center", weight="bold", color=NAVY)
        axb.set_title("Predictability by target (out-of-sample 2024–26)", color=NAVY, weight="bold")
        for s in ["top", "right"]:
            axb.spines[s].set_visible(False)
        box(ax, 0.06, 0.16, 0.88, 0.16,
            "  So ARJUNA forecasts  RISK · REGIME · EXPOSURE · WEIGHTS  — never returns.\n"
            "  Objective: long-term risk-adjusted compounding. Survival first; raw CAGR last.",
            INDIGO, fs=12.5, align="left")
        pdf.savefig(fig); plt.close(fig)

        # ---------- PAGE 3 — validated results ----------
        fig, ax = newpage(pdf)
        header(ax, "VALIDATED RESULTS", "Champion vs the index (₹1L, ~5.5y, net of cost)")
        axc = fig.add_axes([0.11, 0.42, 0.80, 0.40])
        axc.plot(dts, champ, color=TEAL, lw=2.4, label="ARJUNA v2 (HRP+regime+global)")
        axc.plot(dts, ew, color=GOLD, lw=1.6, label="Equal-weight basket")
        axc.plot(dts, nifty, color=GREY, lw=1.6, label="Nifty-50")
        axc.legend(frameon=False, fontsize=10, loc="upper left")
        axc.set_ylabel("₹ (from ₹1,00,000)"); axc.set_title("Growth of ₹1,00,000", color=NAVY, weight="bold")
        axc.grid(alpha=0.25)
        for s in ["top", "right"]:
            axc.spines[s].set_visible(False)
        cards = [("CAGR", "17.7%", TEAL), ("Sharpe", "2.04", GREEN), ("max DD", "12.8%", GOLD),
                 ("vs Nifty Sharpe", "0.80", GREY)]
        for i, (k, v, c) in enumerate(cards):
            x = 0.07 + i * 0.22
            box(ax, x, 0.24, 0.195, 0.10, "", "white"); ax.add_patch(FancyBboxPatch((x, 0.24), 0.195, 0.014, color=c, lw=0))
            ax.text(x + 0.097, 0.30, v, color=NAVY, fontsize=17, weight="bold", ha="center")
            ax.text(x + 0.097, 0.262, k, color=GREY, fontsize=9.5, ha="center")
        ax.text(0.06, 0.16, "Rigour gate (3 independent checks):", fontsize=12, weight="bold", color=NAVY)
        box(ax, 0.06, 0.075, 0.27, 0.07, "Deflated Sharpe\n0.996  ✓", GREEN, fs=11)
        box(ax, 0.37, 0.075, 0.27, 0.07, "PBO\n0.00  ✓", GREEN, fs=11)
        box(ax, 0.68, 0.075, 0.26, 0.07, "Purged walk-fwd\n✓", GREEN, fs=11)
        ax.text(0.06, 0.045, "Survivorship inflates absolute CAGR → trust the Sharpe/drawdown EDGE over the index.",
                fontsize=8.5, color=GREY, style="italic")
        pdf.savefig(fig); plt.close(fig)

        # ---------- PAGE 4 — architecture ----------
        fig, ax = newpage(pdf)
        header(ax, "ARCHITECTURE", "Four layers — risk in, portfolio out")
        layers = [("LAYER 1 · MARKET STATE", "Global Risk Engine (S&P/VIX/USD) · regime (VIX+200DMA) · breadth · FII/DII", TEAL),
                  ("LAYER 2 · RISK FORECAST", "Volatility (AUC 0.76) · drawdown · trailing covariance", INDIGO),
                  ("LAYER 3 · CORRELATION ENGINE", "Ledoit-Wolf covariance · HRP clusters · sector caps (20 stocks ≠ 20 bets)", GREEN),
                  ("LAYER 4 · PORTFOLIO", "HRP / min-var / inverse-vol weights · per-name cap · news blow-up filter", GOLD)]
        y = 0.80
        for k, v, c in layers:
            box(ax, 0.12, y, 0.76, 0.105, "", c)
            ax.text(0.15, y + 0.072, k, color="white", fontsize=12.5, weight="bold")
            ax.text(0.15, y + 0.032, v, color="white", fontsize=9.6)
            if y > 0.45:
                arrow(ax, 0.5, y - 0.012, y - 0.052, NAVY)
            y -= 0.165
        box(ax, 0.30, 0.155, 0.40, 0.075, "FINAL PORTFOLIO\n(monthly rebalance · paper→live)", NAVY, fs=11.5, weight="bold")
        ax.text(0.5, 0.10, "AI is used for risk, regime & news — NOT for 'which stock doubles'.",
                color=NAVY, fontsize=11, ha="center", style="italic", weight="bold")
        pdf.savefig(fig); plt.close(fig)

        # ---------- PAGE 5 — what survived vs died ----------
        fig, ax = newpage(pdf)
        header(ax, "THE DISCIPLINE", "Evidence killed hypotheses — only survivors ship")
        box(ax, 0.06, 0.78, 0.42, 0.07, "✓  SURVIVED (risk & regime)", GREEN, fs=12.5, weight="bold")
        box(ax, 0.52, 0.78, 0.42, 0.07, "✗  REJECTED (tested, no edge)", RED, fs=12.5, weight="bold")
        alive = ["Global Risk Engine", "Regime (VIX + 200-DMA)", "Breadth · FII/DII (live)",
                 "HRP / min-var / inverse-vol", "Volatility forecast (0.76)", "News blow-up filter",
                 "Broad diversification"]
        dead = ["13 ML return-models (~0.50)", "HMM regime (1.06 < 1.64)", "RL · GNN · Transformers",
                "GARCH (no gain vs trailing)", "Vol-targeting (just levers up)", "Crash classifier (0.56, wash)",
                "Concentration / multibaggers"]
        for i, (a, d) in enumerate(zip(alive, dead)):
            yy = 0.70 - i * 0.083
            box(ax, 0.06, yy, 0.42, 0.062, "  " + a, "#e7f5ef", tc=NAVY, fs=10.5, align="left")
            box(ax, 0.52, yy, 0.42, 0.062, "  " + d, "#fdea ea".replace(" ", ""), tc=NAVY, fs=10.5, align="left")
        ax.text(0.5, 0.06, "Every rejection made ARJUNA simpler and more honest. Data is the bottleneck — not models.",
                color=GREY, fontsize=10, ha="center", style="italic")
        pdf.savefig(fig); plt.close(fig)

        # ---------- PAGE 6 — how to use it ----------
        fig, ax = newpage(pdf)
        header(ax, "HOW TO USE IT", "From config to compounding")
        steps = [("1 · CONFIGURE", "india/config.py — universe, method=hrp, regime=global, capital. One file, no logic edits."),
                 ("2 · DAILY RUN (auto)", "Scheduled task 'ArjunaDailyPaper' (weekdays 18:00): pull data → FII/DII → news → portfolio → paper log."),
                 ("3 · GET THE BASKET", "python india/run_arjuna.py --capital 100000 → risk-weighted holdings, regime-scaled, news-filtered."),
                 ("4 · SIZE TO CAPITAL", "Dynamic allocator auto-fits ₹5K→₹5L (more capital = more names; ₹25K+ deploys fully)."),
                 ("5 · PAPER FIRST", "Forward paper log (output/paper_log.csv) for weeks–months → unbiased verdict, no survivorship."),
                 ("6 · GO LIVE", "Only after paper confirms: rotate Angel credentials, fund, wire order placement.")]
        y = 0.82
        for k, v in steps:
            box(ax, 0.06, y, 0.20, 0.085, k, INDIGO, fs=10.5, weight="bold")
            box(ax, 0.27, y, 0.67, 0.085, "  " + v, "white", tc=NAVY, fs=9.8, align="left")
            y -= 0.108
        box(ax, 0.06, 0.10, 0.88, 0.06,
            "  Golden rule: keep cash out until the FORWARD paper run beats the index, net of cost.",
            GOLD, tc=NAVY, fs=11, weight="bold", align="left")
        pdf.savefig(fig); plt.close(fig)

        # ---------- PAGE 7 — honesty & roadmap ----------
        fig, ax = newpage(pdf)
        header(ax, "HONEST EXPECTATIONS", "What it will & won't do")
        box(ax, 0.06, 0.74, 0.88, 0.13,
            "  WILL:  beat the index on risk-adjusted terms · cut drawdowns · de-risk in global/regime\n"
            "  stress · diversify by correlation · avoid news blow-ups · compound steadily.",
            "#e7f5ef", tc=NAVY, fs=11, align="left")
        box(ax, 0.06, 0.57, 0.88, 0.13,
            "  WON'T:  pick the next BSE/multibagger (impossible in advance — proven) · predict returns ·\n"
            "  shoot the lights out every year (it's streaky: great in trends, flat in chop).",
            "#fdeaea", tc=NAVY, fs=11, align="left")
        ax.text(0.06, 0.50, "The real ceiling = DATA (point-in-time India fundamentals), not models.",
                color=NAVY, fontsize=11.5, weight="bold")
        ax.text(0.06, 0.43, "Roadmap (free-data, Lab → Core only via DSR>0.95 + PBO):", color=NAVY, fontsize=11, weight="bold")
        for i, t in enumerate(["Fama-French factor overlay", "Conformal uncertainty bands",
                               "Triple-barrier + meta-labelling", "Point-in-time fundamentals (the unlock)"]):
            ax.text(0.09, 0.40 - i * 0.035, "•  " + t, color=GREY, fontsize=10.5)
        box(ax, 0.06, 0.13, 0.88, 0.10,
            "  ARJUNA Doctrine:  survival > prediction · diversification > concentration · regime > selection\n"
            "  · construction > models · data > complexity · robustness > backtests.",
            NAVY, fs=10.8, align="left")
        ax.text(0.5, 0.05, "ARJUNA v2 — built on evidence, not hope. 🏹", color=GREY, fontsize=10, ha="center")
        pdf.savefig(fig); plt.close(fig)

    print(f"  saved -> {pdf_path}")


if __name__ == "__main__":
    main()
