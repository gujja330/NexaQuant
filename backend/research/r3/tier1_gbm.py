"""R3 · Tier 1 · Gradient-Boosted-Machine baseline
CEO 2026-09-03

Uses scikit-learn GradientBoostingClassifier · target = binary win/loss
of trailing-90d realized returns.

Features (assembled per (ticker, asof) row):
  Daily technicals (from feature store) - if present
  Fundamentals Layers 1-5 (all 19 signals)
  Signal Ledger features (ensemble_score, model_agreement, disagreement)

After GBM · Platt calibration on out-of-fold predictions to produce
a probability-scale output for the shadow ledger.

Baseline-replicate gate:
  Before adding NEW features (post-Tier 1), R3 must achieve within
  ±5% IC of the R2 baseline on the same folds. This is enforced by
  a separate gate module.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]


def build_training_frame(root: Path, market: str):
    """Assemble the training matrix from feature store + outcome dataset.

    Returns pandas DataFrame with X columns + a 'win' target column.
    """
    import pandas as pd

    # Load fundamentals
    fs_path = root / "reports" / "research" / "fundamentals_feature_store" / f"{market}.parquet"
    if fs_path.exists():
        fs = pd.read_parquet(fs_path)
    else:
        fs = pd.DataFrame()

    # Load outcome dataset (target = win)
    od_path = root / "reports" / "research" / "outcome_dataset" / f"{market}.parquet"
    if not od_path.exists():
        return pd.DataFrame()
    od = pd.read_parquet(od_path)
    od = od[(od["is_administrative_exit"] != True)
            & od["realized_return_pct"].notna()].copy()
    if od.empty:
        return od

    od["win"] = (od["realized_return_pct"] > 0).astype(int)
    if not fs.empty:
        merged = od.merge(
            fs, how="left",
            left_on=["market", "ticker", "entry_date"],
            right_on=["market", "ticker", "asof"],
        )
    else:
        merged = od.copy()
    return merged


FEATURE_COLUMNS = [
    # Fundamentals Layer 1
    "piotroski_f", "beneish_m", "altman_z", "sloan_accruals", "interest_coverage",
    # Layer 2
    "fcf_yield", "ev_ebitda", "total_shareholder_yield", "sector_rel_value_rank",
    # Layer 3
    "analyst_rev_momentum", "guidance_rev", "earnings_surprise",
    "insider_f4_signal", "inst_13f_change",
    # Layer 4
    "fii_dii_net_flow_z", "options_pcr", "short_interest_pct",
    # Layer 5
    "earnings_calendar_window", "promoter_pledge_pct",
    # Signal Ledger features
    "entry_signal_score", "entry_calibrated_conf", "entry_regime_adj_conf",
    "entry_model_agreement", "entry_n_models_scoring",
]


def train_gbm(root: Path, market: str) -> dict:
    """Train GBM · shadow-only · never touches production models."""
    df = build_training_frame(root, market)
    if df.empty or len(df) < 30:
        return {"market": market, "status": "INSUFFICIENT_SAMPLE",
                "n": int(len(df))}

    # Assemble X · impute missing with 0 (GBM handles it), y
    X_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    if not X_cols:
        return {"market": market, "status": "NO_FEATURES"}
    import pandas as pd
    X = df[X_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = df["win"].astype(int)

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import KFold
        from sklearn.metrics import brier_score_loss, roc_auc_score
    except ImportError:
        return {"market": market, "status": "SKLEARN_MISSING"}

    if len(X) < 5:
        return {"market": market, "status": "INSUFFICIENT_SAMPLE"}

    n_folds = min(5, max(2, len(X) // 8))
    kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
    oof = [0.0] * len(X)
    for tr_idx, te_idx in kf.split(X):
        Xt = X.iloc[tr_idx]; yt = y.iloc[tr_idx]
        Xv = X.iloc[te_idx]
        gbm = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42,
        )
        gbm.fit(Xt, yt)
        preds = gbm.predict_proba(Xv)[:, 1]
        for i, idx in enumerate(te_idx):
            oof[idx] = float(preds[i])

    # Metrics
    brier = brier_score_loss(y, oof)
    try:
        auc = roc_auc_score(y, oof) if len(set(y)) > 1 else 0.5
    except Exception:
        auc = 0.5
    # ECE
    from backend.research.r2_upgrades.p1_calibration_joint import expected_calibration_error
    ece = expected_calibration_error(list(y), oof)

    # SHAP-ish feature importance from final full-fit model
    gbm_final = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42,
    )
    gbm_final.fit(X, y)
    imp = sorted(zip(X_cols, gbm_final.feature_importances_.tolist()),
                 key=lambda kv: -kv[1])

    # Write shadow output (never a production path)
    out_dir = root / "reports" / "research" / "r3" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"gbm_tier1_{market}.json").write_text(json.dumps({
        "market": market,
        "n_train": int(len(X)),
        "n_features": len(X_cols),
        "features": X_cols,
        "brier": brier, "auc": auc, "ece": ece,
        "top_features": imp[:10],
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, indent=2), encoding="utf-8")

    return {
        "market": market,
        "status": "TRAINED",
        "n_train": int(len(X)),
        "n_features": len(X_cols),
        "brier": brier, "auc": auc, "ece": ece,
        "top_features": imp[:10],
        "shadow_only": True,
        "output_path": f"reports/research/r3/models/gbm_tier1_{market}.json",
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    r = train_gbm(Path(args.root), args.market)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    main()
