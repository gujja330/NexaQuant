# experiments/rc002_earnings_surprise.py
"""
RC002 — Program B (Earnings Intelligence), Sprint 1: post-earnings announcement drift (PEAD).

QUESTION: does an earnings surprise predict forward drift? Free-data version: no paid analyst estimates, so
the expectation is NAIVE — year-over-year same-quarter EPS. Surprise = this quarter's diluted EPS minus the
same quarter a year ago; the EVENT is the SEC filing (`filed` date = point-in-time public availability).

Reuses already-cached SEC CompanyFacts (Program A dataset) — no new ingestion. Quarterly EPS isolated by
period span (80-100 days) to avoid YTD/annual cumulation. Forward drift measured from the trading day on/after
the filing. IC = cross-sectional rank-corr of surprise vs drift within each calendar month; significance on
NON-overlapping months (the RC001.2 embargo discipline). Framework IC helpers imported from the LOCKED engine.

Run:  python -m experiments.rc002_earnings_surprise
"""
import sys, glob, warnings
from datetime import date, datetime
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
warnings.simplefilter("ignore")
from core.market_adapter import USAAdapter
from core.usa_fundamentals import RAW
from core.usa_research import summarize          # reuse locked-framework significance helper
from run_experiment import publish, confidence

HOLD = 42                                          # ~2-month drift window (trading days)


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def quarterly_eps(raw):
    """Point-in-time quarterly diluted EPS events: (end, filed, val). Span-filtered to 3-month periods."""
    facts = raw.get("facts", {}).get("us-gaap", {})
    node = facts.get("EarningsPerShareDiluted") or facts.get("EarningsPerShareBasic")
    if not node:
        return []
    units = node.get("units", {})
    series = units.get("USD/shares") or (next(iter(units.values())) if units else [])
    out = {}
    for it in series:
        if it.get("form") not in ("10-Q", "10-K") or "start" not in it or "filed" not in it:
            continue
        span = (_d(it["end"]) - _d(it["start"])).days
        if not (80 <= span <= 100):                # keep discrete quarter, drop YTD/annual
            continue
        k = it["end"]
        if k not in out or it["filed"] < out[k]["filed"]:   # earliest filing for that quarter (PIT)
            out[k] = {"end": it["end"], "filed": it["filed"], "val": float(it["val"])}
    return sorted(out.values(), key=lambda r: r["end"])


def build_events(symbols, closes):
    rows = []
    for s in symbols:
        f = RAW / f"{s}.json"
        if not f.exists() or s not in closes.columns:
            continue
        import json
        evs = quarterly_eps(json.loads(f.read_text()))
        by_end = {_d(e["end"]): e for e in evs}
        px = closes[s].dropna()
        for e in evs:
            end = _d(e["end"])
            prior = next((by_end[k] for k in by_end if abs((end - k).days - 365) <= 25), None)
            if not prior:
                continue
            surprise = e["val"] - prior["val"]                       # YoY EPS change (rank-standardized later)
            fdt = pd.Timestamp(e["filed"])
            if fdt < px.index[0] or fdt > px.index[-1]:              # PIT: filing must fall INSIDE price history
                continue                                            # (else searchsorted->0 mislabels old filings)
            pos = px.index.searchsorted(fdt)                         # first trading day on/after filing
            if pos >= len(px) - HOLD:
                continue
            if (px.index[pos] - fdt).days > 7:                       # no nearby trading day (data gap) -> skip
                continue
            fwd = float(px.iloc[pos + HOLD] / px.iloc[pos] - 1)
            rows.append({"symbol": s, "month": e["filed"][:7], "surprise": surprise, "fwd": fwd})
    return pd.DataFrame(rows)


def monthly_ic(df, months):
    out = []
    for m in months:
        g = df[df["month"] == m]
        if len(g) < 8:
            continue
        out.append(g["surprise"].rank().corr(g["fwd"].rank()))
    return pd.Series([x for x in out if pd.notna(x)], dtype=float)


