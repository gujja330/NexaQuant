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
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import backtest, stats, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.technical_factors import _rsi
from india.data_nse import NIFTY200
from india.sectors import SECTORS, sector_of
from india.confidence_engine import current_regime
from india.probability_surface import horizon_view, mode_of
from india.capital_ladder import rupees
from india.config import VERSION
from india.horizon_matrix import horizon_matrix, recommend, LABELS
from india.dynamic_policy import choose_horizon, choose_topn

REPORTS = ROOT / "reports"
REG = ROOT / "data" / "aegis_registry.csv"          # INTERNAL evidence DB (not exposed in reports/)

CONFIG = dict(method="hrp", regime="global", sector_cap=2, rebal=63, name_cap=0.30,
              default_capital=500000, default_horizon=126,
              expiry_cal_days=7, review_cal_factor=1.46, buy_band_pct=1.5)
GATES = dict(min_cycles=20, min_win_rate=65, max_dd=15, min_median_q=0.0,
             alpha_min_rqs=0.55, alpha_top_pct=25, min_forward=5)


def arg(flag, default, cast):
    return cast(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


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


def rec_id(asof, months):
    return f"AEGIS-{pd.Timestamp(asof).strftime('%Y%m%d')}-{months}M"


def history_for(reg, idx, capital, closes):
    """Registry -> per-cycle portfolio (with money), full per-stock LIFECYCLE incl trade path / exit quality."""
    h = reg[(reg.scored == 1) & (reg.source == "historical")].copy()
    if h.empty:
        return pd.DataFrame(), pd.DataFrame(), {}, pd.DataFrame()
    cyc_rows, detail_rows = [], []
    for _, grp in h.groupby("rec_id"):
        a = pd.Timestamp(grp["asof"].iloc[0]); m = pd.Timestamp(grp["mature_date"].iloc[0])
        mo = int(grp["holding_months"].iloc[0]); hd = int(grp["holding_days"].iloc[0])
        rid = rec_id(a, mo); port = float((grp["weight"] * grp["actual_ret"]).sum() / grp["weight"].sum())
        nif = 100 * (idx.asof(m) / idx.asof(a) - 1)
        contrib = grp.set_index("symbol").eval("weight * actual_ret")     # per-stock contribution
        top_c, worst_c = contrib.idxmax(), contrib.idxmin()
        winners = int((grp["actual_ret"] > 0).sum()); losers = len(grp) - winners
        # portfolio drawdown DURING the holding window (what the investor had to endure)
        syms = [x for x in grp["symbol"] if x in closes.columns]
        wts = grp.set_index("symbol")["weight"].reindex(syms).fillna(0).values
        pth = closes[syms].loc[a:m].dropna()
        if len(pth) > 1 and wts.sum() > 0:
            pv = ((pth / pth.iloc[0]) * wts).sum(axis=1) / wts.sum()
            cyc_dd = 100 * float(((pv.cummax() - pv) / pv.cummax()).max())
        else:
            cyc_dd = 0.0
        inv_tot = exit_tot = 0.0
        for _, r in grp.sort_values("actual_ret", ascending=False).iterrows():
            sh = int((capital * r["weight"]) // r["buy_price"]) if r["buy_price"] > 0 else 0
            inv = sh * r["buy_price"]; ev = sh * r["exit_price"]; inv_tot += inv; exit_tot += ev
            cagr = ((1 + r["actual_ret"] / 100) ** (252 / max(hd, 1)) - 1) * 100
            # trade path / exit quality from the price path during the holding window
            path = closes[r["symbol"]].loc[a:m] if r["symbol"] in closes.columns else pd.Series(dtype=float)
            if len(path) > 1 and r["buy_price"] > 0:
                max_p = 100 * (path.max() / r["buy_price"] - 1); min_p = 100 * (path.min() / r["buy_price"] - 1)
                capture = round(100 * r["actual_ret"] / max_p) if max_p > 0 else None
            else:
                max_p = min_p = capture = None
            detail_rows.append({"Rec ID": rid, "Month": a.strftime("%Y-%m"), "Stock": r["symbol"],
                "Sector": sector_of(r["symbol"]), "Buy Price": r["buy_price"], "Exit Price": r["exit_price"],
                "Shares": sh, "Invested Rs": round(inv), "Exit Value Rs": round(ev), "Profit Rs": round(ev - inv),
                "Return %": r["actual_ret"], "Contribution %": round(r["weight"] * r["actual_ret"], 2),
                "Max Profit %": round(max_p, 1) if max_p is not None else None,
                "Max Loss %": round(min_p, 1) if min_p is not None else None,
                "Captured %": capture, "CAGR %": round(cagr, 1), "Holding Days": hd,
                "Rank in Universe": f"{int(r['rank'])}/{int(r['universe_n'])}",
                "Why Picked": f"Low-vol {sector_of(r['symbol'])} holding; risk-managed; regime-timed",
                "Exit Reason": "quarterly rebalance", "Status": "Completed"})
        cyc_rows.append({"Rec ID": rid, "Investment Month": a.strftime("%Y-%m"), "Holding": f"{mo}M",
            "Stocks": ", ".join(grp.sort_values("weight", ascending=False)["symbol"].head(5)) + " ...",
            "Invested Rs": round(inv_tot), "Exit Value Rs": round(exit_tot), "Gain Rs": round(exit_tot - inv_tot),
            "Exit Date": m.strftime("%Y-%m-%d"), "Holding Days": hd,
            "Portfolio Ret %": round(port, 1), "Nifty Ret %": round(nif, 1), "Beat Nifty": "YES" if port > nif else "no",
            "Avg Stock Ret %": round(grp["actual_ret"].mean(), 1),
            "Avg Winner %": round(grp[grp.actual_ret > 0]["actual_ret"].mean(), 1) if winners else 0.0,
            "Avg Loser %": round(grp[grp.actual_ret <= 0]["actual_ret"].mean(), 1) if losers else 0.0,
            "Max DD During Hold %": round(-cyc_dd, 1), "Win Ratio": f"{winners}/{losers}",
            "Top Contributor": f"{top_c} ({contrib[top_c]:+.1f})", "Worst Contributor": f"{worst_c} ({contrib[worst_c]:+.1f})"})
    cyc = pd.DataFrame(cyc_rows); detail = pd.DataFrame(detail_rows)
    track = {s: g for s, g in h.groupby("symbol")}
    clean = h.assign(Status="Completed").rename(columns={"symbol": "Stock", "asof": "Date",
        "buy_price": "Buy", "exit_price": "Exit", "actual_ret": "Return %", "rank": "Rank",
        "hit_top25": "Winner"})[["fingerprint", "Date", "Stock", "Buy", "Exit", "Return %",
        "Rank", "Winner", "regime", "Status"]].sort_values("Date")
    return cyc, detail, track, clean


def main():
    capital = arg("--capital", CONFIG["default_capital"], float)
    C = CONFIG
    # DYNAMIC HORIZON: independently backtest ALL holding periods; choose_horizon picks by regime below
    hmat = horizon_matrix()
    days_for = {v: k for k, v in LABELS.items()}
    closes, highs, lows, vols, idx, vix, spx = load_panels()
    # DYNAMIC TRADABLE UNIVERSE (liquidity/tradability filters) — not a hard-coded index list
    from india.universe import build_universe
    try:
        UNIV = set(build_universe(closes, vols))
        if len(UNIV) < 50:
            UNIV = set(NIFTY200)                          # safety fallback
    except Exception:
        UNIV = set(NIFTY200)
    closes = closes[[c for c in closes.columns if c in UNIV]]
    rets = closes.pct_change(); asof = closes.index[-1]; prices = closes.iloc[-1]
    reg = pd.read_csv(REG) if REG.exists() else pd.DataFrame()
    # AUTO-REFRESH: score any matured recs so history reflects the latest data every run
    if not reg.empty:
        try:
            from india.recommendation_registry import score as _score
            reg, _ns = _score(reg, closes, rets)
            if _ns:
                reg.to_csv(REG, index=False)
        except Exception:
            pass

    champ, _ = backtest(method=C["method"], regime=C["regime"], topn=15,
                        sector_cap=C["sector_cap"], rebal=C["rebal"])
    champ = champ.dropna(); cs = stats(champ, idx); eqc = (1 + champ).cumprod()
    G = evidence_gate(champ, idx, reg)
    if G["pf_grade"] not in ("A", "B"):
        print("  Portfolio evidence gate failed -> no recommendations issued."); return

    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    exp, regime, regime_conf = current_regime()
    # DYNAMIC POLICY (not fixed config): holding period adapts to regime, basket size to breadth+regime.
    # Both are walk-forward backtested in india/dynamic_policy.py (dynamic ~ fixed Sharpe, lower DD).
    rec_label, rec_conf = choose_horizon(hmat, exp)
    horizon = arg("--horizon", days_for.get(rec_label, CONFIG["default_horizon"]), int)
    months = max(1, horizon // 21)
    n_dyn, breadth = choose_topn(hist, closes, exp, cap=C["sector_cap"])
    n = arg("--topn", n_dyn, int)
    # RISK PROFILE (one engine, three profiles). Shield = production default (calmest names).
    # Balanced = medium-vol tier (evidence-backed, india/risk_tiers.py). Growth = high-vol (EXPERIMENTAL).
    profile = arg("--profile", "shield", str).lower()
    PROFILE = {"shield": (0.0, 0.40, "Shield (Conservative)"),
               "balanced": (0.34, 0.70, "Balanced"),
               "growth": (0.60, 1.01, "Growth (Experimental)")}
    plo, phi, profile_label = PROFILE.get(profile, PROFILE["shield"])
    pvr = hist.std().rank(pct=True)
    pool = list(pvr[(pvr > plo) & (pvr <= phi)].index)
    hist_sel = hist[pool] if len(pool) >= max(n, 8) else hist          # fall back if a tier is too thin
    selected, _ = select_with_watchlist(hist_sel, n, C["sector_cap"])
    vol_rank = hist.std().rank(pct=True)                               # FULL-universe rank -> honest risk labels
    w = weights_for("hrp", hist[selected]); w = (w / w.sum()).clip(upper=C["name_cap"]); w = w / w.sum()
    invest = capital * exp
    mode, mode_conf, status = mode_of(horizon)
    hv = horizon_view(eqc, horizon, 100000)
    run_date = datetime.now().date(); market_asof = asof.date()    # run date vs data date (no ambiguity)
    valid_until = (asof + timedelta(days=C["expiry_cal_days"])).date()
    # DYNAMIC REVIEW: weak market -> review sooner (de-risk fast); strong trend -> review later (let it run)
    review_cal = 30 if exp < 0.65 else (60 if exp < 0.9 else 120)
    review = (asof + timedelta(days=review_cal)).date()
    rid_today = rec_id(asof, months)

    # real, causal technical CONTEXT (computed from price; NOT the selection driver, which is low-vol)
    mom3 = (closes.iloc[-1] / closes.iloc[-64] - 1) * 100
    nifty_3m = 100 * (idx.iloc[-1] / idx.iloc[-64] - 1)
    rs = (mom3 - nifty_3m)                                          # relative strength vs Nifty
    rs_rank = rs.rank(pct=True)
    above200 = closes.iloc[-1] > closes.tail(200).mean()

    cyc, detail, track, clean = history_for(reg, idx, capital, closes)
    beat_n = int((cyc["Beat Nifty"] == "YES").sum()) if not cyc.empty else 0
    beat_pct = round(100 * beat_n / len(cyc)) if not cyc.empty else 0
    avg_port = cyc["Portfolio Ret %"].mean() if not cyc.empty else float("nan")

    # ---- Analytics from the registry: Attribution · Stock Track Record · Yearly quality ----
    hh = reg[(reg.scored == 1) & (reg.source == "historical")].copy()
    attribution = track_record = yearly = pd.DataFrame()
    if not hh.empty:
        hh["contrib"] = hh["weight"] * hh["actual_ret"]
        hh["year"] = pd.to_datetime(hh["asof"]).dt.year
        attribution = (hh.groupby("symbol").agg(**{
            "Times Held": ("rec_id", "nunique"), "Total Contribution %": ("contrib", "sum"),
            "Avg Contribution %": ("contrib", "mean"), "Avg Return %": ("actual_ret", "mean")})
            .round(2).sort_values("Total Contribution %", ascending=False).reset_index()
            .rename(columns={"symbol": "Stock"}))
        track_record = (hh.groupby("symbol").agg(**{
            "Times Recommended": ("rec_id", "nunique"), "First": ("asof", "min"), "Last": ("asof", "max"),
            "Avg Return %": ("actual_ret", "mean"), "Best %": ("actual_ret", "max"),
            "Worst %": ("actual_ret", "min"), "Win %": ("actual_ret", lambda x: 100 * (x > 0).mean())})
            .round(1).sort_values("Times Recommended", ascending=False).reset_index()
            .rename(columns={"symbol": "Stock"}))
        yearly = (hh.groupby("year").agg(**{
            "Picks": ("symbol", "count"), "Winners": ("actual_ret", lambda x: int((x > 0).sum())),
            "Losers": ("actual_ret", lambda x: int((x <= 0).sum())),
            "Win %": ("actual_ret", lambda x: round(100 * (x > 0).mean())),
            "Avg Return %": ("actual_ret", "mean"), "Median %": ("actual_ret", "median"),
            "Best %": ("actual_ret", "max"), "Worst %": ("actual_ret", "min")})
            .round(1).reset_index().rename(columns={"year": "Year"}))
        # merge per-year cycle stats: beat-Nifty count + per-year money (compounded within the year from ref capital)
        if not cyc.empty:
            cy = cyc.assign(Year=cyc["Investment Month"].str[:4].astype(int))
            cyg = cy.groupby("Year").agg(**{"Cycles": ("Investment Month", "count"),
                "Beat Nifty": ("Beat Nifty", lambda x: f"{int((x=='YES').sum())}/{len(x)}"),
                "Profit Rs": ("Gain Rs", "sum")}).reset_index()

            def _year_money(g):
                bal = capital
                for r in g.sort_values("Investment Month").to_dict("records"):
                    bal *= (1 + r["Portfolio Ret %"] / 100)
                return pd.Series({"Year Ret %": round(100 * (bal / capital - 1), 1), "End Rs": round(bal)})
            moneyy = cy.groupby("Year").apply(_year_money).reset_index()
            yearly = yearly.merge(cyg, on="Year", how="left").merge(moneyy, on="Year", how="left")
            yearly["Start Rs"] = round(capital)
            # MONEY-FIRST ordering (rupees are easier to grasp than percentages); stats follow
            lead = ["Year", "Start Rs", "End Rs", "Year Ret %", "Beat Nifty", "Cycles", "Picks", "Win %"]
            yearly = yearly[[c for c in lead if c in yearly.columns] +
                            [c for c in yearly.columns if c not in lead]]

    # ---- MULTI-LAYER CANDIDATE SCORES (honest: validated driver + context + DATA NOT AVAILABLE) ----
    risk_score = (100 * (1 - hist.std().rank(pct=True))).round()              # low-vol = high (VALIDATED driver)
    mom3_all = (closes.iloc[-1] / closes.iloc[-64] - 1).reindex(hist.columns)
    above200_all = (closes.iloc[-1] > closes.tail(200).mean()).reindex(hist.columns)
    tech_score = (50 + 25 * above200_all.astype(float) + 25 * mom3_all.rank(pct=True)).round()  # CONTEXT (no validated lift)
    sec_mom = {sec: (closes[[c for c in hist.columns if sector_of(c) == sec]].iloc[-1] /
               closes[[c for c in hist.columns if sector_of(c) == sec]].iloc[-64] - 1).mean()
               for sec in set(sector_of(c) for c in hist.columns)}
    sec_rank = pd.Series(sec_mom).rank(pct=True)
    sec_score = {c: round(100 * sec_rank[sector_of(c)]) for c in hist.columns}                  # CONTEXT
    market_score = round(100 * exp)                                            # regime (VALIDATED)
    NA_DATA = "DATA NOT AVAILABLE"

    # ---- Sheet: Today's Recommendations. Disclaimer is on the Dashboard (not repeated per row). ----
    completion = (asof + timedelta(days=int(horizon * C["review_cal_factor"]))).date()
    daily_vol = hist.std()                                   # for volatility-band entry zone
    gen_date = run_date
    expiry_date = (asof + timedelta(days=int(C.get("expiry_cal_days", 7)))).date()

    MIN_ANALOGUES = 5            # need >=5 historical cases before showing a target/return — else say so

    def score_components(sym):
        """Transparent FACTOR BREAKDOWN (each 0-100) so an investor sees WHY, not one opaque number.
        Overall = weighted blend (risk & history dominate; sector is light context). Same function scores
        any name, so a pick can be ranked against its sector alternatives."""
        tt = track.get(sym); o = len(tt) if tt is not None else 0
        wn = round(100 * (tt["actual_ret"] > 0).mean()) if o else None
        md = float(tt["actual_ret"].median()) if o else None
        hist_raw = round(0.6 * wn + 0.4 * max(0, min(100, (md + 5) * 5))) if o else 50
        shrink = min(1.0, o / MIN_ANALOGUES)                       # small sample -> pull toward neutral 50
        hist_sc = int(round(50 + shrink * (hist_raw - 50)))         # honest: 2 cases can't earn a 100
        a200 = bool(sym in closes.columns and closes[sym].iloc[-1] > closes[sym].tail(200).mean())
        rsr = float(rs_rank.get(sym, 0.5)); rsr = 0.5 if pd.isna(rsr) else rsr   # short-history names -> neutral
        vr = float(vol_rank.get(sym, 0.5)); vr = 0.5 if pd.isna(vr) else vr
        rsv = _rsi(closes[sym].dropna()) if (sym in closes.columns and len(closes[sym].dropna()) > 30) else 50
        if pd.isna(rsv):
            rsv = 50
        rsi_pos = 1.0 if 40 <= rsv <= 70 else 0.5
        tech_sc = int(max(0, min(100, round(40 * (1 if a200 else 0) + 40 * rsr + 20 * rsi_pos))))
        risk_sc = int(round(100 * (1 - vr)))                                   # low vol -> high (validated driver)
        sec_sc = int(sec_score.get(sym, 50))
        regime_sc = int(round(100 * exp))
        overall = int(round(0.30 * hist_sc + 0.25 * risk_sc + 0.20 * tech_sc +
                            0.10 * sec_sc + 0.15 * regime_sc))
        return dict(hist=hist_sc, tech=tech_sc, risk=risk_sc, sector=sec_sc, regime=regime_sc,
                    overall=overall, occ=o, win=wn, med=md)

    def evidence_score(sym):
        return score_components(sym)["overall"]

    rows = []
    for _ord, s in enumerate(w.sort_values(ascending=False).index, 1):
        px = float(prices[s]); band = px * float(daily_vol.get(s, 0.01)) * 2     # ~2-sigma daily band
        sh = int((invest * w[s]) // px) if px > 0 else 0
        t = track.get(s); occ = len(t) if t is not None else 0
        rl = "Low" if vol_rank.get(s, 0.5) < 0.33 else ("Medium" if vol_rank.get(s, 0.5) < 0.66 else "High")
        sample_conf = "High" if occ >= 10 else ("Medium" if occ >= 5 else ("Low" if occ >= 1 else "New"))
        DASH = "No historical analogues yet (<3 obs)"      # explain blanks, never leave empty
        med = t["actual_ret"].median() if occ else None
        best = t["actual_ret"].max() if occ else None
        worst = t["actual_ret"].min() if occ else None
        win = round(100 * (t["actual_ret"] > 0).mean()) if occ else None
        avg = round(t["actual_ret"].mean()) if occ else None
        # ---- technicals for "why today" (descriptive current-state facts, not forecasts) ----
        ser = closes[s].dropna()
        ma200 = float(ser.tail(200).mean()); d200 = round(100 * (px / ma200 - 1), 1)
        rsi = round(_rsi(ser)) if len(ser) > 30 else None
        hi52, lo52 = float(ser.tail(252).max()), float(ser.tail(252).min())
        pos52 = round(100 * (px - lo52) / (hi52 - lo52)) if hi52 > lo52 else None
        volp = round(100 * float(vol_rank.get(s, 0.5)))                  # low pctile = calmest names

        # ---- FACTOR BREAKDOWN (each 0-100) -> transparent Overall score (documented on Methodology) ----
        comp = score_components(s); score = comp["overall"]
        # WHY THIS, NOT THAT? — show the sector alternatives + their scores, but be HONEST that the
        # selector is lowest-volatility under the sector cap, NOT the Evidence Score (which is context).
        peers = [c for c in hist.columns if sector_of(c) == sector_of(s) and c != s]
        alt = sorted(((p, evidence_score(p)) for p in peers), key=lambda kv: -kv[1])[:3]
        if alt:
            alt_str = (f"Picked by lowest-vol + sector cap (the validated rule). Evidence scores — "
                       f"{s}: {score}; " + ", ".join(f"{p}: {sc}" for p, sc in alt))
            if any(sc > score for _, sc in alt):
                alt_str += ". Note: a peer scores higher but is higher-vol or cap-excluded — Evidence Score is context, not the selector."
        else:
            alt_str = "No same-sector peer in the universe."
        # RECOMMENDATION confidence (this single pick's evidence) — distinct from portfolio process confidence
        rec_conf_pct = min(95, int(round(40 + 0.45 * score +
                           (15 if occ >= 10 else (8 if occ >= 5 else (3 if occ >= 1 else 0))))))
        if occ and med is not None and med < 0:
            strength = "WATCH"                        # weak historical analogue -> never a BUY (trust)
        elif score >= 65 and (not occ or med > 0):
            strength = "STRONG BUY"
        elif score >= 55:
            strength = "BUY"
        elif score >= 45:
            strength = "ACCUMULATE"
        else:
            strength = "WATCH"
        # ---- target / upside / range — ONLY when there is enough evidence (>=5 analogues), else say so ----
        enough = occ >= MIN_ANALOGUES
        INSUFF = f"Insufficient evidence (<{MIN_ANALOGUES} cases)" if occ else "No analogues yet"
        if enough:
            p25, p75 = np.percentile(t["actual_ret"], 25), np.percentile(t["actual_ret"], 75)
            target = round(px * (1 + med / 100)); upside = round(med, 1)
            ann = round(((1 + med / 100) ** (252 / horizon) - 1) * 100, 1)
            ret_range = f"{p25:+.1f}% to {p75:+.1f}% (mid 50% of {occ} cases)"
            exp_range = f"{p25:+.0f}% to {p75:+.0f}%"          # ONE clean column for the investor view
            prob_clean = f"{win:.0f}%"
        else:
            target = upside = ann = ret_range = INSUFF
            exp_range = "—"; prob_clean = "—"                  # short dash, not a sentence repeated 5x
        trend = f"{'Above' if d200 >= 0 else 'Below'} 200-DMA ({d200:+.1f}%)"
        rstr = "Outperforming" if rs_rank[s] > 0.6 else ("In-line" if rs_rank[s] > 0.4 else "Lagging")
        # ---- WHY TODAY: current-state setup (descriptive context — NOT a forecast) ----
        setup = [f"{'above' if d200 >= 0 else 'below'} 200-DMA {d200:+.1f}%",
                 f"{'calm' if volp < 40 else ('elevated' if volp > 66 else 'normal')} vol ({volp}th pctile)"]
        if pos52 is not None:
            setup.append("near 52w high" if pos52 >= 80 else ("near 52w low" if pos52 <= 20 else f"{pos52}% of 52w range"))
        if rsi is not None:
            setup.append(f"RSI {rsi}" + (" (overbought)" if rsi >= 70 else (" (oversold)" if rsi <= 30 else "")))
        setup += [f"sector rank {sec_score[s]:.0f}/100", "regime " + ("risk-on" if exp >= 0.85 else "cautious")]
        today_setup = "; ".join(setup)
        # plain-English WHY-NOW, as bullets (facts, not forecasts)
        wb = [f"Low-risk {sector_of(s)} holding ({rl.lower()} vol)", trend.lower(),
              f"sector strength {sec_score[s]:.0f}/100",
              "regime favourable" if exp >= 0.85 else "regime cautious (partial deploy)"]
        if rs_rank[s] > 0.6:
            wb.insert(2, "outperforming Nifty")
        if occ:
            wb.append(f"{occ} similar past recs: {win:.0f}% positive, median {med:+.1f}%")
            if med < 0:
                wb.append("HELD FOR DIVERSIFICATION despite weak historical analogue — sized by risk, not conviction")
        else:
            wb.append("no historical analogue yet (<3 obs)")
        rows.append({
            "Strength": strength, "Score /100": score, "Stock": s, "Sector": sector_of(s),
            "Current Price": round(px, 1), "Buy Range": f"{px-band:.0f} - {px+band:.0f}",
            "Expected Range (hist)": exp_range, "Prob +ve": prob_clean,
            "Hist Target": target, "Expected Return Range": ret_range, "Upside %": upside,
            "Hist Median Ret %": round(med, 1) if enough else INSUFF, "Annualized %": ann,
            "Risk / Reward (hist)": round(med / abs(worst), 1) if (enough and worst < 0) else INSUFF,
            "Probability Positive %": win if enough else INSUFF,
            "Probability >10% %": round(100 * (t["actual_ret"] > 10).mean()) if enough else INSUFF,
            "Best Case %": round(best, 1) if enough else INSUFF, "Worst Case %": round(worst, 1) if enough else INSUFF,
            # FACTOR BREAKDOWN (each 0-100) — the "why this stock" detail behind the Overall score
            "F: Historical": comp["hist"], "F: Technical/Trend": comp["tech"], "F: Risk/Vol": comp["risk"],
            "F: Sector": comp["sector"], "F: Regime": comp["regime"],
            "Dist 200-DMA %": d200, "RSI": rsi if rsi is not None else DASH, "Vol Pctile": volp,
            "52W Range Pos %": pos52 if pos52 is not None else DASH,
            "Trend": trend, "Rel Strength": rstr,
            "Today's Setup": today_setup, "Why This vs Alternatives": alt_str,
            "Rec Confidence %": rec_conf_pct,
            "Recommended Holding": f"{months} months ({rec_label})", "Expected Exit": str(completion),
            "Generated": str(gen_date), "Valid Until": str(expiry_date), "Review Date": str(review),
            "Allocation Rs": round(sh * px), "Shares": sh,
            "Weight %": round(100 * w[s], 1), "Evidence": sample_conf, "Similar Past Cases": occ,
            "Why": " • ".join(wb)})
    live = pd.DataFrame(rows)
    # SORT top-to-bottom = best first: strength tier, then Evidence Score desc, then weight desc.
    # One sort on the source -> xlsx, canonical CSV, Telegram and Google Sheets all share this order.
    if not live.empty:
        rank = {"STRONG BUY": 0, "BUY": 1, "ACCUMULATE": 2, "WATCH": 3}
        live["_sr"] = live["Strength"].map(rank).fillna(9)
        live = (live.sort_values(["_sr", "Score /100", "Weight %"], ascending=[True, False, False])
                .drop(columns="_sr").reset_index(drop=True))
        live["Profile"] = profile_label

    # ---- CLEAN investor view (no 40-column wall): the actionable columns only ----
    clean_cols = ["Strength", "Score /100", "Stock", "Sector", "Current Price", "Buy Range",
                  "Expected Range (hist)", "Prob +ve", "Rec Confidence %", "Recommended Holding",
                  "Review Date", "Allocation Rs", "Shares", "Weight %", "Why"]
    recs_clean = live[[c for c in clean_cols if c in live.columns]] if not live.empty else live
    # "Why this stock" factor breakdown (kept, but as a compact second block — not 40 columns up top)
    factor_cols = ["Stock", "F: Historical", "F: Technical/Trend", "F: Risk/Vol", "F: Sector",
                   "F: Regime", "Trend", "RSI", "52W Range Pos %", "Today's Setup",
                   "Why This vs Alternatives"]
    recs_factors = live[[c for c in factor_cols if c in live.columns]] if not live.empty else live
    # canonical machine-readable snapshot (decouples the DB / Telegram / sync from the report layout)
    canon_cols = ["Generated", "Profile", "Stock", "Sector", "Strength", "Score /100", "Current Price",
                  "Buy Range", "Hist Target", "Expected Range (hist)", "Prob +ve", "Rec Confidence %",
                  "Recommended Holding", "Review Date", "Valid Until", "Allocation Rs", "Shares",
                  "Weight %", "Why"]
    if not live.empty:
        live[[c for c in canon_cols if c in live.columns]].to_csv(ROOT / "data" / "aegis_today.csv", index=False)

    # ---- Sheet: Factor Snapshot — Observed / Used by Strategy / Contribution (no faked signals) ----
    from india.technical_factors import snapshot as tech_snapshot
    why_rows = []
    for s in w.index:
        sec_syms = [x for x in closes.columns if SECTORS.get(x) == sector_of(s)]
        for st, cat, ind, obs, used, contrib in tech_snapshot(closes, highs, lows, vols, idx, s, sec_syms):
            why_rows.append({"Stock": st, "Category": cat, "Indicator": ind, "Observed": obs,
                             "Used by Strategy": used, "Contribution": contrib})
        # portfolio drivers actually used + the NOT-EVALUATED layers (honest)
        for cat, ind, obs, used, contrib in [
            ("Portfolio", "HRP cluster weight", f"{100*w[s]:.1f}%", "YES", "Positive"),
            ("Portfolio", f"Sector cap <= {C['sector_cap']}", "diversified", "YES", "Positive"),
            ("Macro", "Regime exposure", regime, "YES", "Positive"),
            ("Fundamental", "ROE/PE/EPS/Debt", "Not Evaluated", "No", "no PIT data"),
            ("News/Events", "earnings/orders/upgrades", "Not Evaluated", "No", "no data")]:
            why_rows.append({"Stock": s, "Category": cat, "Indicator": ind, "Observed": obs,
                             "Used by Strategy": used, "Contribution": contrib})
    why = pd.DataFrame(why_rows)

    # ---- Selection Decision: WHY each pick won vs the rejected candidates (the real metric: vol) ----
    vol_all = (hist.std() * np.sqrt(252) * 100)
    sel_set = set(w.index); sel_sectors = {}
    for s in w.index:
        sel_sectors[sector_of(s)] = sel_sectors.get(sector_of(s), 0) + 1
    dec_rows = []
    for s in w.sort_values(ascending=False).index:
        sec = sector_of(s)
        peers = [x for x in hist.columns if sector_of(x) == sec and x != s]
        cheaper = [x for x in peers if vol_all.get(x, 1e9) < vol_all[s]]   # lower-vol same-sector not taken
        why_won = (f"Lowest-volatility pick available for {sec} under the sector cap "
                   f"(vol {vol_all[s]:.0f}%). " + ("" if not cheaper else
                   f"Lower-vol {sec} names ({', '.join(cheaper[:2])}) were already used by the cap. "))
        dec_rows.append({"Stock": s, "Sector": sec, "Decision": "SELECTED",
                         "Volatility %": round(vol_all[s]), "HRP Weight %": round(100 * w[s], 1),
                         "Why": why_won + "Risk-driven selection — not an alpha call."})
    sel_vol_med = float(vol_all[list(sel_set)].median())
    rej = vol_all.drop(list(sel_set), errors="ignore").sort_values().head(12)
    for s in rej.index:
        sec = sector_of(s); reasons = []
        if sel_sectors.get(sec, 0) >= C["sector_cap"]:
            reasons.append("sector cap filled")
        if vol_all[s] > sel_vol_med:
            reasons.append(f"higher volatility ({vol_all[s]:.0f}% vs {sel_vol_med:.0f}% median selected)")
        if not reasons:
            reasons.append("outside top-N by volatility")
        dec_rows.append({"Stock": s, "Sector": sec, "Decision": "rejected",
                         "Volatility %": round(vol_all[s]), "HRP Weight %": None, "Why": "; ".join(reasons)})
    decision = pd.DataFrame(dec_rows)

    # ---- Candidate Scores: the intermediate Universe -> Scores -> Portfolio table (why in/out) ----
    cand_rows = []
    for s in sorted(hist.columns, key=lambda x: -risk_score.get(x, 0)):
        chosen = s in sel_set
        if chosen:
            reason = "SELECTED"
        elif sel_sectors.get(sector_of(s), 0) >= C["sector_cap"]:
            reason = "sector cap filled"
        else:
            reason = "lower risk score (higher volatility)"
        cand_rows.append({"Stock": s, "Sector": sector_of(s),
            "Candidate Score": int(risk_score.get(s, 0)), "Risk Score (driver)": int(risk_score.get(s, 0)),
            "Sector Score (context)": sec_score.get(s), "Technical Score (context)": int(tech_score.get(s, 50)),
            "Market Score": market_score, "Fundamental": NA_DATA, "News": NA_DATA,
            "Selected": "YES" if chosen else "no", "Reason": reason})
    candidate_scores = pd.DataFrame(cand_rows)
    try:                                                # research/engine internals stay INTERNAL
        candidate_scores.to_csv(ROOT / "data" / "aegis_candidates.csv", index=False)
    except Exception:
        pass

    # ---- Historical Expectation block (#1 ask): evidence from past cycles, NOT a forecast ----
    er = hmat[hmat["Horizon"] == rec_label]
    er = er.iloc[0] if not er.empty else None
    hist_expect = pd.DataFrame([
        ["Horizon", f"{rec_label} ({months} months)"],
        ["Historical median return", f"{er['Median Return %']:+.1f}%" if er is not None else "n/a"],
        ["Historical average return", f"{er['Avg Return %']:+.1f}%" if er is not None else "n/a"],
        ["Historical win rate", f"{er['Win Rate %']:.0f}%" if er is not None else "n/a"],
        ["Historical best cycle", f"{er['Best Cycle %']:+.1f}%" if er is not None else "n/a"],
        ["Historical worst cycle", f"{er['Worst Cycle %']:+.1f}%" if er is not None else "n/a"],
        ["Beat Nifty rate", f"{er['Beat Nifty %']:.0f}%" if er is not None else "n/a"],
        ["Cycles observed", int(er["Cycles"]) if er is not None else 0],
        ["Expected review", str(review)],
        ["NOTE", "How similar historical AEGIS portfolios performed at this horizon. EVIDENCE-BASED, "
         "NOT a guarantee or forecast. Levels are survivorship-inflated -> trust the odds/relative edge, "
         "not the exact %."]], columns=["Historical Expectation", "Value"])

    # ---- Candidate Universe funnel with REAL counts (honest; no fabricated thresholds) ----
    n_uni = len(hist.columns); vmed = float(vol_all.median())
    n_lowvol = int((vol_all.reindex(hist.columns) < vmed).sum())
    n_sectors = len(set(sector_of(x) for x in hist.columns))
    funnel = pd.DataFrame([
        ["Nifty-200 with full lookback history", n_uni, "eligible universe"],
        ["Lower-half by volatility (selection pool)", n_lowvol, "the only selection signal is low vol"],
        [f"Sectors available (cap <= {C['sector_cap']}/sector)", n_sectors, "diversification constraint"],
        ["Final portfolio (capital-sized)", len(w), f"top {len(w)} for Rs{capital:,.0f} = {100*len(w)/n_uni:.0f}% of universe"]],
        columns=["Stage", "Count", "Note"])

    # ---- Sheet 1: Dashboard (correct dates, no ambiguity) ----
    dashboard = pd.DataFrame([
        ["** WHAT IS VALIDATED **", "PORTFOLIO recommendation = evidence-backed. INDIVIDUAL stock "
         "= construction candidate, NOT validated as alpha (selection RQS ~0.5)."],
        ["Workbook Version", f"AEGIS_{run_date}"], ["Recommendation Cycle", f"{asof.year}-Q{(asof.month-1)//3+1}"],
        ["Run Date", str(run_date)], ["Market Data As Of", str(market_asof)], ["Valid Until", str(valid_until)],
        ["Strategy", f"AEGIS {VERSION.split('(')[0].strip()}"], ["Universe", "Nifty-200"],
        ["Recommended Horizon", f"{rec_label} (confidence {rec_conf})"],
        ["Suggested Holding Window", f"{months} months"],
        ["Portfolio Grade", G["pf_grade"]], ["Recommendation Grade", G["al_grade"]],
        ["Current Market", regime], ["Exposure", f"{exp:.0%}"], ["Recommended Stocks", len(w)],
        ["Portfolio beat Nifty (history)", f"{beat_n}/{len(cyc)} ({beat_pct}%)"],
        ["Historical median return (%s)" % rec_label, f"{er['Median Return %']:+.1f}%" if er is not None else "n/a"],
        ["Historical win rate (%s)" % rec_label, f"{er['Win Rate %']:.0f}%" if er is not None else "n/a"],
        ["Expected drawdown", f"~{round(cs['dd'])}% (historical)"], ["Cycles observed", len(cyc)],
        ["Selection RQS (all history)", f"{G['rqs']:.3f} (~random)"], ["Review Date", str(review)],
        ["Recommendation Status", f"Running — {len(w)} Active · 0 Reviewed · 0 Completed"],
        ["Sample Confidence key", "High >=10 obs · Medium 5-9 · Low 2-4 · New 0"],
        ["(expectations)", "historical, evidence-based — NOT forecasts/guarantees"]],
        columns=["Field", "Value"])
    # ---- Evidence Badges (what's validated vs experimental vs not evaluated) ----
    badges = pd.DataFrame([
        ["Portfolio Strategy", "VALIDATED", f"grade {G['pf_grade']} · beat Nifty {beat_pct}% of cycles"],
        ["Stock Selection (alpha)", "EXPERIMENTAL", f"RQS {G['rqs']:.2f} ~ random · holdings, not bets"],
        ["Recommendation Horizon", "HISTORICALLY TESTED", f"all horizons backtested · best = {rec_label}"],
        ["Technical Context", "COMPUTED (not a driver)", "momentum / rel-strength / 200-DMA shown for info"],
        ["Fundamental Analysis", "NOT EVALUATED", "no point-in-time data"],
        ["News / Events", "NOT EVALUATED", "no event database"]], columns=["Layer", "Status", "Detail"])
    if not cyc.empty:
        pr = cyc["Portfolio Ret %"]; wins = pr > 0
        # longest win / loss streaks
        def streak(mask):
            best = cur = 0
            for x in mask:
                cur = cur + 1 if x else 0; best = max(best, cur)
            return best
        statistics = pd.DataFrame([
            ["Total cycles", len(cyc)], ["Cycles beating Nifty", f"{beat_n} ({beat_pct}%)"],
            ["Cycles positive", f"{int(wins.sum())} ({round(100*wins.mean())}%)"],
            ["Avg portfolio return", f"{pr.mean():+.1f}%"], ["Median portfolio return", f"{pr.median():+.1f}%"],
            ["Std deviation", f"{pr.std():.1f}%"], ["Avg outperformance vs Nifty", f"{(pr-cyc['Nifty Ret %']).mean():+.1f}%"],
            ["Best cycle", f"{pr.max():+.1f}%"], ["Worst cycle", f"{pr.min():+.1f}%"],
            ["Avg winning cycle", f"{pr[wins].mean():+.1f}%"], ["Avg losing cycle", f"{pr[~wins].mean():+.1f}%"],
            ["Median winning cycle", f"{pr[wins].median():+.1f}%"], ["Median losing cycle", f"{pr[~wins].median():+.1f}%"],
            ["Avg holding period", f"{months} months ({C['rebal']} trading days)"],
            ["Avg drawdown during hold", f"{cyc['Max DD During Hold %'].mean():.1f}%" if 'Max DD During Hold %' in cyc else 'n/a'],
            ["Longest win streak", f"{streak(wins)} cycles"], ["Longest loss streak", f"{streak(~wins)} cycles"]],
            columns=["Metric", "Value"])
    else:
        statistics = pd.DataFrame([["(no scored history yet)", ""]], columns=["Metric", "Value"])

    # ---- Strategy Replay: the money diary (compound non-overlapping quarterly cycles) ----
    sr_rows = []; bal = nbal = capital
    for r in (cyc.to_dict("records") if not cyc.empty else []):
        start = bal; bal *= (1 + r["Portfolio Ret %"] / 100); nbal *= (1 + r["Nifty Ret %"] / 100)
        sr_rows.append({"Cycle": r["Investment Month"], "Start Rs": round(start),
            "Return %": r["Portfolio Ret %"], "End Rs": round(bal), "If Nifty Rs": round(nbal),
            "Beat Nifty": r["Beat Nifty"], "Win Ratio": r.get("Win Ratio", ""),
            "Max DD %": r.get("Max DD During Hold %", ""), "Largest Winner": r.get("Top Contributor", ""),
            "Largest Loser": r.get("Worst Contributor", "")})
    strategy_replay = pd.DataFrame(sr_rows)
    if not strategy_replay.empty:
        strategy_replay = pd.concat([strategy_replay, pd.DataFrame([{"Cycle": "FINAL",
            "Start Rs": round(capital), "Return %": round(100 * (bal / capital - 1), 1),
            "End Rs": round(bal), "If Nifty Rs": round(nbal), "Beat Nifty": "AEGIS" if bal > nbal else "Nifty"}])],
            ignore_index=True)

    # ---- Market Snapshot ----
    sec_mom = {sec: (closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-1] /
               closes[[c for c in closes.columns if SECTORS.get(c) == sec]].iloc[-64] - 1).mean()
               for sec in set(SECTORS.values()) if len([c for c in closes.columns if SECTORS.get(c) == sec]) >= 2}
    nifty_3m = 100 * (idx.iloc[-1] / idx.iloc[-64] - 1) if len(idx) > 64 else float("nan")
    spx_3m = (100 * (spx.dropna().iloc[-1] / spx.dropna().iloc[-64] - 1)
              if spx is not None and len(spx.dropna()) > 64 else None)
    market = pd.DataFrame([["As of (market data)", str(market_asof)], ["Regime", regime],
        ["Suggested exposure", f"{exp:.0%}"], ["India VIX", f"{float(vix.iloc[-1]):.1f}" if vix is not None else "n/a"],
        ["Nifty vs 200-DMA", "above" if idx.iloc[-1] > idx.tail(200).mean() else "below"],
        ["Nifty 3M trend", f"{nifty_3m:+.1f}%"],
        ["Global (S&P 500 3M)", f"{spx_3m:+.1f}%" if spx_3m is not None else "n/a"],
        ["Sector leaders (3M)", ", ".join(sorted(sec_mom, key=sec_mom.get, reverse=True)[:3])],
        ["Sector laggards (3M)", ", ".join(sorted(sec_mom, key=sec_mom.get)[:3])]], columns=["Field", "Value"])

    # ---- About AEGIS (honest one-pager) ----
    about = pd.DataFrame([
        ["What AEGIS is", "A risk-managed PORTFOLIO engine: low-volatility selection + HRP weighting + "
         "sector cap + market-regime exposure timing. Rebalances quarterly."],
        ["What is validated", f"The PORTFOLIO process (grade {G['pf_grade']}): beat Nifty {beat_pct}% of "
         f"cycles, ~half the drawdown, higher risk-adjusted return. Out-of-sample tested."],
        ["What is NOT validated", f"Individual stock-picking ALPHA. Selection RQS {G['rqs']:.2f} ~ random "
         "— picks are portfolio CONSTITUENTS, not proven winners."],
        ["What AEGIS is NOT", "Not a tip sheet, not a multibagger finder, not a return predictor. It does "
         "not forecast which stock will rise."],
        ["Exit philosophy", "Process-based: hold to the quarterly review/rebalance. No fixed stop-loss "
         "(unvalidated). Emergency exit only on fraud/delisting/regime-off."],
        ["Review frequency", "Quarterly. Recommendation valid ~1 week from generation."],
        ["Not evaluated (no data)", "Fundamentals (ROE/PE/EPS), news/events, earnings, institutional flow. "
         "Shown as 'Not Evaluated' — never invented."],
        ["Honest caveat", "Absolute return levels are survivorship-inflated; trust the RELATIVE edge vs "
         "Nifty. Forward paper (live cycles) is the real, ongoing test."]], columns=["Topic", "Detail"])

    # ================= EXECUTIVE SUMMARY (the one screen 95% of users read) =================
    exp_med = f"{er['Median Return %']:+.1f}%" if er is not None else "n/a"
    exp_win = f"{er['Win Rate %']:.0f}%" if er is not None else "n/a"
    em = er["Median Return %"] if er is not None else 0.0
    eb = er["Best Cycle %"] if er is not None else 0.0
    ewc = er["Worst Cycle %"] if er is not None else 0.0
    median_val, best_val, worst_val = (round(capital * (1 + x / 100)) for x in (em, eb, ewc))
    # Portfolio sheet (expected outcomes — historical distribution, not a forecast)
    portfolio_sheet = pd.DataFrame([
        ["Capital", rupees(capital)], ["Deploy now", f"Rs{round(invest):,.0f} ({exp:.0%})"],
        ["Cash buffer", f"Rs{round(capital-invest):,.0f} ({1-exp:.0%})"], ["Holdings", len(w)],
        ["Recommended holding", f"{months} months ({rec_label})"],
        ["Expected return (hist median)", exp_med], ["Median expected value", f"Rs{median_val:,.0f}"],
        ["Best historical case", f"Rs{best_val:,.0f}"], ["Worst historical case", f"Rs{worst_val:,.0f}"],
        ["Probability positive", exp_win], ["Expected drawdown", f"~{round(cs['dd'])}%"],
        ["Review date", str(review)], ["Expected completion", str(completion)],
        ["Note", "Expected values are HISTORICAL distributions of similar portfolios — evidence, NOT a forecast."]],
        columns=["Field", "Value"])
    exec_block = pd.DataFrame([
        ["TODAY'S RECOMMENDATION", f"Hold a {len(w)}-stock risk-managed portfolio"],
        ["Risk Profile", profile_label + ("  (default)" if profile == "shield" else
         "  (experimental — not production default)" if profile == "growth" else "  (evidence-backed option)")],
        ["Run Date / Market Data", f"{run_date}  /  {market_asof}"],
        ["Market Regime", regime], ["Recommended Holding", f"{rec_label} ({months} months)"],
        ["Suggested Capital", rupees(capital)], ["Deploy now", f"Rs{round(invest):,.0f} ({exp:.0%})"],
        ["Cash (intentional)", f"Rs{round(capital-invest):,.0f} ({1-exp:.0%})"],
        ["Review Date", str(review)],
        ["— EXPECTED (historical similar cycles, NOT a forecast) —", ""],
        ["Probability positive", exp_win], ["Expected return (median)", exp_med],
        ["Median expected value", f"Rs{median_val:,.0f}"],
        ["Best historical case", f"Rs{best_val:,.0f}"], ["Worst historical case", f"Rs{worst_val:,.0f}"],
        ["Worst historical drawdown", f"{round(cs['dd'])}%"],
        ["— HISTORICAL PORTFOLIO (%d cycles, 2021-2026) —" % len(cyc), ""],
        ["Cycles beating Nifty", f"{beat_n}/{len(cyc)} ({beat_pct}%)"],
        ["Median cycle return", f"{cyc['Portfolio Ret %'].median():+.1f}%" if not cyc.empty else "n/a"],
        ["Avg cycle return", f"{avg_port:+.1f}%" if not np.isnan(avg_port) else "n/a"],
        ["Money diary (ref capital)", f"{rupees(capital)} -> Rs{round(bal):,.0f} ({bal/capital:.2f}x)" if not cyc.empty else "n/a"],
        ["Backtest CAGR (survivorship-inflated)", f"{cs['cagr']:.1f}%"],
        ["Backtest Sharpe", f"{cs['sharpe']:.2f}"], ["Backtest max drawdown", f"{cs['dd']:.1f}%"],
        ["Recommended deployment now", f"{exp:.0%} ({regime} regime)"],
        ["Portfolio process confidence", f"{min(96, round(50 + beat_pct*0.5 + (10 if G['pf_grade']=='A' else 0)))}% (validated process)"],
        ["Confidence note", "Portfolio confidence = the validated PROCESS. Per-stock 'Rec Confidence %' "
         "in Today's sheet = strength of that one pick's evidence — a different, weaker thing."],
        ["Strategy version", f"AEGIS {VERSION.split('(')[0].strip()}"],
        ["— TOP RISKS —", ""],
        ["1", f"Lags in strong bull markets (low beta {cs['beta']:.2f})"],
        ["2", "Stock selection is NOT validated alpha (RQS ~0.5) — these are risk constituents"],
        ["3", "Absolute returns survivorship-inflated; trust the relative edge vs Nifty"],
        ["VALIDATION", f"Portfolio grade {G['pf_grade']} (validated) · stock-alpha experimental"]],
        columns=["Field", "Value"])
    # compact recommendation table for the summary
    et = live.copy()
    exec_table = pd.DataFrame({
        "Strength": et["Strength"], "Stock": et["Stock"], "Sector": et["Sector"],
        "Buy ~Rs": et["Current Price"], "Allocation Rs": et["Allocation Rs"], "Weight %": et["Weight %"],
        "Expected Range": et["Expected Range (hist)"], "Prob +ve": et["Prob +ve"]})

    methodology = pd.DataFrame([
        ["Selection", "Pick the lowest trailing-volatility names (the only signal with out-of-sample skill)."],
        ["Sector cap", f"At most {C['sector_cap']} stocks per sector — forced diversification, not a bet."],
        ["Weighting", "Hierarchical Risk Parity (HRP): correlation-cluster aware, down-weights crowded risk."],
        ["Regime overlay", "Scale exposure by market state (India VIX + Nifty 200-DMA + global risk). The "
         "single biggest validated edge — de-risks in weak regimes."],
        ["Rebalance", "Quarterly (beats monthly net of cost; less churn)."],
        ["Evidence gate", "Promote nothing on intuition: DSR / PBO / rolling OOS / forward paper."],
        ["Factor breakdown (each 0-100)", "Every pick shows 5 sub-scores so you see WHY, not one opaque "
         "number: Historical (win rate + median, SHRUNK toward neutral when <5 cases), Technical/Trend "
         "(200-DMA, relative strength, RSI), Risk/Vol (low volatility = high), Sector, Regime. Overall = "
         "0.30 Historical + 0.25 Risk + 0.20 Technical + 0.10 Sector + 0.15 Regime."],
        ["Strength tiers", ">=65 STRONG BUY, >=55 BUY, >=45 ACCUMULATE, else WATCH. HARD RULE: a negative "
         "historical median is always WATCH (never a BUY), even if held for diversification."],
        ["Evidence threshold", f"A target price / return range is shown only with >={5} historical analogues; "
         "fewer says 'Insufficient evidence'. We never invent a number from a tiny sample."],
        ["Sector Score (x/100)", "Percentile rank of the stock's sector by 3-month sector momentum. CONTEXT "
         "only — it failed the incremental-value test, so it informs but does not drive selection."],
        ["Sector-risk tilt", "A risk-first sector tilt (overweight low-vol sectors) was BUILT and walk-forward "
         "VALIDATED — it underperformed (Sharpe 0.99 vs 1.15) so it is kept OFF. Honest: tested, not adopted."],
        ["Today's Setup", "Descriptive current-state facts (distance from 200-DMA, volatility percentile, "
         "52-week range position, RSI, sector rank, regime). Context for 'why today', NOT a forecast."],
        ["Holding period (DYNAMIC)", f"Chosen by choose_horizon() from the backtested Horizon Matrix, "
         f"REGIME-CONDITIONAL: risk-off favours a strong SHORT horizon (de-risk fast), risk-on lets it run "
         f"longer. Today: {rec_label}. The full menu of horizons (1W-1Y) with win rates is on this sheet so "
         "you can pick a shorter commitment. Per-STOCK horizons are NOT offered (small-sample skill ~random)."],
        ["Number of holdings (DYNAMIC)", "Sized by choose_topn() from market BREADTH (% above 200-DMA) + "
         "regime: wider book when healthy, concentrate + more cash when weak. Risk-first, NOT return-tuned "
         "(return-tuning N loses OOS). Walk-forward tested: dynamic ~ fixed Sharpe with LOWER drawdown."],
        ["What it does NOT do", "Predict returns or pick 'winners'. Returns are ~unpredictable on this data; "
         "risk is. AEGIS forecasts risk, not direction."]], columns=["Component", "How it works"])
    badge_rows = (pd.DataFrame([[b["Layer"], f"{b['Status']} — {b['Detail']}"] for _, b in badges.iterrows()],
                  columns=["Topic", "Detail"]) if not badges.empty else pd.DataFrame(columns=["Topic", "Detail"]))
    about_full = pd.concat([about, pd.DataFrame([["", ""], ["EVIDENCE STATUS", ""]], columns=["Topic", "Detail"]),
                            badge_rows], ignore_index=True)

    # ================= consolidated 7-sheet workbook (stacked blocks per sheet) =================
    attr_top = attribution.head(8) if not attribution.empty else attribution
    attr_bot = attribution.tail(5) if not attribution.empty else attribution
    horizon_brief = hmat[["Horizon", "Win Rate %", "Median Return %", "Worst Cycle %", "Confidence"]] \
        if not hmat.empty else hmat
    # Holding-period MENU — every horizon's backtested evidence so an investor can pick a shorter commitment
    if not hmat.empty:
        hm = hmat.copy()
        hm["Chosen"] = hm["Horizon"].map(lambda h: "<-- engine pick (regime)" if h == rec_label else "")
        horizon_menu = hm[["Horizon", "Mode", "Win Rate %", "Median Return %", "Beat Nifty %",
                           "Worst Cycle %", "Sharpe (ann)", "Confidence", "Chosen"]]
    else:
        horizon_menu = pd.DataFrame([["(horizon matrix unavailable)"]])
    # ===== AEGIS Engine v4 — the connected pipeline, made visible to the investor =====
    try:
        from india.aegis_engine import run as engine_run
        _er = engine_run()
        engine_pipeline = pd.DataFrame([(s.name, s.action, s.detail) for s in _er.stages],
                                       columns=["Pipeline Stage", "Action", "Detail"])
        engine_changed = pd.DataFrame({"What changed in today's recommendation (and why)": _er.changed})
        if _er.ledger is not None and not _er.ledger.empty:
            _l = _er.ledger.copy()
            engine_layers = pd.DataFrame({
                "Information Layer": _l["layer"], "Type": _l["kind"],
                "Incremental Value (RQS lift vs 0.50)": _l.get("incr_value", 0.0).round(3),
                "Lifecycle Status": _l.get("status", "—")})
        else:
            engine_layers = pd.DataFrame([["No layers evaluated yet", "", "", ""]],
                columns=["Information Layer", "Type", "Incremental Value (RQS lift vs 0.50)", "Lifecycle Status"])
        engine_note = pd.DataFrame([
            ["How to read this sheet", "AEGIS connects Market -> Sector -> Company -> Data Layers -> "
             "Portfolio into ONE pipeline. Only PRODUCTION information layers can move your picks."],
            ["Today", "There are 0 production layers, so today's recommendation reflects the VALIDATED "
             "portfolio + market-regime engine only — nothing speculative is influencing it."],
            ["What unlocks change", "A new data source (earnings, FII/DII flows, analyst revisions) must "
             "pass the gate (IC, RQS lift, walk-forward, DSR) AND live forward paper before it is promoted "
             "to production. Then these picks adapt automatically and this sheet explains exactly what moved."]],
            columns=["Topic", "Detail"])
        engine_blocks = [engine_pipeline, engine_changed, engine_layers, engine_note]
    except Exception as _e:
        engine_blocks = [pd.DataFrame([[f"engine view unavailable: {_e}"]], columns=["Note"])]

    # ---- Backtest Summary: a single OVERALL block so users don't interpret raw trades ----
    if not hh.empty:
        overall = pd.DataFrame([
            ["Years covered", f"{hh['year'].nunique()} ({hh['year'].min()}-{hh['year'].max()})"],
            ["Investment cycles", len(cyc)], ["Total stock-picks", len(hh)],
            ["Win rate (picks)", f"{round(100 * (hh['actual_ret'] > 0).mean())}%"],
            ["Median pick return", f"{hh['actual_ret'].median():+.1f}%"],
            ["Average pick return", f"{hh['actual_ret'].mean():+.1f}%"],
            ["Cycles beating Nifty", f"{beat_n}/{len(cyc)} ({beat_pct}%)"],
            ["Money diary (ref capital)", f"{rupees(capital)} -> Rs{round(bal):,.0f} ({bal/capital:.2f}x)"]],
            columns=["Overall (all history)", "Value"])
    else:
        overall = pd.DataFrame([["(no scored history yet)", ""]], columns=["Overall (all history)", "Value"])

    # ---- Portfolio: sector mix (weight % + holdings) and intentional cash ----
    secw = {}
    for s in w.index:
        secw[sector_of(s)] = secw.get(sector_of(s), 0.0) + float(w[s])
    sector_mix = pd.DataFrame(
        [[sec, f"{100 * exp * wt:.1f}%", sum(1 for x in w.index if sector_of(x) == sec)]
         for sec, wt in sorted(secw.items(), key=lambda kv: -kv[1])],
        columns=["Sector", "% of Capital", "Holdings"])
    sector_mix = pd.concat([sector_mix, pd.DataFrame([
        ["CASH (intentional)", f"{100 * (1 - exp):.1f}%", 0],
        ["TOTAL", "100.0%", f"{len(w)} stocks / {len(secw)} sectors"]],
        columns=sector_mix.columns)], ignore_index=True)

    # ===== ONE CLEAN TABLE PER SHEET (single header row) — required for Google Sheets / filters /
    # pivots / programmatic self-learning. No stacked blocks (which put headers mid-sheet). =====
    # Recommendations: clean actionable cols + compact factor scores, all in ONE wide table.
    wide_cols = ["Strength", "Score /100", "F: Historical", "F: Technical/Trend", "F: Risk/Vol",
                 "F: Sector", "F: Regime", "Stock", "Sector", "Current Price", "Buy Range",
                 "Expected Range (hist)", "Prob +ve", "Rec Confidence %", "Trend", "RSI",
                 "Recommended Holding", "Review Date", "Allocation Rs", "Shares", "Weight %",
                 "Why This vs Alternatives", "Why"]
    recs_wide = live[[c for c in wide_cols if c in live.columns]] if not live.empty else live
    # Dashboard: all KPIs + backtest stats as ONE Field|Value table (each source is already 2-col).
    def _kv(df, sep):
        d = df.copy(); d.columns = ["Field", "Value"]
        head = pd.DataFrame([[f"— {sep} —", ""]], columns=["Field", "Value"])
        return pd.concat([head, d], ignore_index=True)
    dashboard_tbl = pd.concat([_kv(exec_block, "TODAY"), _kv(overall, "BACKTEST (ALL HISTORY)"),
                               _kv(statistics, "CYCLE STATISTICS")], ignore_index=True)
    # About: methodology + evidence as ONE Topic|Detail table.
    meth = methodology.copy(); meth.columns = ["Topic", "Detail"]
    about_one = pd.concat([pd.DataFrame([["— METHODOLOGY —", ""]], columns=["Topic", "Detail"]), meth,
                           pd.DataFrame([["— ABOUT / EVIDENCE —", ""]], columns=["Topic", "Detail"]),
                           about_full], ignore_index=True)

    # ===== TODAY — one-glance summary page (the single at-a-glance addition) =====
    top_pick = live.iloc[0] if not live.empty else None              # already sorted best-first
    weak_pick = live.sort_values("Score /100").iloc[0] if not live.empty else None
    try:
        from india.scorecard import load_scored, headline, rolling_12m
        _sr = load_scored(); _h = headline(_sr) if not _sr.empty else {}
        _r12 = rolling_12m(_sr) if not _sr.empty else {}
    except Exception:
        _h, _r12 = {}, {}
    chg_new, chg_removed, chg_rot = [], [], []
    try:
        from india.recommendation_db import load_db, daily_diff
        _db = load_db()
        if not _db.empty:
            _last = sorted(_db["recommended_date"].astype(str).unique())[-1]
            _prev = set(_db[_db["recommended_date"].astype(str) == _last]["symbol"])
            chg_new = sorted(set(live["Stock"]) - _prev); chg_removed = sorted(_prev - set(live["Stock"]))
    except Exception:
        pass
    pconf = min(96, round(50 + beat_pct * 0.5 + (10 if G["pf_grade"] == "A" else 0)))
    today_summary = pd.DataFrame([
        ["Date", str(run_date)],
        ["Market regime", f"{regime}  ·  deploy {exp:.0%}  ·  cash {1-exp:.0%}"],
        ["Risk profile", profile_label], ["Holdings", len(w)],
        ["Buy-rated", int((live["Strength"].isin(["STRONG BUY", "BUY"])).sum()) if not live.empty else 0],
        ["Recommended holding", f"{rec_label} ({months} months)"], ["Review date", str(review)],
        ["Highest conviction", f"{top_pick['Stock']} (score {top_pick['Score /100']})" if top_pick is not None else "—"],
        ["Weakest holding", f"{weak_pick['Stock']} (score {weak_pick['Score /100']})" if weak_pick is not None else "—"],
        ["New today", ", ".join(chg_new) or "—"], ["Removed today", ", ".join(chg_removed) or "—"],
        ["Recommendation changes", len(chg_new) + len(chg_removed)],
        ["Portfolio confidence", f"{pconf}%"],
        ["Track record (win rate)", f"{_h.get('win_rate', '—')}%  ·  median {_h.get('median_ret', '—')}%"],
        ["Rolling 12M win rate", f"{_r12.get('win_rate', '—')}%"],
        ["Note", "One-glance summary. Historical evidence, NOT a forecast. Selection experimental."]],
        columns=["TODAY", "Value"])

    sheets = [                                # each entry = ONE dataframe -> ONE header row, no stacking
        ("TODAY", [today_summary]),                    # one-glance summary (first thing you read)
        ("Dashboard", [dashboard_tbl]),                # KPIs + backtest stats (Field | Value)
        ("Today's Recommendations", [recs_wide]),      # clean wide decision table
        ("Backtest", [yearly]),                        # per-year money + win/return
        ("Trade Log", [detail]),                       # every backtested trade
        ("Holding Options", [horizon_menu]),           # dynamic horizon menu (1W-1Y)
        ("History", [strategy_replay]),                # compounded money diary per cycle
        ("Market", [sector_mix]),                      # sector allocation + cash
        ("About", [about_one]),                        # methodology + evidence
    ]
    out = REPORTS / "AEGIS_LATEST.xlsx"              # ONE live file, overwritten each run (no day-by-day clutter)

    def _write(path):
        with pd.ExcelWriter(path, engine="openpyxl") as xl:
            for name, blocks in sheets:
                row = 0
                for df in blocks:
                    d = df if (df is not None and not df.empty) else pd.DataFrame([["(none)"]])
                    d.to_excel(xl, sheet_name=name[:31], startrow=row, index=False)
                    row += len(d) + 2
    try:
        _write(out)
    except PermissionError:                          # workbook is open in Excel -> fallback, don't crash
        out = REPORTS / "AEGIS_LATEST_new.xlsx"
        _write(out)
        print(f"  (note: AEGIS_LATEST.xlsx was open/locked -> wrote {out.name}; close Excel & re-run to refresh)")

    try:
        from india.recommendation_registry import log_rec
        rdf, k = log_rec(closes, rets, asof, source="live", horizon=C["rebal"]); rdf.to_csv(REG, index=False)
    except Exception:
        k = 0
    print("  HISTORICAL EVIDENCE GATE: PORTFOLIO grade %s · STOCK-ALPHA grade %s" % (G["pf_grade"], G["al_grade"]))
    print(f"  PUBLISHED -> {out.relative_to(ROOT)}  ({len(sheets)} investor sheets · recommended horizon {rec_label})")
    print(f"  {len(w)} holdings · portfolio beat Nifty {beat_n}/{len(cyc)} ({beat_pct}%) in history · registry +{k}")


if __name__ == "__main__":
    main()
