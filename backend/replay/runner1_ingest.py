"""
Sprint 7.7 · Runner 1 (legacy adaptive_rec_v2 + india/recommendation_generator)
audit-trail ingest.

The legacy runner emits `data/aegis_recommendation_db.csv` — an append-only
ledger of every recommendation it has ever issued (real STRONG_BUY / BUY /
ACCUMULATE / WATCH calls, with entry/target/review/expiry/confidence/weight
fields). We ingest that ledger read-only into
`reports/recommendation_history_runner1.parquet` so the walk-forward and
Sprint 7.8 benchmark have Runner 1's institutional signal on the same
substrate as Runner 2's Rec v3 ledger.

Legacy code UNTOUCHED — this is a pure read + reshape.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


ACTION_MAP = {
    "STRONG BUY":  "STRONG_BUY",
    "BUY":         "BUY",
    "ACCUMULATE":  "BUY",       # institutional convention: ACCUMULATE == smaller BUY
    "WATCH":       "HOLD",
    "SELL":        "SELL",
    "STRONG SELL": "STRONG_SELL",
    "HOLD":        "HOLD",
}


def _safe_float(v: Any) -> Optional[float]:
    if v is None: return None
    try:
        f = float(v)
        if pd.isna(f): return None
        return f
    except (TypeError, ValueError):
        return None


def _norm_action(a: Optional[str]) -> str:
    if not a: return "HOLD"
    a = str(a).strip().upper()
    return ACTION_MAP.get(a, a.replace(" ", "_"))


def ingest_legacy_ledger(*, repo_root: Path, market: str = "india",
                            source_csv: Optional[Path] = None,
                            history_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Read the legacy audit trail and write it into the Sprint 7.5-style
    history parquet shape (one row per (market, asof) — where a single asof
    day may carry multiple ticker-level recommendations bundled in a
    JSON-encoded `recommendations` column).

    Non-invasive: writes to a NEW file `recommendation_history_runner1.parquet`
    (parallel to Rec v3's `recommendation_history.parquet`) so downstream
    tooling never confuses the two streams.
    """
    source_csv = source_csv or (repo_root / "data" / "aegis_recommendation_db.csv")
    history_path = history_path or (repo_root / "reports" / "recommendation_history_runner1.parquet")

    if not source_csv.exists():
        return {"status": "no-source", "source": str(source_csv), "rows_written": 0}

    df = pd.read_csv(source_csv)
    if df.empty:
        return {"status": "source-empty", "source": str(source_csv), "rows_written": 0}

    if "recommended_date" not in df.columns:
        return {"status": "schema-mismatch", "source": str(source_csv),
                  "reason": "no recommended_date column", "rows_written": 0}

    df["recommended_date"] = pd.to_datetime(df["recommended_date"], errors="coerce").dt.date
    df = df.dropna(subset=["recommended_date"])

    # Group by day → one history row per (market, asof)
    grouped: Dict[date, List[Dict[str, Any]]] = {}
    for _, r in df.iterrows():
        d = r["recommended_date"]
        rec_row = {
            "ticker":     str(r.get("symbol", "")),
            "action":     _norm_action(r.get("action")),
            "action_raw": str(r.get("action", "")),
            "sector":     str(r.get("sector", "")),
            "score":      _safe_float(r.get("score")),
            "confidence": (lambda c: c / 100.0 if c is not None and c > 1 else c)(_safe_float(r.get("confidence"))),
            "regime_adjusted_confidence": (lambda c: c / 100.0 if c is not None and c > 1 else c)(_safe_float(r.get("confidence"))),
            "ensemble_score": _safe_float(r.get("score")),
            "entry":      _safe_float(r.get("entry")),
            "target":     _safe_float(r.get("target")),
            "horizon":    str(r.get("horizon", "")),
            "review_date":  str(r.get("review_date", "")),
            "expiry_date":  str(r.get("expiry_date", "")),
            "weight":     _safe_float(r.get("weight")),
            "status":     str(r.get("status", "")),
        }
        grouped.setdefault(d, []).append(rec_row)

    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history_rows: List[Dict[str, Any]] = []
    for d, recs in sorted(grouped.items()):
        dist = {"STRONG_BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG_SELL": 0}
        for r in recs:
            dist[r["action"]] = dist.get(r["action"], 0) + 1
        history_rows.append({
            "engine": "adaptive_rec_v2.legacy",
            "version": "runner1",
            "market": market,
            "run_utc": now_utc,
            "asof": d.isoformat(),
            "currency": "INR" if market == "india" else "USD",
            "n_tickers": len(recs),
            "distribution": json.dumps(dist),
            "n_disagreement_collapsed": 0,
            "recommendations": json.dumps(recs),
            "notes": f"ingested from {source_csv.name}",
            "replay": False,
            "source": "runner1_audit_ledger",
            "history_schema_version": "1.0.0",
            "appended_utc": now_utc,
        })

    out_df = pd.DataFrame(history_rows)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    if history_path.exists():
        try:
            existing = pd.read_parquet(history_path)
            keep_mask = ~((existing["market"] == market) & (existing["asof"].isin(out_df["asof"])))
            combined = pd.concat([existing[keep_mask], out_df], ignore_index=True)
        except Exception:
            combined = out_df
    else:
        combined = out_df

    combined = combined.sort_values("asof", kind="stable").reset_index(drop=True)
    combined.to_parquet(history_path, index=False)

    action_totals = {"STRONG_BUY": 0, "BUY": 0, "HOLD": 0, "SELL": 0, "STRONG_SELL": 0}
    for row in history_rows:
        d = json.loads(row["distribution"])
        for k, v in d.items():
            action_totals[k] = action_totals.get(k, 0) + v

    return {
        "status": "ingested",
        "source": str(source_csv),
        "destination": str(history_path),
        "rows_written": len(history_rows),
        "unique_dates": len(grouped),
        "total_recommendations": int(sum(len(v) for v in grouped.values())),
        "action_totals": action_totals,
        "date_range": f"{min(grouped)}..{max(grouped)}" if grouped else None,
    }


