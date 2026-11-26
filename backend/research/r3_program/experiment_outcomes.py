"""Outcome resolution for the R3 EXPERIMENT track · isolated storage.

WHY THIS IS NOT outcome_resolver
--------------------------------
CEO 2026-10-28 · C4. `outcome_resolver.resolve()` accepts a `ledger=`
argument, so the obvious wiring is to hand it the experiment decisions.
Inspected before wiring, and that is a trap:

    out_p = outcomes_path(root, market)      # outcome_resolver.py:155

The destination is HARDCODED to
reports/research/r3/shadow/outcomes_<market>.jsonl. There is no parameter
to redirect it. Passing the experiment ledger would append experiment
outcomes into the SHADOW track's outcomes file, silently merging two
different decision populations into one analysis - the shadow track's
4,000+ universal abstentions and the experiment's rank-baseline TAKE and
AVOID decisions - and neither analysis could be trusted afterwards.

Second problem found in the same inspection: outcome rows carry
(as_of, ticker, market, horizon_days, fwd_pct, ...) and NO decision_id.
Linkage is therefore (as_of, ticker). That is not sufficient here,
because experiment identity includes the engine version: two policy
versions scoring the same ticker on the same date are different
decisions that would collide on that key.

So this module owns its own storage and its own key. It reuses exactly
one thing from the resolver - `forward_return`, which is pure, has no
I/O, and is already covered by tests. It never references the shadow
path, which makes the isolation structural rather than a promise.

THE KEY IS (decision_id, horizon)
---------------------------------
decision_id already subsumes market, date, ticker and engine version, so
this key cannot collide across policies or markets, and a horizon matures
independently of its siblings.

UNRESOLVED IS A STATE, NOT A ZERO
---------------------------------
A horizon that has not matured is simply absent. It is appended once, on
the first run after its bars exist. Writing 0.0 for an immature horizon
is the single easiest way to manufacture a flattering result.

DECISIONS ARE NEVER TOUCHED
---------------------------
This module opens the decision ledger read-only and writes only to its
own outcomes file. A decision cannot be improved after its result is
known, because nothing here can write to where decisions live.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.r3.experiment.outcomes.v1"

# CEO 2026-10-28 · criterion 5. Bars DO get restated - a split, a
# dividend adjustment, a vendor backfill. The resolver is append-only, so
# a restatement must not be an in-place edit: that would silently change
# a measurement after it had been read, with no trace.
CORRECTION_PATH = (
    "append a NEW outcome row with the same (decision_id, horizon_days), "
    "`supersedes` set to the superseded row's resolved_utc, and "
    "`correction_reason` stating why. Readers take the row with the "
    "latest resolved_utc per key. Nothing is ever edited or deleted, so "
    "the original measurement and the reason it was replaced both stay "
    "auditable. append_correction() is the only writer permitted to "
    "re-use an existing key.")


def latest_by_key(rows: list) -> dict:
    """(decision_id, horizon) -> the effective row.

    Later resolved_utc wins, so a correction supersedes its original
    without either being removed.
    """
    out = {}
    for r in sorted(rows, key=lambda x: str(x.get("resolved_utc") or "")):
        try:
            out[(r.get("decision_id"), int(r.get("horizon_days")))] = r
        except Exception:
            continue
    return out


def append_correction(root: Path, market: str, decision_id: str,
                      horizon_days: int, fwd_pct: float,
                      correction_reason: str) -> dict:
    """The ONLY sanctioned way to restate an already-resolved outcome."""
    if not correction_reason:
        raise ValueError("a correction without a stated reason is not "
                         "auditable · refuse it")
    p = outcomes_path(root, market)
    existing = latest_by_key(_read_jsonl(p)).get(
        (decision_id, int(horizon_days)))
    if existing is None:
        raise ValueError("nothing to correct for (%s, %s)"
                         % (decision_id, horizon_days))
    row = dict(existing)
    row.update({
        "fwd_pct": round(float(fwd_pct), 4),
        "resolved_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "supersedes": existing.get("resolved_utc"),
        "correction_reason": correction_reason,
        "is_correction": True,
    })
    _append_jsonl(p, [row])
    return row

# Reused deliberately · pure function, no I/O, already tested.
from backend.research.r3_program.outcome_resolver import (  # noqa: E402
    forward_return, HORIZONS as _RESOLVER_HORIZONS)
from backend.research.r3_program.shadow_recommender import (  # noqa: E402
    BARS, HORIZONS, ledger_path as _decision_ledger_path, _read_jsonl,
    _append_jsonl)


def _tkey_safe(t) -> str:
    """Bars are stored without the exchange suffix."""
    return str(t).upper().strip().replace(".NS", "").replace(".BO", "")


def outcomes_path(root: Path, market: str) -> Path:
    """Experiment-only · deliberately NOT the shadow path."""
    return (Path(root) / "reports" / "research" / "r3" / "experiment"
            / ("outcomes_%s.jsonl" % str(market).lower()))


_bars_cache: dict = {}


def reset_cache() -> None:
    """Drop the bar cache · required when a process handles >1 root."""
    _bars_cache.clear()


def _bars(root: Path, market: str, ticker: str):
    import pandas as pd
    mk = str(market).lower()
    t = _tkey_safe(ticker)
    # CEO 2026-10-28 · ROOT IS PART OF THE KEY. Without it a process that
    # touches two roots serves the first root's prices for the second
    # one's tickers. Found by a test whose tmp_path tree inherited bars
    # from an earlier test's tmp_path tree - the same collision would
    # happen to any caller resolving two repositories in one run.
    k = (str(Path(root).resolve()), mk, t)
    if k in _bars_cache:
        return _bars_cache[k]
    d = None
    if mk in BARS:
        p = Path(root) / (BARS[mk] % t)
        if p.exists():
            try:
                d = pd.read_parquet(p)
                d.index = pd.to_datetime(d.index)
                d = d.sort_index()
                d.columns = [c.lower() for c in d.columns]
            except Exception:
                d = None
    _bars_cache[k] = d
    return d


def _already(p: Path) -> set:
    have = set()
    for o in _read_jsonl(p):
        try:
            have.add((o.get("decision_id"), int(o.get("horizon_days"))))
        except Exception:
            continue
    return have


def resolve(root: Path, market: str,
            decisions: Optional[list] = None) -> dict:
    """Resolve matured horizons for experiment decisions. Append-only."""
    root = Path(root)
    mk = str(market).lower()

    dec = (decisions if decisions is not None
           else _read_jsonl(_decision_ledger_path(root, mk)))
    if not dec:
        return {"market": mk, "schema_version": SCHEMA_VERSION,
                "resolved_this_run": 0, "decisions": 0,
                "error": "no experiment decisions"}

    out_p = outcomes_path(root, mk)
    have = _already(out_p)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, seen = [], set()
    stats = {"appended": 0, "still_immature": 0, "no_bars": 0,
             "skipped_already": 0}
    # Explicitly represented, never silently dropped. Immature keys are
    # ABSENT from the outcomes ledger - writing a resolved=False row would
    # have to be UPDATED when it matures, which breaks append-only - so
    # they are reported here, per key, with a reason.
    unresolved: dict = {}
    rejected: list = []

    def _unres(did, h, code):
        unresolved.setdefault(code, []).append([did, h])

    seen_ids = set()
    for d in dec:
        did = d.get("decision_id")
        asof = str(d.get("as_of") or "")[:10]
        tic = d.get("ticker")
        # REJECT rather than skip · a decision we cannot key is a defect
        # in the ledger, and silently passing over it would make the
        # expected-key arithmetic wrong without anything saying so.
        if not did:
            rejected.append({"reason": "MISSING_DECISION_ID",
                             "as_of": asof, "ticker": tic})
            continue
        if not asof or not tic:
            rejected.append({"reason": "INCOMPLETE_DECISION_REFERENCE",
                             "decision_id": did, "as_of": asof,
                             "ticker": tic})
            continue
        if did in seen_ids:
            prev = next((x for x in dec if x.get("decision_id") == did), {})
            if (str(prev.get("as_of"))[:10] != asof
                    or str(prev.get("ticker")) != str(tic)):
                rejected.append({"reason": "CONFLICTING_DECISION_REFERENCE",
                                 "decision_id": did})
                continue
        seen_ids.add(did)

        df = _bars(root, mk, tic)
        if df is None:
            stats["no_bars"] += 1
        for h in HORIZONS:
            key = (did, h)
            if key in have or key in seen:
                stats["skipped_already"] += 1
                continue
            if df is None:
                _unres(did, h, "NO_PRICE_SERIES")
                continue
            pct, ok = forward_return(df, asof, h)
            if not ok:
                stats["still_immature"] += 1
                _unres(did, h, "INSUFFICIENT_FUTURE_BARS")
                continue            # absent until matured · never 0.0
            seen.add(key)
            stats["appended"] += 1
            rows.append({
                "schema_version": SCHEMA_VERSION,
                # the link back to the exact decision, engine included
                "decision_id": did,
                "market": mk,
                "ticker": str(tic).upper().strip(),
                "as_of": asof,
                "horizon_days": h,
                "fwd_pct": round(pct, 4),
                "resolved": True,
                # copied from the decision, NOT recomputed · recomputing
                # would let a backtest row drift into prospective
                "evidence_segment": d.get("evidence_segment"),
                "action_at_decision": d.get("action"),
                "engine_version": d.get("engine_version"),
                "resolved_utc": now,
            })

    _append_jsonl(out_p, rows)

    total = _read_jsonl(out_p)
    by_h = {}
    for h in HORIZONS:
        by_h["resolved_%dd" % h] = sum(
            1 for r in total if int(r.get("horizon_days", -1)) == h)
    pending = max(0, len(dec) * len(HORIZONS) - len(total))
    return {
        "market": mk,
        "schema_version": SCHEMA_VERSION,
        "resolved_this_run": len(rows),
        "outcomes_total": len(total),
        "decisions": len(dec),
        "expected_keys": len(dec) * len(HORIZONS),
        "pending_keys": pending,
        **by_h, **stats,
        "unresolved_by_reason": {k: len(v) for k, v in unresolved.items()},
        "n_unresolved": sum(len(v) for v in unresolved.values()),
        "rejected": rejected,
        "n_rejected": len(rejected),
        "path": str(out_p).replace("\\", "/"),
        "isolation": ("writes ONLY to reports/research/r3/experiment/ · the "
                      "shadow outcomes ledger is never opened for writing"),
        "contract": ("keyed (decision_id, horizon) · append-only · an "
                     "immature horizon is ABSENT and reported under "
                     "unresolved_by_reason, never 0.0 · decisions are "
                     "opened read-only and never rewritten"),
        "correction_path": CORRECTION_PATH,
    }


def coverage(root: Path, market: str) -> dict:
    """Resolved vs pending, split by evidence segment.

    Segments are reported separately because pooling them is the one
    thing the protocol forbids.
    """
    root = Path(root)
    mk = str(market).lower()
    dec = _read_jsonl(_decision_ledger_path(root, mk))
    out = _read_jsonl(outcomes_path(root, mk))
    rep = {"market": mk, "decisions": len(dec), "outcomes": len(out)}
    for seg in ("prospective", "backtest"):
        d_seg = [d for d in dec if d.get("evidence_segment") == seg]
        o_seg = [o for o in out if o.get("evidence_segment") == seg]
        rep[seg] = {
            "decisions": len(d_seg),
            "dates": len({d.get("as_of") for d in d_seg}),
            "outcomes": len(o_seg),
            "expected_keys": len(d_seg) * len(HORIZONS),
            "pending_keys": max(0, len(d_seg) * len(HORIZONS) - len(o_seg)),
            **{"resolved_%dd" % h: sum(1 for o in o_seg
                                       if int(o.get("horizon_days", -1)) == h)
               for h in HORIZONS},
        }
    rep["note"] = ("resolvable is not validated · a resolved outcome is a "
                   "measurement, not evidence of skill")
    return rep


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", default="both",
                    choices=["india", "usa", "both"])
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        r = resolve(root, m)
        print("R3-EXP-OUTCOMES:%s · appended %d · total %d · immature %d · "
              "no_bars %d" % (m, r.get("resolved_this_run", 0),
                              r.get("outcomes_total", 0),
                              r.get("still_immature", 0),
                              r.get("no_bars", 0)))
        c = coverage(root, m)
        for seg in ("prospective", "backtest"):
            s = c[seg]
            print("    %-12s decisions %5d over %2d date(s) · outcomes "
                  "%5d · pending %5d" % (seg, s["decisions"], s["dates"],
                                         s["outcomes"], s["pending_keys"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
