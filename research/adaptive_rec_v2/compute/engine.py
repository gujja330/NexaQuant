"""Adaptive Rec v2.0 · orchestration.

Loads DEV025 learning data, fits candidate signal models, evaluates each
on held-out test data, compares against the v1.4 raw-confidence baseline,
and produces the full metric panel + reliability + per-tier discrimination."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "research"))

from adaptive_rec_v2.lib import features, model, metrics, reliability                # noqa: E402


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                            capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "nogit"
    except Exception:
        return "nogit"


def run(verbose: bool = True) -> dict:
    df = features.load_learning()
    if df.empty:
        return {"error": "reports/learning.parquet missing or empty"}

    if verbose:
        print(f"  loaded {len(df)} trades")

    X_raw, y, feature_names = features.build_feature_matrix(df)
    X, medians = features.impute(X_raw, feature_names)

    conf_idx = feature_names.index("confidence")

    train_mask, test_mask = features.time_train_test_split(df, train_frac=0.7)
    X_tr, X_te = X[train_mask], X[test_mask]
    y_tr, y_te = y[train_mask], y[test_mask]
    returns_te = df.loc[test_mask, "return_pct"].astype(float).values

    if verbose:
        print(f"  train {len(X_tr)} · test {len(X_te)}")
        print(f"  train winrate {y_tr.mean():.3f} · test winrate {y_te.mean():.3f}")
        print(f"  features {X.shape[1]} ({len(features.NUMERIC_FEATURES)} numeric + "
                f"{X.shape[1] - len(features.NUMERIC_FEATURES)} categorical one-hot)")

    models = model.fit_all(X_tr, y_tr, feature_names, conf_idx)

    scoreboard = {}
    per_model_pred = {}
    for name, m in models.items():
        p = m.predict(X_te)
        per_model_pred[name] = p
        panel = metrics.full_panel(p, y_te, returns_te)
        curve = reliability.reliability_curve(p, y_te)
        tiers = reliability.tier_discrimination(p, y_te, returns_te)
        tier_check = reliability.discrimination_summary(tiers)
        scoreboard[name] = {
            "metrics":            panel,
            "reliability_curve":  curve,
            "tier_discrimination": tiers,
            "tier_check":         tier_check,
            "params":             m.params,
        }
        if verbose:
            print(f"  [{name:<32}] Brier={panel['brier']:.4f} "
                    f"AUC={panel['auc']:.4f} P@5={panel['precision_at_5']:.3f} "
                    f"P@10={panel['precision_at_10']:.3f}")

    # Selection rule: PREFER top-tail edge over global calibration.
    # Precision@10 anchors around the champion's target holding count.
    def _score(m_name: str) -> float:
        p_at_10 = scoreboard[m_name]["metrics"]["precision_at_10"]
        p_at_5  = scoreboard[m_name]["metrics"]["precision_at_5"]
        return (p_at_10 or 0) + 0.5 * (p_at_5 or 0)

    best = max(scoreboard.keys(), key=_score)
    baseline = "v1.4_baseline_raw_confidence"

    if verbose:
        base_p10 = scoreboard[baseline]["metrics"]["precision_at_10"]
        best_p10 = scoreboard[best]["metrics"]["precision_at_10"]
        print(f"  best: {best}  Precision@10 = {best_p10:.3f} "
                f"vs baseline {base_p10:.3f}  (delta +{(best_p10 - base_p10)*100:.1f}pp)")

    # Feature importance from the best model (HGB most likely)
    best_model = models[best]

    return {
        "run_utc":                datetime.now(timezone.utc).isoformat() + "Z",
        "code_sha":               _git_sha(),
        "engine":                 "Adaptive Recommendation Engine",
        "version":                "v2.0",
        "supersedes":             "v1.4 (DEV023 + DEV029)",
        "n_trades_total":         int(len(df)),
        "n_trades_train":         int(train_mask.sum()),
        "n_trades_test":          int(test_mask.sum()),
        "train_win_rate":         round(float(y_tr.mean()), 4),
        "test_win_rate":          round(float(y_te.mean()), 4),
        "feature_names":          feature_names,
        "feature_medians":        medians,
        "n_features":             int(X.shape[1]),
        "scoreboard":             scoreboard,
        "best_model":             best,
        "baseline":               baseline,
        "feature_importance":     best_model.feature_importance,
        "governance":             ("Advisory only. v2.0 model surfaces a top-K "
                                    "identification signal; global AUC remains close "
                                    "to chance. Do not treat raw prediction as calibrated "
                                    "probability outside the ranked top-K context."),
        # internal for publish layer
        "_per_model_pred":        per_model_pred,
        "_y_test":                y_te,
        "_returns_test":          returns_te,
        "_df_test_index":         df.index[test_mask].tolist(),
    }
