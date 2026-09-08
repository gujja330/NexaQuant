"""MR_DEPENDENCY_WINNER_LOSER_60D_V1 · CEO-preregistered · 2026-09-08.

> "Run the 8-dimension preregistered primary study now, while
>  simultaneously accumulating the broader substrate and exploratory
>  dimensions."

THE QUESTION
------------
> "Which characteristics distinguish the stocks that subsequently lose
>  badly from those that produce persistent positive returns, and how
>  should entry/stop/exit treatment respond?"

Not "which feature correlates with losses". The deliverable is a
conditional structure that separates the two tails and survives
correction.

PREREGISTERED CONFIRMATORY FAMILY · frozen before results are read
------------------------------------------------------------------
Eight dimensions only:

    1 confidence          raw model confidence
    2 momentum            momentum_20d / momentum_60d
    3 trend               MA20/50/200 distance + direction
    4 volatility          realized vol_20d
    5 stop_distance       stop-to-entry %, and relative to volatility
    6 investability       investability band / liquidity
    7 rank                recommendation position
    8 liquidity           within-market 60d traded-value tercile

MAE/MFE were REMOVED from this family after the first run: they are path
outcomes of the same price series as the forward return, so testing them
against it is circular. They are retained as the exit/failure-path
dataset.

Everything else - sector, market cap, FII/DII, earnings, fundamentals,
regime, and every interaction - belongs to the SEPARATE exploratory
family and may generate hypotheses only. It may never be reported as a
validated discovery.

HORIZONS
--------
fwd_5d and fwd_10d are PRIMARY. fwd_20d is supplementary and India-only:
the USA cohort is 12 trading days old and no 20-day outcome has matured.
India is not truncated to force symmetry - that would discard real
evidence to make a table look neat.

SUBSTRATE LIMITATIONS CARRIED WITH EVERY RESULT
-----------------------------------------------
  regime         UNAVAILABLE · producer has emitted 'unknown' for all 19
                 observations it has ever made. Not joined.
  sector         CURRENT-TIME, NOT PIT · no historical snapshot exists.
                 Exploratory only.
  market cap     NO SOURCE ANYWHERE in the repository.
  liquidity      `cap_bucket` in the enriched cohort is NOT market cap -
                 it buckets 60-day average traded value using identical
                 thresholds for INR and USD. It is recomputed here as
                 `liquidity_bucket_60d` from within-market quantiles, so
                 the two markets are finally comparable.
  fundamentals   current-time only; PIT accumulator holds 2 dates.

MULTIPLE TESTING
----------------
Every confirmatory test is counted and Benjamini-Hochberg corrected
across the whole family before any result is interpreted. A dimension
that survives is a VALIDATION CANDIDATE, never a production rule - the
existing PIT / walk-forward / OOS gates still stand between it and
production.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.mr_dependency.v1"
FAMILY = "MR_DEPENDENCY_WINNER_LOSER_60D_V1"
EXPLORATORY_FAMILY = "MR_DEPENDENCY_EXPLORATORY_60D_V1"

PRIMARY_HORIZONS = ["fwd_5d_pct", "fwd_10d_pct"]
SUPPLEMENTARY_HORIZON = "fwd_20d_pct"
TAIL_Q = 0.10                     # bottom/top decile define the two cohorts

TIERS = ((5, "OBSERVATION"), (15, "HYPOTHESIS"), (30, "RESEARCH_SIGNAL"),
         (50, "STRONGER_EVIDENCE"))


def tier(n: int) -> str:
    for cap, name in TIERS:
        if n < cap:
            return name
    return "VALIDATION_CANDIDATE"


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


# ── PREREGISTERED DIMENSIONS ────────────────────────────────────────────
# (name, extractor) · frozen. Adding one after seeing results would
# invalidate the correction, so the list lives here and nowhere else.
def _trend_state(r) -> Optional[str]:
    d200 = _num(r.get("ma200_dist_pct"))
    d50 = _num(r.get("ma50_dist_pct"))
    if d200 is None:
        return None
    if d200 > 0 and (d50 or 0) > 0:
        return "ABOVE_50_AND_200"
    if d200 > 0:
        return "ABOVE_200_ONLY"
    if (d50 or 0) > 0:
        return "ABOVE_50_ONLY"
    return "BELOW_BOTH"


def _stop_dist_pct(r) -> Optional[float]:
    ep, st = _num(r.get("entry_price_at_pred")), _num(r.get("stop_at_pred"))
    if not ep or st is None or ep <= 0:
        return None
    return (ep - st) / ep * 100.0


def _stop_vs_vol(r) -> Optional[float]:
    """Stop distance in units of 20-day volatility · a 5% stop on a 2%-vol
    name and on an 8%-vol name are entirely different instruments."""
    sd, vol = _stop_dist_pct(r), _num(r.get("vol_20d_pct"))
    if sd is None or not vol:
        return None
    return sd / vol


PRIMARY_DIMENSIONS = [
    ("confidence", lambda r: _num(r.get("confidence_pct"))),
    ("momentum_20d", lambda r: _num(r.get("momentum_20d_pct"))),
    ("momentum_60d", lambda r: _num(r.get("momentum_60d_pct"))),
    ("trend_ma200_dist", lambda r: _num(r.get("ma200_dist_pct"))),
    ("trend_state", _trend_state),
    ("volatility_20d", lambda r: _num(r.get("vol_20d_pct"))),
    ("stop_distance_pct", _stop_dist_pct),
    ("stop_vs_volatility", _stop_vs_vol),
    ("investability", lambda r: (str(r.get("investability_band") or "").upper()
                                 or None)),
    ("rank", lambda r: _num(r.get("rank"))),
    ("liquidity_bucket_60d", lambda r: r.get("_liquidity_bucket")),
]

# PATH OUTCOMES · CEO 2026-09-08 · REMOVED from the confirmatory family.
#
# > "The code counts MAE and MFE as confirmatory dimensions, then discovers
# >  that they are mechanically tied to the forward-return tail. Those
# >  should have been excluded from the confirmatory family BEFORE
# >  correction."
#
# MAE and MFE are measured from the SAME price path as the forward return,
# so a bottom-decile loser necessarily has a bad MAE. Testing them posted
# p=0.0 in every market and horizon and consumed 8 of 16 FDR survivors
# with a near-tautology. They are not available at entry and cannot inform
# selection.
#
# They remain essential - but as the EXIT / FAILURE-PATH dataset, where the
# question is "was this a bad stock, or a good stock with a bad exit?".
# They are profiled in cohort signatures and never significance-tested.
PATH_OUTCOMES = [
    ("mae_pct", lambda r: _num(r.get("mae_pct"))),
    ("mfe_pct", lambda r: _num(r.get("mfe_pct"))),
]


def load_cohort(root: Path, market: str) -> list:
    p = (root / "reports" / "research"
         / f"mr_prediction_autopsy_{market}_enriched.jsonl")
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    _attach_liquidity(rows)
    return rows


def _attach_liquidity(rows: list) -> None:
    """Within-market quantile buckets of 60-day traded value.

    The enriched cohort's `cap_bucket` applies 5e8/5e7 thresholds to BOTH
    markets, so India (INR, median 2.2e9) reads as overwhelmingly LARGE
    and USA (USD, median 4.3e8) as mostly MID. That split is a currency
    artifact. Quantiles within each market make the buckets comparable and,
    critically, stop this being mistaken for market capitalisation.
    """
    vals = sorted(v for v in (_num(r.get("avg_dv_60d")) for r in rows)
                  if v is not None)
    if not vals:
        for r in rows:
            r["_liquidity_bucket"] = None
        return
    lo, hi = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    for r in rows:
        v = _num(r.get("avg_dv_60d"))
        r["_liquidity_bucket"] = (
            None if v is None else
            "LIQ_LOW" if v <= lo else "LIQ_MID" if v <= hi else "LIQ_HIGH")


def _stats(vals: list) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    wins = [v for v in s if v > 0]
    losses = [v for v in s if v < 0]

    def q(p):
        return s[min(n - 1, max(0, int(n * p)))]
    return {
        "n": n, "tier": tier(n),
        "expectancy_pct": round(sum(s) / n, 3),
        "median_pct": round(s[n // 2], 3),
        "win_rate_pct": round(len(wins) / n * 100, 1),
        "mean_win_pct": round(sum(wins) / len(wins), 3) if wins else None,
        "mean_loss_pct": round(sum(losses) / len(losses), 3) if losses else None,
        "p10_pct": round(q(0.10), 3), "p90_pct": round(q(0.90), 3),
        "worst_pct": round(s[0], 3), "best_pct": round(s[-1], 3),
        "total_negative_contribution_pct": round(sum(losses), 2),
        "total_positive_contribution_pct": round(sum(wins), 2),
        "profit_factor": (round(sum(wins) / abs(sum(losses)), 3)
                          if losses and sum(losses) else None),
    }


def _cohort_profile(rows: list) -> dict:
    """Mean of every primary dimension over a cohort · this is what makes
    the loser/winner comparison a SIGNATURE rather than one correlation."""
    out = {}
    for name, fn in list(PRIMARY_DIMENSIONS) + list(PATH_OUTCOMES):
        vals = [fn(r) for r in rows]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if nums:
            out[name] = round(sum(nums) / len(nums), 3)
        else:
            cats = [v for v in vals if isinstance(v, str)]
            if cats:
                top = max(set(cats), key=cats.count)
                out[name] = f"{top} ({cats.count(top)}/{len(cats)})"
    ex = [r for r in rows if _num(r.get("mae_pct")) is not None]
    if ex:
        out["_stop_hit_pct"] = round(
            sum(1 for r in rows if r.get("stop_hit_within_20d")) / len(rows)
            * 100, 1)
    return out


def _mannwhitney_p(a: list, b: list) -> Optional[float]:
    """Two-sided Mann-Whitney U, normal approximation with tie correction.

    Non-parametric on purpose: forward returns are fat-tailed and a
    t-test would overstate significance in exactly the tails this study
    is about.
    """
    if len(a) < 5 or len(b) < 5:
        return None
    comb = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i, n = {}, 0, len(comb)
    rank_of = [0.0] * n
    while i < n:
        j = i
        while j + 1 < n and comb[j + 1][0] == comb[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rank_of[k] = avg
        ranks[comb[i][0]] = j - i + 1
        i = j + 1
    r1 = sum(rank_of[k] for k in range(n) if comb[k][1] == 0)
    n1, n2 = len(a), len(b)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    tie = sum(t ** 3 - t for t in ranks.values())
    sd2 = (n1 * n2 / 12.0) * ((n + 1) - tie / float(n * (n - 1)))
    if sd2 <= 0:
        return None
    z = (u1 - mu) / math.sqrt(sd2)
    return round(2.0 * 0.5 * math.erfc(abs(z) / math.sqrt(2.0)), 6)


def _bh_fdr(pvals: list, alpha: float = 0.05) -> list:
    """Benjamini-Hochberg · returns the survival flag per input index."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    if not m:
        return [False] * len(pvals)
    order = sorted(idx, key=lambda i: pvals[i])
    keep, thresh = [False] * len(pvals), 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= alpha * rank / m:
            thresh = rank
    for rank, i in enumerate(order, 1):
        if rank <= thresh:
            keep[i] = True
    return keep


