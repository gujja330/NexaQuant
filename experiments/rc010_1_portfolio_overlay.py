# experiments/rc010_1_portfolio_overlay.py
"""
RC010.1 — is the regime overlay a production-quality PORTFOLIO RISK overlay (not just index timing)?

RC010 tested the overlay on the S&P index. This tests it where it would actually live: on top of a USA
stock PORTFOLIO (equal-weight of the universe, rebalanced daily), using the market regime (SPX+VIX) to scale
exposure. Judge it as RISK MANAGEMENT — Sortino, Ulcer index, max time-underwater, MaxDD — not as alpha.
Also breaks the effect down BY REGIME STATE (Strong/Neutral/Weak) so we know WHEN it helps (RC010.2/.3/.4).

Reuses the LOCKED `core.engine.regime_exposure`. Survivorship note: the base portfolio is current-universe
(inflates absolute return) but the overlay's INCREMENTAL effect is what we measure, and that largely cancels.

Run:  python -m experiments.rc010_1_portfolio_overlay
"""
import sys, warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
warnings.simplefilter("ignore")
from core.engine import regime_exposure
from core.market_adapter import USAAdapter
from run_experiment import publish, confidence

RAW_USA = ROOT / "data" / "raw" / "usa"


def risk_metrics(r):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / 252 or 1
    dd = eq / eq.cummax() - 1
    downside = r[r < 0].std()
    underwater = (dd < 0).astype(int)
    # longest consecutive underwater run (days)
    mx = cur = 0
    for u in underwater.values:
        cur = cur + 1 if u else 0
        mx = max(mx, cur)
    return dict(
        cagr=eq.iloc[-1] ** (1 / yrs) - 1,
        sharpe=(r.mean() / (r.std() + 1e-12)) * np.sqrt(252),
        sortino=(r.mean() / (downside + 1e-12)) * np.sqrt(252),
        maxdd=dd.min(),
        ulcer=np.sqrt((dd * 100).pow(2).mean()),
        underwater_days=mx,
    )


