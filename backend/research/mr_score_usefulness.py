"""AEGIS · M-R2 · Score Usefulness Deep-Dive · Sprint M.

CEO handover 2026-08-27:
> "Don't let Urgency / Inv Quality / Investability become the research
>  conclusion. Test whether they actually predict forward return. If they
>  don't, remove/de-emphasize them."

For each score column stamped in AEGIS Daily, compute:

  - bucket distribution
  - fwd_5d / fwd_10d WR + avg by bucket
  - monotonicity: does higher score → higher WR?
  - KEEP / PRUNE verdict:
       KEEP           · WR spread >= 15pp AND monotonic
       KEEP_WARN      · WR spread >= 15pp but non-monotonic (works but not as expected)
       ANTI_SIGNAL    · monotonic in WRONG direction (high score → lower WR)
       PRUNE          · WR spread < 5pp (no predictive value)
       WEAK_KEEP      · 5-15pp spread

Scores audited: investability_band, confidence_pct, and any urgency /
inv_quality columns visible in AEGIS Daily. Emits verdicts per market.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_score_usefulness.v0.1"

WIN = 0.5


def _wr(rows: list, key: str = "fwd_5d_pct") -> Optional[float]:
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    if not vals: return None
    return round(sum(1 for v in vals if v > WIN)/len(vals)*100, 2)


def _avg(rows: list, key: str = "fwd_5d_pct") -> Optional[float]:
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    if not vals: return None
    return round(mean(vals), 3)


def _load(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists():
        p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _monotonicity(ordered_wrs: list) -> str:
    """Given WR values in order of ascending bucket, classify direction.

    Uses strict-direction test: n_up = strictly increasing pairs, n_dn =
    strictly decreasing, flat transitions ignored. A run is monotonic if
    it never reverses direction.
    """
    clean = [x for x in ordered_wrs if x is not None]
    if len(clean) < 3: return "UNDEFINED"
    n_up = sum(1 for i in range(1, len(clean)) if clean[i] > clean[i-1])
    n_dn = sum(1 for i in range(1, len(clean)) if clean[i] < clean[i-1])
    if n_up >= 1 and n_dn == 0: return "MONOTONIC_UP"
    if n_dn >= 1 and n_up == 0: return "MONOTONIC_DOWN"
    first_last_up = clean[-1] > clean[0]
    first_last_dn = clean[-1] < clean[0]
    if abs(clean[-1] - clean[0]) < 3: return "FLAT"
    return "MIXED_UP" if first_last_up else "MIXED_DOWN" if first_last_dn else "MIXED"


def _verdict(wr_spread: Optional[float], monotonicity: str, expected_direction: str) -> str:
    if wr_spread is None: return "NO_DATA"
    if wr_spread < 5: return "PRUNE"
    if wr_spread < 15:
        if monotonicity == expected_direction: return "WEAK_KEEP"
        if (expected_direction == "MONOTONIC_UP" and monotonicity == "MONOTONIC_DOWN") or \
           (expected_direction == "MONOTONIC_DOWN" and monotonicity == "MONOTONIC_UP"):
            return "ANTI_SIGNAL_WEAK"
        return "PRUNE"
    # spread >= 15pp
    if monotonicity == expected_direction: return "KEEP"
    if (expected_direction == "MONOTONIC_UP" and monotonicity == "MONOTONIC_DOWN") or \
       (expected_direction == "MONOTONIC_DOWN" and monotonicity == "MONOTONIC_UP"):
        return "ANTI_SIGNAL"
    return "KEEP_WARN"


def audit_score(rows: list, name: str, keyfn, ordered_labels: list,
                expected_direction: str) -> dict:
    """Compute per-bucket WR + verdict."""
    buckets = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is None: continue
        buckets[str(k)].append(r)
    per_bucket = {}
    for lb in ordered_labels:
        rs = buckets.get(lb, [])
        if not rs:
            per_bucket[lb] = {"n": 0}
            continue
        per_bucket[lb] = {
            "n":       len(rs),
            "wr_5d":   _wr(rs, "fwd_5d_pct"),
            "wr_10d":  _wr(rs, "fwd_10d_pct"),
            "avg_5d":  _avg(rs, "fwd_5d_pct"),
            "avg_10d": _avg(rs, "fwd_10d_pct"),
        }
    ordered_wrs = [per_bucket[lb]["wr_5d"] for lb in ordered_labels
                   if per_bucket[lb].get("n",0) >= 20]
    spread = None
    if len([x for x in ordered_wrs if x is not None]) >= 2:
        vals = [x for x in ordered_wrs if x is not None]
        spread = round(max(vals) - min(vals), 2)
    mono = _monotonicity(ordered_wrs)
    verdict = _verdict(spread, mono, expected_direction)
    return {
        "name":               name,
        "expected_direction": expected_direction,
        "buckets":            per_bucket,
        "wr_spread_pp":       spread,
        "monotonicity":       mono,
        "verdict":            verdict,
    }


def _band_key(r):
    return r.get("investability_band")


def _confidence_key(r):
    v = r.get("confidence_pct")
    if v is None: return None
    if v < 30:  return "conf_lt30"
    if v < 50:  return "conf_30_50"
    if v < 70:  return "conf_50_70"
    if v < 85:  return "conf_70_85"
    return "conf_ge85"


def _quality_key(r):
    """AEGIS Daily may carry an Inv Quality column · currently we only have
    investability_band. The band is the operational proxy for quality."""
    return r.get("investability_band")


def run_market(root: Path, market: str) -> dict:
    rows = _load(root, market)
    if not rows: return {}
    audits = {}
    audits["investability_band"] = audit_score(
        rows, "investability_band", _band_key,
        ordered_labels=["AVOID","OK","MARGINAL","QUALITY"],
        expected_direction="MONOTONIC_UP",
    )
    audits["confidence_pct"] = audit_score(
        rows, "confidence_pct", _confidence_key,
        ordered_labels=["conf_lt30","conf_30_50","conf_50_70","conf_70_85","conf_ge85"],
        expected_direction="MONOTONIC_UP",
    )
    return {
        "engine":        ENGINE_ID,
        "experiment_id": EXPERIMENT_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":        market.upper(),
        "n_rows":        len(rows),
        "audits":        audits,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_score_usefulness_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res: return
    print(f"\n======== SCORE USEFULNESS · {res['market']} · n={res['n_rows']} ========")
    for name, a in res["audits"].items():
        print(f"\n  [{name}]  expected={a['expected_direction']}  "
              f"actual={a['monotonicity']}  spread={a['wr_spread_pp']}pp  "
              f"VERDICT={a['verdict']}")
        for lb, b in a["buckets"].items():
            if b.get("n"):
                print(f"    {lb:15s} n={b['n']:4d}  WR_5d={b['wr_5d']}%  "
                      f"avg_5d={b['avg_5d']}%")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = run_market(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"\n[score_usefulness:{m}] -> {p.name}")