def analyse(root: Path, market: str) -> dict:
    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}

    horizons = list(PRIMARY_HORIZONS)
    n20 = sum(1 for r in rows if _num(r.get(SUPPLEMENTARY_HORIZON)) is not None)
    if n20 >= 30:
        horizons.append(SUPPLEMENTARY_HORIZON)

    results, tests = {}, []
    for h in horizons:
        pop = [r for r in rows if _num(r.get(h)) is not None]
        if len(pop) < 30:
            continue
        vals = sorted(_num(r.get(h)) for r in pop)
        lo_cut = vals[max(0, int(len(vals) * TAIL_Q) - 1)]
        hi_cut = vals[min(len(vals) - 1, int(len(vals) * (1 - TAIL_Q)))]
        losers = [r for r in pop if _num(r.get(h)) <= lo_cut]
        winners = [r for r in pop if _num(r.get(h)) >= hi_cut]

        dims = {}
        for name, fn in PRIMARY_DIMENSIONS:
            lv = [fn(r) for r in losers]
            wv = [fn(r) for r in winners]
            ln = [v for v in lv if isinstance(v, (int, float))]
            wn = [v for v in wv if isinstance(v, (int, float))]
            if len(ln) >= 5 and len(wn) >= 5:
                p = _mannwhitney_p(ln, wn)
                entry = {
                    "type": "numeric",
                    "loser_n": len(ln), "winner_n": len(wn),
                    "loser_mean": round(sum(ln) / len(ln), 3),
                    "winner_mean": round(sum(wn) / len(wn), 3),
                    "delta_winner_minus_loser": round(
                        sum(wn) / len(wn) - sum(ln) / len(ln), 3),
                    "p_value": p, "tier": tier(min(len(ln), len(wn))),
                }
                dims[name] = entry
                tests.append((market, h, name, p))
            else:
                lc = [v for v in lv if isinstance(v, str)]
                wc = [v for v in wv if isinstance(v, str)]
                if lc and wc:
                    def share(c):
                        t = {}
                        for v in c:
                            t[v] = t.get(v, 0) + 1
                        return {k: round(v / len(c) * 100, 1)
                                for k, v in sorted(t.items(),
                                                   key=lambda kv: -kv[1])}
                    dims[name] = {"type": "categorical",
                                  "loser_n": len(lc), "winner_n": len(wc),
                                  "loser_mix_pct": share(lc),
                                  "winner_mix_pct": share(wc),
                                  "p_value": None,
                                  "tier": tier(min(len(lc), len(wc)))}

        results[h] = {
            "population": _stats([_num(r.get(h)) for r in pop]),
            "loser_cohort": {"cut_at_pct": round(lo_cut, 3),
                             "stats": _stats([_num(r.get(h)) for r in losers]),
                             "signature": _cohort_profile(losers)},
            "winner_cohort": {"cut_at_pct": round(hi_cut, 3),
                              "stats": _stats([_num(r.get(h)) for r in winners]),
                              "signature": _cohort_profile(winners)},
            "dimensions": dims,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_family": FAMILY,
        "mode": "RESEARCH ONLY · no production rule · no threshold changed",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_cohort": len(rows),
        "horizons_analysed": horizons,
        "tail_quantile": TAIL_Q,
        "substrate_limitations": [
            "regime UNAVAILABLE · producer emitted 'unknown' for all 19 "
            "observations · not joined",
            "sector CURRENT-TIME not PIT · exploratory family only",
            "market cap has NO source in the repository · "
            "`liquidity_bucket_60d` is 60d traded value, NOT company size",
            "fundamentals PIT accumulator holds 2 dates (2026-09-03..04)",
            "USA fwd_20d has not matured · India not truncated to match",
        ],
        "results": results,
        "_tests": tests,
    }


