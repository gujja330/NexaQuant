"""Does the R2 score SEPARATE good trades from bad ones?

THE DECISIVE QUESTION
---------------------
Per the 2026-10-27 directive: "test whether the top-ranked bucket
actually outperforms the next bucket on unseen data. If the ranking
cannot separate the two reliably, it is not yet useful for selecting the
best trades."

Everything in Stage 3 ("rank the survivors") depends on the answer. If
the score carries no information about forward returns, then no gate, no
weighting and no additional dimension can rescue it - they would all be
ranking with a ruler that does not measure.

WHY THIS CAN BE ANSWERED NOW, AND HONESTLY
------------------------------------------
`history/<market>/<date>/r2_scores.parquet` is a SEALED daily snapshot:
every ticker's ensemble_score as it stood at decision time, written that
morning and never revised. So the score is genuinely point-in-time -
there is no reconstruction, no inference about what was available, and
no opportunity for today's prices to leak into yesterday's ranking.

India has 32 such snapshots (2026-09-11 -> 2026-10-26). That is 32 DATE
UNITS, above the programme's 20-date floor - the first test in this
programme that clears it on sealed data rather than on row count.

THE STATISTIC, AND WHY NOT A SIMPLER ONE
----------------------------------------
Per-date Spearman rank correlation between score and forward return -
the information coefficient. Then inference across DATES, never across
rows.

Pooling 228 x 32 = 7296 rows and computing one correlation would give a
t-statistic inflated by roughly sqrt(228), because every name on a given
day shares that day's market move. The market factor is the dominant
term in any single day's cross-section. Measuring IC within each date
removes it by construction, and treating each date as one observation is
what makes the error bar honest.

Bucket means are reported too, because an IC can be positive while the
relationship is non-monotonic - and it is the TOP bucket versus the NEXT
bucket that the directive actually asks about.

Decides nothing. Promotes nothing. Production scoring untouched.
"""
from __future__ import annotations

import glob
import json
import math
import statistics as st
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.rank_separation.v1"

HORIZONS = (10, 20, 30)
N_BUCKETS = 5
SCORE_COLS = ("ensemble_score", "calibrated_confidence",
              "regime_adjusted_confidence")

BARS = {"india": "data/raw/india/%s_D1.parquet",
        "usa": "usa/data/raw/us/%s_D1.parquet"}

_cache: dict = {}


def _tkey(t) -> str:
    return str(t).upper().strip().replace(".NS", "").replace(".BO", "")


def _bars(root: Path, market: str, ticker: str) -> Optional[pd.DataFrame]:
    k = (market, _tkey(ticker))
    if k in _cache:
        return _cache[k]
    p = Path(root) / (BARS[market] % _tkey(ticker))
    d = None
    if p.exists():
        try:
            d = pd.read_parquet(p)
            d.index = pd.to_datetime(d.index)
            d = d.sort_index()
            d.columns = [c.lower() for c in d.columns]
        except Exception:
            d = None
    _cache[k] = d
    return d


def _fwd(df: Optional[pd.DataFrame], asof: str, h: int) -> Optional[float]:
    """Close-to-close from the bar AFTER asof · never includes asof."""
    if df is None:
        return None
    w = df[df.index > pd.Timestamp(asof)]
    if len(w) < 2:
        return None
    a = float(w["close"].iloc[0])
    b = float(w["close"].iloc[min(h, len(w) - 1)])
    return 100.0 * (b - a) / a if a else None


def _spearman(xs: list, ys: list) -> Optional[float]:
    n = len(xs)
    if n < 8:
        return None

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return (num / (dx * dy)) if dx and dy else None


def snapshots(root: Path, market: str) -> list:
    out = []
    for f in sorted(glob.glob(str(Path(root) / "history" / market
                                  / "*" / "r2_scores.parquet"))):
        d = Path(f).parent.name
        try:
            date.fromisoformat(d) if False else None
        except Exception:
            pass
        out.append((d, f))
    return out


from datetime import date  # noqa: E402  (used in snapshots guard above)


