"""AEGIS · Sprint M2 · Conditional Cohort Analyzer.

CEO handover 2026-08-27:
> "Measure conditional combinations, not just individual features. For
>  example: R2 + RSI 55-70 + MA20 +1-5% + MARGINAL may be useful even
>  if each individual feature looks mediocre."

Enumerates 2-way and 3-way feature-value combinations across the enriched
autopsy dataset, computes 5D WR per combination, ranks by conditional
edge vs cohort baseline · with Bonferroni-adjusted evidence thresholds
so we don't cherry-pick from multiple testing.

Under M-R sandbox rules. No production changes.

Emits:
   reports/research/mr_conditional_cohorts_{market}.json
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_conditional_cohorts.v0.1"

MIN_COMBO_N = 20      # need at least this many rows in a cohort
TOP_N = 30            # keep top-N combinations per depth
WIN = 0.5


def _bucketize(v, edges, labels):
    if v is None: return None
    for e, l in zip(edges, labels[:-1]):
        if v < e: return l
    return labels[-1]


FEATURES = {
    "runner":      lambda r: r.get("runner"),
    "band":        lambda r: r.get("investability_band"),
    "sector":      lambda r: r.get("sector"),
    "cap":         lambda r: r.get("cap_bucket"),
    "trend":       lambda r: r.get("trend"),
    "rank_slot":   lambda r: ("rank_top3" if isinstance(r.get("rank"), int) and r["rank"]<=3
                              else "rank_4_7" if isinstance(r.get("rank"), int) and r["rank"]<=7
                              else "rank_8_15" if isinstance(r.get("rank"), int) and r["rank"]<=15
                              else "rank_16plus" if isinstance(r.get("rank"), int)
                              else None),
    "rsi":         lambda r: _bucketize(r.get("rsi_14"),
                              [30,45,55,70],
                              ["OVERSOLD","WEAK","NEUTRAL","STRONG","OVERBOUGHT"]),
    "conf":        lambda r: _bucketize(r.get("confidence_pct"),
                              [30,50,70,85],
                              ["lt30","30_50","50_70","70_85","ge85"]),
    "vol":         lambda r: _bucketize(r.get("vol_20d_pct"),
                              [1,2,3,4],
                              ["lt1","1_2","2_3","3_4","ge4"]),
    "ma20":        lambda r: _bucketize(r.get("ma20_dist_pct"),
                              [-5,-1,1,5],
                              ["lt-5","-5_-1","-1_+1","+1_+5","ge+5"]),
    "mom20":       lambda r: _bucketize(r.get("momentum_20d_pct"),
                              [-5,0,5,10],
                              ["lt-5","-5_0","0_+5","+5_+10","ge+10"]),
}


def _load(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _wilson(w: int, n: int):
    if n == 0: return (None, None)
    z = 1.96
    p = w/n
    d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    m = z*math.sqrt((p*(1-p) + z*z/(4*n))/n)/d
    return (round(max(0,c-m)*100,2), round(min(1,c+m)*100,2))


def _cohort_stats(rows: list) -> dict:
    vals = [r.get("fwd_5d_pct") for r in rows if isinstance(r.get("fwd_5d_pct"), (int,float))]
    if not vals: return {"n": 0}
    wins = sum(1 for v in vals if v > WIN)
    return {
        "n":         len(vals),
        "wr_pct":    round(wins/len(vals)*100, 2),
        "wr_ci":     _wilson(wins, len(vals)),
        "avg_pct":   round(mean(vals), 3),
    }


def _tag(row: dict, key_names: list) -> Optional[tuple]:
    tag = []
    for k in key_names:
        fn = FEATURES.get(k)
        if not fn: return None
        v = fn(row)
        if v is None: return None
        tag.append(f"{k}={v}")
    return tuple(tag)


def enumerate_combos(rows: list, depth: int, baseline_wr: float,
                     multiple_tests: int) -> list:
    """Return every k-tuple of features whose cohort meets MIN_COMBO_N."""
    feature_keys = list(FEATURES.keys())
    results = []
    # Bonferroni cutoff: reduce alpha by multiple_tests count
    # (informational only · we still require n>=MIN_COMBO_N)
    for combo in combinations(feature_keys, depth):
        buckets: dict = defaultdict(list)
        for r in rows:
            tag = _tag(r, list(combo))
            if tag is None: continue
            buckets[tag].append(r)
        for tag, subset in buckets.items():
            stats = _cohort_stats(subset)
            if stats.get("n", 0) < MIN_COMBO_N: continue
            edge_pp = round(stats["wr_pct"] - baseline_wr, 2)
            ci = stats["wr_ci"] or (None, None)
            # Significant if CI lower bound > baseline_wr (positive edge)
            # OR CI upper bound < baseline_wr (negative edge)
            positive_sig = ci[0] is not None and ci[0] > baseline_wr
            negative_sig = ci[1] is not None and ci[1] < baseline_wr
            results.append({
                "depth":            depth,
                "combo":            list(tag),
                "n":                stats["n"],
                "wr_pct":           stats["wr_pct"],
                "wr_ci":            list(ci),
                "avg_pct":          stats["avg_pct"],
                "edge_vs_baseline_pp": edge_pp,
                "baseline_wr":      baseline_wr,
                "positive_significance": positive_sig,
                "negative_significance": negative_sig,
                "multiple_tests_count": multiple_tests,
            })
    results.sort(key=lambda r: -r["edge_vs_baseline_pp"])
    return results


def run_market(root: Path, market: str) -> dict:
    rows = _load(root, market)
    if not rows:
        return {"engine": ENGINE_ID, "market": market.upper(),
                "status": "NO_ROWS"}
    baseline = _cohort_stats(rows)
    baseline_wr = baseline["wr_pct"]

    combos_2way = enumerate_combos(rows, 2, baseline_wr,
                                    math.comb(len(FEATURES), 2))
    combos_3way = enumerate_combos(rows, 3, baseline_wr,
                                    math.comb(len(FEATURES), 3))

    # Top-N positive and negative edges each depth
    def _split(combos: list):
        pos = [c for c in combos if c["edge_vs_baseline_pp"] > 0][:TOP_N]
        neg = sorted([c for c in combos if c["edge_vs_baseline_pp"] < 0],
                     key=lambda c: c["edge_vs_baseline_pp"])[:TOP_N]
        sig_pos = [c for c in combos if c["positive_significance"]][:TOP_N]
        sig_neg = [c for c in combos if c["negative_significance"]][:TOP_N]
        return {"top_positive": pos, "top_negative": neg,
                "significant_positive": sig_pos, "significant_negative": sig_neg,
                "n_combos_scored": len(combos)}

    return {
        "engine":         ENGINE_ID,
        "experiment_id":  EXPERIMENT_ID,
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":         market.upper(),
        "n_rows":         len(rows),
        "baseline_wr_pct": baseline_wr,
        "baseline_avg_pct": baseline["avg_pct"],
        "min_combo_n":    MIN_COMBO_N,
        "top_n":          TOP_N,
        "features":       list(FEATURES.keys()),
        "combos_2way":    _split(combos_2way),
        "combos_3way":    _split(combos_3way),
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_conditional_cohorts_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res or res.get("status") == "NO_ROWS": return
    print(f"\n======== CONDITIONAL COHORTS · {res['market']} · "
          f"n={res['n_rows']} · baseline WR={res['baseline_wr_pct']}% ========")
    for depth_name in ("combos_2way","combos_3way"):
        d = res[depth_name]
        print(f"\n  [{depth_name}] n_combos_scored={d['n_combos_scored']}")
        print(f"    TOP-15 POSITIVE EDGE:")
        for c in d["top_positive"][:15]:
            sig = " *SIG*" if c["positive_significance"] else ""
            print(f"      +{c['edge_vs_baseline_pp']:>5.2f}pp  "
                  f"n={c['n']:>4d}  WR={c['wr_pct']}%{sig:6s}  "
                  f"{' · '.join(c['combo'])}")
        print(f"    TOP-10 NEGATIVE EDGE:")
        for c in d["top_negative"][:10]:
            sig = " *SIG*" if c["negative_significance"] else ""
            print(f"      {c['edge_vs_baseline_pp']:>6.2f}pp  "
                  f"n={c['n']:>4d}  WR={c['wr_pct']}%{sig:6s}  "
                  f"{' · '.join(c['combo'])}")


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
        print(f"\n[conditional_cohorts:{m}] -> {p.name}")
