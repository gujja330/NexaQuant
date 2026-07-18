"""Adaptive Rec v2.0 · publish."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[3]
REPORTS = _ROOT / "reports"


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, tuple):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    return obj


def build_and_publish(result: dict) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)

    core = {k: v for k, v in result.items() if not k.startswith("_")}

    # 1. Headline
    with (REPORTS / "adaptive_rec_v2_signal.json").open("w", encoding="utf-8") as f:
        headline = {k: v for k, v in core.items() if k not in ("scoreboard",)}
        headline["best_model_summary"] = core["scoreboard"][core["best_model"]]["metrics"]
        headline["baseline_summary"]   = core["scoreboard"][core["baseline"]]["metrics"]
        headline["delta_precision_10"] = round(
            (headline["best_model_summary"].get("precision_at_10") or 0)
            - (headline["baseline_summary"].get("precision_at_10") or 0), 4)
        headline["delta_precision_5"]  = round(
            (headline["best_model_summary"].get("precision_at_5") or 0)
            - (headline["baseline_summary"].get("precision_at_5") or 0), 4)
        json.dump(_sanitize(headline), f, indent=2, default=str)

    # 2. Full scoreboard
    with (REPORTS / "adaptive_rec_v2_scoreboard.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":     core["run_utc"],
            "scoreboard":  core["scoreboard"],
            "best_model":  core["best_model"],
            "baseline":    core["baseline"],
        }), f, indent=2, default=str)

    # 3. Feature importance
    with (REPORTS / "adaptive_rec_v2_feature_importance.json").open("w", encoding="utf-8") as f:
        sorted_fi = sorted(core["feature_importance"].items(),
                              key=lambda kv: -kv[1])
        json.dump(_sanitize({
            "run_utc":            core["run_utc"],
            "model":              core["best_model"],
            "feature_importance": [{"feature": name, "importance": imp}
                                     for name, imp in sorted_fi],
            "top_5":              [{"feature": name, "importance": imp}
                                     for name, imp in sorted_fi[:5]],
            "governance":         core["governance"],
        }), f, indent=2, default=str)

    # 4. Reliability curves (baseline + best)
    with (REPORTS / "adaptive_rec_v2_reliability.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize({
            "run_utc":       core["run_utc"],
            "baseline":      {"name": core["baseline"],
                                "curve": core["scoreboard"][core["baseline"]]["reliability_curve"]},
            "best_model":    {"name": core["best_model"],
                                "curve": core["scoreboard"][core["best_model"]]["reliability_curve"]},
        }), f, indent=2, default=str)

    # 5. Per-trade parquet (test set only)
    per_model_pred = result["_per_model_pred"]
    y_test = result["_y_test"]
    returns_test = result["_returns_test"]
    df_out = pd.DataFrame({
        "raw_confidence":  per_model_pred.get(core["baseline"]),
        "v2_signal":       per_model_pred.get(core["best_model"]),
        "is_winner":       y_test,
        "return_pct":      returns_test,
    })
    df_out.to_parquet(REPORTS / "adaptive_rec_v2_signal.parquet", index=False)

    # 6. Migration guide markdown
    baseline_p = core["scoreboard"][core["baseline"]]["metrics"]
    best_p     = core["scoreboard"][core["best_model"]]["metrics"]
    tier_best  = core["scoreboard"][core["best_model"]]["tier_discrimination"]
    tier_check = core["scoreboard"][core["best_model"]]["tier_check"]
    lines = [
        "# Adaptive Recommendation Engine · v1.4 → v2.0 · Migration Guide",
        "",
        f"_Generated {core['run_utc']} · code_sha `{core['code_sha']}`_",
        "",
        "## Summary",
        "",
        f"- **Best model**: `{core['best_model']}`",
        f"- **Baseline**:   `{core['baseline']}` (v1.4 raw confidence pass-through)",
        f"- **Trades**: {core['n_trades_total']} total · "
            f"{core['n_trades_train']} train · {core['n_trades_test']} test",
        "",
        "## Full metric panel (test set)",
        "",
        "| Metric              | Baseline (v1.4) | v2.0 (best) | Delta |",
        "|---------------------|-----------------|-------------|-------|",
    ]
    for k in ["brier", "log_loss", "ece", "auc", "confidence_bias", "sharpness",
                "precision_at_1", "precision_at_3", "precision_at_5",
                "precision_at_10", "precision_at_20",
                "avg_win", "avg_loss", "expectancy", "profit_factor"]:
        b = baseline_p.get(k)
        v = best_p.get(k)
        if b is None or v is None:
            lines.append(f"| {k} | {b} | {v} | — |")
        else:
            delta = v - b
            lines.append(f"| {k} | {b:.4f} | {v:.4f} | {delta:+.4f} |")

    lines += [
        "",
        "## Tier discrimination (Adaptive v2.0 · exit criterion)",
        "",
        "Phase 2 exit criterion (PHASE2_MASTER_ROADMAP.md §6):",
        "`Strong-Buy WR > Buy WR > Hold WR > Sell WR` — monotone decreasing.",
        "",
        f"- Verdict: **{tier_check.get('verdict')}**",
        f"- Monotone decreasing: `{tier_check.get('monotone_decreasing')}`",
        f"- Top-vs-bottom spread: `{tier_check.get('top_bottom_spread')}`",
        "",
        "| Tier | n | Win rate | Predicted mean | Expectancy |",
        "|------|---|---------:|---------------:|-----------:|",
    ]
    for t, row in tier_best.items():
        lines.append(f"| **{t}** | {row['n']} | {row['win_rate']} | "
                        f"{row['predicted_mean']} | {row.get('expectancy', '—')} |")

    lines += [
        "",
        "## Feature importance (top 10)",
        "",
        "| Rank | Feature | Importance |",
        "|-----:|---------|-----------:|",
    ]
    sorted_fi = sorted(core["feature_importance"].items(), key=lambda kv: -kv[1])
    for i, (name, imp) in enumerate(sorted_fi[:10], start=1):
        lines.append(f"| {i} | `{name}` | {imp:.4f} |")

    lines += [
        "",
        "## Governance",
        "",
        f"> {core['governance']}",
        "",
        "## Recommended action",
        "",
        "- Adopt `v2.0` prediction as the **top-K identifier** for the",
        "  Adaptive Recommendation Engine's Strong-Buy / Buy assignment.",
        "- Do NOT expose the raw v2.0 output as a probability outside the",
        "  ranked-top-K context — global AUC remains close to chance.",
        "- Continue calibration via DEV029 on the v2.0 signal to close",
        "  ECE gap where the ranked-top-K interpretation would be surfaced",
        "  as confidence to the operator.",
        "",
        "## Files",
        "",
        "- `reports/adaptive_rec_v2_signal.json` — headline + metrics",
        "- `reports/adaptive_rec_v2_scoreboard.json` — all model results",
        "- `reports/adaptive_rec_v2_feature_importance.json` — per-feature importance",
        "- `reports/adaptive_rec_v2_reliability.json` — baseline + v2 curves",
        "- `reports/adaptive_rec_v2_signal.parquet` — per-trade predictions",
        "- `reports/adaptive_rec_v2_migration.md` — this file",
    ]

    (REPORTS / "adaptive_rec_v2_migration.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "best_model":         core["best_model"],
        "baseline":           core["baseline"],
        "delta_precision_10": round(
            (best_p.get("precision_at_10") or 0) - (baseline_p.get("precision_at_10") or 0), 4),
        "tier_verdict":       tier_check.get("verdict"),
    }
