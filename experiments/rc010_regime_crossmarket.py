# experiments/rc010_regime_crossmarket.py
"""
RC010 — CROSS-MARKET validation of the ONLY research-validated AEGIS alpha: the India regime-timing overlay.
Question: does the same defensive overlay (de-risk when index < 200-DMA and/or VIX in its top quintile)
improve risk-adjusted returns on the USA index too? If yes, our strongest edge becomes GLOBAL — far more
valuable than any new dataset. No new data, no ingestion: reuse the LOCKED `core.engine.regime_exposure`
on deep USA history (^GSPC + ^VIX), with India as the reference baseline.

Method: at each day t compute the regime scale from data ≤ t, apply it to t+1's index return (lagged → no
look-ahead). Compare the regime-scaled equity curve vs buy-and-hold. Metrics: CAGR, vol, Sharpe, MaxDD.
Robustness: per-calendar-year consistency (in how many years did the overlay cut drawdown / lift Sharpe).

Run:  python -m experiments.rc010_regime_crossmarket
"""
import sys, warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
warnings.simplefilter("ignore")
from core.engine import regime_exposure        # LOCKED engine — reuse, don't rewrite
from run_experiment import publish

RAW_USA = ROOT / "data" / "raw" / "usa"


def regime_scaled(idx, vix):
    """Daily lagged regime exposure applied to index returns (faithful loop over regime_exposure)."""
    idx = idx.dropna()
    vix = vix.reindex(idx.index) if vix is not None else None
    exp = np.ones(len(idx))
    for i in range(200, len(idx)):
        exp[i], _ = regime_exposure(idx.iloc[:i + 1], None if vix is None else vix.iloc[:i + 1])
    ret = idx.pct_change().fillna(0.0).values
    pos = np.concatenate([[1.0], exp[:-1]])          # lag: yesterday's signal drives today's return
    return pd.Series(ret, index=idx.index), pd.Series(ret * pos, index=idx.index)


def metrics(r):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 252 or 1
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(252)
    sharpe = (r.mean() / (r.std() + 1e-12)) * np.sqrt(252)
    mdd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sharpe, mdd=mdd)


def run_market(name, idx, vix):
    bh, rg = regime_scaled(idx, vix)
    mb, mr = metrics(bh), metrics(rg)
    # per-year robustness: did the overlay lift Sharpe AND/OR cut drawdown?
    yrs = sorted(set(idx.index.year))[1:]
    sh_win = dd_win = tot = 0
    for y in yrs:
        m = idx.index.year == y
        if m.sum() < 60:
            continue
        a, b = metrics(bh[m]), metrics(rg[m]); tot += 1
        sh_win += b["sharpe"] >= a["sharpe"]
        dd_win += b["mdd"] >= a["mdd"]              # less negative = better
    print(f"\n  {name}:  buy&hold  Sharpe {mb['sharpe']:+.2f} CAGR {mb['cagr']*100:+.1f}% MaxDD {mb['mdd']*100:.0f}%")
    print(f"  {' '*len(name)}   regime    Sharpe {mr['sharpe']:+.2f} CAGR {mr['cagr']*100:+.1f}% MaxDD {mr['mdd']*100:.0f}%")
    print(f"  {' '*len(name)}   per-year: Sharpe-improved {sh_win}/{tot} · DD-improved {dd_win}/{tot}")
    return mb, mr, (sh_win, dd_win, tot)


