"""AEGIS · M-R · Winner/Loser Genome + Ranker Autopsy · Sprint M Phase B.

Reads mr_prediction_autopsy_{market}.jsonl and answers:

  Q1 · Winner vs Loser Genome
       For fwd_5d winners (return > +0.5%) vs losers (return < -0.5%),
       how do features distribute differently?
         - runner (R1/R2)
         - rank bucket
         - confidence
         - sector
         - investability band
         - MAE / MFE profile
         - stop-hit rate

  Q2 · India Ranker Autopsy
       Why is TOP-3 the WORST bucket? For each rank bucket:
         - What confidence/band mix is being placed there?
         - Which runner dominates?
         - Which sectors dominate?
         - What was the eventual outcome trajectory?
       Split by R1 vs R2 to see whether the pathology is one-runner-only.

  Q3 · Investability Boundary Autopsy
       QUALITY 34.29% WR · OK 17.39% WR (WORST) · MARGINAL 29.94% WR
       Why is OK below MARGINAL? Same feature-distribution comparison.

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


ENGINE_ID = "aegis.mr_winner_loser_genome.v0.1"
SCHEMA_FINGERPRINT = "aegis.mr_wlg.v0.1.20260827"

WIN_THRESHOLD = 0.5   # fwd_5d > +0.5%
LOSS_THRESHOLD = -0.5  # fwd_5d < -0.5%


def _wilson_ci(wins: int, n: int) -> tuple:
    if n == 0: return (None, None)
    z = 1.96
    p = wins / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    margin = z * math.sqrt((p*(1-p) + z*z/(4*n))/n) / denom
    return (round(max(0, center - margin) * 100, 2),
            round(min(1, center + margin) * 100, 2))


def _load_autopsy(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip(): continue
        try: rows.append(json.loads(ln))
        except Exception: continue
    return rows


def _classify(r: dict) -> str:
    """WINNER / LOSER / NEUTRAL / UNKNOWN based on fwd_5d."""
    v = r.get("fwd_5d_pct")
    if v is None: return "UNKNOWN"
    if v > WIN_THRESHOLD: return "WINNER"
    if v < LOSS_THRESHOLD: return "LOSER"
    return "NEUTRAL"


def _feature_dist(subset: list, feature: str) -> dict:
    """Distribution of categorical feature across subset."""
    vals = [r.get(feature) for r in subset if r.get(feature) is not None]
    if not vals: return {}
    total = len(vals)
    ctr = Counter(vals)
    return {str(k): {"n": v, "pct": round(v/total*100, 2)}
            for k, v in ctr.most_common()}


def _numeric_stats(subset: list, feature: str) -> dict:
    vals = [r.get(feature) for r in subset if isinstance(r.get(feature), (int, float))]
    if not vals: return {"n": 0}
    return {
        "n":      len(vals),
        "avg":    round(mean(vals), 3),
        "median": round(median(vals), 3),
        "min":    round(min(vals), 3),
        "max":    round(max(vals), 3),
    }


def _rank_bucket(r: dict) -> Optional[str]:
    rk = r.get("rank")
    if rk is None: return None
    if rk <= 3: return "top3"
    if rk <= 7: return "rank_4_7"
    if rk <= 15: return "rank_8_15"
    return "rank_16plus"


def winner_loser_genome(rows: list) -> dict:
    """Compare feature distributions between winners and losers at fwd_5d."""
    classified = [(r, _classify(r)) for r in rows]
    win = [r for r, c in classified if c == "WINNER"]
    lose = [r for r, c in classified if c == "LOSER"]
    neu = [r for r, c in classified if c == "NEUTRAL"]

    def _cohort_summary(subset, label):
        conf_vals = [r["confidence_pct"] for r in subset
                     if isinstance(r.get("confidence_pct"), (int, float))]
        mfe_vals = [r["mfe_pct"] for r in subset if isinstance(r.get("mfe_pct"), (int, float))]
        mae_vals = [r["mae_pct"] for r in subset if isinstance(r.get("mae_pct"), (int, float))]
        stop_hits = [r for r in subset if r.get("stop_hit_within_20d") is True]
        stop_evaluated = [r for r in subset if r.get("stop_hit_within_20d") is not None]
        return {
            "label":   label,
            "n":       len(subset),
            "runners": _feature_dist(subset, "runner"),
            "bands":   _feature_dist(subset, "investability_band"),
            "sectors": _feature_dist(subset, "sector"),
            "rank_buckets": Counter(_rank_bucket(r) for r in subset if _rank_bucket(r)),
            "confidence_stats": {
                "n": len(conf_vals),
                "avg": round(mean(conf_vals), 2) if conf_vals else None,
                "median": round(median(conf_vals), 2) if conf_vals else None,
                "min": round(min(conf_vals), 2) if conf_vals else None,
                "max": round(max(conf_vals), 2) if conf_vals else None,
            },
            "mfe_pct_avg": round(mean(mfe_vals), 3) if mfe_vals else None,
            "mae_pct_avg": round(mean(mae_vals), 3) if mae_vals else None,
            "stop_hit_rate_pct": (
                round(len(stop_hits)/len(stop_evaluated)*100, 2)
                if stop_evaluated else None),
        }

    return {
        "cohort_WINNER":  _cohort_summary(win, "WINNER (fwd_5d > +0.5%)"),
        "cohort_LOSER":   _cohort_summary(lose, "LOSER (fwd_5d < -0.5%)"),
        "cohort_NEUTRAL": _cohort_summary(neu, "NEUTRAL"),
        "genome_signals": _genome_signals(win, lose),
    }


def _genome_signals(winners: list, losers: list) -> list:
    """Distinguish features where winners vs losers differ meaningfully."""
    signals = []
    w_n = len(winners); l_n = len(losers)
    if w_n < 10 or l_n < 10:
        return [{"signal": "INSUFFICIENT_EVIDENCE", "note": f"winners={w_n}, losers={l_n}"}]

    # Runner distribution
    w_run = Counter(r.get("runner") for r in winners)
    l_run = Counter(r.get("runner") for r in losers)
    for r in ("R1", "R2"):
        wp = w_run.get(r, 0)/w_n
        lp = l_run.get(r, 0)/l_n
        if abs(wp - lp) >= 0.10:
            signals.append({
                "signal":     f"runner_{r}_skew",
                "winner_pct": round(wp*100, 2),
                "loser_pct":  round(lp*100, 2),
                "delta_pct":  round((wp-lp)*100, 2),
                "verdict":    "winners_favor_" + r if wp > lp else "losers_favor_" + r,
            })

    # Band distribution
    for band in ("QUALITY", "OK", "MARGINAL", "AVOID", "PENDING"):
        wp = sum(1 for r in winners if r.get("investability_band") == band) / w_n
        lp = sum(1 for r in losers if r.get("investability_band") == band) / l_n
        if abs(wp - lp) >= 0.05:
            signals.append({
                "signal":     f"band_{band}_skew",
                "winner_pct": round(wp*100, 2),
                "loser_pct":  round(lp*100, 2),
                "delta_pct":  round((wp-lp)*100, 2),
            })

    # Rank bucket
    for rb in ("top3", "rank_4_7", "rank_8_15", "rank_16plus"):
        wp = sum(1 for r in winners if _rank_bucket(r) == rb) / w_n
        lp = sum(1 for r in losers if _rank_bucket(r) == rb) / l_n
        if abs(wp - lp) >= 0.05:
            signals.append({
                "signal":     f"rank_{rb}_skew",
                "winner_pct": round(wp*100, 2),
                "loser_pct":  round(lp*100, 2),
                "delta_pct":  round((wp-lp)*100, 2),
            })

    # Confidence
    w_conf = [r["confidence_pct"] for r in winners
              if isinstance(r.get("confidence_pct"), (int, float))]
    l_conf = [r["confidence_pct"] for r in losers
              if isinstance(r.get("confidence_pct"), (int, float))]
    if len(w_conf) >= 10 and len(l_conf) >= 10:
        signals.append({
            "signal":         "confidence_diff",
            "winner_avg":     round(mean(w_conf), 2),
            "loser_avg":      round(mean(l_conf), 2),
            "delta":          round(mean(w_conf) - mean(l_conf), 2),
        })

    return signals


def ranker_autopsy(rows: list) -> dict:
    """Per-runner per-rank-bucket forward outcome + feature mix."""
    by_key = defaultdict(list)
    for r in rows:
        rb = _rank_bucket(r)
        run = r.get("runner")
        if not (rb and run): continue
        by_key[(run, rb)].append(r)

    def _panel(subset):
        f5_vals = [r["fwd_5d_pct"] for r in subset
                   if isinstance(r.get("fwd_5d_pct"), (int, float))]
        wins = sum(1 for v in f5_vals if v > WIN_THRESHOLD)
        conf_vals = [r["confidence_pct"] for r in subset
                     if isinstance(r.get("confidence_pct"), (int, float))]
        return {
            "n":              len(subset),
            "n_scored":       len(f5_vals),
            "fwd_5d_wr_pct":  round(wins/max(1,len(f5_vals))*100, 2),
            "fwd_5d_wr_ci":   _wilson_ci(wins, len(f5_vals)),
            "fwd_5d_avg_pct": round(mean(f5_vals), 3) if f5_vals else None,
            "confidence_avg": round(mean(conf_vals), 2) if conf_vals else None,
            "confidence_min": round(min(conf_vals), 2) if conf_vals else None,
            "confidence_max": round(max(conf_vals), 2) if conf_vals else None,
            "band_mix":       _feature_dist(subset, "investability_band"),
            "top_sectors":    dict(list(_feature_dist(subset, "sector").items())[:5]),
        }

    return {
        f"{run}__{rb}": _panel(rows)
        for (run, rb), rows in sorted(by_key.items())
    }


def band_boundary_autopsy(rows: list) -> dict:
    """Compare OK vs MARGINAL vs QUALITY vs AVOID feature distributions."""
    by_band = defaultdict(list)
    for r in rows:
        b = r.get("investability_band")
        if b: by_band[b].append(r)

    out = {}
    for band, subset in by_band.items():
        f5 = [r["fwd_5d_pct"] for r in subset
              if isinstance(r.get("fwd_5d_pct"), (int, float))]
        conf_vals = [r["confidence_pct"] for r in subset
                     if isinstance(r.get("confidence_pct"), (int, float))]
        wins = sum(1 for v in f5 if v > WIN_THRESHOLD)
        out[band] = {
            "n":             len(subset),
            "fwd_5d_wr":     round(wins/max(1,len(f5))*100, 2),
            "fwd_5d_wr_ci":  _wilson_ci(wins, len(f5)),
            "fwd_5d_avg":    round(mean(f5), 3) if f5 else None,
            "confidence":    round(mean(conf_vals), 2) if conf_vals else None,
            "runners":       _feature_dist(subset, "runner"),
            "top_sectors":   dict(list(_feature_dist(subset, "sector").items())[:5]),
            "rank_buckets":  {rb: sum(1 for r in subset if _rank_bucket(r)==rb)
                              for rb in ("top3","rank_4_7","rank_8_15","rank_16plus")},
        }
    return out


def run_market(root: Path, market: str) -> dict:
    rows = _load_autopsy(root, market)
    if not rows: return {}
    result = {
        "engine":            ENGINE_ID,
        "experiment_id":     EXPERIMENT_ID,
        "schema_fingerprint": SCHEMA_FINGERPRINT,
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":            market.upper(),
        "n_rows":            len(rows),
        "genome":            winner_loser_genome(rows),
        "ranker_autopsy":    ranker_autopsy(rows),
        "band_boundary":     band_boundary_autopsy(rows),
    }
    # Sanitize Counter → dict for JSON
    def _sanitize(o):
        if isinstance(o, Counter): return dict(o)
        if isinstance(o, dict): return {k: _sanitize(v) for k, v in o.items()}
        if isinstance(o, list): return [_sanitize(v) for v in o]
        return o
    result = _sanitize(result)
    p = root / ALLOWED_WRITE_ROOT / f"mr_winner_loser_genome_{market.lower()}.json"
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def _fmt_dist(d: dict, keys=None) -> str:
    if not d: return "none"
    items = [(k, v.get("pct", 0)) for k, v in d.items()]
    if keys:
        items = [(k, next((v.get("pct",0) for kk,v in d.items() if kk==k), 0)) for k in keys]
    return " · ".join(f"{k}={p}%" for k, p in items[:6])


def render_console(res: dict):
    if not res: return
    market = res["market"]; n = res["n_rows"]
    print(f"\n======== WINNER/LOSER GENOME - {market} - n={n} ========")
    g = res["genome"]
    w = g["cohort_WINNER"]; l = g["cohort_LOSER"]
    print(f"\n[COHORT SIZES]")
    print(f"  winners  (fwd_5d > +0.5%) n={w['n']}")
    print(f"  losers   (fwd_5d < -0.5%) n={l['n']}")
    print(f"  neutrals                  n={g['cohort_NEUTRAL']['n']}")

    print(f"\n[RUNNER MIX]")
    print(f"  winners: { _fmt_dist(w['runners']) }")
    print(f"  losers:  { _fmt_dist(l['runners']) }")

    print(f"\n[BAND MIX]")
    print(f"  winners: { _fmt_dist(w['bands']) }")
    print(f"  losers:  { _fmt_dist(l['bands']) }")

    print(f"\n[CONFIDENCE]")
    wc = w["confidence_stats"]; lc = l["confidence_stats"]
    if wc.get("avg") is not None and lc.get("avg") is not None:
        print(f"  winners avg={wc['avg']}%  (range {wc['min']}-{wc['max']})")
        print(f"  losers  avg={lc['avg']}%  (range {lc['min']}-{lc['max']})")
        print(f"  DELTA  {round(wc['avg'] - lc['avg'], 2)}%")

    print(f"\n[GENOME SIGNALS]")
    for s in g["genome_signals"]:
        print(f"  · {s}")

    print(f"\n======== RANKER AUTOPSY - {market} ========")
    for k, p in res["ranker_autopsy"].items():
        run, rb = k.split("__")
        ci = p["fwd_5d_wr_ci"] or (None, None)
        print(f"  {run:3s} · {rb:12s} n={p['n']:4d}  WR={p['fwd_5d_wr_pct']:5.2f}%  "
              f"[CI {ci[0]}-{ci[1]}]  avg={p['fwd_5d_avg_pct']}%  "
              f"conf={p['confidence_avg']}  band={_fmt_dist(p['band_mix'])}")

    print(f"\n======== BAND BOUNDARY AUTOPSY - {market} ========")
    for b, p in res["band_boundary"].items():
        ci = p["fwd_5d_wr_ci"] or (None, None)
        print(f"  {b:10s} n={p['n']:4d}  WR={p['fwd_5d_wr']:5.2f}%  "
              f"[CI {ci[0]}-{ci[1]}]  avg={p['fwd_5d_avg']}%  "
              f"conf={p['confidence']}  runners={_fmt_dist(p['runners'])}  "
              f"ranks(top3/47/815/16+)="
              f"{p['rank_buckets']['top3']}/{p['rank_buckets']['rank_4_7']}/"
              f"{p['rank_buckets']['rank_8_15']}/{p['rank_buckets']['rank_16plus']}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = run_market(root, m)
        render_console(res)
