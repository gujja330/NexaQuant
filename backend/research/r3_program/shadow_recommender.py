"""R3 experimental shadow recommendation track · research-only.

WHY THIS EXISTS, AND WHAT IT IS NOT
-----------------------------------
`shadow.py` records an observation per R2 candidate and sets
`r3_action` to the string literal "ABSTAIN". There is no code path in it
that can emit TAKE or AVOID: `_specialist_block` builds every entry with
`contributes: False` hardcoded, so `contributing_specialists` is always
empty and the stated reason ("every specialist is at a non-validated
disposition") is true by construction rather than by measurement.

Audited 2026-10-28: ZERO of the 11 registered specialists has executable
scoring logic. Two attach descriptive facts (R3-A copies confidence/pnl/
holding_days, R3-F copies the CURRENT sector while flagging
pit_sector NOT_AVAILABLE_AT_ASOF). Neither produces a score.

Per the CEO directive of 2026-10-28, no specialist is unfrozen and no
specialist output is manufactured. Instead this module implements the
shadow EXPERIMENT interface plus one transparently specified baseline
policy, kept rigorously distinct from specialist output.

WHAT IT DECIDES ON, AND WHY NOT THE LIFECYCLE
---------------------------------------------
shadow.py reads reports/context/canonical_lifecycle_<market>.json, which
is R2's OUTPUT - 33 India rows, mostly positions already held. A layer
that only sees what R2 already picked cannot run a parallel track; it can
only comment.

This module reads history/<market>/<date>/r2_scores.parquet instead: the
SEALED daily snapshot of the whole scored universe (228 India, 516 USA)
written each morning and never revised. Point-in-time holds by
construction - nothing is reconstructed and today's prices cannot reach
yesterday's ranking.

THE POLICY · R3_EXPERIMENTAL_BASELINE_v1
-----------------------------------------
Per-date cross-sectional rank on `ensemble_score`:

    TAKE    ensemble_score in the top    TAKE_PCT of that date
    AVOID   ensemble_score in the bottom AVOID_PCT of that date
    ABSTAIN everything else, and every failure path

Zero fitted parameters. No probability is invented - the probability
fields stay null exactly as in shadow.py, because a rank rule produces an
ordering, not a calibrated probability.

Its honest limitation, stated up front: this is a RE-RANKING OF R2'S OWN
SCORE. A positive result shows that score is usable for selection. It
does NOT show R3 has independent predictive skill, and must never be
reported as if it did.

Grounded in rank_separation, which measured on this same sealed data that
India's ensemble_score separates monotonically across 5 buckets - with
the caveat that its naive t is inflated ~sqrt(20) by overlapping windows,
which is why evaluation here stays DATE-level.

IMMUTABILITY
------------
Records are append-only and keyed by a deterministic decision_id. A
correction is a NEW record carrying `supersedes`; nothing already written
is ever edited. Re-running a date is a no-op, not a rewrite.

ISOLATION
---------
This module imports nothing from backend.delivery, backend.recommendation
or any execution path, and writes only under
reports/research/r3/experiment/. It cannot reach production even by
accident, and tests assert that structurally.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.experiment.v1"
CONTRACT_ID = "R3_EXPERIMENT_RECOMMENDATION_v1"
ENGINE_VERSION = "R3_EXPERIMENTAL_BASELINE_v1"

# The policy IS these two numbers. Both are configuration, not fitted.
TAKE_PCT = 0.10
AVOID_PCT = 0.10

# Below this the cross-section is too thin for a decile to mean anything.
MIN_UNIVERSE = 30

# A snapshot older than this many calendar days is refused, not used.
MAX_SNAPSHOT_AGE_DAYS = 5

HORIZONS = (5, 10, 20)

ACTIONS = ("TAKE", "AVOID", "ABSTAIN")

# Markets are resolved from the filesystem, never hardcoded per market.
SNAPSHOT_GLOB = "history/%s/*/r2_scores.parquet"
BARS = {"india": "data/raw/india/%s_D1.parquet",
        "usa": "usa/data/raw/us/%s_D1.parquet"}

SCORE_COL = "ensemble_score"


# ── storage ──────────────────────────────────────────────────────────
def ledger_path(root: Path, market: str) -> Path:
    return (Path(root) / "reports" / "research" / "r3" / "experiment"
            / ("recommendations_%s.jsonl" % str(market).lower()))


def clock_start_path(root: Path, market: str) -> Path:
    """WRITE-ONCE record of when the 90-day window actually began.

    CEO 2026-10-28 · B7. The protocol carried only a PLANNED window
    (2026-10-28 -> 2027-01-26), which left the one thing that actually
    matters undefined: the experiment begins when the first eligible
    prospective decision is successfully PERSISTED, not when someone
    wrote a date into a config.

    This file is never overwritten. A re-run that finds it already
    present leaves it exactly as it was, so the start event cannot drift
    forward as the calendar moves or backward if the ledger is rebuilt.
    """
    return (Path(root) / "reports" / "research" / "r3" / "experiment"
            / ("clock_start_%s.json" % str(market).lower()))


def read_clock_start(root: Path, market: str) -> Optional[dict]:
    p = clock_start_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def record_clock_start(root: Path, market: str, rows: list) -> Optional[dict]:
    """Stamp the start event from the first persisted prospective rows.

    Returns the existing event untouched if one is already recorded.
    `rows` must be rows that have just been WRITTEN - the clock starts on
    persistence, not on a decision being computed in memory.
    """
    existing = read_clock_start(root, market)
    if existing is not None:
        return existing
    pros = [r for r in rows if r.get("evidence_segment") == "prospective"]
    if not pros:
        return None
    pros.sort(key=lambda r: (str(r.get("as_of")),
                             str(r.get("decision_utc")),
                             str(r.get("decision_id"))))
    first = pros[0]

    # Planned vs observed · never silently reconciled.
    try:
        from backend.research.r3_program.experiment_protocol import (
            PREREGISTERED_ON, OBSERVATION_DAYS, PROTOCOL_VERSION,
            protocol_hash, observation_end)
        planned_start, planned_end = PREREGISTERED_ON, observation_end()
        pv, ph, days = PROTOCOL_VERSION, protocol_hash(), OBSERVATION_DAYS
    except Exception:
        planned_start = planned_end = pv = ph = None
        days = None

    observed = str(first.get("as_of"))[:10]
    within = (planned_start is not None
              and planned_start <= observed <= planned_end)

    ev = {
        "event": "PROSPECTIVE_EXPERIMENT_START",
        "market": str(market).lower(),
        "observed_start_as_of": observed,
        "observed_start_utc": first.get("decision_utc"),
        "first_decision_id": first.get("decision_id"),
        "first_ticker": first.get("ticker"),
        "n_prospective_rows_at_start": len(pros),
        "engine_version": first.get("engine_version"),
        "protocol_version": pv,
        "protocol_hash_at_start": ph,
        "planned_window": {"start": planned_start, "end": planned_end,
                           "days": days},
        "observed_start_within_planned_window": within,
        "discrepancy": (None if within else
                        "observed start %s falls OUTSIDE the preregistered "
                        "window %s..%s · this requires an explicit protocol "
                        "amendment · preregistration dates must NOT be "
                        "rewritten and decisions must NOT be reclassified "
                        "to make them agree"
                        % (observed, planned_start, planned_end)),
        "immutable": True,
        "note": ("write-once · the 90-day clock starts at this persisted "
                 "decision, not at the planned window's start date"),
    }
    # ATOMIC, create-only. CEO 2026-10-28 · criterion 6. A plain
    # write_text can be interrupted and leave a truncated start event, and
    # two concurrent runs could both pass the `existing is None` check
    # above and then both write. os.open with O_CREAT|O_EXCL makes the
    # creation itself the lock: the second writer fails and re-reads the
    # first one's event instead of overwriting it.
    p = clock_start_path(root, market)
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(ev, indent=2, default=str, ensure_ascii=False)
    tmp = p.with_suffix(".json.tmp%d" % os.getpid())
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return read_clock_start(root, market) or ev
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(blob)
        try:
            # link-then-unlink · fails if the target already exists, so a
            # racing writer cannot clobber an event already in place.
            os.link(str(tmp), str(p))
        except FileExistsError:
            return read_clock_start(root, market) or ev
        except (AttributeError, OSError):
            if p.exists():
                return read_clock_start(root, market) or ev
            os.replace(str(tmp), str(p))
            return ev
    finally:
        try:
            if tmp.exists():
                os.unlink(str(tmp))
        except OSError:
            pass
    return ev


def coverage_path(root: Path, market: str) -> Path:
    """Run coverage over time · a run that records nothing must not look
    identical to a run that never happened."""
    return (Path(root) / "reports" / "research" / "r3" / "experiment"
            / ("coverage_%s.jsonl" % str(market).lower()))


def _read_jsonl(p: Path) -> list:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _append_jsonl(p: Path, rows: list) -> None:
    if not rows:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


# ── identity ─────────────────────────────────────────────────────────
def decision_id(market: str, asof: str, ticker: str,
                engine_version: Optional[str] = None) -> str:
    """Deterministic and immutable.

    Includes the engine version so a different policy on the same
    (market, date, ticker) is a DIFFERENT decision rather than a silent
    overwrite of the first one.

    CEO 2026-10-28 · the default was `engine_version=ENGINE_VERSION`,
    which Python binds ONCE at import. The recorded `engine_version`
    field reads the module attribute at call time, so after a policy bump
    the two disagreed: the row said v2 while its decision_id was still
    hashed from v1. Identity and the version it claims must come from the
    same place, so the default is resolved here, at call time.
    """
    raw = "|".join([str(market).lower(), str(asof)[:10],
                    str(ticker).upper().strip(),
                    engine_version or ENGINE_VERSION])
    return "r3x_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


# ── snapshot discovery ───────────────────────────────────────────────
def snapshot_dates(root: Path, market: str) -> list:
    import glob
    pat = os.path.join(str(root), SNAPSHOT_GLOB % str(market).lower())
    out = []
    for f in glob.glob(pat):
        d = os.path.basename(os.path.dirname(f))
        if len(d) == 10 and d[4] == "-":
            out.append(d)
    return sorted(out)


def load_snapshot(root: Path, market: str, asof: str) -> Optional[pd.DataFrame]:
    p = (Path(root) / "history" / str(market).lower() / str(asof)[:10]
         / "r2_scores.parquet")
    if not p.exists():
        return None
    try:
        d = pd.read_parquet(p)
    except Exception:
        return None
    if SCORE_COL not in d.columns or "ticker" not in d.columns:
        return None
    return d


def _reference_price(root: Path, market: str, ticker: str,
                     asof: str) -> tuple:
    """Last close at or before `asof` · (price, bar_date) or (None, None).

    Strictly <= asof. Using a later bar would leak the future into a
    decision-time field, which is the one error this whole track exists
    to avoid.
    """
    mk = str(market).lower()
    if mk not in BARS:
        return None, None
    t = str(ticker).upper().strip().replace(".NS", "").replace(".BO", "")
    p = Path(root) / (BARS[mk] % t)
    if not p.exists():
        return None, None
    try:
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index)
        d = d.sort_index()
        d.columns = [c.lower() for c in d.columns]
        w = d[d.index <= pd.Timestamp(asof)]
        if not len(w):
            return None, None
        return float(w["close"].iloc[-1]), str(w.index[-1])[:10]
    except Exception:
        return None, None


# ── the policy ───────────────────────────────────────────────────────
def classify(df: pd.DataFrame, take_pct: float = TAKE_PCT,
             avoid_pct: float = AVOID_PCT) -> dict:
    """ticker -> decision dict for one sealed date. Deterministic.

    Rank is computed on the WHOLE cross-section of that date, so a name's
    action depends only on that morning's universe.

    THE FOUR EDGE CASES, DECIDED EXPLICITLY
    ---------------------------------------
    MISSING SCORE     ABSTAIN, reason NO_SCORE, and RECORDED. Dropping the
                      row instead would make the universe silently smaller
                      and the denominator wrong - and a name we could not
                      evaluate would be indistinguishable from one that was
                      never a candidate.

    DUPLICATE TICKER  identical scores collapse to one row. CONFLICTING
                      scores are a data defect: every copy ABSTAINs with
                      DUPLICATE_CONFLICTING_SCORE. Picking one arbitrarily
                      would silently choose which of two truths to act on.

    TIE AT A BOUNDARY the thresholds are applied STRICTLY (> and <), so any
                      name whose score equals the cut ABSTAINs with
                      TIE_AT_BOUNDARY. If two names are numerically
                      identical there is no basis to take one and not the
                      other, and an arbitrary sort order would make the
                      decision depend on row order rather than on evidence.

    SMALL UNIVERSE    handled by the caller: below MIN_UNIVERSE a decile is
                      noise wearing a rule, so the whole date ABSTAINs.

    Ranks and the denominator are computed over SCORED names only, but the
    unscored ones are still returned so every candidate gets a record.
    """
    d = df[["ticker", SCORE_COL]].copy()
    d["ticker"] = d["ticker"].astype(str).str.upper().str.strip()

    out = {}

    # ── duplicates ───────────────────────────────────────────────────
    conflicting = set()
    if d["ticker"].duplicated().any():
        for tkr, grp in d.groupby("ticker"):
            vals = grp[SCORE_COL].dropna().unique()
            if len(vals) > 1:
                conflicting.add(tkr)
        d = d.drop_duplicates(subset=["ticker", SCORE_COL])
        d = d.drop_duplicates(subset=["ticker"], keep="first")
    for tkr in sorted(conflicting):
        out[tkr] = {"action": "ABSTAIN", "rank": None, "n": None,
                    "pct_rank": None, "score": None,
                    "reason_code": "DUPLICATE_CONFLICTING_SCORE"}

    # ── missing scores · recorded, not dropped ───────────────────────
    unscored = d[d[SCORE_COL].isna()]["ticker"].tolist()
    for tkr in unscored:
        if tkr not in out:
            out[tkr] = {"action": "ABSTAIN", "rank": None, "n": None,
                        "pct_rank": None, "score": None,
                        "reason_code": "NO_SCORE"}

    scored = d.dropna(subset=[SCORE_COL])
    scored = scored[~scored["ticker"].isin(out.keys())]
    n = len(scored)
    if n < MIN_UNIVERSE:
        return out          # caller turns this into a whole-date abstention

    scored = scored.sort_values(
        [SCORE_COL, "ticker"], ascending=[False, True]).reset_index(drop=True)
    scored["rank"] = scored.index + 1
    scored["pct_rank"] = scored["rank"] / float(n)

    # Threshold SCORES, not positions · this is what makes ties safe.
    k_take = max(1, int(n * take_pct))
    k_avoid = max(1, int(n * avoid_pct))
    take_cut = float(scored[SCORE_COL].iloc[k_take - 1])
    avoid_cut = float(scored[SCORE_COL].iloc[n - k_avoid])

    for r in scored.itertuples(index=False):
        s = float(getattr(r, SCORE_COL))
        code = None
        if s > take_cut:
            a = "TAKE"
        elif s < avoid_cut:
            a = "AVOID"
        elif s == take_cut or s == avoid_cut:
            # On the cut itself. Unique at the cut -> act; tied -> abstain.
            n_at = int((scored[SCORE_COL] == s).sum())
            if n_at == 1:
                a = "TAKE" if s == take_cut else "AVOID"
                if take_cut == avoid_cut:
                    a, code = "ABSTAIN", "DEGENERATE_CUT_SINGLE_SCORE"
            else:
                a, code = "ABSTAIN", "TIE_AT_BOUNDARY"
        else:
            a, code = "ABSTAIN", "MID_RANK"
        out[str(r.ticker)] = {
            "action": a, "rank": int(r.rank), "n": n,
            "pct_rank": round(float(r.pct_rank), 4), "score": s,
            "reason_code": code,
        }
    return out


def _abstain_record(market: str, asof: str, ticker: str, reason: str,
                    snapshot_id: Optional[str]) -> dict:
    return _record(market, asof, ticker, "ABSTAIN", None, snapshot_id,
                   abstention_reason=reason)


def evidence_segment(asof: str, recorded_on: Optional[str] = None) -> str:
    """PROSPECTIVE iff no outcome existed when the row was written.

    CEO 2026-10-28 · This replaces a fixed-date rule I had first written,
    which was wrong. The question that decides the segment is not "is this
    date before some constant" - it is "had the outcome already happened
    when we recorded the decision".

    A snapshot sealed this morning has no 5d outcome yet, so recording it
    today is genuinely prospective. A snapshot from 2026-09-15 already has
    all three horizons resolved, so recording it today is a backtest no
    matter how point-in-time its INPUTS were.

    Stamped into the record at write time and never recomputed, because
    recomputing it later would silently convert backtest rows into
    prospective ones as the calendar moves.
    """
    from datetime import date as _d
    try:
        a = _d.fromisoformat(str(asof)[:10])
    except Exception:
        return "unknown"
    r = (_d.fromisoformat(str(recorded_on)[:10]) if recorded_on
         else datetime.now(timezone.utc).date())
    return "prospective" if a >= r else "backtest"


def _record(market: str, asof: str, ticker: str, action: str,
            cls: Optional[dict], snapshot_id: Optional[str],
            abstention_reason: Optional[str] = None,
            ref_price: Optional[float] = None,
            ref_price_date: Optional[str] = None,
            risk_flags: Optional[list] = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "decision_id": decision_id(market, asof, ticker),
        "market": str(market).lower(),
        "ticker": str(ticker).upper().strip(),
        "as_of": str(asof)[:10],
        "decision_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        # Where the inputs came from and when they were sealed.
        "market_data_asof": str(asof)[:10],
        "snapshot_id": snapshot_id,
        "snapshot_source": "history/%s/%s/r2_scores.parquet"
                           % (str(market).lower(), str(asof)[:10]),
        # Engine identity · this is NOT a specialist.
        "engine": ENGINE_VERSION,
        "engine_version": ENGINE_VERSION,
        "specialist_id": None,
        "specialist_version": None,
        "output_kind": "EXPERIMENTAL_BASELINE",
        "action": action,
        # Frozen at write time · see evidence_segment(). Only `prospective`
        # rows can support a forward-skill claim.
        "evidence_segment": evidence_segment(asof),
        "reason_code": (cls or {}).get("reason_code"),
        "rationale": ({
            "policy": "per-date cross-sectional rank on %s" % SCORE_COL,
            "take_pct": TAKE_PCT, "avoid_pct": AVOID_PCT,
            "rank": cls.get("rank"), "universe_n": cls.get("n"),
            "pct_rank": cls.get("pct_rank"),
            "score": cls.get("score"),
        } if cls else None),
        "feature_refs": [SCORE_COL] if cls else [],
        "abstention_reason": abstention_reason,
        "risk_flags": risk_flags or [],
        "reference_price": ref_price,
        "reference_price_date": ref_price_date,
        "reference_price_source": ("last close at or before as_of"
                                   if ref_price is not None else None),
        "horizons": list(HORIZONS),
        # Null, never 0.0 · a rank rule emits an ordering, not a
        # calibrated probability. Zero would read as a confident forecast.
        "take_probability": None,
        "avoid_probability": None,
        "abstain_probability": None,
        "status": "RECORDED",
        "supersedes": None,
        "production_impact": "NONE · research only · never an order",
        "validation_status": "EXPERIMENTAL · UNVALIDATED",
    }


# ── the run ──────────────────────────────────────────────────────────
def decide_date(root: Path, market: str, asof: str) -> dict:
    """Every eligible opportunity on one sealed date. Pure · no writes."""
    root = Path(root)
    mk = str(market).lower()
    snap = load_snapshot(root, mk, asof)
    if snap is None:
        return {"market": mk, "as_of": asof, "records": [],
                "refused": "SNAPSHOT_MISSING_OR_MALFORMED"}

    try:
        age = (datetime.now(timezone.utc).date()
               - datetime.strptime(str(asof)[:10], "%Y-%m-%d").date()).days
    except Exception:
        return {"market": mk, "as_of": asof, "records": [],
                "refused": "ASOF_UNPARSEABLE"}

    snapshot_id = "%s:%s:%drows" % (mk, str(asof)[:10], len(snap))
    cls = classify(snap)
    ranked = any(c.get("n") for c in cls.values())
    candidates = sorted({str(t).upper().strip()
                         for t in snap["ticker"].astype(str).tolist()})

    if not ranked:
        # Fail SAFE: a thin universe abstains on the record · it does not
        # emit deciles of a 4-name cross-section. Every candidate still
        # gets a row, so the date is visible rather than simply absent.
        recs = [_abstain_record(mk, asof, t, "UNIVERSE_BELOW_MINIMUM_%d"
                                % MIN_UNIVERSE, snapshot_id)
                for t in candidates]
        return {"market": mk, "as_of": asof, "records": recs,
                "refused": "UNIVERSE_BELOW_MINIMUM"}

    records = []
    for ticker in candidates:
        c = cls.get(ticker)
        if c is None:
            records.append(_abstain_record(mk, asof, ticker,
                                           "NOT_CLASSIFIED", snapshot_id))
            continue
        flags = []
        if age > MAX_SNAPSHOT_AGE_DAYS:
            flags.append("SNAPSHOT_AGE_%dd" % age)
        px, pxd = _reference_price(root, mk, ticker, asof)
        if px is None:
            flags.append("NO_REFERENCE_PRICE")
        records.append(_record(
            mk, asof, ticker, c["action"], c, snapshot_id,
            abstention_reason=(None if c["action"] != "ABSTAIN"
                               else (c.get("reason_code") or "MID_RANK")),
            ref_price=px, ref_price_date=pxd, risk_flags=flags))
    return {"market": mk, "as_of": asof, "records": records, "refused": None}


def run(root: Path, market: str, dates: Optional[list] = None) -> dict:
    """Record decisions for every sealed date not already recorded.

    Append-only and idempotent: a (market, as_of, ticker, engine) already
    present is skipped, never rewritten.
    """
    root = Path(root)
    mk = str(market).lower()
    p = ledger_path(root, mk)
    have = {r.get("decision_id") for r in _read_jsonl(p)}

    all_dates = dates if dates is not None else snapshot_dates(root, mk)
    new, stats = [], {"dates_seen": 0, "dates_recorded": 0,
                      "dates_skipped_already": 0, "dates_refused": 0,
                      "TAKE": 0, "AVOID": 0, "ABSTAIN": 0}
    refusals = {}
    for d in all_dates:
        stats["dates_seen"] += 1
        res = decide_date(root, mk, d)
        if res["refused"] and not res["records"]:
            stats["dates_refused"] += 1
            refusals[d] = res["refused"]
            continue
        fresh = [r for r in res["records"] if r["decision_id"] not in have]
        if not fresh:
            stats["dates_skipped_already"] += 1
            continue
        for r in fresh:
            stats[r["action"]] += 1
            have.add(r["decision_id"])
        new.extend(fresh)
        stats["dates_recorded"] += 1

    _append_jsonl(p, new)

    total = _read_jsonl(p)

    # The clock starts on PERSISTENCE · stamped after the append above
    # succeeded, from the LEDGER rather than from `new`.
    #
    # CEO 2026-10-28 · stamping only from `new` left a hole: the first 228
    # India prospective rows were persisted at 08:15:59Z before this
    # feature existed, so every later run saw new=[] and the clock was
    # never recorded at all. Reading the ledger is not retrospective
    # invention - each row carries the decision_utc at which it was
    # actually written, which is precisely the start event. Still
    # write-once, so this can only ever fill an absent clock.
    clock = read_clock_start(root, mk)
    if clock is None:
        clock = record_clock_start(root, mk, total)
    rep = {
        "engine": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "market": mk,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorded_this_run": len(new),
        "ledger_total": len(total),
        "distinct_dates_in_ledger": len({r.get("as_of") for r in total}),
        "prospective_rows": sum(1 for r in total
                                if r.get("evidence_segment") == "prospective"),
        "prospective_dates": len({r.get("as_of") for r in total
                                  if r.get("evidence_segment")
                                  == "prospective"}),
        "clock_started": bool(clock),
        "clock_start_utc": (clock or {}).get("observed_start_utc"),
        "refusals": refusals,
        "evidence_class": evidence_class(len({r.get("as_of")
                                              for r in total})),
        "production_impact": "NONE · research only",
        "validation_status": "EXPERIMENTAL · UNVALIDATED",
        **stats,
    }
    _append_jsonl(coverage_path(root, mk), [rep])
    return rep


MIN_DATES_CONFIRMATORY = 20


def evidence_class(n_dates: int) -> str:
    """Date units, never rows · the programme's binding constraint."""
    return ("CONFIRMATORY-ELIGIBLE" if n_dates >= MIN_DATES_CONFIRMATORY
            else "EXPLORATORY")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", default="both",
                    choices=["india", "usa", "both"])
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    markets = ["india", "usa"] if a.market == "both" else [a.market]
    for m in markets:
        rep = run(root, m)
        print("R3-EXPERIMENT:%s · recorded %d · ledger %d over %d date(s) · "
              "%s" % (m, rep["recorded_this_run"], rep["ledger_total"],
                      rep["distinct_dates_in_ledger"], rep["evidence_class"]))
        print("    TAKE %d · AVOID %d · ABSTAIN %d · refused dates %d"
              % (rep["TAKE"], rep["AVOID"], rep["ABSTAIN"],
                 rep["dates_refused"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
