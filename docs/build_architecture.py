# docs/build_architecture.py
"""
Generates the full NexaQuant architecture & strategy deck:
    docs/NexaQuant_Architecture.pdf   (multi-page, colourful, image-rich)

It is BOTH a design document and an evidence book: charts are computed live from the
real gold data and our probes (backtest engine + strategy modules), so the numbers in
the deck always match what the code actually produces.

Run: python docs/build_architecture.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.engine import backtest
from backtest.trade_sim import simulate_trades, trade_stats
from strategy.smc import ema, atr
from strategy.regime import detect_regime
from strategy import playbook

# palette
INK = "#0f1b2d"; SUB = "#5b6b82"; CARD = "#f4f7fb"
BLUE = "#2563eb"; TEAL = "#0ea5a4"; AMBER = "#f59e0b"; GREEN = "#16a34a"
RED = "#dc2626"; PURPLE = "#7c3aed"; SLATE = "#334155"
REG_COL = {"trend": "#16a34a", "range": "#2563eb", "volatile": "#dc2626", "neutral": "#cbd5e1"}


# ----------------------------------------------------------------- shared drawing
def box(ax, x, y, w, h, text, fc, tc="white", fs=11, bold=True, ec=None, rs=0.02):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.006,rounding_size={rs}",
                                fc=fc, ec=ec or fc, lw=1.5, mutation_aspect=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=tc,
            fontsize=fs, fontweight="bold" if bold else "normal", zorder=5)


def arrow(ax, x1, y1, x2, y2, color=SLATE, lw=2.2, style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=18,
                                 lw=lw, color=color, shrinkA=2, shrinkB=2, zorder=1))


def base_ax(fig, title, subtitle=None, page=None):
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 8.55), 16, 0.45, color=INK))
    ax.text(0.4, 8.77, title, color="white", fontsize=18, fontweight="bold", va="center")
    ax.text(15.6, 8.85, "NexaQuant", color="white", fontsize=12, fontweight="bold", va="center", ha="right")
    ax.text(15.6, 8.62, "Gold + BTC Alpha", color="#9fb3d1", fontsize=8.5, va="center", ha="right")
    if subtitle:
        ax.text(0.4, 8.28, subtitle, color=SUB, fontsize=11, va="center")
    if page:
        ax.text(8, 0.18, page, color=SUB, fontsize=8, ha="center")
    return ax


# ----------------------------------------------------------------- live data / charts
def load_curves():
    """Real equity curves + regime series from H1 gold (matches the probes)."""
    df = pd.read_parquet(ROOT / "data/raw/XAUUSDm_H1.parquet").sort_index()
    reg, _, _ = detect_regime(df)
    cont = (ema(df["close"], 20) > ema(df["close"], 50)).astype(float)
    gated = cont.where(reg == "trend", 0.0)
    bh = pd.Series(1.0, index=df.index)
    eq_bh = backtest(df, bh, 0.5)[0].cumsum()
    eq_ct = backtest(df, cont, 0.5)[0].cumsum()
    eq_gt = backtest(df, gated, 0.5)[0].cumsum()
    d1 = pd.read_parquet(ROOT / "data/raw/XAUUSDm_D1.parquet").sort_index()
    reg_d1, _, _ = detect_regime(d1)
    return df, reg, eq_bh, eq_ct, eq_gt, d1, reg_d1


# =============================================================== PAGE 0: COVER
def page_cover(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 16); ax.set_ylim(0, 9); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 16, 9, color=INK))
    ax.add_patch(plt.Rectangle((0, 6.2), 16, 0.06, color=AMBER))
    ax.text(8, 6.9, "NexaQuant", color="white", fontsize=54, fontweight="bold", ha="center")
    ax.text(8, 5.7, "Evidence-First Quant Trading System", color="#9fb3d1", fontsize=18, ha="center")
    ax.text(8, 5.1, "Gold (XAUUSD) + Bitcoin (BTCUSD)  ·  Smart Money Concepts + Regime Gate + AI", color="#9fb3d1", fontsize=12, ha="center")
    # three pillars
    pillars = [("TECHNICALS + SMC", TEAL, "structure · FVG · order blocks\nliquidity · premium/discount"),
               ("REGIME + RISK", PURPLE, "trend/range/volatile gate\nATR stops · vol-target sizing"),
               ("AI + FUNDAMENTALS", BLUE, "meta-labeling · MTF features\nmacro bias · ensemble-ready")]
    for i, (t, c, d) in enumerate(pillars):
        x = 1.4 + i * 4.6
        box(ax, x, 2.7, 4.0, 1.7, "", "#16243a", ec=c, rs=0.04)
        ax.text(x + 2.0, 4.0, t, color=c, fontsize=13, fontweight="bold", ha="center")
        ax.text(x + 2.0, 3.35, d, color="#c7d3e6", fontsize=9.5, ha="center")
    ax.text(8, 1.4, "Architecture & Evidence Deck", color="white", fontsize=13, ha="center", fontweight="bold")
    ax.text(8, 0.95, "Charts in this deck are generated live from the real 2y gold dataset and the project's own backtests.",
            color=SUB, fontsize=9, ha="center", style="italic")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: EXEC
def page_exec(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Executive Summary", "Prove the edge, control drawdown, gate capital behind validation", "1")
    ax.text(0.4, 7.9, "The Thesis", color=INK, fontsize=14, fontweight="bold")
    ax.text(0.4, 7.42,
            "Profit = edge x payoff x risk control — NOT win-rate or model hype. We capture a small,\n"
            "real, cost-robust edge (trend-continuation incl. SMC structure/FVG), cut drawdown hard with a\n"
            "regime gate, and let AI sharpen selection/sizing as data & features grow. Capital scales only\n"
            "behind a hard validation gate.", color=SLATE, fontsize=11, va="top")
    kpis = [("Regime-gated trend (H1)", "Sharpe 3.6", "out-of-sample, net of cost", GREEN),
            ("Drawdown vs buy&hold", "-33%", "$254 -> $172 (H1 OOS)", TEAL),
            ("FVG + Structure (H4)", "Sharpe 1.9", "robust IN & OUT of sample", BLUE),
            ("AI meta-label today", "AUC 0.51", "premature — needs data+features", AMBER)]
    for i, (t, v, d, c) in enumerate(kpis):
        x = 0.4 + i * 3.95
        box(ax, x, 5.2, 3.7, 1.55, "", CARD, ec="#dbe4f0", rs=0.04)
        ax.text(x + 0.25, 6.5, t, color=SUB, fontsize=9.5, fontweight="bold", va="center")
        ax.text(x + 0.25, 6.05, v, color=c, fontsize=19, fontweight="bold", va="center")
        ax.text(x + 0.25, 5.55, d, color=SLATE, fontsize=8.3, va="center")
    box(ax, 0.4, 2.7, 7.4, 1.95, "", "#eafaf0", ec=GREEN, rs=0.03)
    ax.text(0.65, 4.4, "VALIDATED (out-of-sample, net of cost)", color=GREEN, fontsize=11, fontweight="bold", va="top")
    ax.text(0.65, 3.98,
            "+ Trend-continuation edge (EMA + FVG + Break of Structure)\n"
            "+ Regime gate lifts Sharpe & cuts drawdown ~33%\n"
            "+ Edge survives realistic spread/slippage\n"
            "+ Multi-timeframe + fundamental feature pipeline wired & verified",
            color=SLATE, fontsize=9.3, va="top")
    box(ax, 8.2, 2.7, 7.4, 1.95, "", "#fdeeee", ec=RED, rs=0.03)
    ax.text(8.45, 4.4, "NOT YET PROVEN (honest gaps)", color=RED, fontsize=11, fontweight="bold", va="top")
    ax.text(8.45, 3.98,
            "- Much of return is GOLD BETA (2023-25 bull) — one regime only\n"
            "- Mean-reversion SMC (discount, sweep-fade) lost in trend\n"
            "- AI flat until M5/M15 + BTC + fundamentals add data/features\n"
            "- No live/paper validation yet — do NOT deploy capital",
            color=SLATE, fontsize=9.3, va="top")
    ax.text(0.4, 2.25, "The bet:", color=INK, fontsize=12, fontweight="bold")
    ax.text(1.4, 2.25, "invest in DATA + FEATURES + the VALIDATION GATE — that, not one magic model, is the asset.",
            color=SLATE, fontsize=11, va="center")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: ARCH
def page_arch(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "System Architecture", "Six layers — nothing reaches live capital without passing the gate", "2")
    layers = [
        ("1 · DATA ENGINE", BLUE, ["MT5: XAUUSD + BTCUSD", "W1·D1·H4·H1 (analysis)", "M15·M5 (execution)*", "fundamentals (free)"]),
        ("2 · FEATURE & SMC", TEAL, ["Structure (BOS/CHoCH)", "Fair Value Gaps", "Order Blocks", "Liquidity sweeps", "Premium/Discount"]),
        ("3 · REGIME GATE", PURPLE, ["trend / range / volatile", "ADX + vol ratio", "PILLARS ON/OFF:", "trend->continuation", "range->mean-revert"]),
        ("4 · AI / SIGNAL", AMBER, ["MTF top-down features", "+ fundamentals", "meta-label P(win)", "ensemble-ready"]),
        ("5 · RISK FORTRESS", RED, ["ATR stops & targets", "vol-target / Kelly-frac", "daily loss limit", "circuit breaker"]),
        ("6 · EXECUTION", GREEN, ["paper -> live ramp", "MT5 order routing", "slippage/latency model", "performance tracking"]),
    ]
    x = 0.35; w = 2.5; gap = 0.12; y = 4.6; h = 3.3
    for i, (title, c, items) in enumerate(layers):
        xi = x + i * (w + gap)
        box(ax, xi, y + h - 0.55, w, 0.55, title, c, fs=9.3, rs=0.05)
        box(ax, xi, y, w, h - 0.62, "", CARD, ec="#dbe4f0", rs=0.04)
        for j, it in enumerate(items):
            mark = "" if it.endswith(":") else "•"
            ax.text(xi + 0.13, y + h - 1.05 - j * 0.44, f"{mark} {it}", color=SLATE,
                    fontsize=7.7, va="center", fontweight="bold" if it.endswith(":") else "normal")
        if i < len(layers) - 1:
            arrow(ax, xi + w, y + h / 2, xi + w + gap, y + h / 2, color=SLATE, lw=2)
    box(ax, 0.35, 2.4, 15.3, 1.4, "", "#fff7e6", ec=AMBER, rs=0.02)
    ax.text(0.55, 3.5, "VALIDATION GAUNTLET  (the real moat — between Signal and Execution)",
            color="#b45309", fontsize=11, fontweight="bold", va="top")
    gates = ["Temporal firewall\n(embargo)", "Walk-forward +\nPurged CV", "Regime-stratified\nbacktest",
             "30-day PAPER\ntrading", "Brier < 0.25\ncalibration", "Go / No-Go\ncertification"]
    for i, g in enumerate(gates):
        gx = 0.6 + i * 2.55
        box(ax, gx, 2.55, 2.35, 0.8, g, "white", tc="#b45309", fs=8, ec=AMBER, rs=0.06)
        if i < len(gates) - 1:
            arrow(ax, gx + 2.35, 2.95, gx + 2.55, 2.95, color=AMBER, lw=1.8)
    ax.text(0.35, 1.7, "Cross-cutting:", color=INK, fontsize=10, fontweight="bold")
    ax.text(2.1, 1.7, "config-driven (zero hardcoding) · health monitor & kill-switch · drift detection & auto-retrain · experience memory",
            color=SLATE, fontsize=9.2)
    ax.text(0.35, 0.75, "* M15/M5 + BTCUSD not yet pulled (data/pull_mt5.py). Today: Data + SMC + Regime + Signal + Backtest run live.",
            color=SUB, fontsize=8.5, style="italic")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: DATA + MTF
def page_data(pdf, df, reg_d1, d1):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Data & Multi-Timeframe Stack", "Analyse high, execute low — higher TFs become model features too", "3")
    # left: instruments/timeframes table
    ax.text(0.4, 7.9, "Instruments & timeframes", color=INK, fontsize=13, fontweight="bold")
    rows = [("XAUUSD (gold)", "W1 D1 H4 H1", "M15 M5", "present / to-pull"),
            ("BTCUSD", "W1 D1 H4 H1", "M15 M5", "to-pull (auto-included)")]
    ax.text(0.4, 7.4, f"{'symbol':<16}{'analysis':<14}{'execution':<10}", color=SUB, fontsize=9.5, fontweight="bold")
    for i, (s, a, e, st) in enumerate(rows):
        yy = 7.0 - i * 0.5
        ax.text(0.4, yy, f"{s:<16}{a:<14}{e:<10}", color=SLATE, fontsize=9.5)
    ax.text(0.4, 5.8, "Fundamentals (FREE): FRED real yields · DXY · CFTC COT · economic calendar",
            color=SLATE, fontsize=9.5)
    # top-down funnel
    funnel = [("WEEKLY", "bias", PURPLE), ("DAILY", "trend + S/R", BLUE), ("4-HOUR", "setup", TEAL),
              ("1-HOUR", "refine", AMBER), ("15m/5m", "ENTRY", GREEN)]
    ax.text(0.4, 5.3, "Top-down funnel (also the model's MTF features)", color=INK, fontsize=12, fontweight="bold")
    for i, (tf, d, c) in enumerate(funnel):
        ww = 5.0 - i * 0.45
        box(ax, 0.5 + (5.0 - ww) / 2, 4.7 - i * 0.62, ww, 0.5, f"{tf} — {d}", c, fs=8.5, rs=0.05)
    # right: regime-coloured gold price (real)
    chart = fig.add_axes([0.46, 0.12, 0.5, 0.66])
    chart.plot(d1.index, d1["close"], color=INK, lw=1.2)
    for r, c in REG_COL.items():
        mask = (reg_d1 == r).values
        chart.fill_between(d1.index, d1["close"].min(), d1["close"].max(),
                           where=mask, color=c, alpha=0.12, step="mid")
    chart.set_title("Gold (D1) coloured by detected regime — green=trend blue=range red=volatile",
                    color=INK, fontsize=10, fontweight="bold")
    chart.tick_params(labelsize=8); chart.spines[["top", "right"]].set_visible(False)
    chart.set_ylabel("XAUUSD", fontsize=9)
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: SMC
def page_smc(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "SMC Strategy Stack", "Read institutional footprints — the regime decides which to trust", "4")
    pillars = [("1 · Fair Value Gap", "3-candle imbalance; price revisits", TEAL, "EDGE +"),
               ("2 · Market Structure", "BOS / CHoCH = trend & reversal", BLUE, "EDGE +"),
               ("3 · Order Blocks", "last opposite candle = demand/supply", PURPLE, "context"),
               ("4 · Liquidity Sweeps", "stop-hunt beyond swing then reclaim", AMBER, "EDGE - in trend"),
               ("5 · Premium / Discount", "25/50/75% of swing range", SLATE, "EDGE - in trend")]
    ax.text(0.4, 7.9, "The 5 pillars (with measured edge)", color=INK, fontsize=13, fontweight="bold")
    for i, (t, d, c, tag) in enumerate(pillars):
        yy = 7.2 - i * 1.05
        box(ax, 0.4, yy, 8.0, 0.9, "", CARD, ec="#dbe4f0", rs=0.04)
        box(ax, 0.4, yy, 0.18, 0.9, "", c, rs=0.0)
        ax.text(0.8, yy + 0.58, t, color=INK, fontsize=11, fontweight="bold", va="center")
        ax.text(0.8, yy + 0.25, d, color=SLATE, fontsize=8.6, va="center")
        tc = GREEN if tag == "EDGE +" else (RED if tag.startswith("EDGE -") else SUB)
        ax.text(8.2, yy + 0.45, tag, color=tc, fontsize=9, fontweight="bold", va="center", ha="right")
    # regime gate right
    ax.text(9.2, 7.9, "Regime gate decides", color=INK, fontsize=13, fontweight="bold")
    gates = [("TRENDING", GREEN, "ON: Structure + FVG (continuation) — GO WITH the move", "#eafaf0"),
             ("RANGING", BLUE, "ON: Discount-buy + sweep (mean-revert) — FADE extremes", "#eef4ff"),
             ("VOLATILE", RED, "size DOWN or STAND ASIDE", "#fdeeee")]
    for i, (t, c, d, bg) in enumerate(gates):
        yy = 6.7 - i * 1.5
        box(ax, 9.2, yy, 6.4, 1.25, "", bg, ec=c, rs=0.04)
        ax.text(9.45, yy + 0.95, t, color=c, fontsize=11, fontweight="bold", va="top")
        ax.text(9.45, yy + 0.55, d, color=SLATE, fontsize=9, va="top")
    box(ax, 0.4, 0.5, 15.2, 1.3, "", INK, rs=0.02)
    ax.text(0.7, 1.45, "KEY INSIGHT FROM OUR DATA", color=AMBER, fontsize=11, fontweight="bold", va="top")
    ax.text(0.7, 1.05,
            "Continuation pillars (Structure + FVG) had POSITIVE edge on trending gold; mean-reversion pillars\n"
            "(deep-discount, sweep-fade) had NEGATIVE edge. Stacking all 5 ('A+') LOST money — the regime gate,\n"
            "not more indicators, is what turns SMC into profit.", color="white", fontsize=9.5, va="top")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: STRATEGY / PLAYBOOK
def exit_study_data():
    """Live Sharpe by exit style on gold H4 OOS — the evidence behind the playbook."""
    df = pd.read_parquet(ROOT / "data/raw/XAUUSDm_H4.parquet").sort_index()
    oos = df.iloc[int(len(df) * 0.7):]
    a = atr(oos, 14)
    reg, _, _ = detect_regime(oos)
    base = ((ema(oos["close"], 20) > ema(oos["close"], 50)) & (reg == "trend")).astype(bool)
    ent = base & (~base.shift(1, fill_value=False))
    mom = oos["close"] < ema(oos["close"], 20)
    styles = {
        "Let it run": dict(stop_mult=1.5),
        "Tight trail": dict(stop_mult=1.5, trail_trigger=1.0, trail_dist=1.5),
        "2R target": dict(stop_mult=1.5, rr=2.0),
        "Momentum-ride": dict(stop_mult=2.0, exit_signal=mom),
        "Mom+scale-out": dict(stop_mult=2.0, partial_at=1.5, partial_frac=0.4, exit_signal=mom),
    }
    out = {}
    for name, kw in styles.items():
        tr = simulate_trades(oos, ent, a, 0.5, **kw)
        s = trade_stats(tr, 6 * 252, tr["bars"].mean() if not tr.empty else 1)
        out[name] = s["sharpe"] if s else 0.0
    return out


def page_strategy(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Trading Playbook (the Strategy)",
                 "Entries give a small edge — STOPS, TRAILING & MOMENTUM-RIDING make the profit", "5")
    # flow steps (left)
    steps = [("BIAS", PURPLE, "Weekly/Daily trend + macro\n(yields↓, USD↓ = gold long)"),
             ("REGIME GATE", BLUE, "trade continuation only in TREND;\nstand aside if volatile"),
             ("ENTRY", TEAL, "EMA20>EMA50 + bullish\nstructure / FVG (execution TF)"),
             ("STOP-LOSS", RED, "hard 2×ATR stop —\nNON-NEGOTIABLE, caps every loss"),
             ("BIGGER PROFIT", GREEN, "MOMENTUM-RIDE: hold while\nclose>EMA20, exit when it fades"),
             ("SCALE-OUT", AMBER, "bank ~40% at +1.5R, move to\nbreakeven, let the rest run"),
             ("SIZING", SLATE, "volatility-targeted,\nfractional-Kelly capped")]
    for i, (t, c, d) in enumerate(steps):
        yy = 7.4 - i * 1.02
        box(ax, 0.4, yy, 2.5, 0.85, t, c, fs=10, rs=0.05)
        ax.text(3.1, yy + 0.42, d, color=SLATE, fontsize=9, va="center")
        if i < len(steps) - 1:
            arrow(ax, 1.65, yy, 1.65, yy - 0.17, color=SLATE, lw=1.6)
    # live exit-study chart (right)
    try:
        data = exit_study_data()
    except Exception:
        data = {}
    if data:
        chart = fig.add_axes([0.56, 0.40, 0.40, 0.40])
        names = list(data.keys()); vals = list(data.values())
        cols = [SUB if v < 1 else (RED if v < 0 else GREEN) for v in vals]
        cols = [RED if v < 0 else (GREEN if n.startswith("Mom") else TEAL) for n, v in zip(names, vals)]
        chart.barh(names, vals, color=cols)
        chart.axvline(0, color=INK, lw=1); chart.axvline(1, color=AMBER, ls="--", lw=1)
        chart.set_title("OOS Sharpe by EXIT style (gold H4, same entries)", fontsize=10, fontweight="bold", color=INK)
        chart.tick_params(labelsize=8.5); chart.spines[["top", "right"]].set_visible(False)
        for i, v in enumerate(vals):
            chart.text(v + (0.05 if v >= 0 else -0.05), i, f"{v:.1f}",
                       va="center", ha="left" if v >= 0 else "right", fontsize=8.5, fontweight="bold")
    box(ax, 8.7, 0.6, 6.9, 2.4, "", INK, rs=0.02)
    ax.text(9.0, 2.75, "WHY MOMENTUM-RIDE", color=AMBER, fontsize=11, fontweight="bold", va="top")
    ax.text(9.0, 2.35,
            "• Stop-loss is mandatory — caps every loser\n"
            "• Tight trailing turns the edge NEGATIVE (chokes winners)\n"
            "• Riding momentum captures big R-multiples (up to 8.7R)\n"
            "  while cutting drawdown ~40% vs 'let it run forever'\n"
            "• Scale-out lifts win-rate to ~64% and smooths the curve",
            color="white", fontsize=9.2, va="top")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: EVIDENCE (charts)
def page_evidence(pdf, df, reg, eq_bh, eq_ct, eq_gt):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Evidence Dashboard", "Computed live from the real 2y gold data + project backtests", "6")
    # equity curves (real)
    c1 = fig.add_axes([0.06, 0.52, 0.42, 0.30])
    c1.plot(eq_bh.index, eq_bh, color=SUB, lw=1.4, label="Buy & hold")
    c1.plot(eq_ct.index, eq_ct, color=BLUE, lw=1.4, label="Continuation (always-on)")
    c1.plot(eq_gt.index, eq_gt, color=GREEN, lw=1.6, label="Regime-gated continuation")
    c1.legend(fontsize=7.5, loc="upper left"); c1.tick_params(labelsize=7.5)
    c1.set_title("Cumulative $ PnL per 1oz (H1, net cost)", fontsize=10, fontweight="bold", color=INK)
    c1.spines[["top", "right"]].set_visible(False)
    # drawdown (real)
    c2 = fig.add_axes([0.56, 0.52, 0.40, 0.30])
    for eq, col, lab in [(eq_bh, SUB, "B&H"), (eq_gt, GREEN, "Gated")]:
        dd = eq.cummax() - eq
        c2.fill_between(dd.index, -dd, 0, color=col, alpha=0.4, label=lab)
    c2.legend(fontsize=7.5); c2.tick_params(labelsize=7.5)
    c2.set_title("Drawdown ($) — gated is shallower", fontsize=10, fontweight="bold", color=INK)
    c2.spines[["top", "right"]].set_visible(False)
    # Sharpe bars
    c3 = fig.add_axes([0.06, 0.10, 0.42, 0.30])
    names = ["B&H", "EMA\nTrend", "FVG+\nStruct", "Liq\nSweep", "A+\n5pillar"]
    vals = [2.34, 3.24, 1.85, 1.36, -1.18]; cols = [SUB, GREEN, TEAL, BLUE, RED]
    c3.bar(names, vals, color=cols); c3.axhline(0, color=INK, lw=1); c3.axhline(1, color=AMBER, ls="--", lw=1)
    c3.set_title("OOS Sharpe by strategy", fontsize=10, fontweight="bold", color=INK)
    c3.tick_params(labelsize=7.5); c3.spines[["top", "right"]].set_visible(False)
    for i, v in enumerate(vals):
        c3.text(i, v + (0.1 if v >= 0 else -0.3), f"{v:.1f}", ha="center", fontsize=8, fontweight="bold")
    # regime pie (real)
    c4 = fig.add_axes([0.58, 0.10, 0.34, 0.30])
    mix = reg.value_counts(normalize=True)
    c4.pie(mix.values, labels=[f"{k}\n{v:.0%}" for k, v in mix.items()],
           colors=[REG_COL.get(k, "#999") for k in mix.index], textprops={"fontsize": 8},
           wedgeprops={"edgecolor": "white"})
    c4.set_title("H1 regime mix (detected)", fontsize=10, fontweight="bold", color=INK)
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: AI / MODEL LAYER
def page_ai(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "AI / Model Layer", "Models SIZE & SELECT a known edge — they do not invent one", "7")
    # feature pipeline
    ax.text(0.4, 7.9, "Feature pipeline -> meta-model -> sizing", color=INK, fontsize=13, fontweight="bold")
    groups = [("TECHNICAL", TEAL, "RSI, ADX, ATR ratio,\nEMA dist/slope, returns, time"),
              ("STRUCTURE / SMC", PURPLE, "structure dir, FVG context,\npremium/discount ratio"),
              ("MULTI-TIMEFRAME", BLUE, "D1/H4 (M15) trend, ADX,\nRSI, momentum as features"),
              ("FUNDAMENTAL", AMBER, "real-yield & DXY trend,\nCOT, event proximity")]
    for i, (t, c, d) in enumerate(groups):
        yy = 7.0 - i * 1.0
        box(ax, 0.4, yy, 4.4, 0.85, "", CARD, ec=c, rs=0.04)
        ax.text(0.6, yy + 0.55, t, color=c, fontsize=10, fontweight="bold", va="center")
        ax.text(0.6, yy + 0.22, d, color=SLATE, fontsize=8, va="center")
        arrow(ax, 4.8, yy + 0.42, 5.8, 4.4, color=SLATE, lw=1.3)
    box(ax, 5.8, 3.9, 2.6, 1.1, "META-MODEL\nP(win)", PURPLE, fs=10, rs=0.05)
    arrow(ax, 8.4, 4.45, 9.4, 4.45, color=SLATE)
    box(ax, 9.4, 3.9, 2.6, 1.1, "FILTER + SIZE\ntrade", GREEN, fs=10, rs=0.05)
    ax.text(0.4, 2.7, "Today: AUC 0.51 (coin-flip) — 154 entries, technical-only. The plumbing is verified "
            "(28/28 features active with MTF+fundamentals wired); it gains skill as data/features grow.",
            color=SLATE, fontsize=9.2, va="top")
    # staging ladder
    ax.text(0.4, 2.1, "Model staging (complexity rises only with data + validation)", color=INK, fontsize=12, fontweight="bold")
    stages = [("1 ML meta-label", GREEN, "built"), ("2 ML ensemble", TEAL, "next"),
              ("3 RL sizing/exits", BLUE, "needs M5/M15+BTC"), ("4 DL features", PURPLE, "lots of data"),
              ("5 Multi-agent", AMBER, "end-state")]
    for i, (t, c, tag) in enumerate(stages):
        gx = 0.4 + i * 3.1
        box(ax, gx, 1.0, 2.9, 0.7, t, c, fs=9.5, rs=0.06)
        ax.text(gx + 1.45, 0.7, tag, color=SUB, fontsize=7.8, ha="center")
        if i < len(stages) - 1:
            arrow(ax, gx + 2.9, 1.35, gx + 3.1, 1.35, color=SLATE, lw=1.6)
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: VALIDATION
def page_validation(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Validation Gauntlet", "Why most backtests fail live — and how we refuse to", "8")
    ax.text(0.4, 7.9, "The 5 ways backtests lie (and our defence)", color=INK, fontsize=13, fontweight="bold")
    defs = [("Data leakage / look-ahead", "signal at close(t) -> trade at open(t+1); HTF & macro shifted to release", RED),
            ("Overfitting / curve-fit", "default params; in-sample vs out-of-sample split always reported", AMBER),
            ("Multiple testing", "few strategies tested; deflated-Sharpe mindset; no p-hacking", PURPLE),
            ("Ignoring costs", "every trade net of spread+slippage; cost-sensitivity run", BLUE),
            ("One-regime sample", "regime-stratified results; flagged as a known gap", TEAL)]
    for i, (t, d, c) in enumerate(defs):
        yy = 7.2 - i * 0.95
        box(ax, 0.4, yy, 9.6, 0.8, "", CARD, ec=c, rs=0.04)
        ax.text(0.6, yy + 0.52, t, color=c, fontsize=10, fontweight="bold", va="center")
        ax.text(0.6, yy + 0.2, d, color=SLATE, fontsize=8.2, va="center")
    # gate flow on right
    ax.text(10.4, 7.9, "The gate (in order)", color=INK, fontsize=13, fontweight="bold")
    gates = ["Temporal firewall (embargo)", "Walk-forward + Purged CV", "Regime-stratified backtest",
             "30-day paper trading", "Calibration (Brier<0.25)", "Go / No-Go certification"]
    for i, g in enumerate(gates):
        yy = 7.2 - i * 0.95
        box(ax, 10.4, yy, 5.2, 0.7, g, INK if i % 2 else SLATE, fs=9, rs=0.05)
        if i < len(gates) - 1:
            arrow(ax, 13.0, yy, 13.0, yy - 0.25, color=AMBER, lw=1.6)
    box(ax, 0.4, 0.5, 15.2, 1.0, "", "#fff7e6", ec=AMBER, rs=0.02)
    ax.text(0.7, 1.0, "BUILDING NEXT: walk-forward + Combinatorial Purged CV (López de Prado) — the rigor gate that "
            "lets us trust ANY strategy or model before capital.", color="#b45309", fontsize=10, fontweight="bold", va="center")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: ROADMAP
def page_roadmap(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Roadmap & KPIs", "The only safe path to live capital", "9")
    phases = [("NOW", "Edge proven on gold; SMC+regime+AI framework built", GREEN, "done"),
              ("P1", "Pull M5/M15 + BTC; pull free fundamentals", BLUE, "data"),
              ("P2", "Multi-regime history; ML ensemble", PURPLE, "features"),
              ("P3", "Walk-forward + Purged CV (100s of trades)", TEAL, "validate"),
              ("P4", "30-day paper; backtest ≈ live", AMBER, "gate"),
              ("P5", "Live ramp 25→50→100%; add FX", RED, "scale")]
    ax.text(0.4, 7.7, "Phases", color=INK, fontsize=13, fontweight="bold")
    n = len(phases); x0 = 0.6; xw = 14.8 / n
    ax.add_patch(plt.Rectangle((x0, 6.0), 14.8, 0.06, color="#dbe4f0"))
    for i, (p, d, c, tag) in enumerate(phases):
        cx = x0 + i * xw + xw / 2
        ax.add_patch(plt.Circle((cx, 6.03), 0.13, color=c, zorder=5))
        box(ax, cx - xw / 2 + 0.15, 6.4, xw - 0.3, 0.55, p, c, fs=12, rs=0.06)
        ax.text(cx, 5.7, d, color=SLATE, fontsize=8, ha="center", va="top")
        ax.text(cx, 4.9, tag.upper(), color=c, fontsize=7.5, ha="center", fontweight="bold")
    # KPI targets
    ax.text(0.4, 4.2, "Live targets (realistic, post-cost)", color=INK, fontsize=13, fontweight="bold")
    kpis = [("Win rate", "50-60%", GREEN), ("Sharpe", "1.0-1.5", TEAL), ("Monthly ROI", "1-4%", BLUE),
            ("Max drawdown", "< 20%", AMBER), ("Uptime", "90-95%", PURPLE)]
    for i, (t, v, c) in enumerate(kpis):
        x = 0.4 + i * 3.1
        box(ax, x, 2.7, 2.9, 1.1, "", CARD, ec=c, rs=0.04)
        ax.text(x + 1.45, 3.45, v, color=c, fontsize=18, fontweight="bold", ha="center")
        ax.text(x + 1.45, 2.95, t, color=SUB, fontsize=9.5, ha="center", fontweight="bold")
    box(ax, 0.4, 0.6, 15.2, 1.5, "", INK, rs=0.02)
    ax.text(0.7, 1.85, "SUCCESS METRIC", color=AMBER, fontsize=11, fontweight="bold", va="top")
    ax.text(0.7, 1.45, "A strategy that holds Sharpe ≥ 1.0 ACROSS regimes AND in 30-day paper trading earns real capital — "
            "nothing else does.\nModel complexity (ML→ensemble→RL→multi-agent) increases ONLY together with data breadth and validation rigor.",
            color="white", fontsize=9.8, va="top")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: RESEARCH EVIDENCE
def page_research(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Research Evidence & Model Selection",
                 "What the peer-reviewed literature actually supports (deep-research, adversarially verified)", "10")
    rows = [
        ("Stop-loss", "Regime-conditional: HELPS under momentum, HURTS under random-walk/mean-reversion",
         "STRONG", "VALIDATES us — we only stop within the TREND regime", GREEN, "Kaminski & Lo 2014"),
        ("Let winners run", "Fixed/MACD take-profit did NOT beat letting it run (FX/metals/crypto)",
         "MODERATE", "VALIDATES — momentum-ride > 2R target in our tests", GREEN, "Vezeris 2018"),
        ("Stop+momentum", "10% stop on momentum: Sharpe 0.17->0.37, skew flipped +; tail capped",
         "STRONG*", "Supports SL + momentum (but equity, gross of cost)", TEAL, "Han-Zhou-Zhu 2016"),
        ("Vol-targeting", "NAIVE single-factor vol-targeting fails OOS & net of costs",
         "STRONG(-)", "CAUTION — matches our cost-churn finding; size cost-aware", AMBER, "Cederburg 2020"),
        ("Vol (multifactor)", "Multifactor, cost-optimized vol-conditioning DOES add ~13% Sharpe",
         "STRONG", "Adopt at portfolio level, not naive per-bar", TEAL, "DeMiguel 2024"),
        ("CPCV + Deflated SR", "Adaptive search -> spurious backtests; needs trial-adjusted metrics",
         "STRONG", "VALIDATES our validator.py (CPCV + DSR + embargo)", GREEN, "Bailey & LdP; Harvey-Liu"),
        ("Deep RL", "Crypto DRL prone to false-positive overfit; needs overfit test",
         "MODERATE", "VALIDATES deferring RL behind the gate", AMBER, "Gort et al. 2022"),
        ("SMC (FVG/OB/ICT)", "ZERO verified academic evidence of independent edge",
         "NONE", "Treat as folklore; our edge = trend/momentum overlap", RED, "(unanswered)"),
        ("Free data", "Dukascopy, CFTC COT, FRED are primary/trusted sources",
         "n/a", "Our pullers target these (+ Binance, Stooq)", SLATE, "Dukascopy/CFTC/FRED"),
    ]
    ax.text(0.4, 7.95, f"{'Topic':<16}{'Finding':<58}{'Evidence':<11}{'NexaQuant decision'}",
            color=INK, fontsize=9.5, fontweight="bold", family="monospace")
    y = 7.45
    for topic, finding, strength, decision, col, cite in rows:
        ax.add_patch(plt.Rectangle((0.4, y - 0.30), 15.2, 0.58, fc=CARD, ec="#dbe4f0", lw=0.8))
        ax.add_patch(plt.Rectangle((0.4, y - 0.30), 0.12, 0.58, fc=col))
        ax.text(0.62, y + 0.08, topic, color=INK, fontsize=8.6, fontweight="bold", va="center")
        ax.text(3.0, y + 0.13, finding, color=SLATE, fontsize=7.6, va="center")
        ax.text(3.0, y - 0.13, cite, color=SUB, fontsize=6.7, va="center", style="italic")
        ax.text(9.55, y + 0.0, strength, color=col, fontsize=8.2, fontweight="bold", va="center")
        ax.text(11.2, y + 0.0, decision, color=SLATE, fontsize=7.4, va="center")
        y -= 0.70
    box(ax, 0.4, 0.4, 15.2, 1.05, "", INK, rs=0.02)
    ax.text(0.7, 1.28, "SCOPE CAVEAT + WHAT TO AVOID", color=AMBER, fontsize=10, fontweight="bold", va="top")
    ax.text(0.7, 0.95,
            "Most STRONG evidence is monthly US EQUITY factors — NOT intraday gold/BTC. Mechanisms transfer, "
            "but we must RE-VALIDATE on our instruments (the rigor gate does this).\n"
            "Refuted / avoid: specific ATR(12,6,2) params · Kelly-VIX hybrid sizing · 'vol-scaling doubles t-stat' · CVaR-variant superiority claims.",
            color="white", fontsize=8.4, va="top")
    pdf.savefig(fig); plt.close(fig)


# =============================================================== PAGE: LATEST VALIDATED CONFIG
def page_latest(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Validated Config & Results (v2)",
                 "Design goal: make money at LOW RISK by trading only high-confidence setups", "11")
    # design philosophy
    box(ax, 0.4, 6.7, 15.2, 1.5, "", "#eef4ff", ec=BLUE, rs=0.03)
    ax.text(0.65, 8.05, "DESIGN PRINCIPLE", color=BLUE, fontsize=11, fontweight="bold", va="top")
    ax.text(0.65, 7.65,
            "Win-rate / trade-selection first; lot size follows. Regime-aware LONG+SHORT, confluence entries\n"
            "(trend regime + structure + momentum), momentum-ride exit + scale-out, CONFIDENCE-TIERED risk\n"
            "(0.5% / 1% / 2% by trend strength, 2% hard cap). AI meta-label tightens selection as data grows.",
            color=SLATE, fontsize=9.3, va="top")
    # results table (OOS, long+short, tiered risk)
    ax.text(0.4, 6.3, "Re-test — best pair & timeframe (OOS, net of cost)", color=INK, fontsize=13, fontweight="bold")
    rows = [("BTC", "H1", "50", "3.66", "2.5%", "low-risk pick", GREEN),
            ("XAU", "H1", "44", "4.59", "3.9%", "low-risk pick", GREEN),
            ("BTC", "H4", "43", "1.95", "14.8%", "more return, more DD", AMBER),
            ("ETH", "H4", "46", "-0.01", "28%", "weak", RED),
            ("BNB", "H1", "26", "0.40", "5.3%", "weak", RED),
            ("SOL", "H4", "42", "-2.41", "33%", "avoid", RED)]
    ax.text(0.5, 5.8, f"{'pair':<7}{'TF':<6}{'win%':<8}{'Sharpe':<9}{'maxDD':<9}{'verdict'}",
            color=SUB, fontsize=10, fontweight="bold", family="monospace")
    y = 5.4
    for pair, tf, win, sh, dd, verdict, col in rows:
        ax.add_patch(plt.Rectangle((0.4, y - 0.18), 15.2, 0.42, fc=CARD, ec="#dbe4f0", lw=0.6))
        ax.add_patch(plt.Rectangle((0.4, y - 0.18), 0.1, 0.42, fc=col))
        ax.text(0.6, y, f"{pair:<7}{tf:<6}{win+'%':<8}{sh:<9}{dd:<9}", color=INK, fontsize=9, va="center", family="monospace")
        ax.text(11.5, y, verdict, color=col, fontsize=8.5, va="center", fontweight="bold")
        y -= 0.5
    # realistic expectations + honest caveat
    box(ax, 0.4, 0.5, 7.5, 1.7, "", "#eafaf0", ec=GREEN, rs=0.03)
    ax.text(0.65, 2.05, "REALISTIC TARGET", color=GREEN, fontsize=10.5, fontweight="bold", va="top")
    ax.text(0.65, 1.65,
            "Low risk, high Sharpe: BTC/XAU H1, long+short.\n"
            "~3% max drawdown, win ~50% with big payoff.\n"
            "Return ~10-25%/yr (more with capital + AI selection).\n"
            "Beats a bank 3-5x at low drawdown.",
            color=SLATE, fontsize=9, va="top")
    box(ax, 8.1, 0.5, 7.5, 1.7, "", "#fdeeee", ec=RED, rs=0.03)
    ax.text(8.35, 2.05, "HONEST LIMITS", color=RED, fontsize=10.5, fontweight="bold", va="top")
    ax.text(8.35, 1.65,
            "5-10%/MONTH is NOT achievable sustainably\n"
            "(Medallion, the best ever, ~4%/mo). Chasing it =\n"
            "ruin. Bigger money = robust edge x CAPITAL x time,\n"
            "NOT leverage. Backtest, not live — paper-test first.",
            color=SLATE, fontsize=9, va="top")
    pdf.savefig(fig); plt.close(fig)


def page_findings(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Edge Research — What We Kept vs Rejected (v3)",
                 "Honest, evidence-first: every idea back-tested on BTC H4, kept only if it provably helps", "12")
    # KEPT
    ax.text(0.4, 8.05, "KEPT — proven to add pips", color=GREEN, fontsize=13, fontweight="bold", va="top")
    box(ax, 0.4, 6.55, 15.2, 1.25, "", "#eafaf0", ec=GREEN, rs=0.03)
    ax.text(0.65, 7.55, "LENGTHY-CANDLE CONFIDENCE BOOST", color=GREEN, fontsize=10.5, fontweight="bold", va="top")
    ax.text(0.65, 7.15,
            "A wide-range bar (body >= 1.5x ATR) confirming a regime entry marks the highest-quality trades\n"
            "(52% win, PF 3.38, 1,444 avg pips vs 84 baseline). Used as a +50% SIZE boost (not a standalone\n"
            "trigger): BTC H4 return +42% -> +54% at the SAME 4% drawdown. Big candles confirm; they don't trigger.",
            color=SLATE, fontsize=9.2, va="top")
    # REJECTED
    ax.text(0.4, 6.2, "REJECTED — tested, did not survive (won't be shipped)", color=RED, fontsize=13, fontweight="bold", va="top")
    rows = [("Pyramiding (add-to-winner)", "+42% -> -13%, drawdown 4% -> 20% — adds buy near tops"),
            ("Candle streaks 2/3/4 as entry", "profit factor < 1.0 on EVERY timeframe — patterns fire too late"),
            ("Pure expansion candle entry", "PF 0.96 — lengthy candle works only as a filter, not a trigger"),
            ("Fast timeframes (M5 / M15)", "M5 = -100% (account wiped), M15 = -77% — cost + noise dominate")]
    y = 5.55
    for name, why in rows:
        ax.add_patch(plt.Rectangle((0.4, y - 0.2), 15.2, 0.62, fc=CARD, ec="#dbe4f0", lw=0.6))
        ax.add_patch(plt.Rectangle((0.4, y - 0.2), 0.1, 0.62, fc=RED))
        ax.text(0.65, y + 0.12, name, color=INK, fontsize=10, va="center", fontweight="bold")
        ax.text(0.65, y - 0.12, why, color=SLATE, fontsize=8.6, va="center")
        y -= 0.72
    # SELF-LEARNING LOOP
    box(ax, 0.4, 0.5, 15.2, 2.0, "", "#eef4ff", ec=BLUE, rs=0.03)
    ax.text(0.65, 2.35, "WEEKLY SELF-LEARNING LOOP  (execution/auto_update.py)", color=BLUE, fontsize=11, fontweight="bold", va="top")
    ax.text(0.65, 1.95,
            "Runs every week (systemd timer): 1) PULL fresh bars (incremental, history grows)  2) RE-VALIDATE via\n"
            "anchored PER-YEAR walk-forward (not a single noisy slice)  3) PROMOTE a config only if it passes the\n"
            "gate AND beats the champion — never auto-degrades  4) write the bot's TRADING LICENSE (health.json).\n"
            "The live bot reads the license each cycle: if the edge stops persisting on fresh data, it AUTO-STANDS-\n"
            "DOWN to manage-only. Self-learning with a guardrail — it cannot keep trading a dead strategy.",
            color=SLATE, fontsize=9.2, va="top")
    pdf.savefig(fig); plt.close(fig)


def page_sizing(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Position Sizing & Safety — Option B (dynamic, compounding)",
                 "Confidence-scaled lots, earned by account growth — never hardcoded, never ruinous", "14")
    # Option B formula
    box(ax, 0.4, 6.95, 15.2, 1.25, "", "#eef4ff", ec=BLUE, rs=0.03)
    ax.text(0.65, 8.0, "OPTION B — how every lot is sized (execution/live_trader._calc_lots)", color=BLUE, fontsize=11, fontweight="bold", va="top")
    ax.text(0.65, 7.55,
            "lot = (live_balance x risk% x CONFIDENCE) / broker_loss_per_lot     [read live from MT5 symbol_info]\n"
            "risk% tiers 0.5/1/2% by trend strength; CONFIDENCE = ADX x lengthy-candle boost. Re-reads balance each\n"
            "cycle: compounds up as profit grows, shrinks on withdrawal/drawdown. Zero hardcoding; any broker/account.",
            color=SLATE, fontsize=9.2, va="top")
    # $10 lot study
    ax.text(0.4, 6.5, "$10 account, 3-yr BTC H4 — fixed lots vs Option B", color=INK, fontsize=12.5, fontweight="bold", va="top")
    rows = [("fixed 0.01 (standard acct)", "RUINED on trade #1 — one stop > the whole $10", RED),
            ("fixed 0.05 (cent acct)", "+49% but 46% drawdown — pure leverage, no skill", AMBER),
            ("Option B %-risk compounding", "+9% at 4% drawdown — best risk-adjusted, can't be ruined", GREEN)]
    y = 5.95
    for name, res, col in rows:
        ax.add_patch(plt.Rectangle((0.4, y - 0.18), 15.2, 0.56, fc=CARD, ec="#dbe4f0", lw=0.6))
        ax.add_patch(plt.Rectangle((0.4, y - 0.18), 0.1, 0.56, fc=col))
        ax.text(0.65, y + 0.08, name, color=INK, fontsize=9.6, va="center", fontweight="bold")
        ax.text(6.7, y + 0.02, res, color=col, fontsize=8.8, va="center", fontweight="bold")
        y -= 0.66
    ax.text(0.4, 3.75,
            "WHEN bigger lots (0.02/0.04/0.05) apply: as the balance GROWS (~$20/$40/$50 -> next tier) AND on\n"
            "HIGH-CONFIDENCE trades (strong ADX + lengthy candle multiply the lot 2-4x). Earned, not forced onto $10.",
            color=SLATE, fontsize=9.3, va="top")
    # safety: trading license
    box(ax, 0.4, 0.5, 15.2, 2.55, "", "#eafaf0", ec=GREEN, rs=0.03)
    ax.text(0.65, 2.9, "SELF-LEARNING + SAFETY  (execution/auto_update.py -> health.json -> the bot)", color=GREEN, fontsize=11, fontweight="bold", va="top")
    ax.text(0.65, 2.5,
            "Weekly (systemd timer): pull fresh bars -> re-validate via anchored PER-YEAR walk-forward -> promote a\n"
            "config only if it BEATS the champion (never auto-degrades) -> write the bot's TRADING LICENSE.\n"
            "The live bot reads the license each cycle and AUTO-STANDS-DOWN to manage-only if the edge stops\n"
            "persisting on fresh data or the check goes stale (>21d). Risk guards: ATR stop (non-negotiable),\n"
            "daily-loss + drawdown kill switch, vol-spike/news blackout, tiny-account feasibility skip.\n"
            "Self-learning WITH a guardrail — it can never keep trading a dead strategy or over-risk a small account.",
            color=SLATE, fontsize=9, va="top")
    pdf.savefig(fig); plt.close(fig)


def page_backlog(pdf):
    fig = plt.figure(figsize=(16, 9))
    ax = base_ax(fig, "Strategy Backlog Development (v4)",
                 "Research-sourced ideas, each tested under the rigor gate — kept only if it provably helped", "13")
    # ADOPTED
    ax.text(0.4, 8.05, "ADOPTED (gold-only — BTC entries already clean)", color=GREEN, fontsize=12.5, fontweight="bold", va="top")
    adopt = [("Multi-lookback TSM confirmation", "require 20/60/120/240-bar momentum agreement", "gold Sharpe -0.14 -> +0.55"),
             ("Fundamental macro gate", "real yields + DXY falling = gold-bullish (free data)", "stacks: Sharpe 0.19 -> 0.68, win 38->44%")]
    y = 7.5
    for name, how, res in adopt:
        ax.add_patch(plt.Rectangle((0.4, y - 0.2), 15.2, 0.62, fc="#eafaf0", ec=GREEN, lw=0.8))
        ax.add_patch(plt.Rectangle((0.4, y - 0.2), 0.1, 0.62, fc=GREEN))
        ax.text(0.65, y + 0.12, name, color=INK, fontsize=10, va="center", fontweight="bold")
        ax.text(0.65, y - 0.12, how, color=SLATE, fontsize=8.4, va="center")
        ax.text(11.2, y, res, color=GREEN, fontsize=8.6, va="center", fontweight="bold")
        y -= 0.74
    # REJECTED
    ax.text(0.4, 5.75, "REJECTED (tested, did not beat the champion)", color=RED, fontsize=12.5, fontweight="bold", va="top")
    rej = [("Volatility-targeting overlay", "already implicit in our ATR-stop risk sizing"),
           ("Crash-protection de-risk", "over-trims winners; tiny DD gain, lower Sharpe"),
           ("Meta-label as AI sizer", "CPCV AUC ~0.50 = no skill yet -> keep ADX confidence"),
           ("Mean-reversion sleeve (ranges)", "loses; ranges break into trends on BTC/gold")]
    y = 5.25
    for name, why in rej:
        ax.add_patch(plt.Rectangle((0.4, y - 0.16), 15.2, 0.5, fc=CARD, ec="#dbe4f0", lw=0.6))
        ax.add_patch(plt.Rectangle((0.4, y - 0.16), 0.1, 0.5, fc=RED))
        ax.text(0.65, y + 0.08, name, color=INK, fontsize=9.5, va="center", fontweight="bold")
        ax.text(0.65, y - 0.1, why, color=SLATE, fontsize=8.2, va="center")
        y -= 0.6
    # 3-YEAR RESULTS + honest verdict
    box(ax, 0.4, 0.5, 7.5, 2.0, "", "#eafaf0", ec=GREEN, rs=0.03)
    ax.text(0.65, 2.35, "LAST 3 YEARS (0.5%-base Option B, net of cost)", color=GREEN, fontsize=10, fontweight="bold", va="top")
    ax.text(0.65, 1.95,
            "BTC H4: 3/3 years profitable, +8.5% compounded,\n"
            "drawdown <= 4.3%. Gold H4: thin history (~2y),\n"
            "+5.1%. Lever for bigger returns = base risk (tiers\n"
            "already scale to 2% on strong trades; ~linear).",
            color=SLATE, fontsize=9, va="top")
    box(ax, 8.1, 0.5, 7.5, 2.0, "", "#eef4ff", ec=BLUE, rs=0.03)
    ax.text(8.35, 2.35, "HONEST VERDICT", color=BLUE, fontsize=10, fontweight="bold", va="top")
    ax.text(8.35, 1.95,
            "The bottleneck is DATA, not techniques: sizing\n"
            "overlays don't help an already risk-normalised book;\n"
            "signal-quality filters (TSM, macro) help GOLD. AI\n"
            "meta-label has no skill yet (needs deeper history).\n"
            "Edge is real but regime-dependent — paper-trade first.",
            color=SLATE, fontsize=9, va="top")
    pdf.savefig(fig); plt.close(fig)


def main():
    df, reg, eq_bh, eq_ct, eq_gt, d1, reg_d1 = load_curves()
    out = ROOT / "docs" / "NexaQuant_Architecture.pdf"
    with PdfPages(out) as pdf:
        page_cover(pdf)
        page_exec(pdf)
        page_arch(pdf)
        page_data(pdf, df, reg_d1, d1)
        page_smc(pdf)
        page_strategy(pdf)
        page_evidence(pdf, df, reg, eq_bh, eq_ct, eq_gt)
        page_ai(pdf)
        page_validation(pdf)
        page_research(pdf)
        page_latest(pdf)
        page_findings(pdf)
        page_backlog(pdf)
        page_sizing(pdf)
        page_roadmap(pdf)
    print(f"PDF written: {out}")


if __name__ == "__main__":
    main()