def compute_runner1_outcomes(*, repo_root: Path, market: str = "india",
                                horizon_days: int = 20,
                                wall_clock: Optional[date] = None,
                                history_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    For every Runner 1 recommendation whose horizon has closed, compute the
    realized return from raw prices and append to `learning_corpus_runner1.parquet`.
    """
    from datetime import timedelta

    wall_clock = wall_clock or date.today()
    history_path = history_path or (repo_root / "reports" / "recommendation_history_runner1.parquet")
    corpus_path = repo_root / "reports" / "learning_corpus_runner1.parquet"
    raw_dir = (repo_root / "data" / "raw" / "india") if market == "india" \
                else (repo_root / "usa" / "data" / "raw" / "us")

    if not history_path.exists():
        return {"status": "no-history", "n_outcomes": 0}

    df = pd.read_parquet(history_path)
    if "market" in df.columns:
        df = df[df["market"] == market]

    outcomes: List[Dict[str, Any]] = []
    n_open = 0
    n_missing_price = 0

    for _, row in df.iterrows():
        rec_asof = pd.to_datetime(row["asof"]).date()
        close_asof = rec_asof + timedelta(days=horizon_days)
        if close_asof > wall_clock:
            n_open += 1
            continue

        recs_raw = row.get("recommendations")
        recs = json.loads(recs_raw) if isinstance(recs_raw, str) else (recs_raw or [])

        for r in recs:
            action = r.get("action")
            if action in (None, "HOLD"):
                continue
            ticker = r.get("ticker")
            if not ticker:
                continue

            price_file = raw_dir / f"{ticker}_D1.parquet"
            if not price_file.exists():
                n_missing_price += 1
                continue

            try:
                pdf = pd.read_parquet(price_file)
                if "close" not in pdf.columns:
                    n_missing_price += 1
                    continue
                idx = pdf.index
                if hasattr(idx, "date"):
                    pdf = pdf.assign(_d=idx.date)
                elif "time" in pdf.columns:
                    pdf = pdf.assign(_d=pd.to_datetime(pdf["time"]).dt.date)
                else:
                    continue
                # Entry: nearest trading day <= rec_asof (usually rec_asof itself)
                entry_pool = pdf[pdf["_d"] <= rec_asof]
                # Exit: nearest trading day >= close_asof (handles calendar-vs-trading-day gap)
                exit_pool  = pdf[pdf["_d"] >= close_asof]
                if entry_pool.empty or exit_pool.empty:
                    n_missing_price += 1
                    continue
                entry = float(entry_pool.iloc[-1]["close"])
                exit_ = float(exit_pool.iloc[0]["close"])
                if entry <= 0:
                    continue
                ret_pct = (exit_ - entry) / entry * 100.0
                if action in ("SELL", "STRONG_SELL"):
                    ret_pct = -ret_pct

                outcomes.append({
                    "market": market, "ticker": ticker,
                    "rec_asof": rec_asof.isoformat(),
                    "close_asof": close_asof.isoformat(),
                    "asof": rec_asof.isoformat(),
                    "action": action,
                    "entry_price": entry, "exit_price": exit_,
                    "return_pct": round(ret_pct, 4),
                    "is_winner": bool(ret_pct > 0),
                    "horizon_days": horizon_days,
                    "confidence": r.get("confidence"),
                    "score": r.get("score"),
                    "sector": r.get("sector"),
                    "regime_at_entry": row.get("regime"),
                    "runner": "runner1",
                })
            except Exception:
                continue

    # Append to Runner 1's dedicated learning corpus
    if outcomes:
        new_df = pd.DataFrame(outcomes)
        if corpus_path.exists():
            try:
                existing = pd.read_parquet(corpus_path)
                # Dedupe on (market, ticker, rec_asof) — most-recent wins
                key_new = new_df[["market", "ticker", "rec_asof"]].agg("|".join, axis=1)
                key_ex  = existing[["market", "ticker", "rec_asof"]].agg("|".join, axis=1) \
                    if all(c in existing.columns for c in ["market", "ticker", "rec_asof"]) \
                    else pd.Series([], dtype=str)
                keep = ~key_ex.isin(key_new)
                combined = pd.concat([existing[keep], new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df
        combined = combined.sort_values(["rec_asof", "ticker"], kind="stable").reset_index(drop=True)
        combined.to_parquet(corpus_path, index=False)

    return {
        "status": "computed",
        "n_outcomes": len(outcomes),
        "n_open_positions": n_open,
        "n_missing_price": n_missing_price,
        "horizon_days": horizon_days,
        "corpus_path": str(corpus_path),
    }