def combine(reports: list, alpha: float = 0.05) -> dict:
    """Count every confirmatory trial ONCE, across both markets and all
    horizons, and correct before anything is interpreted."""
    tests = []
    for rep in reports:
        tests.extend(rep.get("_tests") or [])
    pvals = [t[3] for t in tests]
    keep = _bh_fdr(pvals, alpha)
    surv = []
    for (mkt, h, name, p), k in zip(tests, keep):
        if k:
            surv.append({"market": mkt, "horizon": h, "dimension": name,
                         "p_value": p})
    return {
        "experiment_family": FAMILY,
        "alpha": alpha,
        "correction": "Benjamini-Hochberg FDR",
        "n_trials_counted": len(tests),
        "n_survived": len(surv),
        "survivors": sorted(surv, key=lambda d: d["p_value"]),
        "note": ("Surviving a correction makes a dimension a VALIDATION "
                 "CANDIDATE. It is not a production rule: PIT, "
                 "walk-forward and OOS gates still stand between it and "
                 "any change to AEGIS."),
    }


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "cohort"
            / f"mr_dependency_v1_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {k: v for k, v in rep.items() if not k.startswith("_")}
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=FAMILY)
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    reps = []
    for m in ("india", "usa"):
        rep = analyse(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        emit(root, rep)
        reps.append(rep)
        print(f"{FAMILY}:{m} · n={rep['n_cohort']} · horizons="
              f"{rep['horizons_analysed']}")
    comb = combine(reps)
    p = (root / "reports" / "research" / "cohort"
         / "mr_dependency_v1_correction.json")
    p.write_text(json.dumps(comb, indent=2, default=str), encoding="utf-8")
    print(f"  trials counted {comb['n_trials_counted']} · survived FDR "
          f"{comb['n_survived']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
