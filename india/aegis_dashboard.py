# india/aegis_dashboard.py
"""
AEGIS DASHBOARD — the free web front-end for the FROZEN v1.0 engine. Pure presentation: it reads the
same validated artifacts the workbook is built from (latest reports/AEGIS_*.xlsx, the registry, the
AI-Lab baseline, the data-layer ledger) and adds NO new claims or logic. The engine stays frozen;
this is the window onto it.

Tabs: Dashboard · Today's Recommendations · Historical Recommendations · Backtest · Portfolio ·
      Performance (full analytics suite) · AI Insights · Settings · Logs

Run:  streamlit run india/aegis_dashboard.py
The data/analytics functions below are plain + testable (no Streamlit needed):
      python -c "import india.aegis_dashboard as d; print(d.analytics(d.cycles(d.load_registry())))"
"""
import sys, glob, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REG = ROOT / "data" / "aegis_registry.csv"
LAYER_REG = ROOT / "data" / "aegis_layer_registry.csv"
BASELINE = ROOT / "data" / "aegis_baseline.json"
REPORTS = ROOT / "reports"
PPY = 252 / 63                                    # quarterly cycles -> ~4 periods / year


# ----------------------------- data model (plain, testable) -----------------------------
def latest_workbook():
    fs = sorted(glob.glob(str(REPORTS / "AEGIS_*.xlsx")))
    return fs[-1] if fs else None


def load_sheet(name):
    f = latest_workbook()
    if not f:
        return pd.DataFrame()
    try:
        return pd.read_excel(f, sheet_name=name)
    except Exception:
        return pd.DataFrame()


def load_registry():
    if not REG.exists():
        return pd.DataFrame()
    r = pd.read_csv(REG)
    return r[(r.get("scored", 0) == 1) & (r.get("source", "") == "historical")].copy()


def _nifty_panel():
    try:
        from india.feature_engine import load_panels
        return load_panels()[4]                       # idx series
    except Exception:
        return None


def cycles(reg, idx=None):
    """Per-cycle portfolio vs Nifty return. Portfolio = weighted registry returns; Nifty computed
    from the index panel between each cycle's asof and mature_date (registry has no benchmark column)."""
    if reg.empty:
        return pd.DataFrame()
    if idx is None:
        idx = _nifty_panel()
    rows = []
    for rid, g in reg.groupby("rec_id"):
        wsum = g["weight"].sum() or 1.0
        port = float((g["weight"] * g["actual_ret"]).sum() / wsum)
        nif = np.nan
        if idx is not None and "mature_date" in g:
            try:
                a = idx.asof(pd.Timestamp(g["asof"].iloc[0]))
                m = idx.asof(pd.Timestamp(g["mature_date"].iloc[0]))
                if a and m and a > 0:
                    nif = 100 * (m / a - 1)
            except Exception:
                pass
        rows.append({"Cycle": pd.Timestamp(g["asof"].iloc[0]).strftime("%Y-%m"),
                     "Stocks": len(g), "Port %": round(port, 2),
                     "Nifty %": round(nif, 2) if not np.isnan(nif) else np.nan,
                     "Winners": int((g.actual_ret > 0).sum()), "Losers": int((g.actual_ret <= 0).sum())})
    return pd.DataFrame(rows)


def money_curve(cyc, capital=500000):
    bal, pts = capital, [capital]
    for r in cyc.to_dict("records"):
        bal *= (1 + r["Port %"] / 100); pts.append(bal)
    return pd.Series(pts)


def _mdd(eq):
    return float(((eq.cummax() - eq) / eq.cummax()).max())


