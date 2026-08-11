"""P1 · Attribution/Interaction Research Engine.

Reads canonical outcome_dataset.parquet · never XLSX (governance).
Runs single-factor + multi-factor cross-tabs · every cell sample-tier tagged.

Answers: which combinations of (Runner, Cap, Sector, Investability) actually
produce positive expectancy · closed positions only per governance rule.

Emits:
  reports/research/attribution_analysis.json  (machine)
  reports/research/attribution_report.md      (human)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


SAMPLE_TIERS = [
    (0, 4,       "observation only"),
    (5, 14,      "hypothesis"),
    (15, 29,     "research signal"),
    (30, 49,     "stronger evidence"),
    (50, 999999, "validation candidate"),
]


def _tier(n: int) -> str:
    for lo, hi, label in SAMPLE_TIERS:
        if lo <= n <= hi:
            return label
    return "unknown"


def _metrics(subset) -> dict:
    """Compute full metric panel for a subset (closed positions).
    N · Win% · Avg · Median · Profit Factor · Expectancy · Max DD · Horizon returns."""
    import pandas as pd
    if len(subset) == 0:
        return {"n": 0, "tier": _tier(0)}

    n = len(subset)
    wins = subset[subset["win_flag"] == True]
    losses = subset[subset["win_flag"] == False]
    pnls = subset["exit_pnl_pct"].dropna()

    if len(pnls) == 0:
        return {"n": n, "tier": _tier(n), "note": "no exit_pnl values"}

    avg = round(float(pnls.mean()), 3)
    median = round(float(pnls.median()), 3)
    max_dd = round(float(subset["max_drawdown_pct"].min()), 2) \
                    if "max_drawdown_pct" in subset.columns else None

    # Profit factor = sum(wins) / abs(sum(losses))
    win_sum = float(wins["exit_pnl_pct"].sum()) if len(wins) else 0
    loss_sum = float(losses["exit_pnl_pct"].sum()) if len(losses) else 0
    if loss_sum == 0:
        profit_factor = float("inf") if win_sum > 0 else None
    else:
        profit_factor = round(win_sum / abs(loss_sum), 2)

    # Expectancy (per-trade edge in %) = mean of exit_pnl_pct
    expectancy = round(avg, 3)

    win_pct = round(len(wins) / n * 100, 1) if n else 0

    # Horizon returns · non-null averages across ALL positions in subset (open + closed)
    horizons = {}
    for h in [1, 3, 5, 10, 17, 30, 60, 90]:
        col = f"ret_{h}d_pct"
        if col in subset.columns:
            observed = subset[col].dropna()
            if len(observed) >= 2:
                horizons[f"{h}d"] = {
                    "n": len(observed),
                    "avg": round(float(observed.mean()), 2),
                    "pct_positive": round((observed > 0).mean() * 100, 1),
                }

    return {
        "n":              n,
        "n_wins":         len(wins),
        "n_losses":       len(losses),
        "win_pct":        win_pct,
        "avg_pnl_pct":    avg,
        "median_pnl_pct": median,
        "profit_factor":  profit_factor if profit_factor != float("inf") else None,
        "expectancy_pct": expectancy,
        "max_drawdown_worst_pos_pct": max_dd,
        "horizons":       horizons,
        "tier":           _tier(n),
    }


def analyze_dimension(df, dim: str, closed_only: bool = True) -> dict:
    """Single-dimension breakdown (e.g., all Runner values)."""
    subset = df[df["is_closed"] == True] if closed_only else df
    if dim not in subset.columns: return {}
    out = {}
    for value in subset[dim].dropna().unique():
        cell = subset[subset[dim] == value]
        out[str(value)] = _metrics(cell)
    return out


def analyze_interaction(df, dims: list, closed_only: bool = True) -> dict:
    """Multi-dimension cross-tab."""
    subset = df[df["is_closed"] == True] if closed_only else df
    if not all(d in subset.columns for d in dims): return {}
    grouped = subset.groupby(dims, dropna=False)
    out = {}
    for keys, cell in grouped:
        if not isinstance(keys, tuple): keys = (keys,)
        key_label = " x ".join(str(k) for k in keys)
        out[key_label] = _metrics(cell)
    return out


def winner_profile(df, top_n_combos: int = 5) -> list:
    """Best-performing (Cap, Sector) combinations · closed only."""
    closed = df[df["is_closed"] == True]
    if len(closed) == 0: return []
    grouped = closed.groupby(["runner", "cap", "sector"], dropna=False).agg(
        n=("position_id", "count"),
        avg_pnl=("exit_pnl_pct", "mean"),
        win_rate=("win_flag", "mean"),
    ).reset_index().sort_values("avg_pnl", ascending=False)
    grouped = grouped[grouped["n"] >= 1]
    result = []
    for _, row in grouped.head(top_n_combos).iterrows():
        result.append({
            "runner":     str(row["runner"]),
            "cap":        str(row["cap"]),
            "sector":     str(row["sector"]),
            "n":          int(row["n"]),
            "avg_pnl":    round(float(row["avg_pnl"]), 2),
            "win_pct":    round(float(row["win_rate"]) * 100, 1),
            "tier":       _tier(int(row["n"])),
        })
    return result


def failure_profile(df, bottom_n_combos: int = 5) -> list:
    """Worst-performing (Cap, Sector) combinations · closed only."""
    closed = df[df["is_closed"] == True]
    if len(closed) == 0: return []
    grouped = closed.groupby(["runner", "cap", "sector"], dropna=False).agg(
        n=("position_id", "count"),
        avg_pnl=("exit_pnl_pct", "mean"),
        win_rate=("win_flag", "mean"),
    ).reset_index().sort_values("avg_pnl", ascending=True)
    grouped = grouped[grouped["n"] >= 1]
    result = []
    for _, row in grouped.head(bottom_n_combos).iterrows():
        result.append({
            "runner":     str(row["runner"]),
            "cap":        str(row["cap"]),
            "sector":     str(row["sector"]),
            "n":          int(row["n"]),
            "avg_pnl":    round(float(row["avg_pnl"]), 2),
            "win_pct":    round(float(row["win_rate"]) * 100, 1),
            "tier":       _tier(int(row["n"])),
        })
    return result


def run(root: Path) -> dict:
    """Full attribution analysis · reads outcome_dataset.parquet."""
    import pandas as pd

    ds_path = root / "reports" / "research" / "outcome_dataset.parquet"
    if not ds_path.exists():
        return {"error": "outcome_dataset.parquet missing · run build_outcome_dataset first"}

    df = pd.read_parquet(ds_path)

    single_dimensions = ["runner", "cap", "sector", "initial_investability_verdict"]
    interactions = [
        ["runner", "cap"],
        ["runner", "sector"],
        ["cap", "sector"],
        ["runner", "cap", "sector"],
        ["runner", "initial_investability_verdict"],
        ["cap", "initial_investability_verdict"],
        ["sector", "initial_investability_verdict"],
    ]

    result = {
        "engine":         "attribution_engine.v1",
        "generated_utc":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source":         str(ds_path.relative_to(root)),
        "n_positions":    len(df),
        "n_closed":       int(df["is_closed"].sum()),
        "n_open":         int((~df["is_closed"]).sum()),
        "sample_tier_policy": {
            "0-4":     "observation only",
            "5-14":    "hypothesis",
            "15-29":   "research signal",
            "30-49":   "stronger evidence",
            "50+":     "validation candidate",
        },
        "single_dimensions": {
            dim: analyze_dimension(df, dim) for dim in single_dimensions
        },
        "interactions": {
            " x ".join(dims): analyze_interaction(df, dims) for dims in interactions
        },
        "winner_profile":  winner_profile(df),
        "failure_profile": failure_profile(df),
    }
    return result


def _tier_emoji(tier: str) -> str:
    return {
        "observation only":     "OBS",
        "hypothesis":           "HYP",
        "research signal":      "SIG",
        "stronger evidence":    "STR",
        "validation candidate": "VAL",
    }.get(tier, "?")


def emit_json(root: Path, result: dict) -> Path:
    p = root / "reports" / "research" / "attribution_analysis.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def emit_markdown(root: Path, result: dict) -> Path:
    """Human-readable attribution report."""
    lines = []
    lines.append(f"# AEGIS Attribution Report")
    lines.append("")
    lines.append(f"**Generated:** {result.get('generated_utc')}")
    lines.append(f"**Source:** `{result.get('source')}`")
    lines.append(f"**Positions:** {result.get('n_positions')} total · "
                       f"{result.get('n_closed')} closed · {result.get('n_open')} open")
    lines.append("")
    lines.append("## Sample-size tiers")
    lines.append("| Tier | N range | Meaning |")
    lines.append("|---|---|---|")
    lines.append("| observation only | 0-4 | anecdote · not actionable |")
    lines.append("| hypothesis | 5-14 | worth testing |")
    lines.append("| research signal | 15-29 | investigate seriously |")
    lines.append("| stronger evidence | 30-49 | candidate for model change |")
    lines.append("| validation candidate | 50+ | ready for walk-forward |")
    lines.append("")

    # Single dimensions
    lines.append("## Single-dimension breakdowns (closed positions only)")
    for dim, cells in (result.get("single_dimensions") or {}).items():
        lines.append(f"### {dim}")
        lines.append("| Value | N | Win% | Avg P&L | Median | Profit Factor | Tier |")
        lines.append("|---|---|---|---|---|---|---|")
        rows = sorted(cells.items(), key=lambda x: (-(x[1].get("avg_pnl_pct") or -999)))
        for value, m in rows:
            if "note" in m and m.get("n", 0) == 0: continue
            lines.append(f"| {value} | {m.get('n')} | "
                              f"{m.get('win_pct','—')}% | "
                              f"{m.get('avg_pnl_pct','—')}% | "
                              f"{m.get('median_pnl_pct','—')}% | "
                              f"{m.get('profit_factor','—')} | "
                              f"{_tier_emoji(m.get('tier','?'))} |")
        lines.append("")

    # Interactions
    lines.append("## Interaction cross-tabs")
    for label, cells in (result.get("interactions") or {}).items():
        lines.append(f"### {label}")
        lines.append("| Combination | N | Win% | Avg P&L | Median | Tier |")
        lines.append("|---|---|---|---|---|---|")
        rows = sorted(cells.items(), key=lambda x: (-(x[1].get("avg_pnl_pct") or -999)))
        for combo, m in rows:
            if "note" in m and m.get("n", 0) == 0: continue
            lines.append(f"| {combo} | {m.get('n')} | "
                              f"{m.get('win_pct','—')}% | "
                              f"{m.get('avg_pnl_pct','—')}% | "
                              f"{m.get('median_pnl_pct','—')}% | "
                              f"{_tier_emoji(m.get('tier','?'))} |")
        lines.append("")

    # Winner profile
    lines.append("## Winner profile (top 5 · Runner × Cap × Sector)")
    lines.append("| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, w in enumerate(result.get("winner_profile") or [], 1):
        lines.append(f"| {i} | {w['runner']} | {w['cap']} | {w['sector']} | "
                          f"{w['n']} | {w['win_pct']}% | {w['avg_pnl']}% | {_tier_emoji(w['tier'])} |")
    lines.append("")

    # Failure profile
    lines.append("## Failure profile (bottom 5 · Runner × Cap × Sector)")
    lines.append("| # | Runner | Cap | Sector | N | Win% | Avg P&L | Tier |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, w in enumerate(result.get("failure_profile") or [], 1):
        lines.append(f"| {i} | {w['runner']} | {w['cap']} | {w['sector']} | "
                          f"{w['n']} | {w['win_pct']}% | {w['avg_pnl']}% | {_tier_emoji(w['tier'])} |")
    lines.append("")

    # Governance footer
    lines.append("---")
    lines.append("**Governance:** No R1/R2 changes above tier 'observation only'. "
                       "No interaction claims below tier 'research signal' (n≥15). "
                       "Winner/failure profiles are early observations · sample sizes noted.")

    p = root / "reports" / "research" / "attribution_report.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
