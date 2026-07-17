"""DEV025 improvement suggestion generator.

Turns statistical findings into ADVISORY recommendations. Never auto-applied
(ARCH001A Article V clause 5.1). Every suggestion carries:
  - `evidence` — the statistical basis
  - `confidence` — how strong the finding is
  - `impact_estimate` — order-of-magnitude expected effect
  - `action` — the proposed change
"""
from __future__ import annotations

import pandas as pd


def generate(engine_result: dict) -> list[dict]:
    """Produce a list of advisory improvement suggestions."""
    suggestions = []
    agg = engine_result.get("aggregate", {})
    trades = engine_result.get("trades")
    score_buckets = engine_result.get("score_buckets")
    sector_perf = engine_result.get("sector_performance")
    dim_corr = engine_result.get("dimension_correlations")
    stop_stats = engine_result.get("stop_loss_stats", {})
    target_stats = engine_result.get("target_stats", {})
    calib_curve = engine_result.get("calibration_curve")
    sector_calib = engine_result.get("sector_calibration")

    if trades is None or (hasattr(trades, "empty") and trades.empty):
        return suggestions

    # ── 1. Calibration: is confidence over- or under-stated? ────────────────
    ece = agg.get("expected_calibration_err")
    if ece is not None:
        if ece > 0.10:
            suggestions.append({
                "id":         "SUG-CALIB-001",
                "category":   "confidence_calibration",
                "severity":   "HIGH",
                "confidence": "high",
                "evidence":   f"Expected Calibration Error = {ece:.3f} (> 0.10 threshold)",
                "impact":     "Confidence values displayed to operator do not match empirical hit rates",
                "action":     "Fit isotonic regression on (confidence, is_winner) pairs and "
                              "apply as post-processing before displaying confidence in Telegram/UI",
                "target_module": "DEV020 confidence output OR DEV029 (calibration engine)",
            })
        elif ece > 0.05:
            suggestions.append({
                "id":         "SUG-CALIB-002",
                "category":   "confidence_calibration",
                "severity":   "MEDIUM",
                "confidence": "medium",
                "evidence":   f"Expected Calibration Error = {ece:.3f} (moderate)",
                "impact":     "Confidence miscalibration is meaningful but not extreme",
                "action":     "Investigate per-sector calibration (already computed in sector_calibration)",
                "target_module": "DEV029 (planned)",
            })

    # ── 2. Per-sector calibration outliers ─────────────────────────────────
    if isinstance(sector_calib, pd.DataFrame) and not sector_calib.empty:
        for _, row in sector_calib.iterrows():
            if row["flag"] == "over_confident":
                suggestions.append({
                    "id":         f"SUG-CALIB-SEC-{row['sector'].upper().replace(' ', '_')}",
                    "category":   "sector_calibration",
                    "severity":   "MEDIUM",
                    "confidence": "medium",
                    "evidence":   f"{row['sector']}: predicted {row['predicted_conf']:.3f}, "
                                  f"actual {row['actual_win_rate']:.3f}, gap {row['gap']:.3f}",
                    "impact":     f"Model over-confident in {row['sector']} recommendations",
                    "action":     f"Reduce confidence output for {row['sector']} by {abs(row['gap']):.2f}",
                    "target_module": "DEV020",
                })

    # ── 3. Score-bucket monotonicity ────────────────────────────────────────
    if isinstance(score_buckets, pd.DataFrame) and not score_buckets.empty and len(score_buckets) > 3:
        # Check if higher score buckets have higher win rates
        wr = score_buckets["win_rate_pct"].values
        monotone_violations = sum(1 for i in range(1, len(wr)) if wr[i] < wr[i - 1] - 5)
        if monotone_violations > len(wr) // 3:
            suggestions.append({
                "id":         "SUG-SCORE-001",
                "category":   "score_calibration",
                "severity":   "HIGH",
                "confidence": "high",
                "evidence":   f"{monotone_violations} score buckets show inverted win rates",
                "impact":     "Score ordering does not reliably predict outcomes",
                "action":     "Re-examine score dimension weights (DEV020 §8 weight table)",
                "target_module": "DEV020",
            })

    # ── 4. Top-quintile signal check per dimension ──────────────────────────
    if isinstance(dim_corr, pd.DataFrame) and not dim_corr.empty:
        for _, row in dim_corr.iterrows():
            spearman = row["spearman_correlation"]
            if abs(spearman) > 0.15 and row["n_trades"] >= 100:
                if spearman > 0:
                    action = f"Preserve or upweight — top quintile avg return "\
                              f"{row['avg_return_top_quintile']:.2f}% vs bottom "\
                              f"{row['avg_return_bot_quintile']:.2f}%"
                else:
                    action = f"Consider inverting or reducing weight — top quintile "\
                              f"underperforms bottom by "\
                              f"{row['avg_return_top_quintile'] - row['avg_return_bot_quintile']:.2f}pp"
                suggestions.append({
                    "id":         f"SUG-DIM-{row['dimension'].upper()}",
                    "category":   "dimension_effectiveness",
                    "severity":   "INFO",
                    "confidence": "medium",
                    "evidence":   f"{row['dimension']} Spearman = {spearman:.3f} (n={row['n_trades']})",
                    "impact":     f"Dimension {row['dimension']} has measurable predictive signal",
                    "action":     action,
                    "target_module": "DEV020",
                })
            elif abs(spearman) < 0.05 and row["n_trades"] >= 100:
                suggestions.append({
                    "id":         f"SUG-DIM-DROP-{row['dimension'].upper()}",
                    "category":   "dimension_effectiveness",
                    "severity":   "LOW",
                    "confidence": "medium",
                    "evidence":   f"{row['dimension']} Spearman ≈ 0 (r={spearman:.3f}, n={row['n_trades']})",
                    "impact":     f"Dimension {row['dimension']} contributes no signal — its weight "
                                  "could be redistributed",
                    "action":     f"Consider setting {row['dimension']} weight to 0 in v0.2",
                    "target_module": "DEV020",
                })

    # ── 5. Stop loss effectiveness ──────────────────────────────────────────
    if stop_stats:
        hit_5pct_rate = stop_stats.get("hit_5pct_stop_rate")
        final_win_dip = stop_stats.get("final_win_rate_among_5pct_dippers")
        if hit_5pct_rate is not None and final_win_dip is not None:
            if final_win_dip < 30:
                suggestions.append({
                    "id":         "SUG-STOP-001",
                    "category":   "stop_loss_optimisation",
                    "severity":   "MEDIUM",
                    "confidence": "medium",
                    "evidence":   f"{hit_5pct_rate:.1f}% of positions dipped -5% at some point; "
                                  f"of those, only {final_win_dip:.1f}% ended positive",
                    "impact":     "-5% dip is a strong bearish signal — tightening stops would "
                                  "have preserved capital",
                    "action":     "Tighten stops from -8% (current default) to -5%",
                    "target_module": "DEV023 entry_exit stop_loss calculation",
                })
            elif final_win_dip > 55:
                suggestions.append({
                    "id":         "SUG-STOP-002",
                    "category":   "stop_loss_optimisation",
                    "severity":   "INFO",
                    "confidence": "medium",
                    "evidence":   f"{final_win_dip:.1f}% of -5%-dippers ended positive",
                    "impact":     "-5% is normal noise for this universe — tight stops would "
                                  "cause premature exits",
                    "action":     "Consider widening stops or use ATR-scaled stops",
                    "target_module": "DEV023 entry_exit",
                })

    # ── 6. Target hit rate ──────────────────────────────────────────────────
    if target_stats:
        hit_5pct = target_stats.get("hit_5pct_target_rate")
        hit_10pct = target_stats.get("hit_10pct_target_rate")
        if hit_5pct and hit_5pct > 50:
            suggestions.append({
                "id":         "SUG-TARGET-001",
                "category":   "target_optimisation",
                "severity":   "INFO",
                "confidence": "medium",
                "evidence":   f"{hit_5pct:.1f}% of positions hit +5% at some point; "
                              f"{hit_10pct:.1f}% hit +10%",
                "impact":     "First target rate suggests exits could be later",
                "action":     "Consider raising Target 1 from +5% to +7% for higher-conviction picks",
                "target_module": "DEV023 entry_exit target_1 calculation",
            })

    # ── 7. Sector allocation ────────────────────────────────────────────────
    if isinstance(sector_perf, pd.DataFrame) and not sector_perf.empty:
        worst = sector_perf.tail(3)
        for _, row in worst.iterrows():
            if row["avg_return_pct"] < -2:
                suggestions.append({
                    "id":         f"SUG-SEC-{row['sector'].upper().replace(' ', '_')}",
                    "category":   "sector_allocation",
                    "severity":   "MEDIUM",
                    "confidence": "medium",
                    "evidence":   f"{row['sector']}: avg return {row['avg_return_pct']:.2f}%, "
                                  f"win rate {row['win_rate_pct']:.1f}% (n={row['n_trades']})",
                    "impact":     f"{row['sector']} consistently underperforms in the AEGIS universe",
                    "action":     f"Reduce or exclude {row['sector']} exposure until regime shifts",
                    "target_module": "DEV018 sector-strength or DEV022 portfolio filtering",
                })

    # ── 8. Holding period ──────────────────────────────────────────────────
    if trades is not None and hasattr(trades, "groupby"):
        # Compare short-hold vs long-hold performance where enough data
        if "n_bars_held" in trades.columns and len(trades) >= 100:
            short = trades[trades["n_bars_held"] <= 15]
            long = trades[trades["n_bars_held"] > 15]
            if len(short) >= 20 and len(long) >= 20:
                if float(short["return_pct"].mean()) > float(long["return_pct"].mean()) + 2:
                    suggestions.append({
                        "id":         "SUG-HOLD-001",
                        "category":   "holding_period",
                        "severity":   "INFO",
                        "confidence": "medium",
                        "evidence":   f"Short holds (≤15 bars): avg {short['return_pct'].mean():.2f}%; "
                                      f"Long holds (>15 bars): avg {long['return_pct'].mean():.2f}%",
                        "impact":     "Short-holding-period trades outperform in this universe",
                        "action":     "Reduce default max_holding from 90d to 45d",
                        "target_module": "DEV023",
                    })

    return suggestions
