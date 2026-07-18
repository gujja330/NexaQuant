"""Risk & Capital v2.0 · publish."""
from __future__ import annotations

import json
from datetime import date
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
    if isinstance(obj, float):
        return None if np.isnan(obj) or np.isinf(obj) else obj
    if isinstance(obj, (np.integer, np.floating)):
        v = float(obj)
        return None if np.isnan(v) or np.isinf(v) else v
    if isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    return obj


def _explanation_md(result: dict) -> str:
    lines = [
        f"# Risk & Capital Engine · v2.0 · {result['as_of']}",
        "",
        f"_Generated {result['run_utc']} · regime **{result['regime']}**_",
        "",
        "## Portfolio-level risk",
        "",
    ]
    risk = result["portfolio_risk"] or {}
    lines += [
        f"- Portfolio annualised vol: **{risk.get('portfolio_vol_annual')}**",
        f"- VaR 95%: **{risk.get('var_95')}** · VaR 99%: **{risk.get('var_99')}**",
        f"- CVaR 95%: **{risk.get('cvar_95')}**",
        f"- Verdict: **{risk.get('verdict')}**",
        "",
        "### Budget utilisation",
        "",
    ]
    bu = risk.get("budget_utilisation") or {}
    for k, v in bu.items():
        lines.append(f"- `{k}` : {v}")

    if risk.get("alerts"):
        lines += ["", "### Risk alerts", ""]
        for a in risk["alerts"]:
            lines.append(f"- [{a['severity']}] **{a['kind']}** · `{a['entity']}` — {a['detail']}")

    if risk.get("per_sector"):
        lines += ["", "### Per-sector variance contribution", "",
                    "| Sector | VaR Contribution | Budget Utilisation |",
                    "|--------|------------------:|---------------------:|"]
        for row in risk["per_sector"]:
            lines.append(f"| {row['sector']} | {row['var_contribution']} | "
                            f"{row['budget_utilisation']} |")

    lines += ["", "## Position sizing (top-10 by target weight)", "",
                "For each position, why the size is what it is — and what would",
                "have to change for the size to become 4% or 12% instead.", ""]

    top = sorted(result["sizing"], key=lambda d: -d["target_weight"])[:10]
    for d in top:
        lines += [
            f"### `{d['ticker']}` · target **{d['target_weight']*100:.2f}%** · verdict **{d['verdict']}**",
            "",
            f"{d['explanation']}", "",
            "**Factors**", "",
        ]
        for f in d["factors"]:
            lines.append(f"- `{f['name']}` = {f['value']}  —  {f['explanation']}")
        cf = d["counterfactuals"]
        lines += [
            "",
            f"**Why not 4%?**   {cf['at_4pct']['reasoning']}",
            "",
            f"**Why not 12%?**  {cf['at_12pct']['reasoning']}",
            "",
        ]

    lines += ["", "## Governance", "", f"> {result['governance']}"]
    return "\n".join(lines)


def build_and_publish(result: dict) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    with (REPORTS / "risk_capital_v2_latest.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(result), f, indent=2, default=str)

    with (REPORTS / f"risk_capital_v2_{stamp}.json").open("w", encoding="utf-8") as f:
        json.dump(_sanitize(result), f, indent=2, default=str)

    (REPORTS / f"risk_capital_v2_explanation_{stamp}.md").write_text(
        _explanation_md(result), encoding="utf-8")

    # Sizing summary parquet
    sizing_df = pd.DataFrame([{
        "ticker":         d["ticker"],
        "target_weight":  d["target_weight"],
        "verdict":        d["verdict"],
        "confidence_factor": next((f["value"] for f in d["factors"] if f["name"] == "confidence"), None),
        "regime_factor":     next((f["value"] for f in d["factors"] if f["name"] == "regime"), None),
        "volatility_factor": next((f["value"] for f in d["factors"] if f["name"] == "volatility"), None),
        "sector_conc_factor": next((f["value"] for f in d["factors"] if f["name"] == "sector_concentration"), None),
    } for d in result["sizing"]])
    sizing_df.to_parquet(REPORTS / "risk_capital_v2_sizing.parquet", index=False)

    return {
        "written": [
            "risk_capital_v2_latest.json",
            f"risk_capital_v2_{stamp}.json",
            f"risk_capital_v2_explanation_{stamp}.md",
            "risk_capital_v2_sizing.parquet",
        ],
        "n_sized":  len(result["sizing"]),
        "verdict":  (result["portfolio_risk"] or {}).get("verdict"),
    }
