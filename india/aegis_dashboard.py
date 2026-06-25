# india/aegis_dashboard.py
"""
AEGIS DASHBOARD — the interactive product (Excel becomes the export, this is the UI).

Reads the SAME validated data model: the internal registry (data/aegis_registry.csv) for all
history, and the latest workbook's "Today's Recommendations" sheet for today's picks. No new logic,
no new claims — it just presents the validated workbook interactively (click a stock -> its trades).

Run:  streamlit run india/aegis_dashboard.py
"""
import sys, glob, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REG = ROOT / "data" / "aegis_registry.csv"
REPORTS = ROOT / "reports"


# ---------- data model (plain functions; testable without a streamlit server) ----------
def load_registry():
    if not REG.exists():
        return pd.DataFrame()
    r = pd.read_csv(REG)
    return r[(r.scored == 1) & (r.source == "historical")].copy()


def latest_workbook():
    fs = sorted(glob.glob(str(REPORTS / "AEGIS_*.xlsx")))
    return fs[-1] if fs else None


def load_today():
    f = latest_workbook()
    if not f:
        return pd.DataFrame(), None
    try:
        return pd.read_excel(f, sheet_name="Today's Recommendations"), f
    except Exception:
        return pd.DataFrame(), f


def cycles(reg):
    """Per-cycle portfolio return vs Nifty proxy from the registry (weighted)."""
    if reg.empty:
        return pd.DataFrame()
    rows = []
    for rid, g in reg.groupby("rec_id"):
        port = float((g["weight"] * g["actual_ret"]).sum() / g["weight"].sum())
        rows.append({"Cycle": pd.Timestamp(g["asof"].iloc[0]).strftime("%Y-%m"),
                     "Stocks": len(g), "Portfolio Ret %": round(port, 1),
                     "Winners": int((g.actual_ret > 0).sum()), "Losers": int((g.actual_ret <= 0).sum())})
    return pd.DataFrame(rows)


def money_curve(cyc, capital=500000):
    bal = capital; pts = [capital]
    for r in cyc.to_dict("records"):
        bal *= (1 + r["Portfolio Ret %"] / 100); pts.append(bal)
    return pd.Series(pts)


def statistics(cyc):
    if cyc.empty:
        return {}
    pr = cyc["Portfolio Ret %"]
    return {"Cycles": len(cyc), "Win rate %": round(100 * (pr > 0).mean()),
            "Avg return %": round(pr.mean(), 1), "Median return %": round(pr.median(), 1),
            "Best cycle %": round(pr.max(), 1), "Worst cycle %": round(pr.min(), 1)}


# ---------- UI ----------
def render():
    import streamlit as st
    st.set_page_config(page_title="AEGIS", page_icon="🛡️", layout="wide")
    reg = load_registry(); today, wbfile = load_today(); cyc = cycles(reg)
    try:
        from india.confidence_engine import current_regime
        exp, regime, _ = current_regime()
    except Exception:
        exp, regime = 0.6, "n/a"

    st.title("🛡️ AEGIS — Risk-Managed Equity")
    st.warning("**Portfolio process: VALIDATED.  Individual stock selection: EXPERIMENTAL "
               "(historically ~random).** Stocks below are risk-managed *constituents*, not proven "
               "winners. Historical figures are evidence from past cycles, NOT forecasts.")

    page = st.sidebar.radio("View", ["Today", "Recommendations", "Historical Performance",
                                     "Backtested Trades", "Statistics", "About"])
    stats = statistics(cyc)

    if page == "Today":
        c = st.columns(4)
        c[0].metric("Market Regime", regime)
        c[1].metric("Suggested Deploy", f"{exp:.0%}")
        c[2].metric("Cash Buffer", f"{1-exp:.0%}")
        c[3].metric("Holdings", len(today) if not today.empty else 0)
        st.subheader("Historical (similar past cycles — evidence, not a forecast)")
        h = st.columns(3)
        h[0].metric("Win rate", f"{stats.get('Win rate %','n/a')}%")
        h[1].metric("Median return", f"{stats.get('Median return %','n/a')}%")
        h[2].metric("Worst cycle", f"{stats.get('Worst cycle %','n/a')}%")
        st.subheader("Today's portfolio")
        if not today.empty:
            cols = [c for c in ["Allocation Order", "Stock", "Sector", "CMP", "Allocated Rs",
                    "Weight %", "Why Selected"] if c in today.columns]
            st.dataframe(today[cols], use_container_width=True, hide_index=True)
        st.caption(f"Source: {Path(wbfile).name if wbfile else 'no workbook'} · registry {len(reg)} scored picks")

    elif page == "Recommendations":
        if today.empty:
            st.info("No workbook found — run india/recommendation_generator.py first.")
        else:
            st.dataframe(today, use_container_width=True, hide_index=True)
            pick = st.selectbox("Drill into a stock", today["Stock"].tolist())
            st.write("**Selected stock — today's row**")
            st.dataframe(today[today.Stock == pick].T, use_container_width=True)
            past = reg[reg.symbol == pick]
            st.write(f"**{pick} — every past recommendation ({len(past)})**")
            if not past.empty:
                st.dataframe(past[["asof", "buy_price", "exit_price", "actual_ret", "rank",
                                   "universe_n", "holding_days"]], use_container_width=True, hide_index=True)
            else:
                st.caption("No prior recommendations for this stock.")

    elif page == "Historical Performance":
        st.subheader("Money diary — Rs 5,00,000 following every cycle")
        if not cyc.empty:
            st.line_chart(money_curve(cyc).rename("Portfolio (Rs)"))
            st.dataframe(cyc, use_container_width=True, hide_index=True)

    elif page == "Backtested Trades":
        if reg.empty:
            st.info("No registry yet.")
        else:
            secs = sorted(set(reg["symbol"].map(lambda s: s)))
            q = st.text_input("Filter by stock symbol (blank = all)").upper().strip()
            d = reg if not q else reg[reg.symbol.str.contains(q)]
            st.caption(f"{len(d)} of {len(reg)} historical picks")
            st.dataframe(d[["asof", "symbol", "buy_price", "exit_price", "actual_ret", "rank",
                            "universe_n", "holding_days", "regime"]].sort_values("asof"),
                         use_container_width=True, hide_index=True)

    elif page == "Statistics":
        cc = st.columns(3)
        for i, (k, v) in enumerate(stats.items()):
            cc[i % 3].metric(k, v)
        if not reg.empty:
            st.subheader("Top contributors (cumulative)")
            reg["contrib"] = reg["weight"] * reg["actual_ret"]
            attr = reg.groupby("symbol")["contrib"].sum().sort_values(ascending=False).round(1)
            st.bar_chart(attr.head(10))

    else:  # About
        st.markdown("""
**AEGIS** is a risk-managed portfolio engine: lowest-volatility selection · HRP weighting ·
sector cap · market-regime exposure timing · quarterly rebalance.

**Validated:** the portfolio process (beats Nifty risk-adjusted, ~half the drawdown, out-of-sample).
**NOT validated:** individual stock-picking alpha (selection ~ random). Picks are *constituents*.
**Not evaluated (no data):** fundamentals, news, earnings, institutional flows.
**Honest caveat:** absolute returns are survivorship-inflated — trust the relative edge vs Nifty.
Forward paper (live cycles) is the real ongoing test. This dashboard presents the validated workbook
interactively; it adds no new claims.
""")


if __name__ == "__main__":
    render()
