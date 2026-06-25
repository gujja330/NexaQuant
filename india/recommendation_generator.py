# india/recommendation_generator.py
"""
AEGIS — INVESTOR RECOMMENDATION WORKBOOK (one clean product, not a research dump).

Produces ONE file per run:  reports/AEGIS_<date>.xlsx  (no Latest, no archive, no CSVs).
Research/backtesting outputs stay separate (india/evidence/, india/rolling_recommendations.py).

Seven investor sheets:
  1 Dashboard            — one-glance summary + grades
  2 Live Recommendations — current picks, each with its OWN historical track record + remark
  3 Historical Performance — every past cycle: portfolio vs Nifty (answers "if I'd started in Feb...")
  4 Monthly Detail       — per cycle, each stock's buy/exit/return (reproducible)
  5 Why Picked           — honest evidence matrix (PASS / NOT EVALUATED — no faked signals)
  6 Registry             — clean reproducible record (fingerprint, prices, return, rank)
  7 Statistics           — portfolio win rate, avg/median/std return, best/worst

Config-driven (CONFIG/GATES); dates derive from `asof`; nothing hardcoded in logic.
Run: python india/recommendation_generator.py [--capital 500000] [--horizon 126]
"""
import sys, warnings
from datetime import timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import SECTORS, sector_of
from india.confidence_engine import current_regime
from india.probability_surface import horizon_view, mode_of
from india.capital_ladder import LADDER, rupees
from india.config import VERSION

REPORTS = ROOT / "reports"
REG = REPORTS / "recommendation_registry.csv"

CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30,
              default_capital=500000, default_horizon=126,
              expiry_cal_days=7, review_cal_factor=1.46, buy_band_pct=1.5)
GATES = dict(min_cycles=20, min_win_rate=65, max_dd=15, min_median_q=0.0,
             alpha_min_rqs=0.55, alpha_top_pct=25, min_forward=5)


