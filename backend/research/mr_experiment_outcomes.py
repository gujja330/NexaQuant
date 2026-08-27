"""AEGIS · Sprint M-R · Per-experiment outcomes ledger.

CEO handover 2026-08-27:
> "Make the daily scorer automatically append forward outcomes to E1/E2/E3."

For each focused experiment, walks every dated shadow.jsonl and joins
each fired row against the corresponding walk-forward scored outcomes
(fwd_5d + fwd_10d matured). Appends the joined result to:

   reports/research/experiments/{experiment_id}/outcomes.jsonl

The file is REWRITTEN on each daemon cycle · but each row is stable so
it's effectively append-only. Zero mutation of shadow.jsonl or scored
JSONL sources. Zero production changes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.research.mr_runner import ALLOWED_WRITE_ROOT
from backend.research.mr_experiment_runner import FOCUSED_EXPERIMENTS

ENGINE_ID = "aegis.mr_experiment_outcomes.v0.1"


def _scored_lookup(root: Path) -> dict:
    """Build {(snap_date, market, ticker) → {5d: row, 10d: row, ...}}."""
    wf_dir = root / ALLOWED_WRITE_ROOT / "walkforward"
    if not wf_dir.exists(): return {}
    out: dict = {}
    for d_dir in sorted(wf_dir.iterdir()):
        if not d_dir.is_dir(): continue
        snap = d_dir.name
        for horizon in ("1d","3d","5d","10d","20d"):
            for market in ("india","usa"):
                fp = d_dir / f"{market}_scored_fwd{horizon}.jsonl"
                if not fp.exists(): continue
                for ln in fp.read_text(encoding="utf-8").splitlines():
                    if not ln.strip(): continue
                    try: r = json.loads(ln)
                    except Exception: continue
                    tk = str(r.get("ticker","")).upper()
                    if not tk: continue
                    key = (snap, market.upper(), tk)
                    out.setdefault(key, {})[horizon] = r
    return out


def _shadow_iter(root: Path, experiment_id: str):
    exp_dir = root / ALLOWED_WRITE_ROOT / "experiments" / experiment_id
    if not exp_dir.exists(): return
    for d_dir in sorted(exp_dir.iterdir()):
        if not d_dir.is_dir(): continue
        for fp in sorted(d_dir.glob("shadow*.jsonl")):
            for ln in fp.read_text(encoding="utf-8").splitlines():
                if not ln.strip(): continue
                try: yield json.loads(ln)
                except Exception: continue


def build_experiment_outcomes(root: Path, experiment_id: str,
                              scored: dict) -> list:
    out = []
    for r in _shadow_iter(root, experiment_id):
        if not r.get("rule_fired"): continue
        snap = str(r.get("iso") or "")
        market = str(r.get("market","")).upper()
        ticker = str(r.get("ticker","")).upper()
        key = (snap, market, ticker)
        horizons = scored.get(key, {})
        row = {
            "iso":              snap,
            "experiment_id":    experiment_id,
            "market":           market,
            "ticker":           ticker,
            "runner":           r.get("runner"),
            "shadow_decision":  r.get("shadow_decision"),
            "reason":           r.get("reason"),
        }
        for horizon in ("1d","3d","5d","10d","20d"):
            sc = horizons.get(horizon) or {}
            if sc:
                row[f"fwd_{horizon}_pct"]   = sc.get(f"fwd_{horizon.replace('d','')}d_pct") or sc.get(f"fwd_{horizon}_pct")
                row[f"mfe_{horizon}_pct"]   = sc.get(f"mfe_pct_h{horizon}")
                row[f"mae_{horizon}_pct"]   = sc.get(f"mae_pct_h{horizon}")
                row[f"stop_hit_{horizon}"]  = sc.get(f"stop_hit_within_h{horizon}")
                row[f"outcome_{horizon}"]   = sc.get("outcome_label")
                row[f"sector_{horizon}"]    = sc.get("sector")
                row[f"cap_{horizon}"]       = sc.get("cap_bucket")
            else:
                row[f"fwd_{horizon}_pct"] = None
        out.append(row)
    return out


def emit_outcomes(root: Path, experiment_id: str, rows: list) -> Path:
    dst_dir = root / ALLOWED_WRITE_ROOT / "experiments" / experiment_id
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "outcomes.jsonl"
    with dst.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    return dst


def run_all(root: Path) -> dict:
    scored = _scored_lookup(root)
    results = []
    for exp_id in FOCUSED_EXPERIMENTS:
        rows = build_experiment_outcomes(root, exp_id, scored)
        dst = emit_outcomes(root, exp_id, rows)
        n_matured = sum(1 for r in rows if r.get("fwd_5d_pct") is not None)
        results.append({
            "experiment_id":  exp_id,
            "n_fired":        len(rows),
            "n_matured_5d":   n_matured,
            "output":         str(dst.relative_to(root)),
        })
    return {
        "engine":       ENGINE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scored_keys":  len(scored),
        "results":      results,
    }


def render_console(res: dict):
    print(f"\n======== EXPERIMENT OUTCOMES · scored_keys={res['scored_keys']} ========")
    for r in res["results"]:
        short = r["experiment_id"].replace("aegis_mr_experiment_20260827_","")
        print(f"  [{short:35s}] fired={r['n_fired']:>4d}  "
              f"matured_5d={r['n_matured_5d']:>4d}  -> {r['output']}")


if __name__ == "__main__":
    root = Path(".").resolve()
    res = run_all(root)
    render_console(res)
    print(f"\n[experiment_outcomes] APPEND-ONLY per-experiment ledger written")
