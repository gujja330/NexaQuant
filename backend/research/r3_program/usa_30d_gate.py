"""USA 30-day horizon · the one live candidate, measured against its gate.

THE CANDIDATE
-------------
Of everything measured in three months, this is the only signal with a
pulse. Every USA entry held a fixed horizon with NO stop and NO target,
against the S&P 500 over the same window:

    10d   alpha -0.59%   beats index 46.0%
    20d   alpha -0.09%   beats index 50.2%
    30d   alpha +0.98%   beats index 59.9%   median +2.84%

It improves with horizon, which is the opposite of India (-1.53% at
30d, beating the index 35.9% of the time).

WHY IT IS NOT A RESULT YET
--------------------------
It rests on 18 distinct ENTRY DATES. Rows are not evidence: 237 entries
across 18 dates is 18 effective observations wearing 237 names, and the
programme's floor is 20. This is the same wall every R3 verdict has died
on, and lowering it to fit would be the "manufacture readiness" move
governance forbids.

THE GATE  (docs/AEGIS/PLAN_EVIDENCE_FIRST_2026-10-26.md)
--------------------------------------------------------
    by 2026-12-31, with selection FROZEN:
      >= 20 clean entry-date units
      out-of-sample alpha > 0 at the chosen horizon
      beat-index rate > 55%

Failing that, the strategy layer is retired and rebuilt - not tuned.

WHAT THIS MODULE DOES
---------------------
Measures where the candidate stands against that gate, every day, and
writes it where it can be read from the repo. It decides nothing and
promotes nothing.

Two null tests guard against reading noise as signal:

  WITHIN-DATE PERMUTATION - shuffle which tickers were picked inside
    each entry date, keeping the date structure intact. If the real
    alpha is not extreme against that distribution, the "signal" is
    just the days we happened to be in the market.

  DATE-BLOCK BOOTSTRAP - resample whole entry DATES with replacement,
    never individual rows, because rows inside a date are correlated by
    the market factor they share.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.usa_30d_gate.v1"

HORIZON_DAYS = 30
GATE_DATE = "2026-12-31"
GATE_MIN_DATE_UNITS = 20
GATE_MIN_BEAT_PCT = 55.0
N_PERMUTATIONS = 2000
N_BOOTSTRAP = 2000
SEED = 20261027

BARS = "usa/data/raw/us/%s_D1.parquet"
INDEX = "usa/data/raw/us/_IDX_GSPC_D1.parquet"

_cache: dict = {}


def _tkey(t) -> str:
    return str(t).upper().strip()


def _bars(root: Path, ticker: str) -> Optional[pd.DataFrame]:
    k = _tkey(ticker)
    if k in _cache:
        return _cache[k]
    p = Path(root) / (BARS % k)
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


def _fwd(df: Optional[pd.DataFrame], entry: str, h: int) -> Optional[float]:
    """Close-to-close from the bar AFTER entry · no lookahead."""
    if df is None:
        return None
    w = df[df.index > pd.Timestamp(entry)]
    if len(w) < 2:
        return None
    a = float(w["close"].iloc[0])
    b = float(w["close"].iloc[min(h, len(w) - 1)])
    return 100.0 * (b - a) / a if a else None


def load_entries(root: Path) -> list:
    """Every USA entry · closed AND open. Open positions must be included
    or the sample is survivors only."""
    p = Path(root) / "reports" / "context" / "canonical_lifecycle_usa.json"
    if not p.exists():
        return []
    lc = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for e in (lc.get("exits") or []):
        if e.get("record_type") == "REALIZED EXIT" and e.get("entry_date"):
            out.append({"ticker": _tkey(e.get("ticker")),
                        "entry_date": str(e["entry_date"])[:10],
                        "state": "closed"})
    for c in (lc.get("current") or []):
        if c.get("entry_date"):
            out.append({"ticker": _tkey(c.get("ticker")),
                        "entry_date": str(c["entry_date"])[:10],
                        "state": "open"})
    return out


def measure(root: Path, horizon: int = HORIZON_DAYS) -> dict:
    """Alpha vs the index at `horizon`, with both null tests."""
    ent = load_entries(root)
    ip = Path(root) / INDEX
    if not ip.exists():
        return {"error": "index bars missing: %s" % INDEX}
    idx = pd.read_parquet(ip)
    idx.index = pd.to_datetime(idx.index)
    idx = idx.sort_index()
    idx.columns = [c.lower() for c in idx.columns]

    # universe per date, for the within-date permutation null
    uni = sorted({e["ticker"] for e in ent})
    rows = []
    for e in ent:
        r = _fwd(_bars(root, e["ticker"]), e["entry_date"], horizon)
        b = _fwd(idx, e["entry_date"], horizon)
        if r is None or b is None:
            continue
        rows.append({**e, "ret": r, "bench": b, "alpha": r - b})
    if not rows:
        return {"error": "no measurable entries"}

    dates = sorted({r["entry_date"] for r in rows})
    alpha = [r["alpha"] for r in rows]
    mean_alpha = sum(alpha) / len(alpha)
    beat = 100.0 * sum(1 for a in alpha if a > 0) / len(alpha)

    # ── within-date permutation null ──────────────────────────────────
    # Precompute alpha for every (ticker, entry-date) in the pool ONCE.
    # Recomputing inside the permutation loop would be 2000 x dates x
    # picks forward-return calls - minutes of work for an identical
    # answer. Permutations then just resample this matrix.
    rnd = random.Random(SEED)
    by_date: dict = {}
    for r in rows:
        by_date.setdefault(r["entry_date"], []).append(r)

    pool: dict = {}
    for d, rs in by_date.items():
        b = rs[0]["bench"]
        vals = []
        for t in uni:
            v = _fwd(_bars(root, t), d, horizon)
            if v is not None:
                vals.append(v - b)
        pool[d] = vals

    perm_means = []
    for _ in range(N_PERMUTATIONS):
        tot, n = 0.0, 0
        for d, rs in by_date.items():
            avail = pool.get(d) or []
            if not avail:
                continue
            k = min(len(rs), len(avail))
            for a in rnd.sample(avail, k):
                tot += a
                n += 1
        if n:
            perm_means.append(tot / n)
    p_perm = None
    if perm_means:
        p_perm = sum(1 for x in perm_means if x >= mean_alpha) / len(perm_means)

    # ── SECOND NULL · vs the FULL tradable universe ───────────────────
    # The null above draws from `uni` - the names the system actually
    # picked at some point. So it answers a NARROW question: given the set
    # of names this system likes, does choosing particular ones on
    # particular days carry information?
    #
    # It cannot see an edge in the LIKED SET ITSELF. If the universe
    # filter is good but the daily ranking inside it is noise, null A
    # would report noise while real value sat in the filter.
    #
    # So this draws from every ticker with bars, asking the broader
    # question: does the system's selection beat picking at random from
    # the market on the same days?
    allp = sorted({f.stem.split("_")[0].upper()
                   for f in (Path(root) / "usa" / "data" / "raw" / "us")
                   .glob("*_D1.parquet")
                   if not f.stem.startswith("_IDX")})
    pool_all: dict = {}
    for d, rs in by_date.items():
        b = rs[0]["bench"]
        vals = []
        for t in allp:
            v = _fwd(_bars(root, t), d, horizon)
            if v is not None:
                vals.append(v - b)
        pool_all[d] = vals
    uni_means = []
    for _ in range(N_PERMUTATIONS):
        tot, n = 0.0, 0
        for d, rs in by_date.items():
            avail = pool_all.get(d) or []
            if not avail:
                continue
            for a in rnd.sample(avail, min(len(rs), len(avail))):
                tot += a
                n += 1
        if n:
            uni_means.append(tot / n)
    p_uni = None
    if uni_means:
        p_uni = sum(1 for x in uni_means if x >= mean_alpha) / len(uni_means)

    # ── date-block bootstrap ──────────────────────────────────────────
    boots = []
    for _ in range(N_BOOTSTRAP):
        pick = [rnd.choice(dates) for _ in dates]
        vals = [r["alpha"] for d in pick for r in by_date.get(d, [])]
        if vals:
            boots.append(sum(vals) / len(vals))
    boots.sort()
    ci = None
    if boots:
        ci = [round(boots[int(0.025 * len(boots))], 4),
              round(boots[int(0.975 * len(boots)) - 1], 4)]

    n_dates = len(dates)
    passes = (n_dates >= GATE_MIN_DATE_UNITS and mean_alpha > 0
              and beat > GATE_MIN_BEAT_PCT
              and (ci is not None and ci[0] > 0))
    return {
        "horizon_days": horizon,
        "n_entries": len(rows),
        "n_entry_date_units": n_dates,
        "first_date": dates[0], "last_date": dates[-1],
        "mean_alpha_pct": round(mean_alpha, 4),
        "median_alpha_pct": round(sorted(alpha)[len(alpha) // 2], 4),
        "beat_index_pct": round(beat, 2),
        "permutation_p_value": (round(p_perm, 4)
                                if p_perm is not None else None),
        "permutation_p_vs_full_universe": (round(p_uni, 4)
                                           if p_uni is not None else None),
        "n_universe_pool": len(allp),
        "date_block_ci95": ci,
        "gate": {
            "deadline": GATE_DATE,
            "min_date_units": GATE_MIN_DATE_UNITS,
            "min_beat_pct": GATE_MIN_BEAT_PCT,
            "date_units_short_by": max(0, GATE_MIN_DATE_UNITS - n_dates),
            "alpha_positive": bool(mean_alpha > 0),
            "beat_above_threshold": bool(beat > GATE_MIN_BEAT_PCT),
            "ci_excludes_zero": bool(ci is not None and ci[0] > 0),
            "VERDICT": "PASS" if passes else "NOT YET",
        },
        "governance": {
            "changes_production": False,
            "evidence_tier": "CANDIDATE UNDER TEST",
            "note": ("Rows are not evidence. %d entries across %d entry "
                     "dates is %d effective observations. Promotion needs "
                     "the gate, not a larger row count."
                     % (len(rows), n_dates, n_dates)),
        },
    }


def run(root: Path) -> dict:
    out = {"schema_version": SCHEMA_VERSION,
           "generated_utc": datetime.utcnow().isoformat(timespec="seconds"),
           "production_authority": False,
           "horizons": {}}
    for h in (10, 20, 30):
        out["horizons"][str(h)] = measure(root, h)
    out["primary"] = out["horizons"][str(HORIZON_DAYS)]
    return out


def write(root: Path, payload: dict) -> Path:
    p = Path(root) / "reports" / "research" / "r3" / "usa_30d_gate.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p