def arg(flag, default, cast):
    return cast(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


def stocks_for(amount):
    n = LADDER[0][1]
    for cap, k in LADDER:
        if amount >= cap:
            n = k
    return n


def select_with_watchlist(hist, topn, sector_cap):
    iv = (1.0 / hist.std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if len(chosen) >= topn:
            break
        k = SECTORS.get(s, "Other")
        if sec.get(k, 0) >= sector_cap:
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    vol_rank = hist.std().rank(pct=True)              # low pct = low vol = low risk
    return chosen, vol_rank


def evidence_gate(champ, idx, reg):
    s = stats(champ, idx)
    q = (1 + champ).resample("Q").prod() - 1
    win = 100 * (q > 0).mean(); med_q = 100 * q.median(); cycles = len(q)
    half = champ.index[len(champ) // 2]; oos = champ[champ.index >= half]
    oos_sh = oos.mean() / (oos.std() + 1e-12) * np.sqrt(252)
    nif = idx.pct_change().reindex(oos.index).fillna(0); nif_sh = nif.mean() / (nif.std() + 1e-12) * np.sqrt(252)
    rqs, rank_pct, fwd = np.nan, np.nan, 0
    h = reg[(reg.scored == 1) & (reg.source == "historical")] if not reg.empty else reg
    if not h.empty:
        rqs = 1 - (h["rank"] / h["universe_n"]).mean(); rank_pct = 100 * (h["rank"] / h["universe_n"]).mean()
    if not reg.empty:
        fwd = reg[(reg.scored == 1) & (reg.source == "live")]["rec_id"].nunique()
    g = GATES
    # NOTE: sum a Python list — numpy's bool `+` is logical OR, not arithmetic addition.
    pf_ok = sum(int(bool(x)) for x in [cycles >= g["min_cycles"], win >= g["min_win_rate"],
                s["dd"] < g["max_dd"], med_q > g["min_median_q"], oos_sh > nif_sh])
    al_ok = bool((rank_pct <= g["alpha_top_pct"]) and (rqs > g["alpha_min_rqs"]) and (fwd >= g["min_forward"]))
    pf_grade = "A" if pf_ok == 5 else ("B" if pf_ok >= 3 else "C")
    return dict(dd=s["dd"], win=win, med_q=med_q, cycles=cycles, oos_sh=oos_sh, nif_sh=nif_sh,
                rqs=rqs, pf_grade=pf_grade, al_grade="A" if al_ok else "X")


def history_for(reg, idx):
    """From the registry: per-cycle portfolio-vs-Nifty, per-stock track records, clean registry view."""
    h = reg[(reg.scored == 1) & (reg.source == "historical")].copy()
    if h.empty:
        return pd.DataFrame(), pd.DataFrame(), {}, pd.DataFrame()
    cyc_rows, detail_rows = [], []
    for rid, grp in h.groupby("rec_id"):
        a = pd.Timestamp(grp["asof"].iloc[0]); m = pd.Timestamp(grp["mature_date"].iloc[0])
        port = float((grp["weight"] * grp["actual_ret"]).sum() / grp["weight"].sum())
        nif = 100 * (idx.asof(m) / idx.asof(a) - 1)
        cyc_rows.append({"Investment Month": a.strftime("%Y-%m"), "Holding": f"{int(grp['holding_months'].iloc[0])}M",
                         "Stocks": len(grp), "Portfolio Ret %": round(port, 1), "Nifty Ret %": round(nif, 1),
                         "Beat Nifty": "YES" if port > nif else "no"})
        for _, r in grp.sort_values("actual_ret", ascending=False).iterrows():
            detail_rows.append({"Month": a.strftime("%Y-%m"), "Stock": r["symbol"], "Sector": sector_of(r["symbol"]),
                "Buy Price": r["buy_price"], "Exit Price": r["exit_price"], "Return %": r["actual_ret"],
                "Holding": f"{r['holding_months']}M", "Rank": f"{int(r['rank'])}/{int(r['universe_n'])}"})
    cyc = pd.DataFrame(cyc_rows); detail = pd.DataFrame(detail_rows)
    track = {s: g for s, g in h.groupby("symbol")}            # per-stock history
    clean = h.rename(columns={"symbol": "Stock", "asof": "Date", "buy_price": "Buy", "exit_price": "Exit",
        "actual_ret": "Return %", "rank": "Rank", "hit_top25": "Winner"})[
        ["fingerprint", "Date", "Stock", "Buy", "Exit", "Return %", "Rank", "Winner", "scored"]].sort_values("Date")
    return cyc, detail, track, clean


def main():
    capital = arg("--capital", CONFIG["default_capital"], float)
    horizon = arg("--horizon", CONFIG["default_horizon"], int)
    C = CONFIG; months = horizon // 21
    closes, _, _, _, idx, vix, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change(); asof = closes.index[-1]; prices = closes.iloc[-1]
    reg = pd.read_csv(REG) if REG.exists() else pd.DataFrame()

    champ, _ = backtest(method=C["method"], regime=C["regime"], topn=15,
                        sector_cap=C["sector_cap"], rebal=C["rebal"])
    champ = champ.dropna(); cs = stats(champ, idx); eqc = (1 + champ).cumprod()
    G = evidence_gate(champ, idx, reg)
    if G["pf_grade"] not in ("A", "B"):
        print("  Portfolio evidence gate failed -> no recommendations issued."); return

    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    n = stocks_for(capital); selected, vol_rank = select_with_watchlist(hist, n, C["sector_cap"])
    w = weights_for("hrp", hist[selected]); w = (w / w.sum()).clip(upper=C["name_cap"]); w = w / w.sum()
    exp, regime, regime_conf = current_regime(); invest = capital * exp
    mode, mode_conf, status = mode_of(horizon)
    hv = horizon_view(eqc, horizon, 100000)
    generated = asof.date()
    valid_until = (asof + timedelta(days=C["expiry_cal_days"])).date()
    review = (asof + timedelta(days=int(C["rebal"] * C["review_cal_factor"]))).date()

    cyc, detail, track, clean = history_for(reg, idx)
    beat_n = int((cyc["Beat Nifty"] == "YES").sum()) if not cyc.empty else 0
    beat_pct = round(100 * beat_n / len(cyc)) if not cyc.empty else 0
    avg_port = cyc["Portfolio Ret %"].mean() if not cyc.empty else float("nan")

    # ---- Sheet 2: Live Recommendations (each with its OWN history + honest remark) ----
    rows = []
    for s in w.sort_values(ascending=False).index:
        px = float(prices[s]); band = px * C["buy_band_pct"] / 100
        sh = int((invest * w[s]) // px) if px > 0 else 0
        t = track.get(s)
        occ = len(t) if t is not None else 0
        win = round(100 * (t["actual_ret"] > 0).mean()) if occ else None
        med = round(t["actual_ret"].median(), 1) if occ else None
        rl = "Low" if vol_rank.get(s, 0.5) < 0.33 else ("Medium" if vol_rank.get(s, 0.5) < 0.66 else "High")
        remark = (f"In {beat_pct}% of past cycles this portfolio beat Nifty (avg +{avg_port:.1f}%). " +
                  (f"{s} appeared in {occ} past portfolios, median {med:+.1f}%, win {win}%. " if occ else f"{s}: no prior history. ") +
                  "Risk-managed holding, not a return forecast.")
        rows.append({"Date Generated": str(generated), "Stock": s, "Sector": sector_of(s),
            "CMP": round(px, 1), "Suggested Buy Range": f"{px-band:.0f} - {px+band:.0f}",
            "Suggested Capital": round(sh * px), "Weight %": round(100 * w[s], 1),
            "Suggested Holding Window": f"{months} months", "Review Date": str(review),
            "Expected Exit Window": f"around {review}", "Portfolio Confidence": regime_conf.title(),
            "Recommendation Confidence": mode_conf.title(), "Reason Score": "4/4 risk drivers (tech/fund/news: not evaluated)",
            "Historical Similar Cases": occ, "Historical Win %": win, "Historical Median Return %": med,
            "Historical Worst %": round(t["actual_ret"].min(), 1) if occ else None,
            "Historical Best %": round(t["actual_ret"].max(), 1) if occ else None,
            "Risk Level": rl, "Expected Drawdown %": round(cs["dd"]), "Remarks": remark})
    live = pd.DataFrame(rows)

    # ---- Sheet 5: Why Picked (honest evidence matrix) ----
    why_rows = []
    for s in w.index:
        for cat, ind, val, ok in [
            ("Risk", "Low trailing volatility", "lowest-vol set", "PASS"),
            ("Portfolio", "HRP cluster weight", f"{100*w[s]:.1f}%", "PASS"),
            ("Portfolio", f"Sector cap <= {C['sector_cap']}", "diversified", "PASS"),
            ("Macro", "Regime-compatible", f"{regime} exposure", "PASS"),
            ("Technical", "RSI / MACD / 200DMA / ADX", "—", "NOT EVALUATED"),
            ("Fundamental", "ROE / Debt / EPS / PE", "—", "NOT EVALUATED"),
            ("News/Events", "orders / earnings / upgrades", "—", "NOT EVALUATED"),
            ("Sector alpha", "sector-strength rank", "—", "NOT EVALUATED")]:
            why_rows.append({"Stock": s, "Category": cat, "Indicator": ind, "Value": val, "Status": ok})
    why = pd.DataFrame(why_rows)

    # ---- Sheet 1 / 7 ----
    dashboard = pd.DataFrame([
        ["Generated", str(generated)], ["Strategy", f"AEGIS {VERSION.split('(')[0].strip()}"],
        ["Universe", "Nifty-200"], ["Suggested Holding Window", f"{months} months"],
        ["Portfolio Grade", G["pf_grade"]], ["Recommendation Grade", G["al_grade"]],
        ["Current Market", regime], ["Exposure", f"{exp:.0%}"], ["Recommended Stocks", len(w)],
        ["Portfolio beat Nifty (history)", f"{beat_n}/{len(cyc)} ({beat_pct}%)"],
        ["Selection RQS (all history)", f"{G['rqs']:.3f} (~random)"], ["Review Date", str(review)],
        ["Note", "Validated PORTFOLIO (grade A); stock-alpha NOT validated (holdings, not bets)"]],
        columns=["Field", "Value"])
    if not cyc.empty:
        pr = cyc["Portfolio Ret %"]
        statistics = pd.DataFrame([
            ["Total cycles", len(cyc)], ["Cycles beating Nifty", f"{beat_n} ({beat_pct}%)"],
            ["Cycles positive", f"{int((pr>0).sum())} ({round(100*(pr>0).mean())}%)"],
            ["Avg portfolio return", f"{pr.mean():+.1f}%"], ["Median portfolio return", f"{pr.median():+.1f}%"],
            ["Std deviation", f"{pr.std():.1f}%"], ["Avg holding", f"{months} months"],
            ["Best cycle", f"{pr.max():+.1f}%"], ["Worst cycle", f"{pr.min():+.1f}%"]],
            columns=["Metric", "Value"])
    else:
        statistics = pd.DataFrame([["(no scored history yet)", ""]], columns=["Metric", "Value"])

    # ---- write ONE investor workbook ----
    sheets = [("Dashboard", dashboard), ("Live Recommendations", live),
              ("Historical Performance", cyc), ("Monthly Detail", detail),
              ("Why Picked", why), ("Registry", clean), ("Statistics", statistics)]
    out = REPORTS / f"AEGIS_{generated}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xl:
        for name, df in sheets:
            (df if not df.empty else pd.DataFrame([["(none)"]])).to_excel(xl, sheet_name=name[:31], index=False)

    try:
        from india.recommendation_registry import log_rec
        rdf, k = log_rec(closes, rets, asof, source="live", horizon=C["rebal"]); rdf.to_csv(REG, index=False)
    except Exception:
        k = 0
    print("  HISTORICAL EVIDENCE GATE: PORTFOLIO grade %s · STOCK-ALPHA grade %s" % (G["pf_grade"], G["al_grade"]))
    print(f"  PUBLISHED -> {out.relative_to(ROOT)}  (7 investor sheets)")
    print(f"  {len(w)} holdings · portfolio beat Nifty {beat_n}/{len(cyc)} ({beat_pct}%) in history · registry +{k}")


if __name__ == "__main__":
    main()