def analytics(cyc, capital=500000):
    """The full Phase-6 portfolio analytics suite, computed from cycle returns (quarterly)."""
    if cyc.empty or len(cyc) < 2:
        return {}
    pr = cyc["Port %"] / 100
    nf = (cyc["Nifty %"] / 100) if "Nifty %" in cyc else pd.Series(0.0, index=pr.index)
    eq = (1 + pr).cumprod(); yrs = len(pr) / PPY
    dd = _mdd(eq); total = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    downside = pr[pr < 0].std()
    gains, losses = pr[pr > 0].sum(), abs(pr[pr < 0].sum())
    beta = float(np.cov(pr, nf)[0, 1] / (nf.var() + 1e-12)) if nf.std() > 0 else np.nan
    active = pr - nf
    out = {
        "Total return": f"{100*total:.1f}%", "CAGR": f"{100*cagr:.1f}%",
        "Final value (Rs5L)": f"Rs{capital*eq.iloc[-1]:,.0f}",
        "Win rate": f"{100*(pr>0).mean():.0f}%",
        "Profit factor": f"{gains/losses:.2f}" if losses > 0 else "inf",
        "Volatility (ann)": f"{pr.std()*np.sqrt(PPY)*100:.1f}%",
        "Sharpe": f"{pr.mean()/(pr.std()+1e-12)*np.sqrt(PPY):.2f}",
        "Sortino": f"{pr.mean()/(downside+1e-12)*np.sqrt(PPY):.2f}",
        "Max drawdown": f"{100*dd:.1f}%",
        "Calmar": f"{cagr/(dd+1e-12):.2f}",
        "Recovery factor": f"{total/(dd+1e-12):.2f}",
        "Beta vs Nifty": f"{beta:.2f}" if not np.isnan(beta) else "n/a",
        "Alpha (ann)": f"{100*(pr.mean()-(beta if not np.isnan(beta) else 0)*nf.mean())*PPY:.1f}%",
        "Information ratio": f"{active.mean()/(active.std()+1e-12)*np.sqrt(PPY):.2f}",
        "Avg outperf vs Nifty": f"{100*active.mean():+.1f}%/cycle",
        "Avg holding": "~63 trading days (quarterly)",
        "Cycles": len(pr),
    }
    return out


def selection_funnel():
    """The funnel that answers 'why these N, not the other 188?' — REAL gates of the frozen engine:
    universe -> tradable (clean history) -> low-risk half -> sector-diversified -> final N. Honest:
    the engine selects by low volatility + sector cap, so those are the stages shown (no fake gates)."""
    try:
        from india.feature_engine import load_panels
        from india.data_nse import NIFTY200
        from india.arjuna_v2 import select_names, LOOKBACK
        from india.dynamic_policy import choose_topn
        from india.confidence_engine import current_regime
    except Exception:
        return pd.DataFrame()
    closes = load_panels()[0]
    uni = [c for c in closes.columns if c in set(NIFTY200)]
    rets = closes[uni].pct_change()
    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    clean = list(hist.columns)
    vol = hist.std(); lowrisk = list(vol[vol <= vol.median()].index)
    diversified = select_names(hist[lowrisk], None, sector_cap=2) if lowrisk else []
    try:
        exp = current_regime()[0]
    except Exception:
        exp = 0.6
    n, _ = choose_topn(hist, closes[uni], exp, cap=2)
    final = select_names(hist, n, sector_cap=2)
    stages = [("Nifty 200 universe", len(uni)),
              ("Tradable (clean history)", len(clean)),
              ("Low-risk half (below-median vol)", len(lowrisk)),
              ("Sector-diversified (<=2/sector)", len(diversified)),
              ("Final selected", len(final))]
    return pd.DataFrame(stages, columns=["Stage", "Count"])


def ai_status():
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    layers = pd.read_csv(LAYER_REG) if LAYER_REG.exists() else pd.DataFrame()
    return base, layers


def config_view():
    try:
        from india.recommendation_generator import CONFIG
        return CONFIG
    except Exception:
        return {}


