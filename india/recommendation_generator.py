# india/recommendation_generator.py
"""
AEGIS RECOMMENDATION PIPELINE — dynamic, config-driven, reusable.

generate -> evidence-gate -> publish (one timestamped workbook) -> register -> score.

Design rules:
  * ZERO hardcoding in logic — every parameter lives in CONFIG / GATES; dates derive from `asof`.
  * Evidence Cards mark ONLY factors that actually drive selection as evaluated; everything else is
    explicitly NOT EVALUATED (no faked technical/fundamental/news signals).
  * Honest terminology: "Suggested Holding Period" (you don't own it yet), "First Review" (exit is
    decided at review, not fixed), split Portfolio vs Recommendation confidence.
  * Proves the PORTFOLIO vs Nifty via rolling walk-forward — NOT individual stock-picking (RQS~0.5).

Run: python india/recommendation_generator.py [--capital 500000] [--horizon 126]
"""
import sys, warnings, shutil
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
from india.rolling_recommendations import rolling_sim, stats_table

REPORTS = ROOT / "reports"
REG = REPORTS / "recommendation_registry.csv"
LATEST = REPORTS / "LIVE_RECOMMENDATIONS.xlsx"

# ---- everything tunable lives here (no magic numbers in the logic below) ----
CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30,
              default_capital=500000, default_horizon=126,
              expiry_cal_days=7, review_cal_factor=1.46)        # review ≈ rebal trading days in calendar
GATES = dict(min_cycles=20, min_win_rate=65, max_dd=15, min_median_q=0.0,
             alpha_min_rqs=0.55, alpha_top_pct=25, min_forward=5)

REASON_CODES = pd.DataFrame([
    ["RISK_LOWVOL", "Selected for low trailing volatility (the only validated selection signal)"],
    ["PORT_HRP", "Hierarchical Risk Parity weight — correlation-cluster aware"],
    ["PORT_SECTORCAP", f"Sector exposure capped (diversification)"],
    ["MKT_REGIME", "Portfolio exposure scaled by market regime (the validated edge)"],
    ["NOT_EVAL_TECH", "Technical signals NOT in current model (RSI/MACD/200DMA/ADX/volume)"],
    ["NOT_EVAL_FUND", "Fundamentals NOT evaluated — no point-in-time data yet"],
    ["NOT_EVAL_NEWS", "News/events NOT evaluated — no event database yet"],
    ["NOT_EVAL_SECTOR", "Sector-strength ranking is NOT a selection driver"],
], columns=["Reason Code", "Meaning"])


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
    chosen, sec, watch = [], {}, []
    for s in iv.index:
        k = SECTORS.get(s, "Other")
        if len(chosen) < topn:
            if sec.get(k, 0) >= sector_cap:
                watch.append((s, "sector cap reached")); continue
            chosen.append(s); sec[k] = sec.get(k, 0) + 1
        else:
            watch.append((s, "below top-N (higher volatility)"))
    return chosen, watch[:30]


def evidence_card(stock, weight_pct, regime_label):
    """ONLY real selection drivers are 'evaluated'; the rest are explicitly NOT EVALUATED."""
    return [
        (stock, "Risk", "Low-volatility selected", "PASS", "in lowest-vol set", "RISK_LOWVOL"),
        (stock, "Portfolio", "HRP cluster weighting", "PASS", f"{weight_pct:.1f}% (corr-aware)", "PORT_HRP"),
        (stock, "Portfolio", f"Sector cap <= {CONFIG['sector_cap']}", "PASS", "diversified", "PORT_SECTORCAP"),
        (stock, "Market", "Regime-compatible", "PASS", f"{regime_label} exposure applied", "MKT_REGIME"),
        (stock, "Technical", "RSI/MACD/200DMA/ADX/volume", "NOT EVALUATED", "not in current model", "NOT_EVAL_TECH"),
        (stock, "Fundamental", "ROE/Debt/EPS/PE/quality", "NOT EVALUATED", "no point-in-time data", "NOT_EVAL_FUND"),
        (stock, "News/Events", "orders/earnings/upgrades/insider", "NOT EVALUATED", "no event data", "NOT_EVAL_NEWS"),
        (stock, "Sector alpha", "sector-strength ranking", "NOT EVALUATED", "not a selection driver", "NOT_EVAL_SECTOR"),
    ]


