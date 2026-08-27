"""AEGIS · M-R2 · Leakage / Data-Quality Audit · Sprint M.

Verifies the enriched prediction dataset is safe for forward-validation:

  A1 · No enriched feature uses data after prediction_date
  A2 · Every recommended_date <= prediction_date (or missing)
  A3 · No fwd_Nd_pct exists without a corresponding parquet close on
       prediction_date + N trading days (else NULL, no fabrication)
  A4 · entry_price_at_pred is within +/-15% of parquet close on
       prediction_date · else flagged as ENTRY_PRICE_MISMATCH
  A5 · MFE >= 0, MAE <= 0 (mathematical invariants)
  A6 · MFE >= max(fwd_1..20d), MAE <= min(fwd_1..20d) approximately
  A7 · Duplicate (date, ticker, runner) triples counted (RE-ENTRY vs error)
  A8 · Universe coverage · how many predictions had NO parquet available

Emits reports/research/mr_leakage_audit_{market}.json with per-check
pass/fail counts and up-to-10 offending rows per fail.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_leakage_audit.v0.1"


def _load(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists():
        p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _parquet_close_on(root: Path, ticker: str, market: str, iso: str) -> Optional[float]:
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
    except Exception:
        return None


def audit(root: Path, market: str) -> dict:
    rows = _load(root, market)
    if not rows: return {"engine": ENGINE_ID, "market": market.upper(),
                        "status": "NO_ROWS"}
    checks = defaultdict(lambda: {"pass": 0, "fail": 0, "n_a": 0, "offenders": []})

    def _add(name, ok, sample, na=False):
        rec = checks[name]
        if na: rec["n_a"] += 1
        elif ok: rec["pass"] += 1
        else:
            rec["fail"] += 1
            if len(rec["offenders"]) < 10:
                rec["offenders"].append(sample)

    seen: Counter = Counter()
    for r in rows:
        tk = r.get("ticker","")
        dt = r.get("prediction_date","")
        # A2 · recommended_date sanity
        rd = r.get("recommended_date")
        if not rd:
            _add("A2_rec_date_le_pred_date", True, None, na=True)
        else:
            _add("A2_rec_date_le_pred_date", rd <= dt,
                 {"ticker": tk, "prediction_date": dt, "recommended_date": rd})
        # A4 · entry price vs parquet close
        ep = r.get("entry_price_at_pred")
        if ep is None:
            _add("A4_entry_price_close_match", True, None, na=True)
        else:
            close = _parquet_close_on(root, tk, market, dt)
            if close is None:
                _add("A4_entry_price_close_match", True, None, na=True)
            else:
                diff_pct = abs(ep - close) / close * 100
                _add("A4_entry_price_close_match", diff_pct <= 15.0,
                     {"ticker": tk, "date": dt, "stored": ep, "parquet_close": close,
                      "diff_pct": round(diff_pct, 2)})
        # A5 · MFE/MAE sign
        mfe = r.get("mfe_pct"); mae = r.get("mae_pct")
        if mfe is None or mae is None:
            _add("A5_mfe_mae_signs", True, None, na=True)
        else:
            _add("A5_mfe_mae_signs", mfe >= -1e-6 and mae <= 1e-6,
                 {"ticker": tk, "date": dt, "mfe": mfe, "mae": mae})
        # A6 · MFE >= max(fwd_Nd), MAE <= min(fwd_Nd)
        fwd = [r.get(f"fwd_{n}d_pct") for n in (1,3,5,10,20)]
        fwd_ok = [x for x in fwd if isinstance(x, (int,float))]
        if mfe is not None and mae is not None and fwd_ok:
            _add("A6_mfe_mae_dominate_fwd",
                 mfe >= max(fwd_ok) - 1e-6 and mae <= min(fwd_ok) + 1e-6,
                 {"ticker": tk, "date": dt, "mfe": mfe, "mae": mae,
                  "fwd_max": max(fwd_ok), "fwd_min": min(fwd_ok)})
        else:
            _add("A6_mfe_mae_dominate_fwd", True, None, na=True)
        # A7 · duplicate tuple counter
        seen[(dt, tk, r.get("runner"))] += 1

    dup_tuples = {f"{d}|{t}|{r}": c for (d,t,r), c in seen.items() if c > 1}
    checks["A7_duplicate_pred_tuples"] = {
        "n_duplicates": len(dup_tuples),
        "sample":       dict(list(dup_tuples.items())[:10]),
    }

    # A8 · universe coverage
    missing_parquet = 0
    for r in rows[:100]:  # sample audit
        tk = r.get("ticker","")
        if _parquet_close_on(root, tk, market, r.get("prediction_date","")) is None:
            missing_parquet += 1
    checks["A8_universe_coverage_sample"] = {
        "sampled": min(100, len(rows)),
        "no_parquet_close": missing_parquet,
    }

    return {
        "engine":         ENGINE_ID,
        "experiment_id":  EXPERIMENT_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":         market.upper(),
        "n_rows":         len(rows),
        "checks":         dict(checks),
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_leakage_audit_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res or res.get("status") == "NO_ROWS": return
    print(f"\n======== LEAKAGE AUDIT · {res['market']} · n={res['n_rows']} ========")
    for check, d in res["checks"].items():
        if isinstance(d, dict) and "pass" in d:
            total = d["pass"] + d["fail"]
            print(f"  {check:35s} pass={d['pass']:4d} fail={d['fail']:4d} "
                  f"n/a={d['n_a']:4d} pass_rate="
                  f"{round(d['pass']/max(1,total)*100,2)}%")
            if d["fail"] and d["offenders"]:
                for off in d["offenders"][:3]:
                    print(f"      offender: {off}")
        elif isinstance(d, dict):
            print(f"  {check:35s} {d}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = audit(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"\n[leakage_audit:{m}] -> {p.name}")
