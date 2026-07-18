"""Validation Engine v2.0 · publish."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
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
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj


def _daily_report_md(result: dict) -> str:
    lines = [
        f"# Validation Engine · Daily Report · {result['as_of']}",
        "",
        f"_Generated {result['run_utc']} · code_sha `{result['code_sha']}`_",
        "",
        "## Portfolio",
        "",
        f"- Open positions: **{result['n_open_positions']}**",
        f"- New opens today: **{result['n_new_opens']}**",
        f"- New closes today: **{result['n_new_closes']}**",
        f"- Closed trades on file: **{result['n_closed_trades']}**",
        f"- Portfolio P&L (open, weighted): **{result['portfolio_pnl_pct']*100:+.2f}%**",
        "",
        "## Expected vs Actual",
        "",
    ]
    rec = result["reconciliation"] or {}
    if rec.get("n", 0) == 0:
        lines.append(f"_{rec.get('note') or 'no closed trades yet'}_")
    else:
        lines += [
            f"- Trades reconciled: **{rec['n']}**",
            f"- Avg return delta (actual - expected): **{rec.get('avg_return_delta')}**",
            f"- Target hit rate: **{rec.get('target_hit_rate')}**",
            f"- Stop hit rate: **{rec.get('stop_hit_rate')}**",
            f"- Within 5pp tolerance: **{rec.get('within_5pp_tolerance')}**",
        ]

    lines += ["", "## Drift", ""]
    dr = result["metric_drift"] or {}
    if dr.get("flag") == "insufficient_evidence":
        lines.append(f"_{dr.get('note') or 'insufficient evidence'}_")
    else:
        lines += [
            f"- Flag: **{dr.get('flag')}**",
            f"- 1st-half Sharpe: {dr.get('first_half_sharpe')} · 2nd-half: {dr.get('second_half_sharpe')}",
            f"- 1st-half winrate: {dr.get('first_half_winrate')} · 2nd-half: {dr.get('second_half_winrate')}",
            f"- Sharpe change: {dr.get('sharpe_change_pct')} · winrate change: {dr.get('winrate_change_pp')}",
        ]
        if dr.get("warning_flags"):
            lines.append(f"- Warnings: `{', '.join(dr['warning_flags'])}`")

    lines += ["", "## Opportunity Cost", ""]
    oc = result["opportunity_cost"] or {}
    if oc.get("n_missed_edges", 0) == 0:
        lines.append(f"_{oc.get('note') or 'no missed edges detected'}_")
    else:
        lines += [
            f"- Window: last **{oc['window_days']} days**",
            f"- Tickers in window: {oc['n_tickers_in_window']}",
            f"- Missed edges: **{oc['n_missed_edges']}**",
            f"- Total missed expectancy: **{oc['total_missed_expectancy']*100:+.2f}%**",
            f"- Avg missed expectancy per ticker: **{oc['avg_missed_expectancy']*100:+.2f}%**",
        ]
        lines.append("")
        lines.append("| Ticker | n | win_rate | expectancy |")
        lines.append("|--------|--:|--------:|-----------:|")
        for row in (oc.get("top_missed") or [])[:10]:
            lines.append(f"| {row.get('ticker')} | {row.get('n_trades')} | "
                            f"{row.get('win_rate')} | {row.get('expectancy')} |")

    lines += [
        "",
        "## Governance",
        "",
        f"> {result['governance']}",
    ]
    return "\n".join(lines)


def build_and_publish(result: dict) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    core = {k: v for k, v in result.items() if not k.startswith("_")}
    stamp = date.today().isoformat()

    # 1. Latest headline
    with (REPORTS / "validation_v2_latest.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(core), f, indent=2, default=str)

    # 2. Timestamped daily snapshot
    with (REPORTS / f"validation_v2_daily_{stamp}.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(core), f, indent=2, default=str)

    # 3. Daily markdown report
    (REPORTS / f"validation_v2_daily_{stamp}.md").write_text(
        _daily_report_md(result), encoding="utf-8")

    # 4. Open positions snapshot
    from validation_v2.lib import paper_portfolio
    open_pos = paper_portfolio.open_positions()
    if not open_pos.empty:
        open_pos.to_csv(REPORTS / f"validation_v2_open_positions_{stamp}.csv", index=False)

    # 5. Closed trades ledger (deterministic snapshot)
    closed = paper_portfolio.closed_trades()
    if not closed.empty:
        closed.to_csv(REPORTS / "validation_v2_closed_trades.csv", index=False)

    return {
        "written": [
            "validation_v2_latest.json",
            f"validation_v2_daily_{stamp}.json",
            f"validation_v2_daily_{stamp}.md",
        ],
        "n_open":  int(result["n_open_positions"]),
        "n_closed": int(result["n_closed_trades"]),
        "drift_flag": (result.get("metric_drift") or {}).get("flag"),
    }