def main():
    adp = USAAdapter()
    closes = adp.get_market_data()[0]
    covered = [Path(f).stem for f in glob.glob(str(RAW / "*.json")) if Path(f).stem != "cik_map"]
    df = build_events(covered, closes).dropna()
    months = sorted(df["month"].unique())
    full = summarize(monthly_ic(df, months))
    nonov = summarize(monthly_ic(df, months[::2]))                   # non-overlapping (~42d ~ 2 months)

    if not full:
        verdict, status = "INSUFFICIENT — too few earnings events with coverage", "not-promoted"
        ic = ir = n = None
    else:
        m_ic, _, n = full
        ir = nonov[1] if nonov else 0.0
        ic = m_ic
        promote = abs(m_ic) > 0.03 and nonov and abs(nonov[1]) > 2.0
        status = "investigate" if (abs(m_ic) > 0.03 and (not nonov or abs(nonov[1]) <= 2.0)) else ("promoted" if promote else "not-promoted")
        verdict = ("PROMISING" if promote else ("directional lead, underpowered" if abs(m_ic) > 0.03 else "no signal"))

    print("=" * 68)
    print("  RC002 — EARNINGS SURPRISE / PEAD (naive YoY expectation, PIT filings)")
    print("=" * 68)
    print(f"  events: {len(df)} · names: {df['symbol'].nunique()} · months: {len(months)} · drift {HOLD}d")
    if full:
        print(f"  monthly IC {full[0]:+.3f} (IR {full[1]:+.2f}, {full[2]} months)")
        if nonov:
            print(f"  non-overlap IC {nonov[0]:+.3f} (IR {nonov[1]:+.2f}, {nonov[2]} months)  <- significance read")
    print(f"  VERDICT: {verdict}")

    md = f"""# RC002 — Earnings Surprise / PEAD (Program B, Sprint 1)

**Status:** CLOSED · **Verdict:** {verdict} · **Date:** {date.today()} · **Script:** `experiments/rc002_earnings_surprise.py`

## Question
Does a naive YoY earnings surprise (this quarter's diluted EPS vs the same quarter last year) predict
post-filing drift? Event = SEC `filed` date (PIT). Free data: no analyst estimates → naive expectation.

## Method
Cached SEC CompanyFacts (Program A dataset, no new ingestion). Quarterly EPS span-filtered to 3-month
periods. Surprise rank-standardized. Forward drift = {HOLD}d return from the trading day on/after filing.
Cross-sectional rank-IC per calendar month; significance on NON-overlapping months (embargo discipline).

## Result
- events {len(df)} · names {df['symbol'].nunique()} · months {len(months)}
- monthly IC {f'{full[0]:+.3f} (IR {full[1]:+.2f}, n={full[2]})' if full else 'insufficient'}
- non-overlap IC {f'{nonov[0]:+.3f} (IR {nonov[1]:+.2f}, n={nonov[2]})' if nonov else 'insufficient'}

## Verdict
{verdict}. {'Naive YoY surprise carries no reliable drift signal on current coverage' if status=='not-promoted' else 'Directional lead; insufficient power to promote'} (74-name SEC overlap, ~2y).
Honest scope: naive expectation is weaker than analyst-estimate surprise; a null is "no evidence with this
proxy/power", not "PEAD is dead." Next in Program B: RC003 guidance, RC004 revisions.
"""
    # leaderboard uses the NON-overlap figures (the significance read) so IC/IR/N/confidence are consistent
    ic_row = nonov[0] if nonov else (full[0] if full else None)
    ir_row = nonov[1] if nonov else 0.0
    n_row = nonov[2] if nonov else 0
    row = {"market": "USA", "program": "B-Earnings", "cycle": "RC002",
           "factor_or_experiment": "earnings_surprise_yoy", "scope": f"PEAD {HOLD}d",
           "IC": f"{ic_row:.3f}" if ic_row is not None else "", "IC_IR": f"{ir_row:.2f}",
           "lift": "", "n": n_row, "status": status, "confidence": confidence(ir_row, n_row),
           "date": str(date.today()), "notes": verdict + "; naive YoY expectation; PIT filed-date events"}
    publish(program="B-Earnings", report_slug="RC002_earnings_surprise", report_md=md, rows=[row])


if __name__ == "__main__":
    main()
