"""Sprint A · R2 Signal Funnel Diagnostic
CEO 2026-09-03 · answers the "zero-entry" question that gates R2 upgrades.

Emits per-market · per-asof-day counts for every stage of R2 selection:

  Stage 1 · Universe declared          (configs/aegis_universes.yaml)
  Stage 2 · Universe actual            (universe file present per market)
  Stage 3 · Data present               (parquet fresh within N days)
  Stage 4 · Features scored            (n_tickers in recommendations_v3.json)
  Stage 5 · Ensemble non-HOLD          (any BUY/ADD/SELL/EXIT action)
  Stage 6 · Passed conflict gate       (disagreement_flag=false)
  Stage 7 · Passed confidence floor    (calibrated_confidence >= 0.55)
  Stage 8 · Passed regime floor        (regime_adjusted_confidence >= 0.55)
  Stage 9 · Registry NEW writes today  (opportunity_registry NEW events)

Also computes the biggest drop stage (funnel bottleneck) and writes:
  reports/research/r2_signal_funnel/{market}/{asof}.json
  reports/research/r2_signal_funnel/{market}/latest.json
  reports/research/r2_signal_funnel/{market}/summary.md
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# Confidence floors mirror R2 ensemble published defaults · CEO-authorized
CONF_FLOOR = 0.55
REG_CONF_FLOOR = 0.55

STAGES = [
    "S1_universe_declared",
    "S2_universe_actual",
    "S3_data_present",
    "S4_features_scored",
    "S5_non_hold",
    "S6_no_disagreement",
    "S7_confidence_floor",
    "S8_regime_floor",
    "S9_registry_new_writes",
]


def _yaml_load(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _load_universe(root: Path, market: str) -> dict:
    """Return declared vs actual universe counts."""
    cfg_path = root / "configs" / "aegis_universes.yaml"
    declared_min = declared_max = 0
    actual = 0
    source = None
    if cfg_path.exists():
        cfg = _yaml_load(cfg_path)
        mcfg = cfg.get("markets", {}).get(market, {})
        declared_min = int(mcfg.get("n_tickers_min", 0))
        declared_max = int(mcfg.get("n_tickers_max", 0))
        source = mcfg.get("source_file")
    if source:
        sp = root / source
        if sp.exists():
            try:
                d = json.loads(sp.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    actual = len(d)
                elif isinstance(d, dict) and "tickers" in d:
                    actual = len(d["tickers"])
                elif isinstance(d, dict) and "constituents" in d:
                    actual = len(d["constituents"])
            except (ValueError, OSError):
                pass
    return {
        "declared_min": declared_min,
        "declared_max": declared_max,
        "actual": actual,
        "source": source,
    }


def _load_recs(root: Path, market: str) -> tuple[dict, str]:
    """Return (recs_v3_payload, asof_date_iso)."""
    if market == "usa":
        p = root / "usa" / "reports" / "recommendations_v3.json"
    else:
        p = root / "reports" / "recommendations_v3.json"
    if not p.exists():
        return {}, ""
    d = json.loads(p.read_text(encoding="utf-8"))
    asof = str(d.get("asof") or d.get("run_utc", "")[:10] or "")
    return d, asof


def _data_freshness(root: Path, market: str, asof: str,
                    freshness_days: int = 5) -> tuple[int, int, int]:
    """Return (n_present_total, n_fresh, days_stale_of_newest).

    Fresh = parquet mtime within freshness_days of asof.
    days_stale_of_newest = 0 if freshest file is at/after asof.
    """
    d = root / "data" / "raw" / market
    if not d.exists():
        return 0, 0, -1
    files = list(d.glob("*_D1.parquet"))
    if not files:
        files = list(d.glob("*.parquet"))
    n_total = len(files)
    if not files:
        return 0, 0, -1
    try:
        asof_dt = datetime.fromisoformat(asof)
    except ValueError:
        return n_total, n_total, 0
    n_fresh = 0
    newest_mtime = None
    for f in files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if newest_mtime is None or mtime > newest_mtime:
                newest_mtime = mtime
            if (asof_dt - mtime).days <= freshness_days:
                n_fresh += 1
        except OSError:
            pass
    stale = max(0, (asof_dt - newest_mtime).days) if newest_mtime else -1
    return n_total, n_fresh, stale


def _registry_new_writes(root: Path, market: str, asof: str) -> tuple[int, dict]:
    """Count R2 opportunities created on `asof` in registry JSONL."""
    p = root / "reports" / "research" / "opportunity_registry.jsonl"
    if not p.exists():
        return 0, {}
    n = 0
    by_signal: Counter = Counter()
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("market") != market:
                continue
            if o.get("runner") != "R2":
                continue
            if o.get("created_date") != asof:
                continue
            n += 1
            by_signal[str(o.get("initial_signal") or "?")] += 1
    return n, dict(by_signal)


def _bottleneck(counts: dict) -> tuple[str, int]:
    """Return (stage_after_biggest_drop, count_dropped)."""
    prev_key = None
    prev_val = None
    worst_drop = 0
    worst_key = ""
    for k in STAGES:
        v = counts.get(k, 0)
        if isinstance(v, int) and prev_val is not None:
            drop = max(0, prev_val - v)
            if drop > worst_drop:
                worst_drop = drop
                worst_key = f"{prev_key}→{k}"
        prev_key, prev_val = k, v
    return worst_key, worst_drop


def compute_funnel(root: Path, market: str) -> dict:
    uni = _load_universe(root, market)
    recs, asof = _load_recs(root, market)
    if not recs:
        return {
            "market": market,
            "asof": None,
            "error": "recommendations_v3.json not found",
        }
    rec_list = recs.get("recommendations", []) or []
    n_scored = len(rec_list)
    n_non_hold = sum(1 for r in rec_list
                     if str(r.get("action", "")).upper() not in ("HOLD", ""))
    n_no_dis = sum(1 for r in rec_list
                   if str(r.get("action", "")).upper() not in ("HOLD", "")
                   and not r.get("disagreement_flag"))
    n_conf_ok = sum(1 for r in rec_list
                    if str(r.get("action", "")).upper() not in ("HOLD", "")
                    and not r.get("disagreement_flag")
                    and float(r.get("calibrated_confidence", 0.0)) >= CONF_FLOOR)
    n_reg_ok = sum(1 for r in rec_list
                   if str(r.get("action", "")).upper() not in ("HOLD", "")
                   and not r.get("disagreement_flag")
                   and float(r.get("calibrated_confidence", 0.0)) >= CONF_FLOOR
                   and float(r.get("regime_adjusted_confidence", 0.0)) >= REG_CONF_FLOOR)
    # Use 30d window · dev environments can lag prod by weeks
    n_data_total, n_data_fresh, days_stale = _data_freshness(
        root, market, asof, freshness_days=30
    )
    # For S3 use total-present · S4 tells us feature/score bridge health
    n_data = n_data_total
    n_new, by_signal = _registry_new_writes(root, market, asof)

    action_dist = Counter(str(r.get("action", "")).upper() for r in rec_list)

    counts = {
        "S1_universe_declared": uni["declared_max"],
        "S2_universe_actual": uni["actual"] or uni["declared_max"],
        "S3_data_present": n_data,
        "S4_features_scored": n_scored,
        "S5_non_hold": n_non_hold,
        "S6_no_disagreement": n_no_dis,
        "S7_confidence_floor": n_conf_ok,
        "S8_regime_floor": n_reg_ok,
        "S9_registry_new_writes": n_new,
    }
    bn_key, bn_drop = _bottleneck(counts)

    return {
        "market": market,
        "asof": asof,
        "generated_utc": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe": uni,
        "stages": counts,
        "action_distribution": dict(action_dist),
        "registry_new_by_signal": by_signal,
        "bottleneck": {"transition": bn_key, "drop": bn_drop},
        "data_health": {
            "parquet_present": n_data_total,
            "parquet_fresh_30d": n_data_fresh,
            "days_stale_newest": days_stale,
        },
        "thresholds": {
            "confidence_floor": CONF_FLOOR,
            "regime_confidence_floor": REG_CONF_FLOOR,
            "data_freshness_days": 30,
        },
        "diagnosis": _diagnose(counts, bn_key, bn_drop, action_dist),
    }


def _diagnose(counts: dict, bn_key: str, bn_drop: int, actions: Counter) -> list[str]:
    d = []
    if counts["S4_features_scored"] < counts["S2_universe_actual"] // 2:
        d.append(
            f"CRITICAL · only {counts['S4_features_scored']} of "
            f"{counts['S2_universe_actual']} universe tickers scored · "
            f"universe-to-scored ratio < 50% · investigate universe→feature bridge"
        )
    if actions.get("HOLD", 0) == counts["S4_features_scored"] and counts["S4_features_scored"] > 0:
        d.append(
            f"WARN · 100% HOLD ({actions.get('HOLD',0)}/{counts['S4_features_scored']}) · "
            f"ensemble not producing BUY/ADD/SELL signals · check score→action thresholds"
        )
    if counts["S5_non_hold"] > 0 and counts["S9_registry_new_writes"] == 0:
        d.append(
            f"WARN · {counts['S5_non_hold']} non-HOLD signals but 0 registry writes today · "
            f"selection→Registry writer disconnected or gate too strict"
        )
    if bn_drop >= 5:
        d.append(f"BOTTLENECK · biggest drop at {bn_key} · lost {bn_drop} tickers")
    if not d:
        d.append("OK · funnel counts look consistent")
    return d


def _write_json(payload: dict, out_dir: Path, asof: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dated = out_dir / f"{asof or 'unknown'}.json"
    dated.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dated


def _write_summary_md(root: Path, market: str, payload: dict, out_dir: Path) -> Path:
    lines: list[str] = []
    lines.append(f"# R2 Signal Funnel · {market.upper()} · {payload.get('asof','?')}\n")
    lines.append(f"_Generated {payload.get('generated_utc','')} · Sprint A diagnostic_\n")
    lines.append("\n## Funnel counts\n")
    lines.append("| Stage | Count | Δ vs prev |")
    lines.append("|---|---:|---:|")
    prev = None
    for k in STAGES:
        v = payload["stages"].get(k, 0)
        delta = "" if prev is None else f"{v - prev:+d}"
        lines.append(f"| {k} | {v} | {delta} |")
        prev = v
    lines.append("\n## Action distribution\n")
    for a, n in sorted(payload.get("action_distribution", {}).items(),
                       key=lambda x: -x[1]):
        lines.append(f"- {a}: {n}")
    if payload.get("registry_new_by_signal"):
        lines.append("\n## Registry NEW writes today by initial_signal\n")
        for k, v in payload["registry_new_by_signal"].items():
            lines.append(f"- {k}: {v}")
    lines.append(f"\n## Bottleneck\n\n**{payload['bottleneck']['transition']}** · "
                 f"lost {payload['bottleneck']['drop']} tickers\n")
    lines.append("\n## Diagnosis\n")
    for d in payload.get("diagnosis", []):
        lines.append(f"- {d}")
    lines.append("")
    p = out_dir / "summary.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser(description="R2 Signal Funnel Diagnostic")
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--root", default=str(_ROOT))
    args = ap.parse_args()
    root = Path(args.root)

    payload = compute_funnel(root, args.market)
    out_dir = root / "reports" / "research" / "r2_signal_funnel" / args.market
    dated = _write_json(payload, out_dir, str(payload.get("asof") or "unknown"))
    md = _write_summary_md(root, args.market, payload, out_dir)

    print(f"[funnel] {args.market} asof={payload.get('asof')} → {dated}")
    print(f"[funnel] summary → {md}")
    for stage in STAGES:
        print(f"  {stage}: {payload['stages'].get(stage, 0)}")
    print(f"  bottleneck: {payload['bottleneck']}")
    for d in payload.get("diagnosis", []):
        print(f"  · {d}")


if __name__ == "__main__":
    main()
