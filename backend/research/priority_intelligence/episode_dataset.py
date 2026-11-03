"""PIE · canonical episode dataset.

CEO 2026-11-03 · WHY THE REGISTRY AND NOT recommendation_history
----------------------------------------------------------------
recommendation_history looked like the obvious training source and is not
one. Measured: India's 15,792 recorded ticker-decisions are 100% HOLD, and
USA's are 100% HOLD except for 34 actionable calls on 4 dates. 68 of
India's 73 rows and 135 of USA's 139 were written by one replay batch on
2026-07-21, so the apparently dense Jan-Jul window contains no prospective
decisions at all.

The opportunity registry does contain real decisions - entries, closes and
exit reasons - keyed by `opportunity_id`, which is unique per EPISODE. That
distinction is not cosmetic: ZBRA and DDOG each hold two episodes in 2026,
and a ticker-keyed view of them is what let two closed positions sit in
CURRENT until I6 refused the workbook.

WHAT THIS MODULE GUARANTEES
---------------------------
- Episode identity. One row per opportunity_id, never per ticker.
- Two outcome families, never blended:
      registry_realized_*  what the system actually did (entry -> close)
      mtm_ret_{h}d_pct     fixed-horizon mark-to-market, matured or absent
- Point-in-time. Every return starts at the first bar AFTER the entry date,
  because a decision taken on `asof` cannot transact at that day's close.
  Horizons that have not matured are absent, never zero.
- Explicit coverage. Episodes without enough bars are kept and MARKED, so
  the denominator stays visible.
- Labelled evidence population, so R2 registry history can never be read
  as an R3 backtest, an R3 prospective observation or a PIE decision.
- Deterministic and idempotent: same registry + same bars -> same frame.

It reuses backend/research/r3_program/outcome_resolver.py for bar loading
and forward returns rather than restating either.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from backend.research import opportunity_registry as _oreg
from backend.research.r3_program import outcome_resolver as _res

#: Horizons PIE evaluates. 20d is the longest the directive asks for.
HORIZONS = (5, 10, 20)

#: Minimum bars after entry for an episode to be scoreable at all.
MIN_BARS_AFTER_ENTRY = 2

#: Evidence populations. Keeping these apart is a hard requirement - the
#: same ticker can appear in several of them with different meanings.
POP_R2_REGISTRY = "R2_REGISTRY"

SCHEMA_VERSION = "1.0.0"


def dataset_dir(root: Path) -> Path:
    return (Path(root) / "reports" / "research" / "priority_intelligence"
            / "historical_baseline")


def episodes_path(root: Path, market: str) -> Path:
    return dataset_dir(root) / ("episodes_%s.parquet" % str(market).lower())


def coverage_path(root: Path, market: str) -> Path:
    return dataset_dir(root) / ("coverage_%s.json" % str(market).lower())


def _latest_per_episode(root: Path, market: str) -> list:
    """One Opportunity per opportunity_id · the latest event wins.

    load_all already collapses to the latest event per id and groups by
    (market, runner, bare_ticker); we flatten those groups back out because
    PIE's unit is the episode, not the name.
    """
    mkt = str(market).lower()
    out = {}
    for opps in _oreg.load_all(Path(root)).values():
        for o in opps:
            if str(o.market).lower() != mkt or not o.opportunity_id:
                continue
            prior = out.get(o.opportunity_id)
            if prior is None or str(o.ts_utc) >= str(prior.ts_utc):
                out[o.opportunity_id] = o
    return [out[k] for k in sorted(out)]


def _entry_bar(df: Optional[pd.DataFrame], entry_date: str):
    """(timestamp, close) of the first bar strictly AFTER entry_date."""
    if df is None or not entry_date:
        return None, None
    w = df[df.index > pd.Timestamp(entry_date)]
    if w.empty:
        return None, None
    return w.index[0], float(w["close"].iloc[0])


def _realized(df: Optional[pd.DataFrame], entry_date: str,
              closed_date: str) -> tuple:
    """(pct, exit_ts, exit_px, resolved) from the entry bar to the close.

    This is what the system actually realized, measured on the same PIT
    convention as the horizons so the two are comparable. It is NOT a
    horizon return and is never mixed with one.
    """
    if df is None or not entry_date or not closed_date:
        return None, None, None, False
    _, entry_px = _entry_bar(df, entry_date)
    if not entry_px:
        return None, None, None, False
    w = df[df.index <= pd.Timestamp(closed_date)]
    w = w[w.index > pd.Timestamp(entry_date)]
    if w.empty:
        return None, None, None, False
    exit_ts, exit_px = w.index[-1], float(w["close"].iloc[-1])
    if not exit_px:
        return None, None, None, False
    return 100.0 * (exit_px - entry_px) / entry_px, exit_ts, exit_px, True


def build(root: Path, market: str) -> tuple[pd.DataFrame, dict]:
    """Build the canonical episode frame and its coverage report."""
    root = Path(root)
    mkt = str(market).lower()
    eps = _latest_per_episode(root, mkt)

    rows = []
    for o in eps:
        tk = _res._tkey(o.ticker)
        bars = _res._bars(root, mkt, tk)
        n_bars = 0 if bars is None else len(bars)
        entry_date = str(o.created_date or "")[:10]
        closed_date = str(o.closed_date or "")[:10]
        entry_ts, entry_px = _entry_bar(bars, entry_date)
        after = 0 if bars is None or not entry_date else int(
            (bars.index > pd.Timestamp(entry_date)).sum())

        excluded = None
        if bars is None:
            excluded = "NO_BARS"
        elif n_bars < MIN_BARS_AFTER_ENTRY:
            excluded = "INSUFFICIENT_HISTORY"
        elif entry_px is None:
            excluded = "NO_BAR_AFTER_ENTRY"

        row = {
            "evidence_population": POP_R2_REGISTRY,
            "schema_version": SCHEMA_VERSION,
            "market": mkt,
            "episode_id": o.opportunity_id,
            "ticker": tk,
            "runner": str(o.runner or ""),
            "status": str(o.status or ""),
            "is_closed": str(o.status or "").upper() == "CLOSED",
            "entry_date": entry_date or None,
            "entry_bar_date": None if entry_ts is None else str(entry_ts.date()),
            "entry_price": entry_px,
            "closed_date": closed_date or None,
            "closed_reason": str(o.closed_reason or "") or None,
            "initial_signal": str(o.initial_signal or "") or None,
            "initial_rank": o.initial_rank,
            "initial_score": o.initial_score,
            "last_seen_date": str(o.last_seen_date or "")[:10] or None,
            "registry_ts_utc": str(o.ts_utc or "") or None,
            "n_bars": n_bars,
            "n_bars_after_entry": after,
            "excluded_reason": excluded,
        }

        # realized · what actually happened
        r_pct, r_ts, r_px, r_ok = _realized(bars, entry_date, closed_date)
        row["registry_realized_pct"] = r_pct
        row["registry_realized_exit_date"] = None if r_ts is None else str(r_ts.date())
        row["registry_realized_exit_price"] = r_px
        row["registry_realized_resolved"] = r_ok

        # fixed-horizon mark-to-market · separate family
        for h in HORIZONS:
            pct, ok = _res.forward_return(bars, entry_date, h) if entry_date \
                else (None, False)
            row["mtm_ret_%dd_pct" % h] = pct
            row["mtm_ret_%dd_resolved" % h] = ok
        rows.append(row)

    cols = list(rows[0].keys()) if rows else []
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df = df.sort_values(["entry_date", "episode_id"], kind="stable",
                            na_position="last").reset_index(drop=True)

    cov = coverage(df, mkt)
    return df, cov


def coverage(df: pd.DataFrame, market: str) -> dict:
    """Counts a reader can check against the registry by hand."""
    n = len(df)
    dates = sorted({d for d in df["entry_date"].dropna()}) if n else []
    out = {
        "market": market,
        "schema_version": SCHEMA_VERSION,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "episodes": n,
        "tickers": int(df["ticker"].nunique()) if n else 0,
        "entry_dates": len(dates),
        "entry_date_min": dates[0] if dates else None,
        "entry_date_max": dates[-1] if dates else None,
        "closed": int(df["is_closed"].sum()) if n else 0,
        "open": int((~df["is_closed"]).sum()) if n else 0,
        "excluded": {},
        "effective_sample_note": (
            "The effective sample is %d entry DATES, not %d episodes. "
            "Episodes sharing an entry date are one market observation and "
            "must stay in the same fold." % (len(dates), n)),
    }
    if n:
        ex = df["excluded_reason"].dropna()
        out["excluded"] = {str(k): int(v) for k, v in ex.value_counts().items()}
        out["excluded_total"] = int(len(ex))
        out["registry_realized_resolved"] = int(df["registry_realized_resolved"].sum())
        for h in HORIZONS:
            c = "mtm_ret_%dd_resolved" % h
            out["mtm_%dd_resolved" % h] = int(df[c].sum())
            out["mtm_%dd_unresolved" % h] = int((~df[c]).sum())
        mon = {}
        for d in dates:
            mon[d[:7]] = mon.get(d[:7], 0) + 1
        out["entry_dates_by_month"] = dict(sorted(mon.items()))
    return out


def write(root: Path, market: str) -> dict:
    df, cov = build(root, market)
    d = dataset_dir(Path(root))
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(episodes_path(root, market), index=False)
    coverage_path(root, market).write_text(
        json.dumps(cov, indent=2, default=str), encoding="utf-8")
    return cov


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="india")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    markets = ("india", "usa") if a.market == "both" else (a.market,)
    for m in markets:
        cov = write(Path(a.root), m)
        print("  [pie] %-6s episodes=%-5d tickers=%-4d entry_dates=%-4d "
              "closed=%-4d excluded=%s"
              % (m, cov["episodes"], cov["tickers"], cov["entry_dates"],
                 cov["closed"], cov.get("excluded") or {}))
        print("        %s" % cov["effective_sample_note"])
        for h in HORIZONS:
            print("        mtm %2dd resolved=%-5d unresolved=%-5d"
                  % (h, cov.get("mtm_%dd_resolved" % h, 0),
                     cov.get("mtm_%dd_unresolved" % h, 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
