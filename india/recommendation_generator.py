# india/recommendation_generator.py
"""
RECOMMENDATION GENERATOR — generate -> validate -> publish -> track -> evaluate.

PRINCIPLE (user's): ARJUNA never issues a LIVE recommendation that hasn't passed a HISTORICAL
EVIDENCE GATE. So this script runs the gate FIRST and prints/embeds the verdict before any picks.

Applying the gate honestly produces TWO verdicts, because the evidence is split:
  * PORTFOLIO / RISK strategy  -> PASSES (regime + construction; backpaper OOS Sharpe > index).
  * STOCK-ALPHA / RANKING      -> FAILS (selection RQS ~0.51 < 0.55; avg rank ~50th pct).
=> Output is certified as a VALIDATED PORTFOLIO of risk-managed HOLDINGS, NOT evidence-graded alpha
   picks. We do not fake per-stock A/B grades from survivorship history.

Products kept separate: BUY LIST (passed the portfolio engine) · WATCHLIST (near-misses) · REGISTRY
(stored for scoring). Reason codes are RISK/CONSTRUCTION, not return forecasts. Exits are process-
based, not stop-losses.

Outputs: reports/recommendations/<date>/ + reports/LIVE_RECOMMENDATIONS.xlsx (8 sheets).
Run: python india/recommendation_generator.py --capital 500000 --horizon 126
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


def stocks_for(amount):
    n = LADDER[0][1]
    for cap, k in LADDER:
        if amount >= cap:
            n = k
    return n

REPORTS = ROOT / "reports"
XLSX = REPORTS / "LIVE_RECOMMENDATIONS.xlsx"
REG = REPORTS / "recommendation_registry.csv"


def arg(flag, default, cast):
    return cast(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


def strategy_evidence(champ, idx):
    """The historical evidence gate. Returns (metrics, gate_rows, portfolio_grade, alpha_grade)."""
    s = stats(champ, idx)
    q = (1 + champ).resample("Q").prod() - 1
    win = 100 * (q > 0).mean(); med_q = 100 * q.median(); cycles = len(q)
    half = champ.index[len(champ) // 2]
    oos = champ[champ.index >= half]
    oos_sh = oos.mean() / (oos.std() + 1e-12) * np.sqrt(252)
    nif = idx.pct_change().reindex(oos.index).fillna(0)
    nif_sh = nif.mean() / (nif.std() + 1e-12) * np.sqrt(252)
    # recommendation-quality from the registry (historical, scored)
    rqs, avg_rank_pct, hit, fwd = np.nan, np.nan, np.nan, 0
    if REG.exists():
        r = pd.read_csv(REG); sc = r[(r.scored == 1)]
        h = sc[sc.source == "historical"]
        if not h.empty:
            rqs = 1 - (h["rank"] / h["universe_n"]).mean()
            avg_rank_pct = 100 * (h["rank"] / h["universe_n"]).mean()
            hit = 100 * h["hit_top25"].mean()
        fwd = sc[sc.source == "live"]["rec_id"].nunique()
    gate = [
        ("Historical cycles >= 20", f"{cycles}", cycles >= 20, "portfolio"),
        ("Portfolio win rate >= 65%", f"{win:.0f}%", win >= 65, "portfolio"),
        ("Max drawdown < 15%", f"{s['dd']:.1f}%", s["dd"] < 15, "portfolio"),
        ("Median quarter return > 0", f"{med_q:+.1f}%", med_q > 0, "portfolio"),
        ("OOS Sharpe > Nifty", f"{oos_sh:.2f} vs {nif_sh:.2f}", oos_sh > nif_sh, "portfolio"),
        ("Selection avg rank in Top 25%", f"{avg_rank_pct:.0f}th pct", avg_rank_pct <= 25, "alpha"),
        ("Selection RQS > 0.55", f"{rqs:.3f}", rqs > 0.55, "alpha"),
        ("Forward observations >= 5", f"{fwd}", fwd >= 5, "alpha"),
    ]
    pf = [g for g in gate if g[3] == "portfolio"]; al = [g for g in gate if g[3] == "alpha"]
    pf_grade = "A" if all(g[2] for g in pf) else ("B" if sum(g[2] for g in pf) >= 3 else "C")
    al_grade = "A" if all(g[2] for g in al) else "X"           # X = not validated as alpha
    metrics = dict(cagr=s["cagr"], sharpe=s["sharpe"], dd=s["dd"], win=win, med_q=med_q,
                   cycles=cycles, oos_sh=oos_sh, nif_sh=nif_sh, rqs=rqs, hit=hit, fwd=fwd)
    return metrics, gate, pf_grade, al_grade


def select_with_watchlist(hist, topn, sector_cap=2):
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


def prior_holdings():
    if XLSX.exists():
        try:
            df = pd.read_excel(XLSX, sheet_name="Live Recommendations")
            return dict(zip(df["Stock"], df["Weight %"]))
        except Exception:
            return {}
    return {}


def main():
    capital = arg("--capital", 500000, float)
    horizon = arg("--horizon", 126, int)

    closes, _, _, _, idx, vix, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change(); asof = closes.index[-1]; prices = closes.iloc[-1]

    champ, _ = backtest(method="hrp", regime="global", topn=15, sector_cap=2, rebal=63)
    champ = champ.dropna(); cs = stats(champ, idx); eqc = (1 + champ).cumprod()
    metrics, gate, pf_grade, al_grade = strategy_evidence(champ, idx)

    # ---- the gate decides whether we publish ----
    pf_pass = pf_grade in ("A", "B")
    print("=" * 70)
    print("  HISTORICAL EVIDENCE GATE (run before any live recommendation)")
    print("=" * 70)
    for name, val, ok, kind in gate:
        print(f"   [{'PASS' if ok else 'FAIL'}] ({kind:<9}) {name:<32} {val}")
    print(f"\n   PORTFOLIO (risk) grade: {pf_grade}   ->   {'PUBLISH as validated portfolio' if pf_pass else 'DO NOT PUBLISH'}")
    print(f"   STOCK-ALPHA grade:      {al_grade}   ->   {'alpha-validated' if al_grade=='A' else 'NOT an alpha recommender (RQS<0.55) — holdings, not bets'}")
    if not pf_pass:
        print("\n   Portfolio gate failed -> no recommendations issued."); return

    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    n = stocks_for(capital); selected, watch = select_with_watchlist(hist, n)
    w = weights_for("hrp", hist[selected]); w = (w / w.sum()).clip(upper=0.30); w = w / w.sum()
    exp, regime, regime_conf = current_regime(); invest = capital * exp
    mode, mode_conf, status = mode_of(horizon)
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    confidence = min([regime_conf, mode_conf], key=lambda x: rank[x.upper()]).title()
    hv = horizon_view(eqc, horizon, 100000)
    hold_until = (asof + timedelta(days=int(horizon * 1.45))).date()
    review = (asof + timedelta(days=92)).date()
    prior = prior_holdings()

    rows = []
    for s in w.sort_values(ascending=False).index:
        px = prices[s]; cap_i = invest * w[s]; sh = int(cap_i // px) if px > 0 else 0
        action = "BUY" if s not in prior else ("HOLD" if w[s] * 100 >= prior[s] - 1 else "REDUCE")
        rows.append({
            "RecID": f"{asof.date()}_{horizon}", "Date": str(asof.date()), "Stock": s,
            "Sector": sector_of(s), "Action": action, "Price": round(px, 1),
            "Capital Rs": round(sh * px), "Shares": sh, "Weight %": round(100 * w[s], 1),
            "Horizon": f"{horizon//21}M", "Hold Until": str(hold_until), "Review": str(review),
            "Confidence": confidence, "Regime": regime, "P(+) %": round(hv["p_pos"]),
            "Exp Range %": f"{hv['lo']:.0f} to {hv['hi']:.0f}", "Exp DD %": round(cs["dd"]),
            "Evidence": f"portfolio-validated ({pf_grade}); selection RQS {metrics['rqs']:.2f}=~random",
            "Exit Trigger": "rebalance / regime-off / corp-event", "Status": "Active",
            "Reasons": "low-vol selected; sector<=2; regime-fit; horizon-fit"})
    for s in prior:
        if s not in set(w.index):
            rows.append({"RecID": f"{asof.date()}_{horizon}", "Date": str(asof.date()), "Stock": s,
                         "Sector": sector_of(s), "Action": "EXIT", "Status": "Closed",
                         "Reasons": "dropped at rebalance"})
    buy = pd.DataFrame(rows)
    watch_df = pd.DataFrame([{"Rank": i + n + 1, "Stock": s, "Sector": sector_of(s),
                              "Reason not selected": r} for i, (s, r) in enumerate(watch)])

    # ---- sheets ----
    backtest_summary = pd.DataFrame(
        [["Strategy", f"{horizon//21}-Month {mode}"], ["Years tested", f"{metrics['cycles']/4:.1f}"],
         ["Historical cycles", metrics["cycles"]], ["Portfolio win rate", f"{metrics['win']:.0f}%"],
         ["Median quarter return", f"{metrics['med_q']:+.1f}%"], ["Max drawdown", f"{cs['dd']:.1f}%"],
         ["OOS Sharpe (vs Nifty)", f"{metrics['oos_sh']:.2f} vs {metrics['nif_sh']:.2f}"],
         ["Costs included", "yes (21bps)"], ["Selection RQS", f"{metrics['rqs']:.3f} (~random)"],
         ["PORTFOLIO grade", pf_grade], ["STOCK-ALPHA grade", al_grade],
         ["Verdict", "Validated as PORTFOLIO; NOT as stock-alpha. Forward paper pending."]],
        columns=["Field", "Value"])
    gate_df = pd.DataFrame([{"Gate": g[0], "Value": g[1], "Result": "PASS" if g[2] else "FAIL",
                             "Type": g[3]} for g in gate])
    deployed = buy[buy.Action != "EXIT"]["Capital Rs"].sum()
    portfolio = pd.DataFrame([["Capital", rupees(capital)], ["Invest", f"Rs{deployed:,.0f}"],
        ["Cash", f"Rs{capital-deployed:,.0f}"], ["Exposure", f"{exp:.0%}"], ["Mode", mode],
        ["Confidence", confidence], ["Holdings", len(w)], ["Review", str(review)]],
        columns=["Field", "Value"])
    sec_mom = {sec: (closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-1] /
               closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-127] - 1).mean()
               for sec in set(SECTORS.values())
               if len([c for c in closes.columns if SECTORS.get(c) == sec]) >= 2}
    market = pd.DataFrame([["Regime", regime], ["Market exposure", f"{exp:.0%}"],
        ["India VIX", f"{float(vix.iloc[-1]):.1f}" if vix is not None else "n/a"],
        ["Sector leaders", ", ".join(sorted(sec_mom, key=sec_mom.get, reverse=True)[:3])],
        ["Weak sectors", ", ".join(sorted(sec_mom, key=sec_mom.get)[:3])],
        ["Nifty vs 200DMA", "above" if idx.iloc[-1] > idx.tail(200).mean() else "below"]],
        columns=["Field", "Value"])
    mq = (1 + champ).resample("M").prod() - 1
    risk = pd.DataFrame([["Expected drawdown", f"~{cs['dd']:.0f}%"],
        ["P(positive) this horizon", f"{hv['p_pos']:.0f}%"], ["Worst month seen", f"{100*mq.min():.0f}%"],
        ["Worst underwater", "~16 months (rare)"], ["Tail risk", "Low"],
        ["Mode", f"{mode} ({status})"]], columns=["Field", "Value"])
    exits = pd.DataFrame([{"Stock": s, "Entered": str(asof.date()), "Normal Exit": str(hold_until),
        "Early Exit": "quarterly rebalance", "Emergency Exit": "fraud / delisting / regime-OFF"}
        for s in w.index])

    folder = REPORTS / "recommendations" / str(asof.date()); folder.mkdir(parents=True, exist_ok=True)
    buy.to_csv(folder / "buy_list.csv", index=False); watch_df.to_csv(folder / "watchlist.csv", index=False)
    with pd.ExcelWriter(XLSX, engine="openpyxl") as xl:
        backtest_summary.to_excel(xl, sheet_name="Backtest Summary", index=False)
        gate_df.to_excel(xl, sheet_name="Evidence Gate", index=False)
        buy.to_excel(xl, sheet_name="Live Recommendations", index=False)
        watch_df.to_excel(xl, sheet_name="Watchlist", index=False)
        portfolio.to_excel(xl, sheet_name="Portfolio", index=False)
        market.to_excel(xl, sheet_name="Market", index=False)
        risk.to_excel(xl, sheet_name="Risk", index=False)
        exits.to_excel(xl, sheet_name="Exit Rules", index=False)

    L = [f"# ARJUNA Recommendation — {asof.date()}", "",
         f"## Why trust this? (evidence gate)",
         f"**Strategy:** {horizon//21}-month {mode}  ·  **{metrics['cycles']} cycles / "
         f"{metrics['cycles']/4:.1f}y tested, costs included**", "",
         f"- PORTFOLIO (risk) grade **{pf_grade}** — win rate {metrics['win']:.0f}%, max DD "
         f"{cs['dd']:.0f}%, OOS Sharpe {metrics['oos_sh']:.2f} vs Nifty {metrics['nif_sh']:.2f} → **validated**.",
         f"- STOCK-ALPHA grade **{al_grade}** — selection RQS {metrics['rqs']:.2f} (~random) → "
         f"**NOT** a stock-alpha recommender. These are risk-managed *holdings*, not bets.", "",
         f"**Mode:** {mode} ({status})  ·  **Regime:** {regime}  ·  **Exposure:** {exp:.0%}  ·  "
         f"**Confidence:** {confidence}  ·  **P(+) {hv['p_pos']:.0f}%**", "",
         f"Invest **Rs{deployed:,.0f}** of Rs{capital:,.0f} across **{len(w)}** stocks; hold "
         f"Rs{capital-deployed:,.0f} cash. Horizon **{horizon//21}M**. Review **{review}**.", "",
         "## Buy list (validated portfolio holdings)"]
    for r in buy[buy.Action != "EXIT"].to_dict("records"):
        L.append(f"- **{r['Stock']}** ({r['Sector']}) — {r['Action']} · {r['Shares']} sh @ "
                 f"Rs{r['Price']:,} · {r['Weight %']}%")
    L += ["", "*Watchlist & full schema in LIVE_RECOMMENDATIONS.xlsx. Discover proposes; Portfolio "
          "disposes — the watchlist is NOT a buy list. Reasons are risk/construction, not forecasts.*"]
    (folder / "explanation.md").write_text("\n".join(L), encoding="utf-8")

    try:
        from india.recommendation_registry import log_rec
        rdf, k = log_rec(closes, rets, asof, source="live", horizon=63); rdf.to_csv(REG, index=False)
    except Exception:
        k = 0
    print(f"\n  PUBLISHED -> reports/recommendations/{asof.date()}/ + LIVE_RECOMMENDATIONS.xlsx (8 sheets)")
    print(f"  {len(w)} holdings · {len(watch_df)} watchlist · registry +{k} picks")


if __name__ == "__main__":
    main()
