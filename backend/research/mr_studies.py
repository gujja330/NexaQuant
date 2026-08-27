"""AEGIS · M-R · Studies · Sprint M Phase C.

Consumes enriched autopsy + market regime and produces per-market cohort
studies covering:

  Q1 · Runner scoreboard (R1 / R2 / Momentum) at 1/3/5/10D
  Q2 · Sector cohort
  Q3 · Cap bucket (LARGE / MID / SMALL) cohort
  Q4 · Technical cohorts (RSI / trend / vol / ma-dist)
  Q5 · Fundamental cohorts (ROE / PE / quality)
  Q6 · Market-regime cohort (BULL / BEAR / NEUTRAL / HIGH_VOL / UNKNOWN)
  Q7 · Score usefulness test (confidence / investability band)
  Q8 · Rank slot (top3 / 4_7 / 8_15 / 16+)

Wilson-95 CI on every WR. Statistical verdict per bucket:
   n<20  = OBSERVATION_ONLY
   n<100 = INSUFFICIENT_EVIDENCE
   n>=100= PRODUCTION_CANDIDATE (for the raw evidence, NOT for shipping)

Under M-R sandbox rules. Writes only to reports/research/.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_studies.v0.1"
SCHEMA_FINGERPRINT = "aegis.mr_studies.v0.1.20260827"

WIN = 0.5
LOSS = -0.5


def _wilson(w: int, n: int):
    if n == 0: return (None, None)
    z = 1.96
    p = w/n
    d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    m = z*math.sqrt((p*(1-p) + z*z/(4*n))/n)/d
    return (round(max(0,c-m)*100,2), round(min(1,c+m)*100,2))


def _verdict(n: int) -> str:
    if n < 20:  return "OBSERVATION_ONLY"
    if n < 100: return "INSUFFICIENT_EVIDENCE"
    return "PRODUCTION_CANDIDATE"


def _load_enriched(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists():
        p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _load_regime(root: Path, market: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / f"mr_market_regime_{market.lower()}.json"
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("regimes", {})
    except Exception:
        return {}


def _rank_bucket(r: dict) -> Optional[str]:
    rk = r.get("rank")
    if rk is None: return None
    if rk <= 3: return "top3"
    if rk <= 7: return "rank_4_7"
    if rk <= 15: return "rank_8_15"
    return "rank_16plus"


def _rsi_bucket(v):
    if v is None: return None
    if v < 30: return "OVERSOLD_lt30"
    if v < 45: return "WEAK_30_45"
    if v < 55: return "NEUTRAL_45_55"
    if v < 70: return "STRONG_55_70"
    return "OVERBOUGHT_ge70"


def _bucketize(v, edges: list, labels: list):
    if v is None: return None
    for e, l in zip(edges, labels[:-1]):
        if v < e: return l
    return labels[-1]


def _cohort_stats(rows: list, key: str) -> dict:
    vals = [r.get(key) for r in rows if isinstance(r.get(key), (int, float))]
    if not vals: return {"n": 0}
    wins = sum(1 for v in vals if v > WIN)
    losses = sum(1 for v in vals if v < LOSS)
    return {
        "n":            len(vals),
        "wins":         wins,
        "losses":       losses,
        "wr_pct":       round(wins/len(vals)*100, 2),
        "wr_ci":        _wilson(wins, len(vals)),
        "avg_pct":      round(mean(vals), 3),
        "median_pct":   round(median(vals), 3),
        "best_pct":     round(max(vals), 3),
        "worst_pct":    round(min(vals), 3),
        "verdict":      _verdict(len(vals)),
    }


def _panel(rows: list) -> dict:
    return {
        "n":       len(rows),
        "fwd_1d":  _cohort_stats(rows, "fwd_1d_pct"),
        "fwd_3d":  _cohort_stats(rows, "fwd_3d_pct"),
        "fwd_5d":  _cohort_stats(rows, "fwd_5d_pct"),
        "fwd_10d": _cohort_stats(rows, "fwd_10d_pct"),
        "fwd_20d": _cohort_stats(rows, "fwd_20d_pct"),
        "avg_mfe_pct": (round(mean(v for r in rows
                                   if (v:=r.get("mfe_pct")) is not None), 3)
                        if any(r.get("mfe_pct") is not None for r in rows) else None),
        "avg_mae_pct": (round(mean(v for r in rows
                                   if (v:=r.get("mae_pct")) is not None), 3)
                        if any(r.get("mae_pct") is not None for r in rows) else None),
        "stop_hit_rate_pct": (
            round(sum(1 for r in rows if r.get("stop_hit_within_20d"))
                  / max(1, sum(1 for r in rows if r.get("stop_hit_within_20d") is not None))
                  * 100, 2)
            if any(r.get("stop_hit_within_20d") is not None for r in rows) else None),
    }


def _by_key(rows: list, key_fn) -> dict:
    out = defaultdict(list)
    for r in rows:
        k = key_fn(r)
        if k is not None: out[str(k)].append(r)
    return {k: _panel(v) for k, v in sorted(out.items())}


def run_market(root: Path, market: str) -> dict:
    rows = _load_enriched(root, market)
    if not rows: return {}
    regimes = _load_regime(root, market)
    for r in rows:
        r["_regime"] = regimes.get(r.get("prediction_date",""), "UNKNOWN")

    def _tk_key(r):
        s = r.get("status","").upper()
        if "MOMENTUM" in s: return "MOMENTUM"
        return r.get("runner")

    return {
        "engine":            ENGINE_ID,
        "experiment_id":     EXPERIMENT_ID,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":            market.upper(),
        "n_rows":            len(rows),
        "Q1_runner_scoreboard":  _by_key(rows, _tk_key),
        "Q2_sector":             _by_key(rows, lambda r: r.get("sector")),
        "Q3_cap_bucket":         _by_key(rows, lambda r: r.get("cap_bucket")),
        "Q4_technicals": {
            "rsi_bucket":            _by_key(rows, lambda r: _rsi_bucket(r.get("rsi_14"))),
            "trend":                 _by_key(rows, lambda r: r.get("trend")),
            "vol_bucket":            _by_key(rows, lambda r: _bucketize(
                                          r.get("vol_20d_pct"),
                                          [1, 2, 3, 4],
                                          ["low_lt1","mid_1_2","high_2_3","vhigh_3_4","xhigh_ge4"])),
            "ma20_dist_bucket":      _by_key(rows, lambda r: _bucketize(
                                          r.get("ma20_dist_pct"),
                                          [-5, -1, 1, 5],
                                          ["deep_below_lt-5","below_-5_-1","near_-1_+1",
                                           "above_+1_+5","far_above_ge+5"])),
            "momentum_20d_bucket":   _by_key(rows, lambda r: _bucketize(
                                          r.get("momentum_20d_pct"),
                                          [-5, 0, 5, 10],
                                          ["falling_lt-5","weak_-5_0","flat_0_+5",
                                           "strong_+5_+10","surge_ge+10"])),
        },
        "Q5_fundamentals": {
            "roe_bucket":     _by_key(rows, lambda r: _bucketize(
                                  r.get("fund_roe"),
                                  [0.05, 0.10, 0.15, 0.25],
                                  ["neg_lt5","low_5_10","mid_10_15","high_15_25","xhigh_ge25"])),
            "pe_bucket":      _by_key(rows, lambda r: _bucketize(
                                  r.get("fund_pe"),
                                  [15, 25, 40, 60],
                                  ["cheap_lt15","fair_15_25","expensive_25_40",
                                   "vexp_40_60","xexp_ge60"])),
            "quality_bucket": _by_key(rows, lambda r: _bucketize(
                                  r.get("fund_quality_score"),
                                  [1.5, 2.0, 2.5, 3.0],
                                  ["poor_lt1.5","fair_1.5_2","good_2_2.5",
                                   "vgood_2.5_3","xgood_ge3"])),
        },
        "Q6_regime":            _by_key(rows, lambda r: r.get("_regime")),
        "Q7_score_usefulness": {
            "band":         _by_key(rows, lambda r: r.get("investability_band")),
            "confidence_bucket": _by_key(rows, lambda r: _bucketize(
                                     r.get("confidence_pct"),
                                     [30, 50, 70, 85],
                                     ["low_lt30","mid_30_50","mid_50_70",
                                      "high_70_85","xhigh_ge85"])),
        },
        "Q8_rank_slot":         _by_key(rows, _rank_bucket),
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_studies_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _render_panel_row(k, p, key="fwd_5d"):
    m = p.get(key, {})
    if not m.get("n"): return None
    ci = m.get("wr_ci") or (None, None)
    return (f"  {str(k)[:20]:20s} n={p['n']:4d}  {key} WR={m['wr_pct']:5.2f}% "
            f"[CI {ci[0]}-{ci[1]}]  avg={m['avg_pct']:+6.3f}%  "
            f"MFE={p['avg_mfe_pct']}%  MAE={p['avg_mae_pct']}%  "
            f"verdict={m['verdict']}")


def render_console(res: dict):
    if not res: return
    print(f"\n======== STUDIES · {res['market']} · n={res['n_rows']} ========")
    for section in ("Q1_runner_scoreboard","Q2_sector","Q3_cap_bucket",
                    "Q6_regime","Q8_rank_slot"):
        print(f"\n[{section}]")
        for k, p in res[section].items():
            line = _render_panel_row(k, p)
            if line: print(line)
    print("\n[Q4_technicals]")
    for sub, panel in res["Q4_technicals"].items():
        print(f"  ~ {sub} ~")
        for k, p in panel.items():
            line = _render_panel_row(k, p)
            if line: print(line)
    print("\n[Q5_fundamentals]")
    for sub, panel in res["Q5_fundamentals"].items():
        print(f"  ~ {sub} ~")
        for k, p in panel.items():
            line = _render_panel_row(k, p)
            if line: print(line)
    print("\n[Q7_score_usefulness]")
    for sub, panel in res["Q7_score_usefulness"].items():
        print(f"  ~ {sub} ~")
        for k, p in panel.items():
            line = _render_panel_row(k, p)
            if line: print(line)


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
        print(f"\n[studies:{m}] -> {p.name}")
