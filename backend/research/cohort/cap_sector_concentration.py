"""AEGIS · CAP x SECTOR LOSS-CONCENTRATION STUDY · CEO 2026-09-08.

> "Across the last 60+ forward predictions in India and USA, where are the
>  losses actually concentrated - by market-cap bucket, sector, and their
>  interaction - and why?"

RESEARCH ONLY. This module reads the forward-prediction cohort and writes
one report. It changes no threshold, writes into no engine or registry,
and produces no production rule. Per the directive it sits DOWNSTREAM of
the lifecycle/rotation work and is deliberately not mixed into it.

WHAT THE DATA ACTUALLY SUPPORTS
-------------------------------
The directive's central warning is that a cap effect may really be a
sector effect:

> "if Mid-cap = bad but Mid-cap Industrials = bad while Mid-cap Healthcare
>  = fine, then 'avoid Mid-cap' is the wrong strategy"

Controlling for that requires sector. In the cohort as it stands:

  cap_bucket   India 725/725 (100%)   ·  USA 1147/1156 (99%)   USABLE
  sector       India 250/725  (34%)   ·  USA   0/1156  (0%)    BROKEN
  regime       India   0/725   (0%)   ·  USA   0/1156  (0%)    ABSENT

USA's `sector` field contains "Large-Cap" for 995 of 1156 rows - a CAP
label written into the sector column, not a sector. So for USA the
sector-confound control the directive specifically demands cannot be
performed at all, and any USA cap finding here is UNCONTROLLED by
construction. That is reported as a blocking limitation rather than
worked around, because a cap verdict that silently ignores sector is
exactly the error the directive was written to prevent.

Regime is null in both markets, so the regime x cap stratum is omitted
rather than fabricated.

STATISTICAL GATE
----------------
Every cell is labelled with the locked sample-size vocabulary and no cell
may be read as a rule:

    n < 5      OBSERVATION
    5-14       HYPOTHESIS
    15-29      RESEARCH_SIGNAL
    30-49      STRONGER_EVIDENCE
    n >= 50    VALIDATION_CANDIDATE

Reaching VALIDATION_CANDIDATE means the cell is worth taking to the
existing forward-validation / multiple-testing / PIT / walk-forward gates.
It does NOT mean it is actionable.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.research.cap_sector_concentration.v1"

HORIZONS = ["fwd_1d_pct", "fwd_3d_pct", "fwd_5d_pct", "fwd_10d_pct",
            "fwd_20d_pct"]
PRIMARY_HORIZON = "fwd_5d_pct"

TIERS = ((5, "OBSERVATION"), (15, "HYPOTHESIS"), (30, "RESEARCH_SIGNAL"),
         (50, "STRONGER_EVIDENCE"))


def tier(n: int) -> str:
    for cap, name in TIERS:
        if n < cap:
            return name
    return "VALIDATION_CANDIDATE"


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _clean(v) -> Optional[str]:
    s = str(v or "").strip()
    if s.upper() in ("", "NONE", "UNKNOWN", "NAN", "?", "N/A"):
        return None
    return s


def load_cohort(root: Path, market: str) -> list:
    p = (root / "reports" / "research"
         / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl")
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def field_health(rows: list) -> dict:
    """Report what the study can and cannot control for.

    USA's sector column holds "Large-Cap" - a cap label in the sector
    field. Detecting that here, rather than grouping on it, is the
    difference between a caveat and a false finding.
    """
    n = len(rows) or 1
    sec_vals = {_clean(r.get("sector")) for r in rows} - {None}
    cap_vals = {_clean(r.get("cap_bucket")) for r in rows} - {None}
    contaminated = sorted(v for v in sec_vals
                          if v.upper().replace("-", "").replace(" ", "")
                          in {"LARGECAP", "MIDCAP", "SMALLCAP"})
    return {
        "n_rows": len(rows),
        "cap_usable": sum(1 for r in rows if _clean(r.get("cap_bucket"))),
        "cap_pct": round(sum(1 for r in rows
                             if _clean(r.get("cap_bucket"))) / n * 100, 1),
        "cap_values": sorted(cap_vals),
        "sector_usable": sum(1 for r in rows if _clean(r.get("sector"))),
        "sector_pct": round(sum(1 for r in rows
                                if _clean(r.get("sector"))) / n * 100, 1),
        "sector_distinct": len(sec_vals),
        "sector_contaminated_with_cap_labels": contaminated,
        "regime_usable": sum(1 for r in rows if _clean(r.get("regime"))),
        "horizons_populated": {h: sum(1 for r in rows
                                      if _num(r.get(h)) is not None)
                               for h in HORIZONS},
        "sector_control_possible": (
            not contaminated
            and sum(1 for r in rows if _clean(r.get("sector"))) >= n * 0.6),
    }


def _stats(vals: list) -> dict:
    """Expectancy-first, per the directive: a bucket with 300 predictions
    and a small negative total may be healthier than one with 20 and a
    large negative total. Aggregate P&L alone ranks the wrong things."""
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    wins = [v for v in s if v > 0]
    losses = [v for v in s if v < 0]
    q = s[max(0, int(n * 0.05) - 1)] if n >= 20 else s[0]
    return {
        "n": n,
        "tier": tier(n),
        "expectancy_pct": round(sum(s) / n, 3),
        "median_pct": round(s[n // 2], 3),
        "win_rate_pct": round(len(wins) / n * 100, 1),
        "mean_win_pct": round(sum(wins) / len(wins), 3) if wins else None,
        "mean_loss_pct": round(sum(losses) / len(losses), 3) if losses else None,
        "worst_pct": round(s[0], 3),
        "p5_tail_pct": round(q, 3),
        "total_negative_contribution_pct": round(sum(losses), 2),
        "profit_factor": (round(sum(wins) / abs(sum(losses)), 3)
                          if losses and sum(losses) else None),
    }


def _group(rows: list, keyfn, horizon: str) -> dict:
    buckets = {}
    for r in rows:
        k = keyfn(r)
        if k is None:
            continue
        v = _num(r.get(horizon))
        if v is None:
            continue
        buckets.setdefault(k, []).append(v)
    return {k: _stats(v) for k, v in sorted(buckets.items())}


def counterfactual(rows: list, horizon: str, exclude_key, keyfn) -> dict:
    """> "Would excluding that bucket have actually improved the portfolio?"

    Guards against a filter that looks good only because it discards half
    the universe: the number of profitable predictions sacrificed is
    reported alongside the improvement.
    """
    base, kept, dropped = [], [], []
    for r in rows:
        v = _num(r.get(horizon))
        if v is None:
            continue
        base.append(v)
        (dropped if keyfn(r) == exclude_key else kept).append(v)
    if not base or not dropped:
        return {}
    b, k = _stats(base), _stats(kept)
    return {
        "excluded": exclude_key,
        "baseline": b,
        "after_exclusion": k,
        "delta_expectancy_pp": round(k["expectancy_pct"] - b["expectancy_pct"], 3),
        "delta_win_rate_pp": round(k["win_rate_pct"] - b["win_rate_pct"], 1),
        "worst_loss_improvement_pp": round(k["worst_pct"] - b["worst_pct"], 3),
        "predictions_removed": len(dropped),
        "profitable_predictions_sacrificed": sum(1 for v in dropped if v > 0),
        "share_of_universe_removed_pct": round(len(dropped) / len(base) * 100, 1),
    }


def _conf_bucket(r) -> Optional[str]:
    c = _num(r.get("confidence_pct"))
    if c is None:
        return None
    if c < 40:
        return "conf<40"
    if c < 55:
        return "conf40-55"
    if c < 70:
        return "conf55-70"
    return "conf>=70"


def compute(root: Path, market: str) -> dict:
    rows = load_cohort(root, market)
    if not rows:
        return {"market": market, "error": "cohort missing"}
    health = field_health(rows)

    by_cap = {h: _group(rows, lambda r: _clean(r.get("cap_bucket")), h)
              for h in HORIZONS}
    by_sector = {h: _group(rows, lambda r: _clean(r.get("sector")), h)
                 for h in HORIZONS} if health["sector_control_possible"] else {}
    by_cap_conf = _group(
        rows,
        lambda r: (f"{_clean(r.get('cap_bucket'))}|{_conf_bucket(r)}"
                   if _clean(r.get("cap_bucket")) and _conf_bucket(r) else None),
        PRIMARY_HORIZON)

    cap_sector = {}
    if health["sector_control_possible"]:
        cap_sector = _group(
            rows,
            lambda r: (f"{_clean(r.get('cap_bucket'))}|{_clean(r.get('sector'))}"
                       if _clean(r.get("cap_bucket")) and _clean(r.get("sector"))
                       else None),
            PRIMARY_HORIZON)

    cfs = {}
    for k in (by_cap.get(PRIMARY_HORIZON) or {}):
        cf = counterfactual(rows, PRIMARY_HORIZON, k,
                            lambda r: _clean(r.get("cap_bucket")))
        if cf:
            cfs[k] = cf

    # Persistence across horizons is the directive's Level-2 requirement.
    persistence = {}
    for cap in (by_cap.get(PRIMARY_HORIZON) or {}):
        neg = [h for h in HORIZONS
               if by_cap.get(h, {}).get(cap, {}).get("n", 0) >= 15
               and (by_cap[h][cap].get("expectancy_pct") or 0) < 0]
        seen = [h for h in HORIZONS
                if by_cap.get(h, {}).get(cap, {}).get("n", 0) >= 15]
        persistence[cap] = {
            "horizons_with_n>=15": seen,
            "horizons_negative": neg,
            "persistent_negative": bool(seen) and len(neg) == len(seen),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "RESEARCH ONLY · no production rule · no threshold changed",
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "primary_horizon": PRIMARY_HORIZON,
        "field_health": health,
        "limitations": _limitations(health),
        "by_cap": by_cap,
        "by_sector": by_sector,
        "cap_x_sector": cap_sector,
        "cap_x_confidence": by_cap_conf,
        "counterfactuals": cfs,
        "persistence_across_horizons": persistence,
    }


def _limitations(h: dict) -> list:
    out = []
    if h["sector_contaminated_with_cap_labels"]:
        out.append(
            "BLOCKING · the sector field contains CAP labels %s · sector is "
            "not recorded for this market, so the cap finding is UNCONTROLLED "
            "for sector and cannot distinguish 'mid-cap is bad' from 'the "
            "sectors that happen to sit in mid-cap are bad'"
            % h["sector_contaminated_with_cap_labels"])
    elif h["sector_pct"] < 60:
        out.append(
            "BLOCKING · sector present on only %.1f%% of rows · any cap x "
            "sector cell is drawn from a biased subset" % h["sector_pct"])
    if not h["regime_usable"]:
        out.append("regime is null on every row · the regime x cap stratum "
                   "is omitted, not estimated")
    for hz, n in h["horizons_populated"].items():
        if n == 0:
            out.append(f"{hz} has no populated values · horizon omitted")
    return out


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "research" / "cohort"
            / f"cap_sector_concentration_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS cap x sector loss-concentration study (research)")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = compute(root, m)
        if rep.get("error"):
            print(f"{m}: {rep['error']}")
            continue
        p = emit(root, rep)
        h = rep["field_health"]
        print(f"cap_sector:{m} · n={h['n_rows']} · cap {h['cap_pct']}% · "
              f"sector {h['sector_pct']}% · sector-control="
              f"{h['sector_control_possible']} -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
