"""Institutional Memory · Recommendation Lifecycle Ledger.

Walks the daily archive and, for every (ticker, first_seen_date) pair,
builds a state-machine object: ACTIVE | EXITED | REMOVED | EXPIRED.
Joined against `reports/learning.parquet` for realized outcomes.

Rebuilt nightly. Deterministic (sorted iteration).

Output artefacts:
- reports/recommendation_lifecycle.parquet   — one row per recommendation
- reports/recommendation_lifecycle.json      — dashboard-consumable summary
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import archive as _archive


_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


# ── State machine
STATE_ACTIVE  = "ACTIVE"      # still in today's recommendation set
STATE_EXITED  = "EXITED"      # closed with a realized return (from learning.parquet)
STATE_REMOVED = "REMOVED"     # dropped from recs before any exit event
STATE_EXPIRED = "EXPIRED"     # past maximum_holding_days without exit


def _extract_from_bundle(day: str) -> dict:
    """Return {ticker: rec_snapshot} from the archived recommendations on `day`."""
    j = _archive.read_archive_bundle(day, "recommendations.json") or {}
    out: dict[str, dict] = {}
    for r in (j.get("recommendations") or []):
        t = r.get("ticker")
        if not t: continue
        ee = r.get("entry_exit") or {}
        out[str(t)] = {
            "ticker": t,
            "action": r.get("recommendation"),
            "confidence": r.get("confidence"),
            "score": r.get("composite_decision_score"),
            "target_1": ee.get("target_1"),
            "target_2": ee.get("target_2"),
            "stop_loss": ee.get("stop_loss"),
            "buy_high": ee.get("ideal_entry_high"),
            "entry_price": ee.get("latest_close"),
            "expected_holding_days": ee.get("expected_holding_days"),
            "maximum_holding_days":  ee.get("maximum_holding_days"),
            "sector": r.get("sector"),
        }
    return out


def _intel_from_bundle(day: str) -> dict:
    j = _archive.read_archive_bundle(day, "investment_intelligence.json") or {}
    out: dict[str, float] = {}
    for r in (j.get("reports") or []):
        t = r.get("ticker")
        if not t: continue
        out[str(t)] = r.get("intelligence_score")
    return out


def _price_from_bundle(day: str) -> dict:
    j = _archive.read_archive_bundle(day, "price_context.json") or {}
    return j.get("tickers") or {}


def build_lifecycle(lookback_days: int | None = None) -> pd.DataFrame:
    """Walk the archive chronologically and produce the lifecycle DataFrame."""
    days = _archive.list_archive_days()
    if lookback_days is not None:
        days = days[-lookback_days:]

    # First-seen index: {ticker → first_seen_date}
    # For each ticker also track the LAST snapshot we saw of it (rolling)
    first_seen: dict[str, str] = {}
    first_snap: dict[str, dict] = {}     # snapshot on first-seen day
    last_snap:  dict[str, dict] = {}     # most-recent snapshot
    last_intel: dict[str, float] = {}
    last_day_seen: dict[str, str] = {}   # last archive day the ticker appeared
    first_price: dict[str, float] = {}   # first-day CMP from price_context

    for day in days:
        snap = _extract_from_bundle(day)
        intel = _intel_from_bundle(day)
        prices = _price_from_bundle(day)

        for t, s in snap.items():
            last_snap[t] = s
            last_intel[t] = intel.get(t)
            last_day_seen[t] = day
            if t not in first_seen:
                first_seen[t] = day
                first_snap[t] = dict(s)
                first_snap[t]["_first_intel"] = intel.get(t)
                pc = prices.get(t) or {}
                first_price[t] = pc.get("cmp") if pc.get("available") else s.get("entry_price")

    # Learning.parquet gives us realized outcomes for closed trades
    learning_p = REPORTS / "learning.parquet"
    closed_by_ticker: dict[str, list[dict]] = {}
    if learning_p.exists():
        try:
            lf = pd.read_parquet(learning_p)
            for ticker, rows in lf.groupby("ticker"):
                closed_by_ticker[str(ticker)] = rows.to_dict(orient="records")
        except Exception:
            pass

    latest_day = days[-1] if days else None
    today_set = set(_extract_from_bundle(latest_day).keys()) if latest_day else set()

    rows: list[dict] = []
    for t in sorted(first_seen.keys()):
        fs = first_snap[t]
        ls = last_snap.get(t, fs)
        # Days active = calendar days from first-seen to last-day-seen (inclusive)
        try:
            f_dt = pd.to_datetime(first_seen[t])
            l_dt = pd.to_datetime(last_day_seen.get(t, first_seen[t]))
            days_active = int((l_dt - f_dt).days) + 1
        except Exception:
            days_active = None

        # State determination
        closed_rows = closed_by_ticker.get(t, [])
        state = STATE_ACTIVE if t in today_set else STATE_REMOVED
        realized = mfe = mae = holding = None
        exit_date = exit_price = exit_reason = None
        target_hit = stop_hit = None
        alpha_capture = None
        if closed_rows:
            # Take the most recent closed trade whose entry falls at/after first-seen
            f_dt = pd.to_datetime(first_seen[t])
            candidates = []
            for rr in closed_rows:
                try:
                    ed = pd.to_datetime(rr.get("entry_date"))
                    if ed >= f_dt - pd.Timedelta(days=3):    # small tolerance
                        candidates.append(rr)
                except Exception:
                    continue
            if candidates:
                latest = sorted(candidates, key=lambda r: str(r.get("exit_date") or ""))[-1]
                realized = latest.get("return_pct")
                # learning.parquet stores percent (e.g. 6.17), normalize to fraction
                if realized is not None and abs(realized) > 1.5:
                    realized = realized / 100.0
                mfe = latest.get("mfe_pct")
                mae = latest.get("mae_pct")
                if mfe is not None and abs(mfe) > 1.5: mfe = mfe / 100.0
                if mae is not None and abs(mae) > 1.5: mae = mae / 100.0
                holding = latest.get("n_bars_held")
                exit_date  = latest.get("exit_date")
                exit_reason = latest.get("exit_reason") or ("winner" if latest.get("is_winner") else "loser")
                state = STATE_EXITED
                # Expected return from first-day snapshot
                if fs.get("target_1") and first_price.get(t):
                    exp_ret = (fs["target_1"] - first_price[t]) / first_price[t]
                    if exp_ret and realized is not None:
                        alpha_capture = round(realized / exp_ret, 3)
                # Target/stop hits
                if fs.get("target_1") and mfe is not None:
                    target_hit = (first_price.get(t) or 0) * (1 + (mfe or 0)) >= fs["target_1"]
                if fs.get("stop_loss") and mae is not None:
                    stop_hit = (first_price.get(t) or 0) * (1 + (mae or 0)) <= fs["stop_loss"]

        # Expired: still ACTIVE / REMOVED but exceeded max hold days without exit
        if state != STATE_EXITED and fs.get("maximum_holding_days") and days_active is not None:
            if days_active > fs["maximum_holding_days"]:
                state = STATE_EXPIRED

        rows.append({
            "ticker":                t,
            "first_seen_date":       first_seen[t],
            "first_action":          fs.get("action"),
            "first_confidence":      fs.get("confidence"),
            "first_intel":           fs.get("_first_intel"),
            "first_target":          fs.get("target_1"),
            "first_stop":            fs.get("stop_loss"),
            "first_entry_price":     first_price.get(t),
            "sector":                fs.get("sector"),
            "current_action":        ls.get("action") if t in today_set else None,
            "current_intel":         last_intel.get(t) if t in today_set else None,
            "days_active":           days_active,
            "state":                 state,
            "exit_date":             exit_date,
            "exit_price":            exit_price,
            "exit_reason":           exit_reason,
            "realized_return":       realized,
            "mfe":                   mfe,
            "mae":                   mae,
            "holding_days":          holding,
            "target_hit":            target_hit,
            "stop_hit":              stop_hit,
            "predicted_hold_days":   fs.get("expected_holding_days"),
            "max_hold_days":         fs.get("maximum_holding_days"),
            "alpha_capture":         alpha_capture,
        })

    df = pd.DataFrame(rows)
    # Deterministic sort: exited winners first (best alpha_capture), then active,
    # then by first_seen_date
    if not df.empty:
        df = df.sort_values(["state", "first_seen_date", "ticker"],
                              kind="mergesort").reset_index(drop=True)
    return df


def build_summary(df: pd.DataFrame) -> dict:
    """Dashboard-consumable summary. All aggregations are deterministic.

    Also emits a per-ticker slice under `by_ticker` — deliberately narrow
    (only the fields the dashboard needs) so the JSON stays small even
    with 200+ tickers.
    """
    if df is None or df.empty:
        return {"n_total": 0, "empty": True, "by_ticker": {}}

    by_state = df["state"].value_counts().to_dict()
    exited = df[df["state"] == STATE_EXITED]
    winners = exited[(exited["realized_return"].notna()) & (exited["realized_return"] > 0)]
    losers  = exited[(exited["realized_return"].notna()) & (exited["realized_return"] < 0)]

    alpha_cap = exited["alpha_capture"].dropna() if "alpha_capture" in exited.columns else pd.Series(dtype=float)

    # Per-ticker mini-slice for the dashboard
    by_ticker: dict[str, dict] = {}
    for _, row in df.iterrows():
        t = str(row["ticker"])
        by_ticker[t] = {
            "first_seen_date": row.get("first_seen_date"),
            "days_active":     int(row["days_active"]) if pd.notna(row.get("days_active")) else None,
            "state":           row.get("state"),
            "realized_return": None if pd.isna(row.get("realized_return")) else float(row["realized_return"]),
            "alpha_capture":   None if pd.isna(row.get("alpha_capture"))   else float(row["alpha_capture"]),
        }

    return {
        "n_total":         int(len(df)),
        "by_state":        {k: int(v) for k, v in sorted(by_state.items())},
        "n_active":        int(by_state.get(STATE_ACTIVE, 0)),
        "n_exited":        int(len(exited)),
        "n_winners":       int(len(winners)),
        "n_losers":        int(len(losers)),
        "win_rate":        round(len(winners) / len(exited), 4) if len(exited) else None,
        "avg_realized":    round(float(exited["realized_return"].mean()), 4) if len(exited) else None,
        "median_realized": round(float(exited["realized_return"].median()), 4) if len(exited) else None,
        "avg_alpha_capture":    round(float(alpha_cap.mean()), 3)   if len(alpha_cap) else None,
        "median_alpha_capture": round(float(alpha_cap.median()), 3) if len(alpha_cap) else None,
        "coverage": {
            "n_days_archived":  len(_archive.list_archive_days()),
            "first_day":        _archive.list_archive_days()[0]  if _archive.list_archive_days() else None,
            "last_day":         _archive.list_archive_days()[-1] if _archive.list_archive_days() else None,
        },
        "by_ticker": by_ticker,
    }
