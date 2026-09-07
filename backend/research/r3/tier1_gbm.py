"""R3 · Tier 1 · Gradient-Boosted-Machine baseline
CEO 2026-09-03 · rebuilt for R3 Sprint 1 foundation repair 2026-09-07

Scope (PDF Tier-1): existing daily features + FII/DII + earnings calendar
+ options PCR + GBM + Platt calibration.

WHAT THE 2026-09-07 REPAIR CHANGED, AND WHY
-------------------------------------------
The R3-1 audit found four defects that made every published Tier-1 metric
invalid as evidence. All four are fixed here.

1 · FEATURE MERGE-SUFFIX COLLISION (Sprint 1 item 10)
    The outcome dataset ALREADY carries all 19 fundamental columns, so
    merging the fundamentals feature store on (market,ticker,entry_date↔asof)
    made pandas suffix every collision to `_x`/`_y`. FEATURE_COLUMNS looks
    for the UNSUFFIXED names, so 19 of 24 features silently vanished and
    the model trained on 5 without any error. The merge now names its
    suffixes explicitly so the canonical column always survives.

2 · NON-PIT FEATURE STORE (Sprint 1 items 11-12)
    The feature store is a CURRENT snapshot (asof 2026-09-03..04) while
    outcome entries are 2026-08-04..06 · zero key overlap. Attaching
    today's fundamentals to an August trade is lookahead. The store is
    therefore joined ONLY on an exact (ticker, date) match, and anything
    it cannot supply for the actual entry date is reported
    NOT_AVAILABLE_AT_ASOF rather than forward-filled.

3 · TIME LEAKAGE IN VALIDATION (Sprint 1 item 15)
    `KFold(shuffle=True)` on time-ordered rows trains on the future to
    predict the past. Replaced with walk-forward folds plus a 5-day
    embargo between train and validation.

4 · PLATT CALIBRATION CLAIMED BUT NEVER FITTED (Sprint 1 item 13)
    The docstring promised Platt calibration; the code only computed ECE
    on raw GBM probabilities. A real sigmoid is now fitted on out-of-fold
    predictions and persisted with its parameters.

Plus item 14: the artifact now serializes the model and the calibrator, so
`artifact + feature row → prediction` reproduces exactly.

Baseline-replicate gate: before adding NEW features (post-Tier 1), R3 must
reproduce the R2 baseline. Enforced separately in baseline_replicate_gate.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]

MODEL_VERSION = "aegis.r3.gbm_tier1.v2"
FEATURE_VERSION = "aegis.r3.features.v2"
CALIBRATOR_VERSION = "aegis.r3.platt.v1"

NOT_AVAILABLE = "NOT_AVAILABLE_AT_ASOF"

# Walk-forward configuration · mirrors the V2 PDF protocol shape.
EMBARGO_DAYS = 5
MIN_FOLD_TRAIN = 40
N_FOLDS = 4
RANDOM_SEED = 42

GBM_PARAMS = {
    "n_estimators": 100,
    "max_depth": 3,
    "learning_rate": 0.05,
    "random_state": RANDOM_SEED,
}


# ── TIER-1 FEATURE CONTRACT · FROZEN · CEO 2026-09-07 (R3-2) ─────────
#
# "Tier-1 contains only the PDF-scoped substrate-independent inputs:
#  existing daily/technical features, FII/DII, earnings calendar, options
#  PCR, GBM and Platt calibration. F01-F05 fundamentals are not part of
#  Tier-1."
#
# The previous FEATURE_COLUMNS list mixed both together, which is how an
# F01-F05 fundamentals signal could have been pulled into Tier-1 simply
# because it happened to already be computed. The partition is now
# explicit and enforced by `usable_features`, so substrate-dependent
# sophistication cannot enter Tier-1 by accident.

TIER1_SCOPE = [
    # Daily / signal-ledger technicals (substrate-independent)
    "entry_signal_score", "entry_calibrated_conf", "entry_regime_adj_conf",
    "entry_model_agreement", "entry_n_models_scoring",
    # FII/DII flows
    "fii_dii_net_flow_z",
    # Options PCR
    "options_pcr",
    # Market microstructure
    "short_interest_pct",
    # Earnings calendar (the CALENDAR window · not an earnings fundamental)
    "earnings_calendar_window",
]

# F01-F05 fundamentals substrate · EXCLUDED from Tier-1 by the
# substrate-before-sophistication rule. These are not "missing"; they are
# deliberately out of scope until the substrate reaches the required
# Coverage Tracker stage. R3 Tier-1 must never consume them.
EXCLUDED_F01_F05 = [
    # Layer 1 · quality / distress
    "piotroski_f", "beneish_m", "altman_z", "sloan_accruals",
    "interest_coverage",
    # Layer 2 · valuation
    "fcf_yield", "ev_ebitda", "total_shareholder_yield",
    "sector_rel_value_rank",
    # Layer 3 · revisions / insider / institutional
    "analyst_rev_momentum", "guidance_rev", "earnings_surprise",
    "insider_f4_signal", "inst_13f_change",
    # Layer 5 · governance
    "promoter_pledge_pct",
]

# Full declared set, kept so the 24-feature audit stays complete.
FEATURE_COLUMNS = TIER1_SCOPE + EXCLUDED_F01_F05


# ── data assembly ─────────────────────────────────────────────────────

def build_training_frame(root: Path, market: str):
    """Assemble the training matrix · PIT-correct, no silent column loss."""
    import pandas as pd

    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return pd.DataFrame()
    od = pd.read_parquet(od_path)
    od = od[(od["is_administrative_exit"] != True)
            & od["realized_return_pct"].notna()].copy()
    if od.empty:
        return od
    od["win"] = (od["realized_return_pct"] > 0).astype(int)

    fs_path = (root / "reports" / "research" / "fundamentals_feature_store"
               / f"{market}.parquet")
    if not fs_path.exists():
        return od
    fs = pd.read_parquet(fs_path)
    if fs.empty:
        return od

    # PIT JOIN ONLY. The store is keyed by its own `asof`; a row may be
    # used only where that asof EQUALS the trade's entry date. Explicit
    # suffixes keep the canonical (outcome-dataset, at-entry) column and
    # park the store's version under _fs, so nothing can vanish silently
    # the way it did before.
    merged = od.merge(
        fs, how="left",
        left_on=["market", "ticker", "entry_date"],
        right_on=["market", "ticker", "asof"],
        suffixes=("", "_fs"),
    )
    return merged


def feature_availability(root: Path, market: str) -> dict:
    """Per-feature PIT availability · the honest 24-feature audit.

    AVAILABLE              at least one non-null at-entry observation
    NOT_AVAILABLE_AT_ASOF  column exists but is entirely unpopulated
    COLUMN_ABSENT          the column is not produced at all
    """
    df = build_training_frame(root, market)
    report = {}
    if df is None or len(df) == 0:
        return {c: "COLUMN_ABSENT" for c in FEATURE_COLUMNS}
    for c in FEATURE_COLUMNS:
        if c not in df.columns:
            report[c] = "COLUMN_ABSENT"
        elif int(df[c].notna().sum()) == 0:
            report[c] = NOT_AVAILABLE
        else:
            report[c] = "AVAILABLE"
    return report


EXCLUDED_BY_SCOPE = "EXCLUDED_F01_F05_SUBSTRATE"


def usable_features(root: Path, market: str) -> tuple:
    """(usable, excluded) · excluded carries an explicit reason each.

    Usable is drawn ONLY from TIER1_SCOPE. An F01-F05 fundamentals column
    that happens to be populated is still excluded, with the reason stated
    · that is the substrate-before-sophistication rule enforced in code
    rather than trusted to a convention. Without this restriction the
    moment the fundamentals substrate became populated it would silently
    enter Tier-1 and quietly invalidate the Tier-1 evidence claim.
    """
    avail = feature_availability(root, market)
    usable = [c for c in TIER1_SCOPE if avail.get(c) == "AVAILABLE"]
    excluded = {}
    for c in TIER1_SCOPE:
        if avail.get(c) != "AVAILABLE":
            excluded[c] = avail.get(c, "COLUMN_ABSENT")
    for c in EXCLUDED_F01_F05:
        excluded[c] = EXCLUDED_BY_SCOPE
    return usable, excluded


# ── walk-forward with embargo ─────────────────────────────────────────

def walk_forward_folds(dates, n_folds: int = N_FOLDS,
                       embargo_days: int = EMBARGO_DAYS,
                       min_train: int = MIN_FOLD_TRAIN):
    """Yield (train_idx, valid_idx) expanding-window folds, time-ordered.

    A fold trains strictly on the PAST, leaves an `embargo_days` gap, then
    validates on the immediately following block. The embargo prevents a
    label whose outcome window overlaps the train period from leaking.
    """
    import pandas as pd

    order = pd.Series(pd.to_datetime(dates)).sort_values()
    idx_sorted = list(order.index)
    n = len(idx_sorted)
    if n < min_train + 2:
        return []
    first = max(min_train, int(n * 0.4))
    remaining = n - first
    if remaining < n_folds:
        n_folds = max(1, remaining)
    block = max(1, remaining // n_folds)

    folds = []
    for k in range(n_folds):
        v_start = first + k * block
        v_end = n if k == n_folds - 1 else min(n, v_start + block)
        if v_start >= n:
            break
        train_pos = idx_sorted[:v_start]
        valid_pos = idx_sorted[v_start:v_end]
        if not train_pos or not valid_pos:
            continue
        # Embargo · drop training rows within embargo_days of the first
        # validation date.
        v_first_date = order.loc[valid_pos[0]]
        cutoff = v_first_date - pd.Timedelta(days=embargo_days)
        train_pos = [i for i in train_pos if order.loc[i] <= cutoff]
        if len(train_pos) < 5:
            continue
        folds.append((train_pos, valid_pos))
    return folds


# ── Platt calibration ─────────────────────────────────────────────────

def fit_platt(raw_p, y):
    """Fit a real Platt sigmoid: P(y=1) = 1 / (1 + exp(A*f + B)).

    Implemented as a 1-D logistic regression on the raw score, which is
    exactly Platt scaling. Returns (calibrator, {A, B}).
    """
    from sklearn.linear_model import LogisticRegression
    import numpy as np

    X = np.asarray(raw_p, dtype=float).reshape(-1, 1)
    yv = np.asarray(y, dtype=int)
    if len(set(yv.tolist())) < 2:
        return None, {"status": "SINGLE_CLASS_NO_CALIBRATION"}
    lr = LogisticRegression(solver="lbfgs")
    lr.fit(X, yv)
    return lr, {
        "A": float(lr.coef_[0][0]),
        "B": float(lr.intercept_[0]),
        "n_calibration": int(len(yv)),
        "version": CALIBRATOR_VERSION,
    }


def apply_platt(calibrator, raw_p):
    import numpy as np
    if calibrator is None:
        return [float(p) for p in raw_p]
    X = np.asarray(raw_p, dtype=float).reshape(-1, 1)
    return [float(p) for p in calibrator.predict_proba(X)[:, 1]]


# ── training ──────────────────────────────────────────────────────────

def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              cwd=str(_ROOT)).stdout.strip()[:12] or NOT_AVAILABLE
    except Exception:
        return NOT_AVAILABLE


def _dataset_hash(X, y) -> str:
    try:
        s = f"{X.shape}-{list(X.columns)}-{int(y.sum())}-{len(y)}"
        return hashlib.sha256(s.encode()).hexdigest()[:16]
    except Exception:
        return NOT_AVAILABLE


def train_gbm(root: Path, market: str) -> dict:
    """Train the Tier-1 baseline · walk-forward, embargoed, Platt-calibrated."""
    import pandas as pd

    df = build_training_frame(root, market)
    usable, excluded = usable_features(root, market)

    base = {
        "market": market,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "calibrator_version": CALIBRATOR_VERSION,
        "n_features_declared": len(FEATURE_COLUMNS),
        "n_features_usable": len(usable),
        "features_usable": usable,
        "features_excluded": excluded,
        "validation": {
            "method": "walk_forward_expanding",
            "embargo_days": EMBARGO_DAYS,
            "n_folds_requested": N_FOLDS,
        },
        "shadow_only": True,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
    }

    if df is None or len(df) == 0:
        return {**base, "status": "NO_DATASET", "n": 0}
    if not usable:
        return {**base, "status": "NO_USABLE_FEATURES", "n": int(len(df))}

    X = df[usable].astype(float).fillna(0.0)
    y = df["win"].astype(int)
    dates = df["entry_date"]

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import brier_score_loss, roc_auc_score
    except ImportError:
        return {**base, "status": "SKLEARN_MISSING"}

    folds = walk_forward_folds(dates)
    if not folds:
        return {**base, "status": "INSUFFICIENT_SAMPLE",
                "n": int(len(X)),
                "reason": (f"need >= {MIN_FOLD_TRAIN + 2} time-ordered rows for "
                           f"walk-forward with a {EMBARGO_DAYS}d embargo")}

    # Out-of-fold predictions · each row scored by a model that never saw
    # it, nor anything within the embargo window before it.
    oof, oof_y, n_used = {}, {}, 0
    for train_pos, valid_pos in folds:
        gbm = GradientBoostingClassifier(**GBM_PARAMS)
        gbm.fit(X.loc[train_pos], y.loc[train_pos])
        preds = gbm.predict_proba(X.loc[valid_pos])[:, 1]
        for i, pos in enumerate(valid_pos):
            oof[pos] = float(preds[i])
            oof_y[pos] = int(y.loc[pos])
        n_used += len(valid_pos)

    keys = list(oof.keys())
    raw = [oof[k] for k in keys]
    yy = [oof_y[k] for k in keys]

    # REAL Platt calibration on the out-of-fold predictions.
    calibrator, platt = fit_platt(raw, yy)
    cal = apply_platt(calibrator, raw)

    from backend.research.r2_upgrades.p1_calibration_joint import (
        expected_calibration_error)

    def _safe_auc(y_true, p):
        try:
            return float(roc_auc_score(y_true, p)) if len(set(y_true)) > 1 else 0.5
        except Exception:
            return 0.5

    metrics = {
        "n_oof": len(keys),
        "raw": {
            "brier": float(brier_score_loss(yy, raw)),
            "auc": _safe_auc(yy, raw),
            "ece": float(expected_calibration_error(yy, raw)),
        },
        "calibrated": {
            "brier": float(brier_score_loss(yy, cal)),
            "auc": _safe_auc(yy, cal),
            "ece": float(expected_calibration_error(yy, cal)),
        },
    }

    # Final full-fit model for serving · trained on everything available.
    gbm_final = GradientBoostingClassifier(**GBM_PARAMS)
    gbm_final.fit(X, y)
    imp = sorted(zip(usable, gbm_final.feature_importances_.tolist()),
                 key=lambda kv: -kv[1])

    out_dir = root / "reports" / "research" / "r3" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)

    # SERIALIZED artifact (item 14) · model + calibrator, so a prediction
    # can be reproduced from the artifact alone.
    pkl_path = out_dir / f"gbm_tier1_{market}.pkl"
    serialized = False
    try:
        import pickle
        with pkl_path.open("wb") as fh:
            pickle.dump({"model": gbm_final, "calibrator": calibrator,
                         "features": usable,
                         "model_version": MODEL_VERSION,
                         "feature_version": FEATURE_VERSION,
                         "calibrator_version": CALIBRATOR_VERSION}, fh)
        serialized = True
    except Exception as e:
        base["serialize_error"] = f"{type(e).__name__}: {e}"

    result = {
        **base,
        "status": "TRAINED",
        "n_train": int(len(X)),
        "dataset_hash": _dataset_hash(X, y),
        "training_window": {
            "start": str(pd.to_datetime(dates).min().date()),
            "end": str(pd.to_datetime(dates).max().date()),
        },
        "gbm_params": GBM_PARAMS,
        "random_seed": RANDOM_SEED,
        "platt": platt,
        "metrics": metrics,
        "top_features": imp[:10],
        "validation": {**base["validation"], "n_folds_used": len(folds),
                       "n_oof_rows": len(keys)},
        "artifact": {
            "json": f"reports/research/r3/models/gbm_tier1_{market}.json",
            "pickle": (f"reports/research/r3/models/gbm_tier1_{market}.pkl"
                       if serialized else NOT_AVAILABLE),
        },
    }
    (out_dir / f"gbm_tier1_{market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def load_model(root: Path, market: str):
    """Load the serialized artifact · (model, calibrator, features)."""
    import pickle
    p = root / "reports" / "research" / "r3" / "models" / f"gbm_tier1_{market}.pkl"
    if not p.exists():
        return None, None, []
    with p.open("rb") as fh:
        d = pickle.load(fh)
    return d.get("model"), d.get("calibrator"), d.get("features") or []


def predict(root: Path, market: str, feature_row: dict) -> dict:
    """Reproducible prediction from the persisted artifact alone."""
    import pandas as pd
    model, calibrator, feats = load_model(root, market)
    if model is None:
        return {"status": "NO_ARTIFACT"}
    X = pd.DataFrame([{f: float(feature_row.get(f) or 0.0) for f in feats}])
    raw = float(model.predict_proba(X)[:, 1][0])
    cal = apply_platt(calibrator, [raw])[0]
    return {"status": "OK", "raw_p": raw, "calibrated_p": cal,
            "model_version": MODEL_VERSION,
            "calibrator_version": CALIBRATOR_VERSION,
            "features_used": feats}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa", "both"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    markets = ["india", "usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = train_gbm(Path(args.root), m)
        print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
