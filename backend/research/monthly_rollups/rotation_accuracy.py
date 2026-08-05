"""Monthly rollup · Rotation Accuracy.

For every rotation event in portfolio_ledger.jsonl within the month, compare
the engine's `expected_alpha_delta_pp` (predicted edge at rotation time) vs
the actual realised alpha between out_ticker and in_ticker over the holding
period.

Metrics:
    · n_rotations                     · total rotations judged
    · directionally_correct_pct       · % where engine predicted correct sign
    · median_expected_pp / median_actual_pp
    · rotation_engine_score           · correlation coefficient
    · top_wins   · top 5 rotations where actual >> expected
    · top_losses · top 5 rotations where actual << expected
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


MIN_ROTATIONS_FOR_ROLLUP = 5    # below this → insufficient_data


@dataclass
class RotationJudgment:
    asof: str
    out_ticker: str
    in_ticker: str
    expected_alpha_pp: float
    out_return_pct: float
    in_return_pct: float
    actual_alpha_pp: float           # in_return - out_return
    error_pp: float                  # actual - expected
    direction_correct: bool


def _load_ledger_rotations(root: Path, market: str, month: str) -> list[dict]:
    """Return matched ROTATE_OUT/ROTATE_IN pairs within the month."""
    p = root / "reports" / "research" / "portfolio_ledger.jsonl"
    if not p.exists(): return []
    events = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:  d = json.loads(line)
        except json.JSONDecodeError: continue
        if d.get("market") != market: continue
        if not str(d.get("asof") or "").startswith(month): continue
        events.append(d)
    pairs: dict[str, dict] = {}
    for e in events:
        if e.get("event") == "ROTATE_OUT":
            key = f"{e['asof']}::{e['ticker']}"
            pairs.setdefault(key, {"out": None, "in": None})["out"] = e
        elif e.get("event") == "ROTATE_IN":
            linked = e.get("linked_from") or ""
            key = f"{e['asof']}::{linked}"
            pairs.setdefault(key, {"out": None, "in": None})["in"] = e
    return [{"out": v["out"], "in": v["in"]}
                for v in pairs.values() if v["out"] and v["in"]]


def _actual_return(root: Path, market: str, ticker: str,
                       from_date: str, to_date: str | None = None) -> float | None:
    """Approximate realised return from position_store history."""
    reports = root / ("usa/reports" if market == "usa" else "reports")
    pos_file = reports / "position_store" / market / "positions.json"
    if not pos_file.exists(): return None
    try:
        d = json.loads(pos_file.read_text(encoding="utf-8"))
        pos = (d.get("positions") or {}).get(ticker)
        if not pos: return None
        entry = pos.get("first_seen_price") or 0
        last = pos.get("last_seen_price") or entry
        if not entry: return None
        return ((last - entry) / entry) * 100.0
    except Exception:
        return None


def compute(root: Path, market: str, month: str) -> dict:
    pairs = _load_ledger_rotations(root, market, month)
    judgments: list[RotationJudgment] = []
    for pair in pairs:
        out_ev = pair["out"]; in_ev = pair["in"]
        expected = float(out_ev.get("edge_pp") or in_ev.get("edge_pp") or 0.0)
        out_r = _actual_return(root, market, out_ev.get("ticker") or "",
                                     out_ev.get("asof") or "")
        in_r = _actual_return(root, market, in_ev.get("ticker") or "",
                                     in_ev.get("asof") or "")
        if out_r is None or in_r is None: continue
        actual = in_r - out_r
        err = actual - expected
        judgments.append(RotationJudgment(
            asof=out_ev.get("asof") or "",
            out_ticker=out_ev.get("ticker") or "",
            in_ticker=in_ev.get("ticker") or "",
            expected_alpha_pp=round(expected, 2),
            out_return_pct=round(out_r, 2),
            in_return_pct=round(in_r, 2),
            actual_alpha_pp=round(actual, 2),
            error_pp=round(err, 2),
            direction_correct=(actual >= 0 and expected >= 0)
                                    or (actual < 0 and expected < 0),
        ))

    n = len(judgments)
    n_correct = sum(1 for j in judgments if j.direction_correct)

    def _median(xs):
        if not xs: return None
        s = sorted(xs); return s[len(s) // 2]

    med_exp = _median([j.expected_alpha_pp for j in judgments])
    med_act = _median([j.actual_alpha_pp for j in judgments])

    # Pearson correlation (only when n ≥ 3)
    corr = None
    if n >= 3:
        xs = [j.expected_alpha_pp for j in judgments]
        ys = [j.actual_alpha_pp for j in judgments]
        mx = sum(xs) / n; my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
        dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
        corr = round(num / (dx * dy), 3) if dx * dy > 0 else 0

    top_wins = sorted(judgments, key=lambda j: -(j.actual_alpha_pp - j.expected_alpha_pp))[:5]
    top_losses = sorted(judgments, key=lambda j: (j.actual_alpha_pp - j.expected_alpha_pp))[:5]

    return {
        "engine":                 "aegis.research.rotation_accuracy.v1",
        "generated_utc":          datetime.now(timezone.utc).isoformat(),
        "market":                 market, "month": month,
        "n_rotations":            n,
        "insufficient_data":      n < MIN_ROTATIONS_FOR_ROLLUP,
        "min_rotations_required": MIN_ROTATIONS_FOR_ROLLUP,
        "directionally_correct_pct": round(n_correct / n * 100.0, 1) if n else None,
        "median_expected_alpha_pp":  med_exp,
        "median_actual_alpha_pp":    med_act,
        "expected_vs_actual_correlation": corr,
        "top_wins":               [asdict(j) for j in top_wins],
        "top_losses":             [asdict(j) for j in top_losses],
        "all_judgments":          [asdict(j) for j in judgments],
    }


def render_md(rep: dict) -> str:
    lines = [f"# Rotation Accuracy · {rep['market'].upper()} · {rep['month']}",
                "",
                f"Rotations judged: **{rep['n_rotations']}** · "
                f"Directionally correct: **{rep.get('directionally_correct_pct') or '—'}%** · "
                f"Correlation: **{rep.get('expected_vs_actual_correlation') or '—'}**",
                ""]
    if rep["insufficient_data"]:
        lines.append(f"> ⚠️ INSUFFICIENT DATA · n={rep['n_rotations']} "
                          f"< min {rep['min_rotations_required']} · directional only.\n")
    lines += [f"Median expected alpha: **{rep.get('median_expected_alpha_pp') or '—'}pp** · "
                 f"Median actual alpha: **{rep.get('median_actual_alpha_pp') or '—'}pp**",
                 ""]
    if rep["top_wins"]:
        lines += ["## Top 5 wins (actual >> expected)", "",
                     "| Asof | Out → In | Expected | Actual | Δ |",
                     "|---|---|---|---|---|"]
        for j in rep["top_wins"]:
            diff = j["actual_alpha_pp"] - j["expected_alpha_pp"]
            lines.append(f"| {j['asof']} | {j['out_ticker']} → {j['in_ticker']} | "
                              f"{j['expected_alpha_pp']:+.1f}pp | {j['actual_alpha_pp']:+.1f}pp | "
                              f"{diff:+.1f}pp |")
    if rep["top_losses"]:
        lines += ["", "## Top 5 misses (actual << expected)", "",
                     "| Asof | Out → In | Expected | Actual | Δ |",
                     "|---|---|---|---|---|"]
        for j in rep["top_losses"]:
            diff = j["actual_alpha_pp"] - j["expected_alpha_pp"]
            lines.append(f"| {j['asof']} | {j['out_ticker']} → {j['in_ticker']} | "
                              f"{j['expected_alpha_pp']:+.1f}pp | {j['actual_alpha_pp']:+.1f}pp | "
                              f"{diff:+.1f}pp |")
    return "\n".join(lines) + "\n"
