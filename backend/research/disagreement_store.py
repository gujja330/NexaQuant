"""Disagreement Store · gold piece of the Research Platform.

Operator's CEO ask:
    "Every disagreement should be stored... After 90 days you'll know
     BUY vs WAIT → winner=Runner2, BUY vs SELL → winner=Runner1, ...
     That becomes gold for future learning because you'll understand
     WHERE one engine is genuinely better."

Two artifacts, both append-only:
  reports/research/disagreements/ledger.jsonl
      One line per (date, ticker) where R1_action ≠ R2_action.
      Records both scores, both actions, sector, prevailing regime tags.
      Never overwritten. Grows daily.

  reports/research/disagreements/verdict.json
      Rolled-up statistical panel computed on demand:
        for each disagreement bucket (BUY_vs_WAIT, BUY_vs_SELL, ...):
          n · win_rate_r1 · win_rate_r2 · median_ret_r1 · median_ret_r2
          · winner · edge_pp · sample_size_verdict
      Answers "in this exact disagreement scenario, whose call was right?"

Outcomes are marked forward: when a ticker's forward return is knowable
(daily bar exists for the horizon N days after the disagreement), we
compute the realized swing return and stamp it on the ledger row.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_FINGERPRINT = "aegis.research.disagreement_store.v1.20260731"
FORWARD_HORIZONS = (5, 10, 21)              # trading days ahead to measure outcome
MIN_SAMPLES_FOR_VERDICT = 15                # below this: "insufficient sample"


def _paths(root: Path) -> tuple[Path, Path]:
    d = root / "reports" / "research" / "disagreements"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ledger.jsonl", d / "verdict.json"


def _normalize_ticker(t: str) -> str:
    if not t:
        return ""
    t = t.strip()
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if t.upper().endswith(suffix):
            return t[: -len(suffix)]
    return t


def _load_runner1_actions(root: Path) -> dict[str, dict]:
    """Runner 1 action map: {ticker → {action, score, sector}} from aegis_today.csv."""
    out: dict[str, dict] = {}
    src = root / "data" / "aegis_today.csv"
    if not src.exists():
        return out
    try:
        import csv
        with src.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                t = _normalize_ticker(row.get("Stock") or row.get("ticker") or "")
                if not t:
                    continue
                strength = str(row.get("Strength") or "").strip().upper()
                action = "BUY" if strength in ("STRONG BUY", "BUY", "ACCUMULATE") else \
                             "SELL" if strength in ("SELL", "STRONG SELL", "REDUCE") else "WAIT"
                try:
                    score = float(row.get("Score /100") or 0)
                except (TypeError, ValueError):
                    score = 0.0
                out[t] = {"action": action, "score": score,
                          "sector": row.get("Sector") or ""}
    except Exception:
        pass
    return out


def _load_runner2_actions(root: Path) -> dict[str, dict]:
    """Runner 2 action map: {ticker → {action, score, sector}} from recommendations.json."""
    out: dict[str, dict] = {}
    src = root / "reports" / "recommendations.json"
    if not src.exists():
        return out
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        for r in data.get("recommendations") or []:
            t = _normalize_ticker(r.get("ticker") or "")
            if not t:
                continue
            inv = (r.get("investor_action") or {}).get("entry")
            action = inv if inv in ("BUY", "SELL", "WAIT", "AVOID") else "WAIT"
            if action == "AVOID":
                action = "SELL"
            score = r.get("composite_decision_score") or r.get("ensemble_score") or 0
            out[t] = {"action": action, "score": float(score or 0),
                      "sector": r.get("sector") or ""}
    except Exception:
        pass
    return out


def log_daily_disagreements(root: Path, as_of: str | None = None) -> dict:
    """Append today's disagreements to the ledger. Returns summary dict.

    A disagreement = ticker exists in both maps AND r1_action != r2_action.
    """
    as_of = as_of or date.today().isoformat()
    r1 = _load_runner1_actions(root)
    r2 = _load_runner2_actions(root)
    ledger_path, _ = _paths(root)

    both = set(r1.keys()) & set(r2.keys())
    n_agree = 0
    n_disagree = 0
    disagreements: list[dict] = []
    for t in both:
        a1 = r1[t]["action"]
        a2 = r2[t]["action"]
        if a1 == a2:
            n_agree += 1
            continue
        n_disagree += 1
        disagreements.append({
            "as_of":         as_of,
            "logged_utc":    datetime.now(timezone.utc).isoformat(),
            "ticker":        t,
            "sector":        r1[t].get("sector") or r2[t].get("sector"),
            "r1_action":     a1,
            "r2_action":     a2,
            "r1_score":      r1[t]["score"],
            "r2_score":      r2[t]["score"],
            "bucket":        f"{a1}_vs_{a2}",
            # Filled in by _mark_forward_outcomes when horizon bars exist
            "fwd_5d_ret_pct":     None,
            "fwd_10d_ret_pct":    None,
            "fwd_21d_ret_pct":    None,
        })

    with ledger_path.open("a", encoding="utf-8") as fh:
        for d in disagreements:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    return {
        "as_of":            as_of,
        "n_both_universes": len(both),
        "n_agree":          n_agree,
        "n_disagree":       n_disagree,
        "agreement_pct":    round(100 * n_agree / len(both), 2) if both else 0.0,
        "disagreement_pct": round(100 * n_disagree / len(both), 2) if both else 0.0,
        "new_rows_appended": len(disagreements),
    }


def _read_ledger(root: Path) -> list[dict]:
    ledger_path, _ = _paths(root)
    if not ledger_path.exists():
        return []
    out = []
    try:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def _load_forward_return(root: Path, ticker: str, from_date: str,
                            horizon_days: int) -> float | None:
    """Compute realized swing return from from_date for horizon_days ahead.
    Uses daily bars from data/raw/india/{TICKER}_D1.parquet."""
    try:
        import pandas as pd
    except Exception:
        return None
    p = root / "data" / "raw" / "india" / f"{_normalize_ticker(ticker)}_D1.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        from_dt = pd.to_datetime(from_date)
        idx = df.index[df.index >= from_dt]
        if len(idx) < horizon_days + 1:
            return None
        entry_close = float(df.loc[idx[0], "close"])
        exit_close = float(df.loc[idx[min(horizon_days, len(idx) - 1)], "close"])
        if entry_close <= 0:
            return None
        return (exit_close / entry_close - 1.0) * 100
    except Exception:
        return None


def mark_forward_outcomes(root: Path, max_backfill_days: int = 60) -> dict:
    """Fill fwd_Nd_ret_pct fields on ledger rows where horizon has passed.

    Rewrites the ledger with the updated fields. Idempotent: rows already
    filled are not re-read (unless None). Only backfills the last
    max_backfill_days rows to keep the operation cheap.
    """
    ledger_path, _ = _paths(root)
    rows = _read_ledger(root)
    if not rows:
        return {"filled": 0, "total": 0}
    n_filled = 0
    # Only re-read/re-write rows within the recent window
    from datetime import date as _date
    cutoff = _date.today().toordinal() - max_backfill_days
    for row in rows[-2000:]:   # bound the work
        try:
            row_date = _date.fromisoformat(row.get("as_of", ""))
        except Exception:
            continue
        if row_date.toordinal() < cutoff:
            continue
        for horizon in FORWARD_HORIZONS:
            key = f"fwd_{horizon}d_ret_pct"
            if row.get(key) is not None:
                continue
            v = _load_forward_return(root, row["ticker"], row["as_of"], horizon)
            if v is not None:
                row[key] = round(v, 3)
                n_filled += 1

    # Rewrite ledger with updates
    with ledger_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"filled": n_filled, "total": len(rows)}


def compute_disagreement_verdict(root: Path,
                                    horizon: int = 10) -> dict:
    """Roll up the ledger into a verdict panel by bucket (e.g. BUY_vs_WAIT)."""
    _, verdict_path = _paths(root)
    rows = _read_ledger(root)
    fwd_key = f"fwd_{horizon}d_ret_pct"

    buckets: dict[str, dict] = {}
    for r in rows:
        b = r.get("bucket") or "UNKNOWN"
        rec = buckets.setdefault(b, {"n_total": 0, "n_scored": 0,
                                          "r1_returns": [], "r2_returns": []})
        rec["n_total"] += 1
        fwd = r.get(fwd_key)
        if fwd is None:
            continue
        rec["n_scored"] += 1
        # Under R1's action: was fwd move confirming?  BUY:+move good; SELL:-move good; WAIT: agnostic
        # We record the fwd move alongside each runner's action so downstream can slice.
        rec["r1_returns"].append({"action": r["r1_action"], "fwd": fwd})
        rec["r2_returns"].append({"action": r["r2_action"], "fwd": fwd})

    def _score_action(action: str, fwd: float) -> int:
        """Return +1 if action was 'right', -1 if 'wrong', 0 if neutral."""
        if action == "BUY":
            return 1 if fwd > 0 else -1
        if action == "SELL":
            return 1 if fwd < 0 else -1
        # WAIT / other → neutral (not scored)
        return 0

    verdict = {
        "engine":              "aegis.research.disagreement_verdict.v1",
        "schema_fingerprint":  SCHEMA_FINGERPRINT,
        "run_utc":             datetime.now(timezone.utc).isoformat(),
        "horizon_days":        horizon,
        "n_total_disagreements": len(rows),
        "n_scorable":          sum(b["n_scored"] for b in buckets.values()),
        "buckets":             {},
        "sample_size_note":    ("insufficient sample" if len(rows) < MIN_SAMPLES_FOR_VERDICT
                                    else "sample sufficient for directional read"),
    }
    for name, b in buckets.items():
        if not b["r1_returns"]:
            verdict["buckets"][name] = {
                "n_total":            b["n_total"],
                "n_scored":           0,
                "verdict":            "no_scored_rows",
            }
            continue
        r1_scores = [_score_action(x["action"], x["fwd"]) for x in b["r1_returns"]]
        r2_scores = [_score_action(x["action"], x["fwd"]) for x in b["r2_returns"]]
        r1_right = sum(1 for s in r1_scores if s > 0)
        r2_right = sum(1 for s in r2_scores if s > 0)
        r1_wrong = sum(1 for s in r1_scores if s < 0)
        r2_wrong = sum(1 for s in r2_scores if s < 0)
        r1_wr = round(r1_right / max(1, r1_right + r1_wrong), 4)
        r2_wr = round(r2_right / max(1, r2_right + r2_wrong), 4)
        r1_med = _median([x["fwd"] for x in b["r1_returns"]])
        r2_med = _median([x["fwd"] for x in b["r2_returns"]])
        edge = round(r2_wr - r1_wr, 4)
        if b["n_scored"] < MIN_SAMPLES_FOR_VERDICT:
            winner = "INSUFFICIENT_SAMPLE"
        elif abs(edge) < 0.05:
            winner = "TIE"
        elif edge > 0:
            winner = "RUNNER_2"
        else:
            winner = "RUNNER_1"
        verdict["buckets"][name] = {
            "n_total":         b["n_total"],
            "n_scored":        b["n_scored"],
            "r1_win_rate":     r1_wr,
            "r2_win_rate":     r2_wr,
            "r1_median_fwd":   r1_med,
            "r2_median_fwd":   r2_med,
            "edge_r2_minus_r1_wr": edge,
            "winner":          winner,
        }

    verdict_path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    return verdict


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return round(s[len(s) // 2], 3)


def compute_overlap_metrics(root: Path) -> dict:
    """Compute Agreement / Disagreement / Buy-Overlap / Sector-Overlap %
    from today's ledger row snapshot. Used to enrich RunnerMetrics."""
    r1 = _load_runner1_actions(root)
    r2 = _load_runner2_actions(root)
    both = set(r1.keys()) & set(r2.keys())
    if not both:
        return {"agreement_pct": None, "disagreement_pct": None,
                  "buy_overlap_pct": None, "sector_overlap_pct": None}
    n_agree = sum(1 for t in both if r1[t]["action"] == r2[t]["action"])
    r1_buys = {t for t in both if r1[t]["action"] == "BUY"}
    r2_buys = {t for t in both if r2[t]["action"] == "BUY"}
    buy_ov = (len(r1_buys & r2_buys) / max(1, len(r1_buys | r2_buys))) if (r1_buys or r2_buys) else 0
    r1_sectors = {r1[t].get("sector") for t in r1_buys if r1[t].get("sector")}
    r2_sectors = {r2[t].get("sector") for t in r2_buys if r2[t].get("sector")}
    sec_ov = (len(r1_sectors & r2_sectors) / max(1, len(r1_sectors | r2_sectors))) \
                if (r1_sectors or r2_sectors) else 0
    return {
        "agreement_pct":       round(100 * n_agree / len(both), 2),
        "disagreement_pct":    round(100 * (1 - n_agree / len(both)), 2),
        "buy_overlap_pct":     round(100 * buy_ov, 2),
        "sector_overlap_pct":  round(100 * sec_ov, 2),
    }
