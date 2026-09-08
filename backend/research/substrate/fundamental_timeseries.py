"""R3-E · FUNDAMENTAL TIME-SERIES SUBSTRATE · CEO 2026-09-08.

> "Don't only ask 'are the fundamentals good?' Ask: are they improving,
>  deteriorating, accelerating, decelerating, surprising, or diverging
>  from price?"

WHY THIS MODULE EXISTS
----------------------
The existing accumulator (`reports/research/fundamentals_history/`) holds
**2 dates** (2026-09-03..04) for 50 India / 102 USA tickers, and the
columns the programme most needs are 1% populated: `earnings_surprise`,
`analyst_rev_momentum`, `guidance_rev`, `altman_z`, `beneish_m` all have a
single non-null row out of 96. Fundamentals also move QUARTERLY, so two
consecutive DAYS contain no fundamental change at all.

On that substrate H2 (change) and H3 (surprise) are not merely weak - they
are uncomputable.

But quarterly statements ARE reachable: 5-7 periods of
financials / balance sheet / cash flow, plus an earnings calendar carrying
EPS estimate, reported EPS and surprise%. That makes all three hypotheses
testable, PROVIDED the point-in-time discipline is right.

THE PIT PROBLEM · AND HOW IT IS HANDLED
----------------------------------------
Statements are keyed by PERIOD END, not by filing date. A quarter ending
2026-06-30 was not public on 2026-07-01. Using it for a July prediction is
lookahead of the exact kind §18 forbids.

Two sources, two different treatments:

  earnings calendar   carries a real PUBLICATION date. Where a period has
                      one, that date is authoritative and the row is
                      marked `PIT_VERIFIED`.

  statements          have no filing date. A conservative publication lag
                      is ASSUMED (45 days, the India quarterly-results and
                      US 10-Q deadline) and the row is marked
                      `PIT_ASSUMED_LAG` - never `PIT_VERIFIED`, because an
                      assumption is not a fact.

Every value therefore carries `period_end`, `available_from`,
`pit_status`, `source` and `fetched_utc`. The accessor `as_of()` returns
ONLY periods whose `available_from` is on or before the query date. There
is no path in this module that can hand a model a figure the market had
not seen.

WHAT IT DOES NOT DO
-------------------
It computes no signal, fits no model and writes to no engine. It builds
the substrate that Waves 2E-2H will need and that does not exist today.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.fundamental_timeseries.v1"

# India quarterly-results deadline and US 10-Q deadline are both ~45 days.
# Deliberately conservative: too long delays a signal, too short invents one.
ASSUMED_PUBLICATION_LAG_DAYS = 45

PIT_VERIFIED = "PIT_VERIFIED"          # real publication date known
PIT_ASSUMED = "PIT_ASSUMED_LAG"        # period_end + assumed lag

# Line items pulled from the statements · names vary by provider, so each
# is a list of accepted aliases.
WANTED = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "total_debt": ["Total Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "total_equity": ["Stockholders Equity", "Total Equity Gross Minority Interest"],
    "operating_cashflow": ["Operating Cash Flow"],
    "free_cashflow": ["Free Cash Flow"],
    "capex": ["Capital Expenditure"],
}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _yq(sym: str, market: str) -> str:
    t = str(sym).upper().split(".", 1)[0]
    return f"{t}.NS" if market == "india" else t


def _pick(df, aliases, col):
    if df is None or col not in df.columns:
        return None
    for a in aliases:
        if a in df.index:
            v = _num(df.loc[a, col])
            if v is not None:
                return v
    return None


def fetch_ticker(sym: str, market: str) -> dict:
    """Quarterly statements + earnings calendar for one ticker."""
    import yfinance as yf
    yq = _yq(sym, market)
    out = {"ticker": str(sym).upper().split(".", 1)[0], "market": market,
           "query_symbol": yq,
           "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "periods": [], "earnings": []}
    try:
        t = yf.Ticker(yq)
        fin = getattr(t, "quarterly_financials", None)
        bal = getattr(t, "quarterly_balance_sheet", None)
        cfs = getattr(t, "quarterly_cashflow", None)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    # Earnings calendar FIRST · it supplies real publication dates.
    pub_by_quarter = {}
    try:
        ed = t.earnings_dates
        if ed is not None and len(ed):
            for idx, row in ed.iterrows():
                d = idx.date() if hasattr(idx, "date") else None
                if d is None:
                    continue
                rep = _num(row.get("Reported EPS"))
                out["earnings"].append({
                    "publication_date": d.isoformat(),
                    "eps_estimate": _num(row.get("EPS Estimate")),
                    "reported_eps": rep,
                    "surprise_pct": _num(row.get("Surprise(%)")),
                    "pit_status": PIT_VERIFIED,
                    "reported": rep is not None,
                })
                # A result published on date d reports the quarter that
                # ended shortly before it.
                pub_by_quarter[(d.year, (d.month - 1) // 3)] = d
    except Exception:
        pass

    cols = []
    for df in (fin, bal, cfs):
        if df is not None and hasattr(df, "columns"):
            cols += [c for c in df.columns]
    seen = set()
    for c in sorted(set(cols), reverse=True):
        pe = c.date() if hasattr(c, "date") else None
        if pe is None or pe in seen:
            continue
        seen.add(pe)
        rec = {"period_end": pe.isoformat()}
        for k, aliases in WANTED.items():
            rec[k] = (_pick(fin, aliases, c) or _pick(bal, aliases, c)
                      or _pick(cfs, aliases, c))
        # Publication date · real if the calendar has one shortly after
        # the period end, otherwise an explicit conservative assumption.
        pub = None
        for off in (0, 1):
            key = (pe.year + (1 if (pe.month - 1) // 3 + off > 3 else 0),
                   ((pe.month - 1) // 3 + off) % 4)
            if key in pub_by_quarter and pub_by_quarter[key] > pe:
                pub = pub_by_quarter[key]
                break
        if pub:
            rec["available_from"] = pub.isoformat()
            rec["pit_status"] = PIT_VERIFIED
        else:
            rec["available_from"] = (
                pe + timedelta(days=ASSUMED_PUBLICATION_LAG_DAYS)).isoformat()
            rec["pit_status"] = PIT_ASSUMED
        rec["source"] = "yfinance.quarterly_statements"
        out["periods"].append(rec)
    out["periods"].sort(key=lambda r: r["period_end"])
    return out


def available_from(p: dict, lag_days: int = ASSUMED_PUBLICATION_LAG_DAYS) -> str:
    """Publication date under a chosen assumed lag.

    A PIT_VERIFIED row has a real publication date and IGNORES the lag -
    a fact does not move because an assumption changed. Only rows resting
    on the assumption are re-dated, which is what makes 30/45/60-day
    sensitivity testing meaningful rather than cosmetic.
    """
    if p.get("pit_status") == PIT_VERIFIED:
        return str(p.get("available_from", "9999"))[:10]
    pe = date.fromisoformat(str(p["period_end"])[:10])
    return (pe + timedelta(days=lag_days)).isoformat()


def as_of(rec: dict, asof: str,
          lag_days: int = ASSUMED_PUBLICATION_LAG_DAYS) -> list:
    """Periods the market could actually have seen on `asof`.

    The single most important function here. Every consumer must go
    through it; nothing else may read `periods` directly.

    `lag_days` re-dates ONLY the assumed rows, so a finding can be
    stressed at 30/45/60 days. If it depends on which lag was chosen, it
    is not a finding.
    """
    d = str(asof)[:10]
    return [p for p in (rec.get("periods") or [])
            if available_from(p, lag_days) <= d]


def earnings_as_of(rec: dict, asof: str) -> list:
    d = str(asof)[:10]
    return [e for e in (rec.get("earnings") or [])
            if e.get("reported") and str(e["publication_date"])[:10] <= d]


def _growth(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur / abs(prev) - 1.0) * 100, 4)


def features_as_of(rec: dict, asof: str,
                   lag_days: int = ASSUMED_PUBLICATION_LAG_DAYS) -> dict:
    """H1 level · H2 trend/acceleration · H3 surprise · all PIT-gated."""
    ps = as_of(rec, asof, lag_days)
    out = {"assumed_lag_days": lag_days,
           "n_periods_available": len(ps),
           "pit_status": ("NONE" if not ps else
                          PIT_VERIFIED if all(p["pit_status"] == PIT_VERIFIED
                                              for p in ps) else PIT_ASSUMED)}
    if not ps:
        return out
    last = ps[-1]
    out["latest_period_end"] = last["period_end"]
    out["latest_available_from"] = last["available_from"]

    # ── H1 · LEVEL ──────────────────────────────────────────────────────
    rev, ni = last.get("revenue"), last.get("net_income")
    ocf, fcf = last.get("operating_cashflow"), last.get("free_cashflow")
    eq, debt = last.get("total_equity"), last.get("total_debt")
    out["h1_net_margin"] = (round(ni / rev * 100, 4)
                            if (ni is not None and rev) else None)
    out["h1_roe"] = (round(ni / eq * 100, 4)
                     if (ni is not None and eq) else None)
    out["h1_debt_to_equity"] = (round(debt / eq, 4)
                                if (debt is not None and eq) else None)
    # Earnings QUALITY · is profit turning into cash?
    out["h1_cfo_to_net_income"] = (round(ocf / ni, 4)
                                   if (ocf is not None and ni) else None)
    out["h1_fcf_to_net_income"] = (round(fcf / ni, 4)
                                   if (fcf is not None and ni) else None)

    # ── H2 · TREND and ACCELERATION ─────────────────────────────────────
    # A level says what the company is. A trend says where it is going.
    # Acceleration needs three periods and is the state the directive
    # singled out: +12/+15/+21 and +28/+20/+11 are both "growing".
    for key, label in (("revenue", "revenue"), ("net_income", "net_income"),
                       ("operating_cashflow", "ocf"),
                       ("free_cashflow", "fcf")):
        s = [p.get(key) for p in ps]
        g1 = _growth(s[-1], s[-2]) if len(s) >= 2 else None
        g2 = _growth(s[-2], s[-3]) if len(s) >= 3 else None
        yoy = _growth(s[-1], s[-5]) if len(s) >= 5 else None
        out[f"h2_{label}_qoq_pct"] = g1
        out[f"h2_{label}_yoy_pct"] = yoy
        out[f"h2_{label}_accel_pp"] = (round(g1 - g2, 4)
                                       if (g1 is not None and g2 is not None)
                                       else None)
    ms = []
    for p in ps[-4:]:
        r, n = p.get("revenue"), p.get("net_income")
        ms.append(n / r * 100 if (n is not None and r) else None)
    ms = [m for m in ms if m is not None]
    out["h2_margin_slope_pp"] = (round(ms[-1] - ms[0], 4)
                                 if len(ms) >= 2 else None)

    # ── H3 · SURPRISE ───────────────────────────────────────────────────
    es = earnings_as_of(rec, asof)
    if es:
        es.sort(key=lambda e: e["publication_date"])
        last_e = es[-1]
        out["h3_last_surprise_pct"] = last_e.get("surprise_pct")
        out["h3_days_since_earnings"] = (
            (date.fromisoformat(str(asof)[:10])
             - date.fromisoformat(last_e["publication_date"])).days)
        recent = [e["surprise_pct"] for e in es[-4:]
                  if e.get("surprise_pct") is not None]
        out["h3_surprise_mean_4q"] = (round(sum(recent) / len(recent), 4)
                                      if recent else None)
        out["h3_surprise_streak_positive"] = sum(
            1 for e in reversed(es)
            if (e.get("surprise_pct") or 0) > 0) if recent else None
        out["h3_n_earnings_available"] = len(es)
    return out


def cache_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "substrate"
            / f"fundamental_timeseries_{market}.json")


def build(root: Path, market: str, tickers: list, limit: int | None = None,
          verbose: bool = True) -> dict:
    """Resumable · already-fetched tickers are skipped."""
    p = cache_path(root, market)
    store = {}
    if p.exists():
        try:
            store = json.loads(p.read_text(encoding="utf-8")).get("tickers", {})
        except Exception:
            store = {}
    todo = [t for t in tickers if t not in store]
    if limit:
        todo = todo[:limit]
    for i, t in enumerate(todo, 1):
        store[t] = fetch_ticker(t, market)
        if verbose and i % 20 == 0:
            print(f"  [{i}/{len(todo)}] fetched")
            _write(root, market, store)
    return _write(root, market, store)


def _write(root: Path, market: str, store: dict) -> dict:
    n_per = sum(len(v.get("periods") or []) for v in store.values())
    n_earn = sum(len(v.get("earnings") or []) for v in store.values())
    with_3 = sum(1 for v in store.values() if len(v.get("periods") or []) >= 3)
    rep = {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assumed_publication_lag_days": ASSUMED_PUBLICATION_LAG_DAYS,
        "pit_note": (
            "statements carry PERIOD END only · publication is ASSUMED at "
            "period_end + lag unless the earnings calendar supplies a real "
            "date · as_of() is the only sanctioned accessor"),
        "n_tickers": len(store),
        "n_periods_total": n_per,
        "n_earnings_rows": n_earn,
        "tickers_with_3plus_periods": with_3,
        "h2_computable_pct": round(with_3 / max(1, len(store)) * 100, 1),
        "tickers": store,
    }
    p = cache_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return rep


def load(root: Path, market: str) -> Optional[dict]:
    p = cache_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="R3-E fundamental time series")
    ap.add_argument("--market", choices=["india", "usa"], required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    from backend.research.cohort.mr_dependency_v1 import load_cohort
    rows = load_cohort(root, a.market)
    tickers = sorted({str(r.get("ticker") or "").upper().split(".", 1)[0]
                      for r in rows} - {""})
    rep = build(root, a.market, tickers, a.limit)
    print(f"fundamental_ts:{a.market} · tickers {rep['n_tickers']} · periods "
          f"{rep['n_periods_total']} · earnings rows {rep['n_earnings_rows']} "
          f"· H2-computable {rep['h2_computable_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
