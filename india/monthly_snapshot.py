# india/monthly_snapshot.py
"""
MONTHLY RESEARCH DESK — freeze a dated recommendation snapshot to reports/YYYY_MM.md.
AEGIS Core v2.0 (frozen): HRP + regime + Global Risk. Run on the first trading day of each month;
it records the basket, weights, cash, regime, per-stock news, expected return by hold, and reasons.
After 12 months you have 12 real, timestamped recommendations to judge the system on.

Run: python india/monthly_snapshot.py            # snapshot for the current month
"""
import sys, warnings
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from india.config import CONFIG, VERSION
from india.sectors import sector_of
from india.run_arjuna import current_portfolio, allocate, holding_projection
from india.arjuna_v2 import backtest, stats


def risk_metrics():
    """Live backtest -> pain/recovery profile (Ulcer Index, MAR, recovery distribution)."""
    net, idx = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    net = net.dropna(); s = stats(net, idx)
    eq = (1 + net).cumprod(); uw = eq / eq.cummax() - 1
    ulcer = float(np.sqrt((uw.values ** 2).mean()) * 100)
    is_high = uw >= -1e-9; reps = []; last = 0
    for i in range(1, len(uw)):
        if is_high.iloc[i]:
            if i - last > 1: reps.append(i - last)
            last = i
    reps = np.array(reps) if reps else np.array([0])
    return dict(sharpe=s["sharpe"], dd=s["dd"], ulcer=ulcer, mar=s["cagr"] / s["dd"],
                med=int(np.median(reps)), worst=int(reps.max()))

REPORTS = ROOT / "reports"; REPORTS.mkdir(exist_ok=True)
NEWS = ROOT / "data" / "raw" / "india" / "news_sentiment.parquet"


def latest_news():
    if not NEWS.exists():
        return {}
    df = pd.read_parquet(NEWS)
    return df.sort_values("asof").groupby("symbol").tail(1).set_index("symbol")["news_sent"].to_dict()


def main():
    asof, w, prices, deploy, regime_lbl, excluded = current_portfolio()
    cap = CONFIG.capital
    df, spent = allocate(w, prices, cap * deploy)
    proj = holding_projection()
    news = latest_news()
    ym = datetime.now().strftime("%Y_%m")
    path = REPORTS / f"{ym}.md"

    L = []
    L.append(f"# AEGIS — Monthly Recommendation · {datetime.now().strftime('%B %Y')}\n")
    L.append(f"**Strategy:** {VERSION} — HRP + regime + Global Risk  ")
    L.append(f"**As of data:** {pd.Timestamp(asof).date()}  |  **Universe:** {CONFIG.universe}  |  "
             f"**Capital:** Rs{cap:,.0f}  ")
    L.append(f"**Regime:** {regime_lbl}  ->  invest Rs{spent:,.0f} ({100*spent/cap:.0f}%), "
             f"hold Rs{cap-spent:,.0f} cash ({100-100*spent/cap:.0f}%)\n")
    if excluded:
        L.append(f"**News filter dropped (negative sentiment):** {', '.join(excluded)}\n")

    L.append("## Holdings\n")
    L.append("| # | Stock | Sector | Weight | Buy ₹ | Shares | Cost ₹ | News |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(df.to_dict("records"), 1):
        ns = news.get(r["symbol"])
        nstr = ("up" if ns and ns > 0.2 else "down" if ns and ns < -0.2 else "-")
        L.append(f"| {i} | {r['symbol']} | {sector_of(r['symbol'])} | {r['weight_%']}% | "
                 f"{r['price']:,.0f} | {r['shares']} | {r['cost_rs']:,.0f} | {nstr} |")

    L.append("\n## Expected return by holding period (backtest; forward realistically lower)\n")
    L.append("| Hold | Avg | Profitable | ₹1L → |")
    L.append("|---|---|---|---|")
    for k, (avg, lo, hi, pos) in proj.items():
        L.append(f"| {k} | {100*avg:+.1f}% | {100*pos:.0f}% | Rs{cap*(1+avg):,.0f} |")

    rm = risk_metrics()
    L.append("\n## Risk profile (backtest; the honest expectation)\n")
    L.append("| Metric | Value | Meaning |")
    L.append("|---|---|---|")
    L.append(f"| Sharpe | {rm['sharpe']:.2f} | risk-adjusted return (Nifty ~0.80) |")
    L.append(f"| Max drawdown | {rm['dd']:.1f}% | worst peak-to-trough |")
    L.append(f"| Ulcer Index | {rm['ulcer']:.2f} | pain = depth × duration; lower is better |")
    L.append(f"| MAR (CAGR/DD) | {rm['mar']:.2f} | return per unit of drawdown; >1.0 is good |")
    L.append(f"| Median recovery | {rm['med']} days | typical time back to a new high |")
    L.append(f"| Worst underwater | ~{rm['worst']//21} months | budget for one long grind per cycle |")
    L.append("\n*Duration risk > depth risk: drawdowns are shallow and usually heal in days; the real cost "
             "is one rare ~12–16 month underwater stretch. That stretch is the cost of the Sharpe, not a malfunction.*\n")

    L.append("\n## Reasons / notes")
    L.append("- **Risk-weighted (HRP):** low-volatility, well-diversified names get more weight; "
             "correlated clusters are down-weighted.")
    L.append(f"- **Regime:** {regime_lbl} (VIX + Nifty-200-DMA + Global Risk Engine).")
    L.append("- **News:** strongly-negative-sentiment names excluded as a blow-up filter.")
    L.append("- **Hold guidance:** designed for ~6–12 month holds; longer = more reliable (see table).")
    L.append(f"\n*Snapshot generated {datetime.now().isoformat(timespec='seconds')}. "
             f"Frozen Core — not tuned. Forward paper-trading record.*")

    path.write_text("\n".join(L), encoding="utf-8")
    print(f"  monthly snapshot saved -> reports/{ym}.md  ({len(df)} holdings, {100*spent/cap:.0f}% invested)")
    print(f"  regime: {regime_lbl}")


if __name__ == "__main__":
    main()