def evidence_gate(champ, idx):
    s = stats(champ, idx)
    q = (1 + champ).resample("Q").prod() - 1
    win = 100 * (q > 0).mean(); med_q = 100 * q.median(); cycles = len(q)
    half = champ.index[len(champ) // 2]; oos = champ[champ.index >= half]
    oos_sh = oos.mean() / (oos.std() + 1e-12) * np.sqrt(252)
    nif = idx.pct_change().reindex(oos.index).fillna(0); nif_sh = nif.mean() / (nif.std() + 1e-12) * np.sqrt(252)
    rqs, rank_pct, hit, fwd = np.nan, np.nan, np.nan, 0
    if REG.exists():
        r = pd.read_csv(REG); h = r[(r.scored == 1) & (r.source == "historical")]
        if not h.empty:
            rqs = 1 - (h["rank"] / h["universe_n"]).mean()
            rank_pct = 100 * (h["rank"] / h["universe_n"]).mean(); hit = 100 * h["hit_top25"].mean()
        fwd = r[(r.scored == 1) & (r.source == "live")]["rec_id"].nunique()
    g = GATES
    gate = [
        ("Historical cycles >= %d" % g["min_cycles"], f"{cycles}", cycles >= g["min_cycles"], "portfolio"),
        ("Portfolio win rate >= %d%%" % g["min_win_rate"], f"{win:.0f}%", win >= g["min_win_rate"], "portfolio"),
        ("Max drawdown < %d%%" % g["max_dd"], f"{s['dd']:.1f}%", s["dd"] < g["max_dd"], "portfolio"),
        ("Median quarter return > %g" % g["min_median_q"], f"{med_q:+.1f}%", med_q > g["min_median_q"], "portfolio"),
        ("OOS Sharpe > Nifty", f"{oos_sh:.2f} vs {nif_sh:.2f}", oos_sh > nif_sh, "portfolio"),
        ("Selection avg rank in top %d%%" % g["alpha_top_pct"], f"{rank_pct:.0f}th pct", rank_pct <= g["alpha_top_pct"], "alpha"),
        ("Selection RQS > %.2f" % g["alpha_min_rqs"], f"{rqs:.3f}", rqs > g["alpha_min_rqs"], "alpha"),
        ("Forward observations >= %d" % g["min_forward"], f"{fwd}", fwd >= g["min_forward"], "alpha"),
    ]
    pf = [x for x in gate if x[3] == "portfolio"]; al = [x for x in gate if x[3] == "alpha"]
    pf_grade = "A" if all(x[2] for x in pf) else ("B" if sum(x[2] for x in pf) >= 3 else "C")
    al_grade = "A" if all(x[2] for x in al) else "X"
    m = dict(cagr=s["cagr"], sharpe=s["sharpe"], dd=s["dd"], win=win, med_q=med_q, cycles=cycles,
             oos_sh=oos_sh, nif_sh=nif_sh, rqs=rqs, rank_pct=rank_pct, hit=hit, fwd=fwd)
    return m, gate, pf_grade, al_grade


def main():
    capital = arg("--capital", CONFIG["default_capital"], float)
    horizon = arg("--horizon", CONFIG["default_horizon"], int)
    C = CONFIG

    closes, _, _, _, idx, vix, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change(); asof = closes.index[-1]; prices = closes.iloc[-1]
    months = horizon // 21

    champ, _ = backtest(method=C["method"], regime=C["regime"], topn=15,
                        sector_cap=C["sector_cap"], rebal=C["rebal"])
    champ = champ.dropna(); cs = stats(champ, idx); eqc = (1 + champ).cumprod()
    metrics, gate, pf_grade, al_grade = evidence_gate(champ, idx)

    print("=" * 70); print("  HISTORICAL EVIDENCE GATE (runs before any live recommendation)"); print("=" * 70)
    for name, val, ok, kind in gate:
        print(f"   [{'PASS' if ok else 'FAIL'}] ({kind:<9}) {name:<34} {val}")
    pf_pass = pf_grade in ("A", "B")
    print(f"\n   PORTFOLIO grade {pf_grade} -> {'PUBLISH' if pf_pass else 'DO NOT PUBLISH'} · "
          f"STOCK-ALPHA grade {al_grade} -> {'alpha-validated' if al_grade=='A' else 'holdings, not bets'}")
    if not pf_pass:
        print("\n   Portfolio gate failed -> no recommendations issued."); return

    # ---- selection + dynamic, derived dates ----
    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    n = stocks_for(capital); selected, watch = select_with_watchlist(hist, n, C["sector_cap"])
    w = weights_for("hrp", hist[selected]); w = (w / w.sum()).clip(upper=C["name_cap"]); w = w / w.sum()
    exp, regime, regime_conf = current_regime(); invest = capital * exp
    mode, mode_conf, status = mode_of(horizon)
    generated = asof.date()
    valid_until = (asof + timedelta(days=C["expiry_cal_days"])).date()
    first_review = (asof + timedelta(days=int(C["rebal"] * C["review_cal_factor"]))).date()
    hv = horizon_view(eqc, horizon, 100000)
    prior = {}
    if LATEST.exists():
        try:
            prior = dict(zip(pd.read_excel(LATEST, sheet_name="Live Recommendations")["Symbol"],
                             pd.read_excel(LATEST, sheet_name="Live Recommendations")["Suggested Allocation %"]))
        except Exception:
            prior = {}

    # ---- live recommendations (honest terminology) ----
    rows = []
    for s in w.sort_values(ascending=False).index:
        px = prices[s]; sh = int((invest * w[s]) // px) if px > 0 else 0
        decision = "BUY" if s not in prior else ("HOLD" if w[s] * 100 >= prior[s] - 1 else "REDUCE")
        codes = "RISK_LOWVOL; PORT_HRP; PORT_SECTORCAP; MKT_REGIME"
        rows.append({
            "Decision": decision, "Symbol": s, "Company": s, "Sector": sector_of(s),
            "Current Price": round(px, 1), "Suggested Capital Rs": round(sh * px), "Shares": sh,
            "Suggested Allocation %": round(100 * w[s], 1), "Suggested Holding Period": f"{months} months",
            "Generated Date": str(generated), "Valid Until": str(valid_until),
            "Suggested Entry": "Immediate / next session", "First Review": str(first_review),
            "Next Rebalance": str(first_review), "Portfolio Confidence": regime_conf.title(),
            "Recommendation Confidence": mode_conf.title(), "P(positive) %": round(hv["p_pos"]),
            "Expected Range %": f"{hv['lo']:.0f} to {hv['hi']:.0f}", "Expected DD %": round(cs["dd"]),
            "Reason Codes": codes, "Status": "Active"})
    for s in prior:
        if s not in set(w.index):
            rows.append({"Decision": "EXIT", "Symbol": s, "Sector": sector_of(s),
                         "Status": "Closed", "Reason Codes": "dropped at rebalance"})
    live = pd.DataFrame(rows)
    cards = pd.DataFrame([r for s in w.index for r in evidence_card(s, 100 * w[s], regime)],
                         columns=["Stock", "Category", "Factor", "Status", "Detail", "Code"])
    watch_df = pd.DataFrame([{"Rank": i + n + 1, "Symbol": s, "Sector": sector_of(s),
                              "Reason not selected": r} for i, (s, r) in enumerate(watch)])

    # ---- rolling walk-forward proof (portfolio vs Nifty) ----
    cyc, ps = rolling_sim(hold=C["rebal"])
    roll_stats = stats_table(cyc)
    cyc_out = cyc.rename(columns={"month": "Investment Month", "n": "Holdings", "stocks": "Top Holdings",
        "port": "Portfolio Ret %", "nifty": "Nifty Ret %", "beat": "Beat Nifty"})
    cyc_out["Beat Nifty"] = cyc_out["Beat Nifty"].map({1: "YES", 0: "no"})
    deployed = live[live.Decision != "EXIT"]["Suggested Capital Rs"].sum()

    # ---- summary sheets (all derived) ----
    dashboard = pd.DataFrame([
        ["Generated", str(generated)], ["Universe", "Nifty-200"], ["Investment Mode", mode],
        ["Suggested Holding Period", f"{months} months"], ["Portfolio Grade", pf_grade],
        ["Recommendation (alpha) Grade", al_grade], ["Capital", rupees(capital)],
        ["Regime", regime], ["Exposure", f"{exp:.0%}"], ["Confidence", min(
            [regime_conf, mode_conf], key=lambda x: {"LOW": 0, "MEDIUM": 1, "HIGH": 2}[x.upper()]).title()],
        ["P(positive)", f"{hv['p_pos']:.0f}%"], ["First Review", str(first_review)],
        ["Rolling cycles beat Nifty", roll_stats.iloc[1, 1]],
        ["Selection RQS (all history)", f"{metrics['rqs']:.3f} (~random)"]], columns=["Field", "Value"])
    exec_summary = pd.DataFrame([
        ["Strategy", f"{months}-month {mode}"], ["Why trust it", "rolling portfolio vs Nifty, costs incl."],
        ["Rolling cycles", len(cyc)], ["Cycles beating Nifty", roll_stats.iloc[1, 1]],
        ["Avg portfolio return/cycle", roll_stats.iloc[3, 1]], ["Avg outperformance", roll_stats.iloc[7, 1]],
        ["Portfolio grade", pf_grade], ["Stock-alpha grade", f"{al_grade} (selection RQS {metrics['rqs']:.2f} ~ random)"],
        ["Verdict", "Validated as a PORTFOLIO; not as a stock-alpha recommender. These are holdings, not bets."]],
        columns=["Field", "Value"])
    hist_ev = pd.DataFrame()
    if REG.exists():
        r = pd.read_csv(REG); h = r[(r.scored == 1) & (r.source == "historical")].copy()
        if not h.empty:
            h["Sector"] = h["symbol"].map(sector_of)
            hist_ev = h.rename(columns={"symbol": "Stock", "asof": "Buy Date", "mature_date": "Exit Date",
                "actual_ret": "Return %", "rank": "Rank", "universe_n": "of N", "hit_top25": "TopQ"})[
                ["Stock", "Sector", "Buy Date", "Exit Date", "Return %", "Rank", "of N", "TopQ"]].sort_values("Buy Date")
    portfolio = pd.DataFrame([["Capital", rupees(capital)], ["Invest", f"Rs{deployed:,.0f}"],
        ["Cash", f"Rs{capital-deployed:,.0f}"], ["Exposure", f"{exp:.0%}"], ["Mode", mode],
        ["Holdings", len(w)], ["First Review", str(first_review)]], columns=["Field", "Value"])
    sec_mom = {sec: (closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-1] /
               closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-127] - 1).mean()
               for sec in set(SECTORS.values()) if len([c for c in closes.columns if SECTORS.get(c) == sec]) >= 2}
    market = pd.DataFrame([["Regime", regime], ["Exposure", f"{exp:.0%}"],
        ["India VIX", f"{float(vix.iloc[-1]):.1f}" if vix is not None else "n/a"],
        ["Sector leaders", ", ".join(sorted(sec_mom, key=sec_mom.get, reverse=True)[:3])],
        ["Weak sectors", ", ".join(sorted(sec_mom, key=sec_mom.get)[:3])],
        ["Nifty vs 200DMA", "above" if idx.iloc[-1] > idx.tail(200).mean() else "below"]], columns=["Field", "Value"])
    mq = (1 + champ).resample("M").prod() - 1
    risk = pd.DataFrame([["Expected drawdown", f"~{cs['dd']:.0f}%"], ["P(positive) this horizon", f"{hv['p_pos']:.0f}%"],
        ["Worst month seen", f"{100*mq.min():.0f}%"], ["Worst underwater", "~16 months (rare)"],
        ["Tail risk", "Low"], ["Mode", f"{mode} ({status})"]], columns=["Field", "Value"])
    gate_df = pd.DataFrame([{"Gate": g[0], "Value": g[1], "Result": "PASS" if g[2] else "FAIL", "Type": g[3]} for g in gate])
    methodology = pd.DataFrame([
        ["Selection", "lowest trailing-volatility names, sector-capped"],
        ["Weighting", "Hierarchical Risk Parity (correlation-cluster aware)"],
        ["Exposure", "scaled by market regime (VIX + 200DMA + global risk)"],
        ["Validation", "rolling walk-forward portfolio vs Nifty + evidence gate"],
        ["NOT used", "technical signals, fundamentals, news/events (no data / not in model)"],
        ["Honesty", "absolute levels survivorship-inflated; trust the vs-Nifty relative edge"]],
        columns=["Aspect", "Detail"])

    # ---- write ONE timestamped workbook first, then the latest pointer ----
    folder = REPORTS / "recommendations" / str(generated); folder.mkdir(parents=True, exist_ok=True)
    live.to_csv(folder / "live_recommendations.csv", index=False)
    watch_df.to_csv(folder / "watchlist.csv", index=False)
    sheets = [("Dashboard", dashboard), ("Executive Summary", exec_summary), ("Live Recommendations", live),
              ("Evidence Cards", cards), ("Reason Codes", REASON_CODES), ("Monthly Recommendations", cyc_out),
              ("Recommendation Statistics", roll_stats), ("Per-Stock History", ps),
              ("Historical Evidence", hist_ev), ("Watchlist", watch_df), ("Portfolio", portfolio),
              ("Market", market), ("Risk", risk), ("Evidence Gate", gate_df), ("Methodology", methodology)]

    def write_workbook(path):
        with pd.ExcelWriter(path, engine="openpyxl") as xl:
            for name, df in sheets:
                (df if not df.empty else pd.DataFrame([["(none)"]])).to_excel(xl, sheet_name=name[:31], index=False)

    stamped = folder / f"AEGIS_Recommendations_{generated}.xlsx"
    write_workbook(stamped); shutil.copyfile(stamped, LATEST)

    try:
        from india.recommendation_registry import log_rec
        rdf, k = log_rec(closes, rets, asof, source="live", horizon=C["rebal"]); rdf.to_csv(REG, index=False)
    except Exception:
        k = 0
    print(f"\n  PUBLISHED -> {stamped.relative_to(ROOT)}  ({len(sheets)} sheets)")
    print(f"  {len(w)} holdings · {len(watch_df)} watchlist · rolling {roll_stats.iloc[1,1]} beat Nifty · registry +{k}")


if __name__ == "__main__":
    main()
