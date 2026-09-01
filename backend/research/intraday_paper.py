"""India Intraday · Shadow Paper Portfolios (daily-OHLC proxy).

Same-day open→close paper P&L using existing daily OHLC bars. This is
the CHEAP path — no external fetches, degrades to no-op if bars are
missing. For real hourly intraday, see intraday_hourly.py.

Storage:
  reports/research/runner1_intraday/positions.json + history.jsonl
  reports/research/runner2_intraday/positions.json + history.jsonl

Shadow means: no user-facing recommendations, no orders, no risk-manager
engagement · measurement only.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.intraday_paper.v1.20260731"
ENGINE_ID = "aegis.research.intraday_paper.v1"

RUNNER1_ACTIVE_STRENGTHS = {"STRONG BUY", "BUY", "ACCUMULATE"}
RUNNER2_ACTIVE_ACTIONS = {"STRONG_BUY", "BUY"}


def _normalize_ticker(t: str) -> str:
    if not t:
        return ""
    t = t.strip()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if t.upper().endswith(suffix):
            return t[: -len(suffix)]
    return t


def _load_ticker_ohlc(root: Path, ticker: str) -> tuple[float | None, float | None]:
    try:
        import pandas as pd
    except ImportError:
        return None, None
    norm = _normalize_ticker(ticker)
    p = root / "data" / "raw" / "india" / f"{norm}_D1.parquet"
    if not p.exists():
        return None, None
    try:
        df = pd.read_parquet(p)
        if len(df) == 0:
            return None, None
        latest = df.iloc[-1]
        o = float(latest.get("open", 0) or 0)
        c = float(latest.get("close", 0) or 0)
        return (o or None), (c or None)
    except Exception:
        return None, None


def _snapshot(root: Path, runner_slug: str, picks: list[dict], as_of: str) -> dict:
    out_dir = root / "reports" / "research" / runner_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    positions: dict[str, dict] = {}
    n_opened = 0
    n_valid = 0
    for pick in picks:
        t = str(pick.get("ticker") or "").strip()
        if not t:
            continue
        o, c = _load_ticker_ohlc(root, t)
        if not o or not c:
            continue
        n_valid += 1
        positions[t] = {
            "ticker":              t,
            "first_seen_date":     as_of,
            "last_seen_date":      as_of,
            "entry_price":         o,
            "first_seen_price":    o,
            "last_seen_price":     c,
            "high_water_price":    c,
            "low_water_price":     c,
            "n_days_active":       1,
            "is_active":           False,
            "score_at_entry":      pick.get("score"),
        }
        n_opened += 1

    payload = {
        "engine":              ENGINE_ID,
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "runner":              runner_slug,
        "mode":                "intraday_shadow_daily_proxy",
        "as_of":               as_of,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "positions":           positions,
    }
    (out_dir / "positions.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    event = {
        "as_of":       as_of,
        "run_utc":     payload["run_utc"],
        "n_picks":     len(picks),
        "n_valid":     n_valid,
        "n_opened":    n_opened,
        "n_active":    0,
        "n_closed":    n_opened,
    }
    with (out_dir / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    return payload


def ingest_runner1_intraday_picks_for_date(root: Path,
                                              as_of: str | None = None) -> dict:
    as_of = as_of or date.today().isoformat()
    # CEO 2026-09-01 · R1 retirement · engine-level dormancy
    try:
        from backend.delivery.canonical.retirement import is_retired as _r1_is_retired
        if _r1_is_retired(root, "R1"):
            return _snapshot(root, "runner1_intraday", [], as_of)
    except Exception:
        pass
    src = root / "data" / "aegis_today.csv"
    picks: list[dict] = []
    if src.exists():
        try:
            import csv
            with src.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    strength = str(row.get("Strength") or row.get("strength") or "").strip().upper()
                    if strength in RUNNER1_ACTIVE_STRENGTHS:
                        tkr = row.get("Stock") or row.get("ticker") or row.get("symbol")
                        raw_score = row.get("Score /100") or row.get("score") or 0
                        try:
                            score = float(raw_score) if raw_score not in (None, "", "-") else None
                        except (TypeError, ValueError):
                            score = None
                        picks.append({"ticker": tkr, "score": score})
        except Exception:
            pass
    return _snapshot(root, "runner1_intraday", picks, as_of)


def ingest_runner2_intraday_picks_for_date(root: Path,
                                              as_of: str | None = None) -> dict:
    as_of = as_of or date.today().isoformat()
    src = root / "reports" / "recommendations.json"
    picks: list[dict] = []
    if src.exists():
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            recs = data.get("recommendations") or []
            for r in recs:
                inv = (r.get("investor_action") or {}).get("entry")
                pct = r.get("percentile_action")
                if inv == "BUY" or pct in RUNNER2_ACTIVE_ACTIONS:
                    picks.append({
                        "ticker":  r.get("ticker"),
                        "score":   r.get("composite_decision_score") or r.get("ensemble_score"),
                    })
        except Exception:
            pass
    return _snapshot(root, "runner2_intraday", picks, as_of)