def main():
    adp = USAAdapter()
    closes = adp.get_market_data()[0]
    rets = closes.pct_change()
    breadth = rets.notna().sum(axis=1)
    rets = rets[breadth >= 30]                      # equal-weight portfolio needs real breadth
    port = rets.mean(axis=1)                          # daily equal-weight USA portfolio return
    idx = pd.read_parquet(RAW_USA / "SPX_D1.parquet")["close"].sort_index()
    vix = pd.read_parquet(RAW_USA / "USVIX_D1.parquet")["close"].sort_index()
    idx = idx.reindex(port.index).ffill(); vix = vix.reindex(port.index).ffill()

    exp = np.ones(len(idx)); labels = []
    for i in range(len(idx)):
        if i < 200:
            labels.append("Strong"); continue
        e, lab = regime_exposure(idx.iloc[:i + 1], vix.iloc[:i + 1])
        exp[i] = e; labels.append(lab)
    exp = pd.Series(exp, index=port.index)
    lab = pd.Series(labels, index=port.index)
    pos = exp.shift(1).fillna(1.0)                    # lag -> no look-ahead
    overlay = port * pos

    bh, ov = risk_metrics(port), risk_metrics(overlay)
    print("=" * 70)
    print("  RC010.1 — REGIME OVERLAY on the USA PORTFOLIO (risk-management view)")
    print("=" * 70)
    print(f"  period {port.index.min().date()}..{port.index.max().date()} · {len(port)} days (breadth>=30)")
    print(f"  {'metric':14}{'portfolio':>12}{'+overlay':>12}")
    for k in ("cagr", "sharpe", "sortino", "maxdd", "ulcer", "underwater_days"):
        f = (lambda x: f"{x*100:+.1f}%") if k in ("cagr", "maxdd") else (lambda x: f"{x:.2f}" if k != "underwater_days" else f"{int(x)}")
        print(f"  {k:14}{f(bh[k]):>12}{f(ov[k]):>12}")

    # RC010.2/.3/.4 — overlay effect by regime STATE (annualized mean portfolio return while in each state)
    print("\n  by regime state (annualized mean PORTFOLIO return + days):")
    for st in ("Strong", "Neutral", "Weak"):
        m = lab == st
        if m.sum():
            print(f"    {st:8} {port[m].mean()*252*100:+6.1f}%/yr   {int(m.sum()):>5} days   (overlay holds {exp[m].mean():.2f}x)")

    # verdict: production-quality risk overlay if it cuts Ulcer + MaxDD + extends Sortino w/o gutting CAGR
    # judge as RISK MANAGEMENT: improved downside (Sortino) + drawdown (MaxDD/Ulcer) is the bar; a small
    # CAGR give-up is the EXPECTED cost of a defensive tool, not a disqualifier.
    dd_better = ov["maxdd"] > bh["maxdd"] + 0.02
    ulcer_better = ov["ulcer"] < bh["ulcer"] * 0.9
    sortino_better = ov["sortino"] > bh["sortino"]
    cagr_gutted = ov["cagr"] < bh["cagr"] - 0.05      # only disqualify if CAGR is badly hurt
    if dd_better and ulcer_better and sortino_better and not cagr_gutted:
        status, verdict = "promoted", "production-quality cross-market DEFENSIVE risk overlay (MaxDD/Ulcer down, Sortino up; small CAGR give-up is the expected cost of a risk tool)"
    elif dd_better and ulcer_better:
        status, verdict = "investigate", "reduces portfolio risk but CAGR cost is large - characterize the trade-off"
    else:
        status, verdict = "not-promoted", "no portfolio-level risk benefit"
    score = 72 if status == "promoted" else (60 if status == "investigate" else 35)
    conf = f"{score} ({'High' if score>=70 else 'Medium' if score>=50 else 'Low'})"
    print(f"\n  VERDICT: {verdict}")

    md = f"""# RC010.1 — Regime overlay on the USA portfolio (risk-management view)

**Status:** {status} · **Date:** {date.today()} · **Script:** `experiments/rc010_1_portfolio_overlay.py`

Equal-weight USA portfolio (breadth>=30), regime overlay from SPX+VIX, lagged (no look-ahead). Judged as
RISK MANAGEMENT. Period {port.index.min().date()}..{port.index.max().date()}, {len(port)} days.

| Metric | Portfolio | +Overlay |
|---|--:|--:|
| CAGR | {bh['cagr']*100:+.1f}% | {ov['cagr']*100:+.1f}% |
| Sharpe | {bh['sharpe']:.2f} | {ov['sharpe']:.2f} |
| Sortino | {bh['sortino']:.2f} | {ov['sortino']:.2f} |
| MaxDD | {bh['maxdd']*100:+.1f}% | {ov['maxdd']*100:+.1f}% |
| Ulcer index | {bh['ulcer']:.2f} | {ov['ulcer']:.2f} |
| Max underwater (days) | {bh['underwater_days']} | {ov['underwater_days']} |

**By regime state** (RC010.2/.3/.4 — annualized mean portfolio return while in each):
{chr(10).join(f"- {st}: {port[lab==st].mean()*252*100:+.1f}%/yr over {int((lab==st).sum())} days (overlay holds {exp[lab==st].mean():.2f}x)" for st in ('Strong','Neutral','Weak') if (lab==st).sum())}

**Verdict:** {verdict}. The overlay de-risks in Neutral/Weak states; it helps iff those states carry low/
negative returns (defensive correctness) and hurts if they're false alarms in a bull.

**Next best experiment:** {"adopt as the standard risk overlay above the USA paper engine; forward-track" if status=='promoted' else "characterize CAGR-vs-drawdown trade-off; tune regime thresholds per market"}.
"""
    row = {"market": "USA", "program": "X-CrossMarket", "cycle": "RC010.1",
           "factor_or_experiment": "regime_overlay_portfolio", "scope": "portfolio risk overlay",
           "IC": "", "IC_IR": "", "lift": "pos" if dd_better else "neg", "n": len(port) // 252,
           "status": status, "confidence": conf, "date": str(date.today()),
           "notes": f"USA EW portfolio: MaxDD {bh['maxdd']*100:.0f}%->{ov['maxdd']*100:.0f}%, Ulcer {bh['ulcer']:.1f}->{ov['ulcer']:.1f}, Sortino {bh['sortino']:.2f}->{ov['sortino']:.2f}, CAGR {bh['cagr']*100:.1f}%->{ov['cagr']*100:.1f}%",
           "next_best_experiment": "adopt as risk overlay above USA engine + forward-track" if status == "promoted" else "tune thresholds; quantify CAGR-vs-DD trade-off"}
    publish(program="X-CrossMarket", report_slug="RC010_1_portfolio_overlay", report_md=md, rows=[row])


if __name__ == "__main__":
    main()
