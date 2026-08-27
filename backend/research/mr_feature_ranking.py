"""AEGIS · M-R2 · Feature Predictive-Power Ranking · Sprint M.

Consumes the enriched autopsy JSONL and answers:

  Q · Of all the features stamped at prediction time, which ones
      ACTUALLY predict forward return?

For every candidate feature (categorical or bucketized numeric) compute:

  - n_used         · # rows where feature had a value
  - wr_spread      · max_bucket_WR - min_bucket_WR across cohorts of n>=20
  - avg_spread     · max_bucket_avg - min_bucket_avg across cohorts of n>=20
  - directionality · sign(rho) between bucket-index and bucket-WR
                     (monotonic = 1, inverted = -1, mixed = 0)
  - stat_verdict   · PRODUCTION_CANDIDATE if wr_spread>=15pp & n_used>=100
                     else INSUFFICIENT_EVIDENCE / OBSERVATION_ONLY

Then rank features by wr_spread (weighted by evidence strength).

Under M-R sandbox rules. Writes only reports/research/mr_feature_ranking_*.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_feature_ranking.v0.1"

MIN_BUCKET_N = 20      # to score a bucket
MIN_FEATURE_N = 100    # to reach PRODUCTION_CANDIDATE
WR_SPREAD_THRESHOLD_PP = 15

WIN = 0.5


def _bucketize(v, edges: list, labels: list):
    if v is None: return None
    for e, l in zip(edges, labels[:-1]):
        if v < e: return l
    return labels[-1]


def _rsi_bucket(v):
    return _bucketize(v, [30,45,55,70],
                      ["OVERSOLD","WEAK","NEUTRAL","STRONG","OVERBOUGHT"])


def _confidence_bucket(v):
    return _bucketize(v, [30,50,70,85],
                      ["conf_lt30","conf_30_50","conf_50_70","conf_70_85","conf_ge85"])


def _vol_bucket(v):
    return _bucketize(v, [1,2,3,4],
                      ["vol_lt1","vol_1_2","vol_2_3","vol_3_4","vol_ge4"])


def _ma20_bucket(v):
    return _bucketize(v, [-5,-1,1,5],
                      ["ma20_lt-5","ma20_-5_-1","ma20_-1_+1","ma20_+1_+5","ma20_ge+5"])


def _momentum_bucket(v):
    return _bucketize(v, [-5,0,5,10],
                      ["mom_lt-5","mom_-5_0","mom_0_+5","mom_+5_+10","mom_ge+10"])


def _rank_bucket(v):
    if v is None: return None
    if v <= 3: return "rank_top3"
    if v <= 7: return "rank_4_7"
    if v <= 15: return "rank_8_15"
    return "rank_16plus"


FEATURES = [
    ("runner",              lambda r: r.get("runner")),
    ("investability_band",  lambda r: r.get("investability_band")),
    ("sector",              lambda r: r.get("sector")),
    ("cap_bucket",          lambda r: r.get("cap_bucket")),
    ("trend",               lambda r: r.get("trend")),
    ("rank_slot",           lambda r: _rank_bucket(r.get("rank"))),
    ("rsi_14",              lambda r: _rsi_bucket(r.get("rsi_14"))),
    ("confidence_pct",      lambda r: _confidence_bucket(r.get("confidence_pct"))),
    ("vol_20d_pct",         lambda r: _vol_bucket(r.get("vol_20d_pct"))),
    ("ma20_dist_pct",       lambda r: _ma20_bucket(r.get("ma20_dist_pct"))),
    ("momentum_20d_pct",    lambda r: _momentum_bucket(r.get("momentum_20d_pct"))),
]


def _load_rows(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _wr(rows: list) -> Optional[float]:
    vals = [r.get("fwd_5d_pct") for r in rows if isinstance(r.get("fwd_5d_pct"), (int,float))]
    if not vals: return None
    wins = sum(1 for v in vals if v > WIN)
    return round(wins/len(vals)*100, 2)


def _avg(rows: list) -> Optional[float]:
    vals = [r.get("fwd_5d_pct") for r in rows if isinstance(r.get("fwd_5d_pct"), (int,float))]
    if not vals: return None
    return round(mean(vals), 3)


def _score_feature(rows: list, keyfn) -> dict:
    buckets: dict = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is None: continue
        buckets[str(k)].append(r)
    ok = {k: v for k, v in buckets.items() if len(v) >= MIN_BUCKET_N}
    if len(ok) < 2:
        return {"n_used": sum(len(v) for v in buckets.values()),
                "n_scoreable_buckets": len(ok),
                "wr_spread_pp": None, "avg_spread_pct": None,
                "verdict": "INSUFFICIENT_EVIDENCE",
                "buckets": {}}
    per_bucket = {}
    wrs = []
    avgs = []
    for k, v in ok.items():
        w = _wr(v); a = _avg(v)
        per_bucket[k] = {"n": len(v), "wr_pct": w, "avg_pct": a}
        if w is not None: wrs.append(w)
        if a is not None: avgs.append(a)
    if len(wrs) < 2:
        return {"n_used": sum(len(v) for v in buckets.values()),
                "n_scoreable_buckets": len(ok),
                "wr_spread_pp": None, "avg_spread_pct": None,
                "verdict": "INSUFFICIENT_EVIDENCE",
                "buckets": per_bucket}
    wr_spread = max(wrs) - min(wrs)
    avg_spread = max(avgs) - min(avgs) if avgs else None
    total_n = sum(len(v) for v in buckets.values())
    if wr_spread >= WR_SPREAD_THRESHOLD_PP and total_n >= MIN_FEATURE_N:
        verdict = "PRODUCTION_CANDIDATE"
    elif total_n >= MIN_FEATURE_N:
        verdict = "WEAK_SIGNAL"
    else:
        verdict = "INSUFFICIENT_EVIDENCE"
    return {
        "n_used":              total_n,
        "n_scoreable_buckets": len(ok),
        "wr_spread_pp":        round(wr_spread, 2),
        "avg_spread_pct":      round(avg_spread, 3) if avg_spread is not None else None,
        "verdict":             verdict,
        "buckets":             per_bucket,
    }


def run_market(root: Path, market: str) -> dict:
    rows = _load_rows(root, market)
    if not rows: return {}
    scores = {name: _score_feature(rows, fn) for name, fn in FEATURES}
    ranked = sorted(
        [(n, s) for n, s in scores.items() if s.get("wr_spread_pp") is not None],
        key=lambda kv: (-kv[1]["wr_spread_pp"], -kv[1]["n_used"]))
    ranking = [{"rank": i+1, "feature": n,
                "wr_spread_pp": s["wr_spread_pp"],
                "avg_spread_pct": s["avg_spread_pct"],
                "verdict": s["verdict"],
                "n_used": s["n_used"],
                "n_scoreable_buckets": s["n_scoreable_buckets"]}
               for i, (n, s) in enumerate(ranked)]
    return {
        "engine":             ENGINE_ID,
        "experiment_id":      EXPERIMENT_ID,
        "generated_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":             market.upper(),
        "n_rows":             len(rows),
        "min_bucket_n":       MIN_BUCKET_N,
        "min_feature_n":      MIN_FEATURE_N,
        "wr_spread_threshold_pp": WR_SPREAD_THRESHOLD_PP,
        "ranking":            ranking,
        "details":            scores,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_feature_ranking_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res: return
    print(f"\n======== FEATURE RANKING · {res['market']} · n={res['n_rows']} ========")
    print(f"  {'#':>2s}  {'feature':22s} {'wr_spread(pp)':>13s} {'avg_spread(%)':>13s} "
          f"{'n':>5s} {'buckets':>7s} verdict")
    for r in res["ranking"]:
        print(f"  {r['rank']:>2d}  {r['feature']:22s} "
              f"{r['wr_spread_pp']:>13.2f} "
              f"{str(r['avg_spread_pct']):>13s} "
              f"{r['n_used']:>5d} {r['n_scoreable_buckets']:>7d} {r['verdict']}")


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
        print(f"\n[feature_ranking:{m}] -> {p.name}")
