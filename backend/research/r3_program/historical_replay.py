"""R3 HISTORICAL REPLAY v1 — the first cross-domain evidence replay.

WHAT THIS IS
------------
The pipeline that turns sealed memory-v2 snapshots into a governed research
dataset, and then refuses to draw conclusions the dataset cannot support.

It is deliberately built so that the GATES run even when the evidence is thin.
A replay harness that only works once there is plenty of data is a harness that
has never been tested against its own failure mode; the interesting behaviour
here is what happens at three dates, not at three hundred.

THE UNIT
--------
MARKET x AS_OF x TICKER. Rows are names. Dates are bets. Every count reported
here carries `effective_date_units` alongside `n_rows`, because the two have
differed by two orders of magnitude in every wave of this programme and the row
count is the one that flatters.

WHAT IT WILL NOT DO
-------------------
No model training, no promotion, no production write, no threshold invented to
clear a gate. When date depth is insufficient the disposition is
BLOCKED_INSUFFICIENT_DATE_DEPTH and the accumulation continues.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

SCHEMA_VERSION = "aegis.r3.historical_replay.v1"

# §13 evidence clock. Tiers are in EFFECTIVE DATE UNITS, never rows.
TIERS = ((5, "OBSERVATION"), (15, "HYPOTHESIS"), (30, "RESEARCH SIGNAL"),
         (50, "STRONGER EVIDENCE"), (10 ** 9, "VALIDATION CANDIDATE"))

# §11 chronological validation needs enough independent dates to hold out a
# test block after a 5-day embargo. Below this, OOS is not attempted.
EMBARGO_DAYS = 5
MIN_DATES_FOR_OOS = 20

SEVERE_BANDS = (-3.0, -5.0, -8.0)


def tier_for(n_dates: int) -> str:
    for lim, name in TIERS:
        if n_dates < lim:
            return name
    return "VALIDATION CANDIDATE"


# ── §1 INVENTORY ──────────────────────────────────────────────────────
def inventory(root: Path) -> dict:
    """Every durable memory-v2 snapshot, with each family classified.

    Availability is read from the seal, never inferred from a file existing.
    """
    from backend.research.r3_program.evidence_vector import (
        assemble, replay_ready, FAMILIES)
    from backend.memory.daily_snapshot import load, verify_seal, snapshot_dir

    root = Path(root)
    out: dict = {"schema_version": SCHEMA_VERSION, "markets": {}}
    for market in ("india", "usa"):
        d = root / "history" / market
        days = sorted(p.name for p in d.iterdir()
                      if p.is_dir() and (p / "SEALED").exists()) if d.exists() else []
        rows = []
        for a in days:
            ev = assemble(root, market, date.fromisoformat(a))
            gate = replay_ready(root, market, date.fromisoformat(a))
            seal_ok, seal_msg = verify_seal(root, market, a)
            snap = load(root, market, a) or {}
            sd = snapshot_dir(root, market, a)
            rows.append({
                "market": market, "as_of": a,
                "run_id": "%s:%s" % (market, a),
                "families": {f: ev.families[f]["status"] for f in FAMILIES},
                "family_reasons": {f: ev.families[f].get("reason") for f in FAMILIES},
                "seal_status": "VERIFIED" if seal_ok else seal_msg.split(":")[0],
                "schema_status": snap.get("schema_version"),
                "feature_schema_fingerprint": (snap.get("fingerprints") or {}).get(
                    "feature_schema_fingerprint"),
                "sidecars": sorted(p.name for p in sd.iterdir() if p.is_file()),
                "replay_ready": gate["R3_HISTORICAL_REPLAY_READY"],
                "blockers": gate["blockers"],
                "usable_families": len(ev.usable_families()),
            })
        out["markets"][market] = {
            "sealed_days": len(days),
            "replay_ready_days": sum(1 for r in rows if r["replay_ready"]),
            "detail": rows,
        }
    return out


# ── §5 DATA-QUALITY GATE ──────────────────────────────────────────────
def quality_gate(df: pd.DataFrame) -> dict:
    """Measured, not asserted. Runs BEFORE any statistical test."""
    from backend.research.r3_program.replay_dataset import HORIZONS
    if df.empty:
        return {"rows": 0, "verdict": "EMPTY"}
    q: dict = {
        "rows": int(len(df)),
        "tickers": int(df["ticker"].nunique()),
        "prediction_dates": int(df["prediction_as_of"].nunique()),
        "markets": sorted(df["market"].unique().tolist()),
        # THE NUMBER THAT MATTERS. market x as_of, not rows.
        "effective_date_units": int(len(df[["market", "prediction_as_of"]]
                                        .drop_duplicates())),
    }
    key = ["market", "prediction_as_of", "ticker"]
    q["duplicate_rows"] = int(len(df) - len(df[key].drop_duplicates()))
    q["duplicate_rate_pct"] = round(100.0 * q["duplicate_rows"] / len(df), 3)

    # PIT / future-data violations
    viol = 0
    for h in HORIZONS:
        c = "fwd_%dd_outcome_date" % h
        if c in df.columns:
            v = df[df[c].notna() & (df[c].astype(str) <= df["prediction_as_of"].astype(str))]
            viol += len(v)
    q["pit_violations"] = int(viol)
    q["future_data_violations"] = int(viol)

    # schema consistency across dates
    q["schema_versions"] = sorted(
        str(x) for x in df["feature_schema_version"].dropna().unique())
    q["schema_violations"] = 0 if len(q["schema_versions"]) <= 1 else len(q["schema_versions"])

    miss = df.isna().mean().sort_values(ascending=False)
    q["fully_empty_columns"] = int((miss >= 1.0).sum())
    q["columns"] = int(len(df.columns))
    q["missingness_median_pct"] = round(100.0 * float(miss.median()), 2)
    q["outcome_coverage"] = {
        "fwd_%dd" % h: int(df["fwd_%dd" % h].notna().sum())
        for h in HORIZONS if "fwd_%dd" % h in df.columns}
    q["verdict"] = "PASS" if (q["pit_violations"] == 0
                              and q["duplicate_rows"] == 0) else "FAIL"
    return q


# ── §7 ENTRY-FAILURE FORENSICS ────────────────────────────────────────
@dataclass
class FactorSpec:
    fid: str
    label: str
    note: str


F_SPECS = [
    FactorSpec("F1", "never profitable", "MFE never reached +2% in the observed window"),
    FactorSpec("F2", "profitable then reversed", "MFE >= +2% and the outcome still went severely negative"),
    FactorSpec("F3", "immediate adverse move", "fwd_3d <= -2%"),
    FactorSpec("F4", "sector-wide failure", "the name's sector fell on the same window (leave-target-out)"),
    FactorSpec("F5", "peer-relative failure", "REJECTED family - not computed"),
    FactorSpec("F6", "market/regime failure", "the market aggregate fell on the same window"),
    FactorSpec("F7", "confidence failure", "R2 entry confidence below 40"),
    FactorSpec("F8", "volatility/liquidity failure", "high 20d volatility or thin liquidity bucket at entry"),
    FactorSpec("F9", "correlated portfolio failure", ">=5 admissions share the entry date"),
    FactorSpec("F10", "data-quality failure", "a feature the decision depended on was null at entry"),
    FactorSpec("F11", "stop/exit failure", "exit reason indicates stop or horizon rather than thesis"),
    FactorSpec("F12", "unknown", "adverse outcome matching no factor above"),
]


def _sector_excl_mean(df: pd.DataFrame, sector_col: str, val_col: str) -> pd.Series:
    """§9 LEAVE-TARGET-OUT sector aggregate.

    A stock must never contribute to the sector average it is then compared
    against - otherwise a large name is partly predicting itself and the
    'sector effect' is that name's own return wearing a sector label.
    """
    g = df.groupby([ "market", "prediction_as_of", sector_col])[val_col]
    s, n = g.transform("sum"), g.transform("count")
    return (s - df[val_col]) / (n - 1).where(n > 1)


def forensics(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Descriptive classification of adverse outcomes. No thresholds invented
    for production; the bands are research bands and are reported as such."""
    if df.empty:
        return df, {"status": "EMPTY"}
    t = df.copy()

    out_col = "fwd_10d" if t["fwd_10d"].notna().any() else (
        "fwd_5d" if t["fwd_5d"].notna().any() else (
            "fwd_3d" if t["fwd_3d"].notna().any() else "fwd_1d"))
    t["_outcome"] = t[out_col]
    t["_outcome_col"] = out_col

    mfe, mae = t.get("mfe_pct"), t.get("mae_pct")
    t["F1"] = ((mfe.notna()) & (mfe < 2.0)).astype(int)
    t["F2"] = ((mfe.notna()) & (mfe >= 2.0)
               & (t["_outcome"].notna()) & (t["_outcome"] <= -5.0)).astype(int)
    t["F3"] = ((t["fwd_3d"].notna()) & (t["fwd_3d"] <= -2.0)).astype(int)

    sec = "sector" if "sector" in t.columns else None
    if sec and t[sec].notna().any() and t["_outcome"].notna().any():
        t["_sector_excl"] = _sector_excl_mean(t, sec, "_outcome")
        t["F4"] = ((t["_sector_excl"].notna()) & (t["_sector_excl"] < 0)).astype(int)
    else:
        t["_sector_excl"] = pd.NA
        t["F4"] = 0
    t["F5"] = 0                      # REJECTED family, deliberately not computed

    mk = t.groupby(["market", "prediction_as_of"])["_outcome"].transform("median")
    t["F6"] = ((mk.notna()) & (mk < 0)).astype(int)

    conf = None
    for c in ("confidence_pct", "dec_confidence_pct", "entry_confidence"):
        if c in t.columns and t[c].notna().any():
            conf = c
            break
    t["_conf_col"] = conf or ""
    t["F7"] = (((t[conf] < 40) & t[conf].notna()).astype(int)) if conf else 0

    vol = "volatility_20d" if "volatility_20d" in t.columns else None
    if vol and t[vol].notna().any():
        hi = t[vol].quantile(0.8)
        t["F8"] = ((t[vol].notna()) & (t[vol] >= hi)).astype(int)
    else:
        t["F8"] = 0

    if "in_sealed_decisions" in t.columns:
        held = t[t["in_sealed_decisions"] == 1]
        cnt = held.groupby(["market", "prediction_as_of"])["ticker"].transform("count") \
            if len(held) else pd.Series(dtype=float)
        t["F9"] = 0
        if len(held):
            t.loc[held.index, "F9"] = (cnt >= 5).astype(int)
    else:
        t["F9"] = 0

    crit = [c for c in ("sma_200", "sector_rank", "adx_14", "rsi_14") if c in t.columns]
    t["F10"] = (t[crit].isna().any(axis=1).astype(int)) if crit else 0

    er = None
    for c in ("exit_reason", "dec_exit_reason"):
        if c in t.columns:
            er = c
            break
    t["F11"] = (t[er].fillna("").str.contains("stop|horizon", case=False).astype(int)) \
        if er else 0

    fcols = ["F%d" % i for i in range(1, 12)]
    adverse = (t["_outcome"].notna()) & (t["_outcome"] < 0)
    t["F12"] = (adverse & (t[fcols].sum(axis=1) == 0)).astype(int)

    summary: dict = {"outcome_column": out_col, "factors": [],
                     "severe_bands": {}, "confidence_column": conf}
    for s in F_SPECS:
        sub = t[t[s.fid] == 1]
        o = sub["_outcome"].dropna()
        summary["factors"].append({
            "id": s.fid, "label": s.label, "note": s.note,
            "n_rows": int(len(sub)),
            "n_tickers": int(sub["ticker"].nunique()) if len(sub) else 0,
            "n_dates": int(len(sub[["market", "prediction_as_of"]].drop_duplicates()))
            if len(sub) else 0,
            "mean_outcome_pct": round(float(o.mean()), 3) if len(o) else None,
            "mean_mae_pct": round(float(sub["mae_pct"].dropna().mean()), 3)
            if "mae_pct" in sub and sub["mae_pct"].notna().any() else None,
            "mean_mfe_pct": round(float(sub["mfe_pct"].dropna().mean()), 3)
            if "mfe_pct" in sub and sub["mfe_pct"].notna().any() else None,
            "n_with_outcome": int(len(o)),
        })
    for b in SEVERE_BANDS:
        sub = t[(t["_outcome"].notna()) & (t["_outcome"] <= b)]
        summary["severe_bands"]["le_%spct" % b] = {
            "n_rows": int(len(sub)),
            "n_tickers": int(sub["ticker"].nunique()) if len(sub) else 0,
            "n_dates": int(len(sub[["market", "prediction_as_of"]].drop_duplicates()))
            if len(sub) else 0,
        }
    summary["note"] = ("Bands are RESEARCH bands. No production loss threshold "
                       "is defined or implied by this table.")
    return t, summary


# ── §11 DATE-AWARE VALIDATION GATE ────────────────────────────────────
def oos_gate(n_dates: int) -> dict:
    """Chronological TRAIN -> EMBARGO -> TEST, or an honest refusal."""
    ok = n_dates >= MIN_DATES_FOR_OOS
    return {
        "attempted": ok,
        "effective_date_units": n_dates,
        "required": MIN_DATES_FOR_OOS,
        "embargo_days": EMBARGO_DAYS,
        "disposition": "OOS_EVALUATED" if ok else "BLOCKED_INSUFFICIENT_DATE_DEPTH",
        "reason": None if ok else (
            "%d effective date units cannot support a chronological train/embargo/test "
            "split. A random row split would report a number, and that number would be "
            "a description of one or two mornings." % n_dates),
    }