def main():
    # USA index + VIX (deep history)
    spx = pd.read_parquet(RAW_USA / "SPX_D1.parquet")["close"].sort_index()
    vix = pd.read_parquet(RAW_USA / "USVIX_D1.parquet")["close"].sort_index()
    print("=" * 72)
    print("  RC010 — CROSS-MARKET regime overlay (India's validated edge, tested on USA)")
    print("=" * 72)
    print(f"  USA index history: {spx.index.min().date()}..{spx.index.max().date()} ({len(spx)} days)")
    umb, umr, (ush, udd, ut) = run_market("USA", spx, vix)

    # India reference (frozen production) — confirms the harness reproduces the known edge
    iref = ""
    try:
        from core.market_adapter import IndiaAdapter
        _, _, _, _, iidx, ivix, _ = IndiaAdapter().get_market_data()
        imb, imr, _ = run_market("INDIA(ref)", iidx.dropna(), ivix)
        iref = f"; India ref Sharpe {imb['sharpe']:+.2f}->{imr['sharpe']:+.2f}"
    except Exception as e:
        print(f"  (India reference skipped: {e})")

    # verdict on USA: does the overlay improve risk-adjusted return / drawdown, consistently?
    sharpe_up = umr["sharpe"] > umb["sharpe"] + 0.05
    dd_better = umr["mdd"] > umb["mdd"] + 0.02
    dd_consistent = ut and (udd / ut >= 0.6)            # drawdown protection robust across years?
    sharpe_consistent = ut and (ush / ut >= 0.5)        # net return benefit robust (not just crisis years)?
    if sharpe_up and dd_better and dd_consistent and sharpe_consistent:
        status, verdict = "promoted", "GENERALIZES unconditionally -> regime overlay is CROSS-MARKET (Global)"
    elif dd_better and dd_consistent:
        status, verdict = "investigate", ("CROSS-MARKET as a DEFENSIVE/crisis-protection overlay (robust "
                                          "drawdown reduction), but benefit is regime-conditional (drags in "
                                          "sustained bulls) -> not an unconditional alpha")
    else:
        status, verdict = "not-promoted", "does NOT generalize -> regime edge is India-specific"
    # confidence in the NET claim: high on DD-reduction, tempered by conditional/period-dependent benefit
    score = 60 if status == "investigate" else (round(100 * (udd / ut)) if (ut and status == "promoted") else 35)
    conf = f"{score} ({'High' if score>=70 else 'Medium' if score>=50 else 'Low'})"
    print(f"\n  VERDICT (USA): {verdict}")

    md = f"""# RC010 — Cross-market regime overlay (India's edge → USA)

**Status:** {status} · **Date:** {date.today()} · **Script:** `experiments/rc010_regime_crossmarket.py`

Tested the LOCKED `regime_exposure` (de-risk below 200-DMA and/or VIX top-quintile) on deep USA index
history vs buy-and-hold; India run as the reference baseline. Lagged signal, no look-ahead.

| Market | Sharpe (B&H → regime) | CAGR | MaxDD (B&H → regime) |
|---|---|---|---|
| USA | {umb['sharpe']:+.2f} → {umr['sharpe']:+.2f} | {umb['cagr']*100:+.1f}% → {umr['cagr']*100:+.1f}% | {umb['mdd']*100:.0f}% → {umr['mdd']*100:.0f}% |

Per-year robustness (USA): Sharpe-improved {ush}/{ut}, drawdown-improved {udd}/{ut}.{iref}

**Verdict:** {verdict}. A defensive timing overlay typically *trades return for much smaller drawdowns*
(lower exposure in bad regimes), so judge it on Sharpe + MaxDD, not raw CAGR.

**Next best experiment:** {"apply regime overlay to the USA paper portfolio (not just the index) and forward-track" if status!='not-promoted' else "regime is India-specific; focus USA on alternative-data domains"}.
"""
    row = {"market": "USA", "program": "X-CrossMarket", "cycle": "RC010",
           "factor_or_experiment": "regime_overlay", "scope": "index timing (deep history)",
           "IC": "", "IC_IR": "", "lift": "pos" if (sharpe_up or dd_better) else "neg",
           "n": ut, "status": status, "confidence": conf, "date": str(date.today()),
           "notes": f"USA Sharpe {umb['sharpe']:+.2f}->{umr['sharpe']:+.2f}, MaxDD {umb['mdd']*100:.0f}%->{umr['mdd']*100:.0f}%, DD-improved {udd}/{ut}yr{iref}",
           "next_best_experiment": "apply to USA paper portfolio + forward-track" if status != "not-promoted" else "regime is India-specific; pursue alt-data"}
    publish(program="X-CrossMarket", report_slug="RC010_regime_crossmarket", report_md=md, rows=[row])


if __name__ == "__main__":
    main()
