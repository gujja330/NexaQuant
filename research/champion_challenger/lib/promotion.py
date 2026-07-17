"""DEV030 · promotion rules.

Rules-based, advisory-only. A challenger is recommended for promotion only if
it satisfies ALL of the following gates:

- **Margin gate** — challenger composite score is at least `MIN_MARGIN` above
  the incumbent champion.
- **Stability gate** — challenger's 2nd-half Sharpe is not `degrading`.
- **Sample gate** — both champion and challenger have >= MIN_TRADES completed
  trades on record.
- **Drawdown gate** — challenger's max drawdown is not more than
  `MAX_EXTRA_DD` percentage points worse than the champion's.

If gates are not met, we still surface the top-ranked strategy as the
CURRENT CHAMPION (best of what's available), but no PROMOTION is
recommended."""
from __future__ import annotations

from typing import Any


MIN_MARGIN     = 3.0     # composite score points
MAX_EXTRA_DD   = 5.0     # +5 percentage points max drawdown allowed
MIN_TRADES     = 30


def _get(strat_row: dict[str, Any], keys: list[str], default=None):
    for k in keys:
        if k in strat_row and strat_row[k] is not None:
            return strat_row[k]
    return default


def evaluate_promotion(current_champion_row: dict,
                         all_scored_rows: list[dict],
                         drift_by_strategy: dict) -> dict:
    """Return a promotion decision dict.

    current_champion_row = the incumbent (the top-ranked *prior* champion). If
    None, we default to the top-of-leaderboard row and skip the gates."""
    if not all_scored_rows:
        return {"decision": "no_data", "reason": "no strategies to evaluate"}

    top = all_scored_rows[0]

    if current_champion_row is None:
        return {
            "decision":         "initial_champion",
            "champion":         top["strategy"],
            "composite_score":  top["composite_score"],
            "reason":           "no prior champion recorded; adopting top-ranked strategy",
            "gates":            {},
        }

    if top["strategy"] == current_champion_row["strategy"]:
        return {
            "decision":         "hold_champion",
            "champion":         top["strategy"],
            "composite_score":  top["composite_score"],
            "reason":           "incumbent still top-ranked",
            "gates":            {},
        }

    # Would we promote the leader over the incumbent?
    margin = top["composite_score"] - current_champion_row["composite_score"]
    margin_ok = margin >= MIN_MARGIN

    top_drift = drift_by_strategy.get(top["strategy"], {})
    stability_ok = top_drift.get("stability_flag") in ("stable", "improving", None)

    top_trades = _get(top, ["n_trades", "trade_metrics_n_trades"], default=0) or 0
    inc_trades = _get(current_champion_row, ["n_trades", "trade_metrics_n_trades"], default=0) or 0
    sample_ok = (top_trades >= MIN_TRADES) and (inc_trades >= MIN_TRADES)

    top_dd = abs(float(_get(top, ["max_dd_pct"], default=0.0) or 0.0))
    inc_dd = abs(float(_get(current_champion_row, ["max_dd_pct"], default=0.0) or 0.0))
    extra_dd = top_dd - inc_dd
    dd_ok = extra_dd <= MAX_EXTRA_DD

    gates = {
        "margin_gate":      {"passed": bool(margin_ok),  "value": round(margin, 3),  "threshold": MIN_MARGIN},
        "stability_gate":   {"passed": bool(stability_ok), "flag": top_drift.get("stability_flag")},
        "sample_gate":      {"passed": bool(sample_ok),  "challenger_trades": int(top_trades),
                              "champion_trades": int(inc_trades), "threshold": MIN_TRADES},
        "drawdown_gate":    {"passed": bool(dd_ok),      "extra_dd_pp": round(extra_dd, 2),
                              "threshold_pp": MAX_EXTRA_DD},
    }

    all_passed = all(g["passed"] for g in gates.values())

    if all_passed:
        return {
            "decision":            "promote_challenger",
            "current_champion":    current_champion_row["strategy"],
            "recommended_champion": top["strategy"],
            "composite_delta":     round(margin, 3),
            "reason":              "all promotion gates passed",
            "gates":               gates,
        }
    else:
        failed = [k for k, v in gates.items() if not v["passed"]]
        return {
            "decision":            "hold_champion",
            "current_champion":    current_champion_row["strategy"],
            "top_of_leaderboard":  top["strategy"],
            "composite_delta":     round(margin, 3),
            "reason":              f"failed gates: {', '.join(failed)}",
            "gates":               gates,
        }
