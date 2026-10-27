"""Attach realised outcomes to R3 predictions, from live price bars.

THE DEFECT THIS REPLACES
------------------------
`shadow.score_outcomes` resolves outcomes through
`core.load_pop -> load_cohort`, which reads

    reports/research/mr_prediction_autopsy_<market>_enriched.jsonl

a FROZEN research cohort from a prior study. Measured 2026-10-27:

    cohort coverage : 2026-08-04 -> 2026-09-08   (725 rows, 26 dates)
    R3 ledger       : 2026-09-08 -> 2026-10-27   (1724 rows, 38 dates)
    key intersection: 0

The outcome source stopped updating the exact day the ledger began, so
`score_outcomes` has returned `scored: 0` on every run since R3 started.
`outcomes_india.jsonl` has never existed. R3 has never been able to score
a single one of its own predictions.

This resolver computes forward returns directly from the market's own
price bars at each prediction's as-of date, so coverage tracks the ledger
instead of a static file.

WHAT IS PRESERVED
-----------------
The existing contract, exactly:

  * outcomes live in a SEPARATE append-only file keyed (as_of, ticker)
  * the prediction ledger is never read-modify-written, so a prediction
    cannot be quietly improved once its result is known
  * an already-scored (as_of, ticker) is never rewritten

WHAT IS NOT DONE
----------------
No prediction is created, altered or promoted. No specialist changes
disposition. This attaches outcomes to decisions that were already
recorded - nothing more. R3 remains research-only.

UNRESOLVED IS A FIRST-CLASS STATE
---------------------------------
A horizon that has not yet matured is NOT written. It stays absent until
the bars exist, then is appended once. An immature horizon is never
recorded as 0.0 - treating it as a zero return is the single easiest way
to manufacture a flattering result.

THE KEY IS (as_of, ticker, HORIZON) - AND THAT MATTERS
-------------------------------------------------------
A first draft keyed on (as_of, ticker) and skipped any key already
present. That froze maturity permanently: 318 rows had no resolved
horizon at all and 758 were resolved at 5d but not 20d, so 1,076 of
1,724 rows - 62% - could never fill in as their bars arrived. 20-day
coverage would have been pinned at 37.6% forever.

Keying per horizon fixes it without rewriting anything: each
(as_of, ticker, horizon) is appended exactly once, on the first run after
that horizon matures. Predictions stay immutable, outcomes stay
append-only, no key is ever duplicated.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.outcome_resolver.v1"

HORIZONS = (5, 10, 20)

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


def forward_return(df: Optional[pd.DataFrame], asof: str,
                   horizon: int) -> tuple:
    """(pct, resolved) measured close-to-close from the bar AFTER asof.

    Starting at asof+1 is what makes this point-in-time: a decision taken
    on `asof` cannot transact at that day's close.

    `resolved` is False when fewer than `horizon` bars exist after the
    entry bar - the horizon has not matured and no number is invented.
    """
    if df is None:
        return None, False
    w = df[df.index > pd.Timestamp(asof)]
    if len(w) < 2:
        return None, False
    entry = float(w["close"].iloc[0])
    if not entry:
        return None, False
    if len(w) - 1 < horizon:
        return None, False          # not matured · never 0.0
    exit_px = float(w["close"].iloc[horizon])
    return 100.0 * (exit_px - entry) / entry, True


def outcomes_path(root: Path, market: str) -> Path:
    return (Path(root) / "reports" / "research" / "r3" / "shadow"
            / ("outcomes_%s.jsonl" % market.lower()))


def _already_scored(p: Path) -> set:
    have = set()
    if not p.exists():
        return have
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            o = json.loads(line)
            have.add((o.get("as_of"), str(o.get("ticker") or "").upper(),
                      int(o.get("horizon_days"))))
        except Exception:
            continue
    return have


def resolve(root: Path, market: str, ledger: Optional[list] = None) -> dict:
    """Score every unscored prediction. Append-only; never edits a ledger."""
    from backend.research.r3_program import shadow
    root = Path(root)
    led = ledger if ledger is not None else shadow.load_ledger(root, market)
    if not led:
        return {"market": market, "schema_version": SCHEMA_VERSION,
                "scored": 0, "error": "empty ledger"}

    out_p = outcomes_path(root, market)
    have = _already_scored(out_p)

    rows = []
    stats = {"appended": 0, "still_immature": 0, "no_bars": 0}
    seen = set()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in led:
        asof = str(r.get("as_of") or "")[:10]
        tic = _tkey(r.get("ticker"))
        if not asof or not tic:
            continue
        df = _bars(root, market, tic)
        if df is None:
            stats["no_bars"] += 1
        for h in HORIZONS:
            key = (asof, tic, h)
            if key in have or key in seen:
                continue
            pct, ok = forward_return(df, asof, h)
            if not ok:
                stats["still_immature"] += 1
                continue        # absent until it matures · never 0.0
            seen.add(key)
            stats["appended"] += 1
            rows.append({"as_of": asof, "ticker": tic,
                         "market": market.lower(), "horizon_days": h,
                         "fwd_pct": round(pct, 4), "resolved": True,
                         "schema_version": SCHEMA_VERSION,
                         "scored_utc": now})

    if rows:
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with out_p.open("a", encoding="utf-8") as fh:
            for rec in rows:
                fh.write(json.dumps(rec, default=str) + "\n")

    total = len(_already_scored(out_p))
    return {"market": market, "schema_version": SCHEMA_VERSION,
            "scored_this_run": len(rows),
            "already_scored": len(have),
            "total_outcomes": total,
            "ledger_rows": len(led),
            "expected_keys": len(led) * len(HORIZONS),
            **stats,
            "path": str(out_p.relative_to(root)).replace("\\", "/"),
            "contract": ("separate append-only file · predictions are never "
                         "edited after the fact · an unmatured horizon is "
                         "None and resolved=False, never 0.0")}


def coverage(root: Path, market: str) -> dict:
    """How much of the ledger can actually be evaluated, per horizon.

    Coverage is reported as a first-class number because a decision layer
    that abstains on everything, or an evaluation that can score nothing,
    must not be able to look like a success.
    """
    p = outcomes_path(Path(root), market)
    if not p.exists():
        return {"market": market, "outcomes": 0,
                "note": "no outcomes file · nothing has been scored"}
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    from backend.research.r3_program import shadow
    led = shadow.load_ledger(Path(root), market)
    n_pred = len(led) or 1
    out = {"market": market, "outcome_rows": len(rows),
           "predictions": len(led)}
    for h in HORIZONS:
        n = sum(1 for r in rows if int(r.get("horizon_days", -1)) == h)
        out["resolved_%dd" % h] = n
        # coverage is against PREDICTIONS, not rows written - an evaluation
        # that can score nothing must not read as 100%
        out["coverage_%dd_pct" % h] = round(100.0 * n / n_pred, 1)
    out["dates"] = len({r.get("as_of") for r in rows})
    out["tickers"] = len({r.get("ticker") for r in rows})
    return out
