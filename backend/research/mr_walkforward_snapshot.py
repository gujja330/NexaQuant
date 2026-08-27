"""AEGIS · M-R2 · Walk-Forward Snapshot Harness · Sprint M.

Captures today's canonical predictions (from
reports/context/portfolio_canonical_{market}.json) into an IMMUTABLE
snapshot under reports/research/walkforward/{YYYY-MM-DD}/{market}.jsonl.

Purpose: build a FORWARD-CAPTURED corpus of predictions whose outcome
will be measurable at +1/+3/+5/+10/+20 trading days from now · without
retroactively touching aegis_history.

A second run mode `--score` reads the snapshot from N days ago and joins
against today's parquet close to compute realized fwd_N returns. This is
the walk-forward evaluator per M-R contract.

Under M-R sandbox rules. Writes only under reports/research/walkforward/.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_walkforward_snapshot.v0.1"


def _canonical_source(root: Path, market: str) -> Path:
    return root / "reports" / "context" / f"portfolio_canonical_{market.lower()}.json"


def snapshot(root: Path, market: str, target_date: Optional[str] = None) -> tuple:
    src = _canonical_source(root, market)
    if not src.exists():
        return (0, None, "CANONICAL_MISSING")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        return (0, None, f"CANONICAL_UNREADABLE:{e}")

    iso = target_date or date.today().isoformat()
    dst_dir = root / ALLOWED_WRITE_ROOT / "walkforward" / iso
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{market.lower()}.jsonl"

    rows = data.get("positions") or data.get("investment_active") or []
    if isinstance(rows, dict):
        rows = list(rows.values())

    n = 0
    with dst.open("w", encoding="utf-8") as f:
        for r in rows:
            if not isinstance(r, dict): continue
            snap = {
                "snapshot_date":    iso,
                "market":           market.upper(),
                "engine":           ENGINE_ID,
                "experiment_id":    EXPERIMENT_ID,
                "ticker":           str(r.get("ticker","")).upper()
                                    .replace(".NS","").replace(".BO",""),
                "runner":           r.get("runner") or r.get("run_type"),
                "status":           r.get("status"),
                "rank":             r.get("rank"),
                "confidence_pct":   r.get("confidence_pct") or r.get("confidence"),
                "investability_band": r.get("investability_band") or r.get("band"),
                "entry_price":      r.get("entry_price") or r.get("recommended_entry"),
                "stop_price":       r.get("stop_price") or r.get("stop_loss"),
                "sector":           r.get("sector"),
                "recommended_date": r.get("recommended_date") or r.get("recommended"),
                "raw_keys":         sorted(r.keys()),
            }
            if not snap["ticker"]: continue
            f.write(json.dumps(snap, default=str, ensure_ascii=False) + "\n")
            n += 1
    return (n, dst, "OK")


def _parquet_close(root: Path, ticker: str, market: str, iso: str) -> Optional[float]:
    import pandas as pd
    clean = ticker.upper().replace(".NS","").replace(".BO","")
    base = "usa/data/raw/us" if market.lower()=="usa" else "data/raw/india"
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        if iso in df.index: return float(df.loc[iso, col])
        earlier = [d for d in df.index if d <= iso]
        if not earlier: return None
        return float(df.loc[sorted(earlier)[-1], col])
    except Exception: return None


def _fwd_close(root: Path, ticker: str, market: str, snap_iso: str,
               horizon: int) -> Optional[float]:
    import pandas as pd
    clean = ticker.upper().replace(".NS","").replace(".BO","")
    base = "usa/data/raw/us" if market.lower()=="usa" else "data/raw/india"
    p = root / base / f"{clean}_D1.parquet"
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else "Close"
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        dates = sorted(df.index)
        if snap_iso in df.index:
            i = dates.index(snap_iso)
        else:
            earlier = [d for d in dates if d <= snap_iso]
            if not earlier: return None
            i = dates.index(earlier[-1])
        fi = i + horizon
        if fi >= len(dates): return None
        return float(df.loc[dates[fi], col])
    except Exception: return None


def score(root: Path, market: str, snap_iso: str, horizon: int = 5) -> tuple:
    """Read snapshot from `snap_iso` and score at +horizon days."""
    src = root / ALLOWED_WRITE_ROOT / "walkforward" / snap_iso / f"{market.lower()}.jsonl"
    if not src.exists(): return (0, None, "NO_SNAPSHOT")
    rows = [json.loads(ln) for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    scored = []
    for r in rows:
        tk = r["ticker"]
        entry_close = _parquet_close(root, tk, market, snap_iso)
        fwd_close = _fwd_close(root, tk, market, snap_iso, horizon)
        if entry_close is None or fwd_close is None or entry_close <= 0:
            continue
        ret_pct = round((fwd_close - entry_close) / entry_close * 100, 3)
        r_out = dict(r)
        r_out[f"entry_close_at_snapshot"] = entry_close
        r_out[f"fwd_{horizon}d_close"] = fwd_close
        r_out[f"fwd_{horizon}d_pct"] = ret_pct
        r_out["scored_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        scored.append(r_out)
    if not scored: return (0, None, "NO_ELIGIBLE_TICKERS")
    dst = root / ALLOWED_WRITE_ROOT / "walkforward" / snap_iso / \
          f"{market.lower()}_scored_fwd{horizon}d.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for r in scored:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    return (len(scored), dst, "OK")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    ap.add_argument("--snapshot", action="store_true", help="capture today's canonical")
    ap.add_argument("--score", type=str, default=None,
                    help="score snapshot from YYYY-MM-DD")
    ap.add_argument("--horizon", type=int, default=5)
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        if args.snapshot:
            n, dst, status = snapshot(root, m)
            print(f"[wf:snapshot:{m}] rows={n} status={status} -> "
                  f"{dst.name if dst else 'none'}")
        if args.score:
            n, dst, status = score(root, m, args.score, args.horizon)
            print(f"[wf:score:{m}:{args.score}:+{args.horizon}d] rows={n} "
                  f"status={status} -> {dst.name if dst else 'none'}")