def measure(root: Path, market: str, score_col: str = "ensemble_score",
            horizon: int = 20) -> dict:
    snaps = snapshots(root, market)
    per_date, buckets_acc = [], {i: [] for i in range(N_BUCKETS)}
    skipped = []

    for asof, path in snaps:
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            skipped.append({"asof": asof, "why": str(e)[:80]})
            continue
        if score_col not in df.columns:
            skipped.append({"asof": asof, "why": "no %s" % score_col})
            continue

        xs, ys = [], []
        for _, r in df.iterrows():
            s = r.get(score_col)
            if s is None or pd.isna(s):
                continue
            fwd = _fwd(_bars(root, market, r.get("ticker")), asof, horizon)
            if fwd is None:
                continue
            xs.append(float(s))
            ys.append(fwd)
        if len(xs) < 20:
            skipped.append({"asof": asof, "why": "only %d measurable"
                            % len(xs)})
            continue

        ic = _spearman(xs, ys)
        # bucket by score within the date · bucket 0 = HIGHEST score
        order = sorted(range(len(xs)), key=lambda i: -xs[i])
        size = max(1, len(order) // N_BUCKETS)
        bmeans = {}
        for b in range(N_BUCKETS):
            lo = b * size
            hi = (b + 1) * size if b < N_BUCKETS - 1 else len(order)
            idx = order[lo:hi]
            if not idx:
                continue
            bm = sum(ys[i] for i in idx) / len(idx)
            bmeans[b] = bm
            buckets_acc[b].append(bm)
        uni_mean = sum(ys) / len(ys)
        per_date.append({"asof": asof, "n": len(xs), "ic": ic,
                         "universe_mean_fwd_pct": round(uni_mean, 4),
                         "bucket_means": {str(k): round(v, 4)
                                          for k, v in bmeans.items()},
                         "top_minus_next": (
                             round(bmeans[0] - bmeans[1], 4)
                             if 0 in bmeans and 1 in bmeans else None)})

    if not per_date:
        return {"error": "no measurable snapshots", "skipped": skipped[:8]}

    ics = [d["ic"] for d in per_date if d["ic"] is not None]
    tmn = [d["top_minus_next"] for d in per_date
           if d["top_minus_next"] is not None]

    def _t(v):
        if len(v) < 3:
            return None
        sd = st.stdev(v)
        return round(st.mean(v) / (sd / math.sqrt(len(v))), 3) if sd else None

    def _nonoverlap(v, step):
        """Every step-th observation · forward windows cannot overlap."""
        return v[::max(1, step)]

    def _newey_west_t(v, lag):
        """t-stat with autocorrelation up to `lag` acknowledged.

        CEO 2026-10-27 · WHY THIS IS NOT OPTIONAL HERE.
        The snapshots are DAILY and the forward window is `horizon` days,
        so consecutive dates share horizon-1 of their horizon days of
        return. Their ICs are therefore strongly autocorrelated, and the
        naive t-stat divides by an error bar computed as if each date
        were independent. On 29 daily dates at a 20-day horizon that
        inflates t by roughly sqrt(20).

        A high naive t here would say almost nothing about whether the
        score predicts - it would mostly restate that 29 overlapping
        windows describe nearly the same stretch of market.
        """
        n = len(v)
        if n < 4:
            return None
        mu = st.mean(v)
        dev = [x - mu for x in v]
        g0 = sum(d * d for d in dev) / n
        var = g0
        for L in range(1, min(lag, n - 1) + 1):
            g = sum(dev[i] * dev[i + L] for i in range(n - L)) / n
            var += 2.0 * (1.0 - L / (lag + 1.0)) * g
        if var <= 0:
            return None
        return round(mu / math.sqrt(var / n), 3)

    bucket_summary = {}
    for b in range(N_BUCKETS):
        v = buckets_acc[b]
        if v:
            bucket_summary[str(b)] = {"n_dates": len(v),
                                      "mean_fwd_pct": round(st.mean(v), 4)}

    # monotonic if each bucket beats the next
    means = [bucket_summary[str(b)]["mean_fwd_pct"]
             for b in range(N_BUCKETS) if str(b) in bucket_summary]
    monotonic = all(means[i] >= means[i + 1] for i in range(len(means) - 1))

    return {
        "market": market, "score_col": score_col, "horizon_days": horizon,
        "n_date_units": len(per_date),
        "date_range": [per_date[0]["asof"], per_date[-1]["asof"]],
        "mean_ic": round(st.mean(ics), 4) if ics else None,
        "median_ic": round(st.median(ics), 4) if ics else None,
        "ic_t_stat_naive_OVERLAPPING": _t(ics),
        "ic_t_stat_newey_west": _newey_west_t(ics, horizon),
        "ic_nonoverlapping": {
            "n_independent_dates": len(_nonoverlap(ics, horizon)),
            "mean_ic": (round(st.mean(_nonoverlap(ics, horizon)), 4)
                        if _nonoverlap(ics, horizon) else None),
            "t_stat": _t(_nonoverlap(ics, horizon)),
        },
        "effective_independent_dates_est": round(len(ics) / max(1, horizon), 2),
        "pct_dates_ic_positive": (round(100.0 * sum(1 for x in ics if x > 0)
                                        / len(ics), 1) if ics else None),
        "top_minus_next_mean_pp": round(st.mean(tmn), 4) if tmn else None,
        "top_minus_next_t_naive_OVERLAPPING": _t(tmn),
        "top_minus_next_t_newey_west": _newey_west_t(tmn, horizon),
        "pct_dates_top_beats_next": (round(100.0 * sum(1 for x in tmn if x > 0)
                                           / len(tmn), 1) if tmn else None),
        "buckets_0_is_highest_score": bucket_summary,
        "monotonic_in_score": bool(monotonic),
        "n_skipped": len(skipped),
        "governance": {
            "changes_production": False,
            "evidence_tier": "PIT SEALED · DATE-LEVEL INFERENCE",
            "note": ("Inference is across %d DATES, not %d rows. A pooled "
                     "row-level t-stat would be inflated by the market "
                     "factor every name on a day shares. The DAILY dates "
                     "then overlap at a %d-day horizon, so the naive "
                     "across-date t-stat is itself inflated by roughly "
                     "sqrt(%d) - read ic_t_stat_newey_west and "
                     "ic_nonoverlapping instead."
                     % (len(per_date), sum(d["n"] for d in per_date),
                        horizon, horizon)),
        },
        "per_date": per_date,
    }


def run(root: Path, market: str) -> dict:
    out = {"schema_version": SCHEMA_VERSION, "market": market,
           "generated_utc": datetime.utcnow().isoformat(timespec="seconds"),
           "production_authority": False, "results": {}}
    for col in SCORE_COLS:
        for h in HORIZONS:
            out["results"]["%s@%dd" % (col, h)] = measure(root, market, col, h)
    return out


def write(root: Path, market: str, payload: dict) -> Path:
    p = (Path(root) / "reports" / "research" / "r3"
         / ("rank_separation_%s.json" % market))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p
