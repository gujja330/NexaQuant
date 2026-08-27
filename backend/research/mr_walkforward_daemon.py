"""AEGIS · Sprint M2 · Automated Walk-Forward Daemon.

One-shot orchestrator meant to be scheduled daily (cron / CI / manual):

  1. Capture TODAY's canonical R1/R2 predictions into
     reports/research/walkforward/{TODAY}/{market}.jsonl
  2. Capture TODAY's Momentum universe into
     reports/research/walkforward/{TODAY}/momentum_{market}.jsonl
  3. Auto-score EVERY prior snapshot that has matured to N=1,3,5,10,20
     forward trading days · appending fwd_Nd_pct + entry/fwd close prices

Never modifies production. Writes only under reports/research/walkforward/.

Idempotent: running twice for the same day updates the same files.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT
from backend.research.mr_walkforward_snapshot import (
    snapshot as _canonical_snapshot,
    score as _score_snapshot,
)

ENGINE_ID = "aegis.mr_walkforward_daemon.v0.1"

HORIZONS = [1, 3, 5, 10, 20]


def _trading_days_between(iso_from: str, iso_to: str, market: str) -> Optional[int]:
    """Count trading days between two ISO dates using an index parquet."""
    import pandas as pd
    for name in (("data/raw/india/NSEI_D1.parquet",) if market.lower()=="india"
                 else ("usa/data/raw/us/_IDX_GSPC_D1.parquet",
                       "usa/data/raw/us/SPY_D1.parquet")):
        p = Path(name)
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            dates = sorted(df.index)
            after_from = [d for d in dates if d > iso_from and d <= iso_to]
            return len(after_from)
        except Exception:
            continue
    return None


def _momentum_source(root: Path, market: str) -> Optional[Path]:
    """Look for a Momentum universe emission that today's engine produces."""
    candidates = [
        root / "reports" / "research" / f"short_term_momentum_{market.lower()}.json",
        root / "reports" / f"momentum_universe_{market.lower()}.json",
        root / "reports" / "context" / f"momentum_{market.lower()}.json",
    ]
    for p in candidates:
        if p.exists(): return p
    return None


def _capture_momentum(root: Path, market: str, iso: str) -> tuple:
    src = _momentum_source(root, market)
    if src is None: return (0, None, "MOMENTUM_SOURCE_MISSING")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        return (0, None, f"MOMENTUM_UNREADABLE:{e}")
    rows = (data.get("watch") or []) + (data.get("emerging") or []) \
           + (data.get("candidates") or []) + (data.get("results") or [])
    if isinstance(data, list): rows = data
    dst_dir = root / ALLOWED_WRITE_ROOT / "walkforward" / iso
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"momentum_{market.lower()}.jsonl"
    n = 0
    with dst.open("w", encoding="utf-8") as f:
        for r in rows:
            if not isinstance(r, dict): continue
            tk = str(r.get("ticker","")).upper() \
                .replace(".NS","").replace(".BO","")
            if not tk: continue
            snap = {
                "snapshot_date":       iso,
                "market":              market.upper(),
                "engine":              ENGINE_ID,
                "experiment_id":       EXPERIMENT_ID,
                "runner":              "MOMENTUM",
                "ticker":              tk,
                "class":               r.get("class") or r.get("bucket") or r.get("status"),
                "score":               r.get("score") or r.get("momentum_score"),
                "source":              str(src.relative_to(root)),
            }
            f.write(json.dumps(snap, default=str, ensure_ascii=False) + "\n")
            n += 1
    return (n, dst, "OK")


def _score_matured(root: Path, market: str, today_iso: str) -> list:
    """For every prior snapshot in walkforward/, score it at any horizons
    it now qualifies for."""
    wf_dir = root / ALLOWED_WRITE_ROOT / "walkforward"
    if not wf_dir.exists(): return []
    scored_files = []
    for d_dir in sorted(wf_dir.iterdir()):
        if not d_dir.is_dir(): continue
        snap_iso = d_dir.name
        if snap_iso >= today_iso: continue
        elapsed = _trading_days_between(snap_iso, today_iso, market)
        if elapsed is None: continue
        for horizon in HORIZONS:
            if elapsed < horizon: continue
            # Score this snapshot at this horizon if not already scored
            expected = d_dir / f"{market.lower()}_scored_fwd{horizon}d.jsonl"
            if expected.exists(): continue
            n, dst, status = _score_snapshot(root, market, snap_iso, horizon)
            scored_files.append({
                "snap_date":  snap_iso,
                "horizon":    horizon,
                "market":     market.upper(),
                "rows":       n,
                "status":     status,
                "output":     str(dst.relative_to(root)) if dst else None,
            })
    return scored_files


def run(root: Path, market: str) -> dict:
    iso = date.today().isoformat()
    result = {
        "engine":         ENGINE_ID,
        "experiment_id":  EXPERIMENT_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_date":       iso,
        "market":         market.upper(),
        "capture":        {},
        "momentum":       {},
        "scored":         [],
    }
    # 1. Capture today's canonical
    n_c, dst_c, status_c = _canonical_snapshot(root, market, iso)
    result["capture"] = {"rows": n_c, "status": status_c,
                         "output": str(dst_c.relative_to(root)) if dst_c else None}
    # 2. Capture today's momentum
    n_m, dst_m, status_m = _capture_momentum(root, market, iso)
    result["momentum"] = {"rows": n_m, "status": status_m,
                          "output": str(dst_m.relative_to(root)) if dst_m else None}
    # 3. Score every matured prior snapshot
    result["scored"] = _score_matured(root, market, iso)
    return result


def emit(root: Path, market: str, res: dict) -> Path:
    dst = root / ALLOWED_WRITE_ROOT / "walkforward" / \
          res["run_date"] / f"daemon_{market.lower()}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return dst


def render_console(res: dict):
    print(f"\n======== WALK-FORWARD DAEMON · {res['market']} · {res['run_date']} ========")
    print(f"  canonical capture: rows={res['capture']['rows']} status={res['capture']['status']}")
    print(f"  momentum  capture: rows={res['momentum']['rows']} status={res['momentum']['status']}")
    print(f"  matured snapshots scored: {len(res['scored'])}")
    for s in res["scored"][:10]:
        print(f"    {s['snap_date']} +{s['horizon']}d rows={s['rows']} status={s['status']}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = run(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"\n[wf_daemon:{m}] -> {p.name}")