# ----------------------------------- UI -----------------------------------
def render():
    import streamlit as st
    import altair as alt
    st.set_page_config(page_title="AEGIS", page_icon="🛡️", layout="wide")
    reg = load_registry(); cyc = cycles(reg)
    today = load_sheet("Today's Recommendations")
    wb = latest_workbook()
    try:
        from india.confidence_engine import current_regime
        exp, regime, rconf = current_regime()
    except Exception:
        exp, regime, rconf = 0.6, "n/a", "n/a"

    st.title("🛡️ AEGIS — Risk-Managed Equity (v1.0, frozen)")
    st.caption("Portfolio process VALIDATED · individual stock selection EXPERIMENTAL (~random). "
               "Historical figures are evidence from past cycles, NOT forecasts. Engine frozen at "
               "v1.0-price-baseline; this dashboard only presents it.")

    tabs = st.tabs(["📊 Dashboard", "🎯 Today", "🗂️ History", "🧪 Backtest", "💼 Portfolio",
                    "📈 Performance", "🤖 AI Insights", "⚙️ Settings", "📜 Logs"])
    stats = analytics(cyc)

    with tabs[0]:                                       # Dashboard — visual story
        c = st.columns(4)
        c[0].metric("Market Regime", regime)
        c[1].metric("Suggested Deploy", f"{exp:.0%}")
        c[2].metric("Cash Buffer", f"{1-exp:.0%}")
        c[3].metric("Holdings", len(today) if not today.empty else 0)
        if stats:
            d = st.columns(4)
            d[0].metric("CAGR", stats["CAGR"]); d[1].metric("Sharpe", stats["Sharpe"])
            d[2].metric("Max DD", stats["Max drawdown"]); d[3].metric("Win rate", stats["Win rate"])
        left, right = st.columns(2)
        with left:
            st.subheader("Why these stocks? — selection funnel")
            fdf = selection_funnel()
            if not fdf.empty:
                st.altair_chart(alt.Chart(fdf).mark_bar().encode(
                    x=alt.X("Count:Q"), y=alt.Y("Stage:N", sort=None),
                    color=alt.value("#2e7d32"), tooltip=["Stage", "Count"]),
                    use_container_width=True)
                st.caption(f"From {int(fdf.Count.iloc[0])} names down to {int(fdf.Count.iloc[-1])} "
                           "by clean-data, low-risk, and sector-diversification filters.")
        with right:
            if not today.empty and "Sector" in today and "Weight %" in today:
                st.subheader("Portfolio allocation")
                sec = today.groupby("Sector")["Weight %"].sum().reset_index()
                st.altair_chart(alt.Chart(sec).mark_arc(innerRadius=55).encode(
                    theta="Weight %:Q", color="Sector:N", tooltip=["Sector", "Weight %"]),
                    use_container_width=True)
        if not cyc.empty:
            st.subheader("Money diary — Rs5,00,000 compounded")
            st.line_chart(money_curve(cyc).rename("Portfolio (Rs)"))
            if stats:
                wins = int(round(float(stats["Win rate"].rstrip("%")) / 100 * stats["Cycles"]))
                wl = pd.DataFrame({"Outcome": ["Win", "Loss"], "Cycles": [wins, stats["Cycles"] - wins]})
                st.altair_chart(alt.Chart(wl).mark_arc(innerRadius=45).encode(
                    theta="Cycles:Q", color=alt.Color("Outcome:N",
                    scale=alt.Scale(domain=["Win", "Loss"], range=["#2e7d32", "#c62828"])),
                    tooltip=["Outcome", "Cycles"]).properties(height=200, title="Win / Loss cycles"),
                    use_container_width=True)
        st.caption(f"Source: {Path(wb).name if wb else 'no workbook'} · {len(reg)} scored historical picks")

    with tabs[1]:                                       # Today
        if today.empty:
            st.info("No workbook found — run india/recommendation_generator.py first.")
        else:
            st.dataframe(today, use_container_width=True, hide_index=True)
            if "Stock" in today:
                pick = st.selectbox("Drill into a recommendation", today["Stock"].tolist())
                st.dataframe(today[today.Stock == pick].T, use_container_width=True)

    with tabs[2]:                                       # Historical Recommendations + live DB
        try:
            from india.recommendation_db import load_db, lifecycle, daily_diff
            db = lifecycle(load_db())
        except Exception:
            db = pd.DataFrame()
        if not db.empty:
            st.subheader("Live recommendation database (accumulates — nothing deleted)")
            lc = db["status"].value_counts().to_dict()
            cc = st.columns(4)
            cc[0].metric("Total records", len(db)); cc[1].metric("LIVE", lc.get("LIVE", 0))
            cc[2].metric("Review-due", lc.get("REVIEW-DUE", 0)); cc[3].metric("Archived", lc.get("ARCHIVED", 0))
            dd = daily_diff(db)
            if dd and not dd.get("note"):
                st.write(f"**Since {dd['from']}:**  NEW {dd['new'] or '—'} · REMOVED {dd['removed'] or '—'} "
                         f"· INCREASED {dd['increased'] or '—'} · REDUCED {dd['reduced'] or '—'}")
            elif dd.get("note"):
                st.caption(dd["note"])
            st.dataframe(db.sort_values("recommended_date", ascending=False),
                         use_container_width=True, hide_index=True)
        st.subheader("Scored outcomes (registry)")
        if reg.empty:
            st.info("No registry yet.")
        else:
            q = st.text_input("Filter by symbol (blank = all)").upper().strip()
            dfr = reg if not q else reg[reg.symbol.str.contains(q)]
            cols = [c for c in ["asof", "symbol", "buy_price", "exit_price", "actual_ret", "rank",
                    "holding_days", "regime"] if c in dfr.columns]
            st.caption(f"{len(dfr)} of {len(reg)} historical picks")
            st.dataframe(dfr[cols].sort_values("asof"), use_container_width=True, hide_index=True)

    with tabs[3]:                                       # Backtest
        bs = load_sheet("Backtest Summary")
        if not bs.empty:
            st.dataframe(bs, use_container_width=True, hide_index=True)
        hm = load_sheet("Holding Period Options")
        if not hm.empty:
            st.subheader("Holding-period menu (backtested)")
            st.dataframe(hm, use_container_width=True, hide_index=True)

    with tabs[4]:                                       # Portfolio
        pf = load_sheet("Portfolio")
        if not pf.empty:
            st.dataframe(pf, use_container_width=True, hide_index=True)
        if not today.empty and "Sector" in today:
            st.subheader("Sector allocation (by weight)")
            wcol = "Weight %" if "Weight %" in today else None
            if wcol:
                st.bar_chart(today.groupby("Sector")[wcol].sum())

    with tabs[5]:                                       # Performance (full analytics suite)
        if not stats:
            st.info("Not enough history yet.")
        else:
            st.subheader("Portfolio analytics (from realised cycles)")
            items = list(stats.items())
            cols = st.columns(4)
            for i, (k, v) in enumerate(items):
                cols[i % 4].metric(k, v)
            if not cyc.empty:
                st.subheader("Portfolio vs Nifty (per cycle %)")
                st.bar_chart(cyc.set_index("Cycle")[["Port %", "Nifty %"]])

    with tabs[6]:                                       # AI Insights
        base, layers = ai_status()
        st.subheader("AI Lab — frozen baseline gate")
        if base:
            c = st.columns(3)
            c[0].metric("Baseline RQS", base.get("baseline_rqs", "n/a"))
            c[1].metric("LtR (price) RQS", base.get("ltr_price_rqs", "n/a"))
            c[2].metric("Promoted?", "YES" if base.get("promoted") else "NO")
            st.caption("A model is promoted to production only if it beats the frozen baseline RQS "
                       "out-of-sample. Price-feature LtR did not — awaiting non-price features.")
        else:
            st.info("Run india/ai_lab/rank_model.py to populate the baseline gate.")
        st.subheader("Data-layer ledger")
        if not layers.empty:
            st.dataframe(layers, use_container_width=True, hide_index=True)
        else:
            st.caption("No information layers evaluated yet. Drop a PIT file in data/layers/.")

    with tabs[7]:                                       # Settings
        st.subheader("Engine configuration (frozen v1.0)")
        cfg = config_view()
        if cfg:
            st.dataframe(pd.DataFrame(list(cfg.items()), columns=["Setting", "Value"]),
                         use_container_width=True, hide_index=True)
        st.caption("These are the frozen production parameters. Changes belong in the AI Lab, gated "
                   "against v1.0-price-baseline.")

    with tabs[8]:                                       # Logs
        st.subheader("Run / data status")
        st.write(f"- Latest workbook: **{Path(wb).name if wb else 'none'}**")
        st.write(f"- Registry rows (scored historical): **{len(reg)}**")
        st.write(f"- Cycles observed: **{len(cyc)}**")
        st.write(f"- Baseline frozen: **{BASELINE.exists()}**  ·  Layer ledger: **{LAYER_REG.exists()}**")
        if not cyc.empty:
            st.dataframe(cyc, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    render()
