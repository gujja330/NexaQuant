"""00_Health · Sprint A governance cockpit
CEO 2026-09-03

Makes Sprint A's invisible governance work visible day-to-day. Single
sheet showing:
  - Funnel counts per market (from r2_signal_funnel JSON)
  - Gate statuses (P0-P5 pass/fail from r2_upgrades)
  - R3 baseline gate + Day-30/60/90 status
  - Signal Silence status + MVS floor status
  - Relaxation budget remaining
  - Signal Ledger + Outcome Dataset row counts
  - Data-freshness · newest parquet mtime per market
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


HEALTH_COLUMNS = ["Metric", "Market", "Value", "Status", "Detail"]

HEALTH_BANNER = (
    "SUPPORTING · system/governance surface · NOT FOR INVESTMENT DECISIONS · "
    "AEGIS HEALTH COCKPIT · Sprint A governance · "
    "single glance of every gate + funnel + budget in the platform. "
    "Green = OK · Yellow = degraded · Red = blocked."
)


def _read_json(p: Path):
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def _status(ok: bool, warn_only: bool = False) -> str:
    if ok: return "OK"
    return "WARN" if warn_only else "FAIL"


def build_health_rows(root: Path, market: str) -> list[list]:
    rows: list[list] = []

    # ── Funnel ────────────────────────────────────────────────────────
    funnel = _read_json(root / "reports" / "research" / "r2_signal_funnel" / market / "latest.json")
    stages = funnel.get("stages", {})
    rows.append(["Universe (S1)", market, stages.get("S1_universe_declared", "?"),
                 "INFO", f"declared max in aegis_universes.yaml"])
    rows.append(["Universe actual (S2)", market, stages.get("S2_universe_actual", "?"),
                 "INFO", f"live universe file"])
    rows.append(["Data present (S3)", market, stages.get("S3_data_present", "?"),
                 "INFO", "parquet ticker coverage"])
    rows.append(["Features scored (S4)", market, stages.get("S4_features_scored", "?"),
                 "INFO", f"n_tickers in recs_v3"])
    rows.append(["Non-HOLD (S5)", market, stages.get("S5_non_hold", "?"),
                 _status(int(stages.get("S5_non_hold", 0)) > 0, warn_only=True),
                 "BUY/ADD/SELL count"])
    rows.append(["Registry NEW today (S9)", market, stages.get("S9_registry_new_writes", "?"),
                 _status(int(stages.get("S9_registry_new_writes", 0)) > 0, warn_only=True),
                 "positions written today"])
    bn = funnel.get("bottleneck", {})
    rows.append(["R2 funnel bottleneck", market, bn.get("transition", "?"),
                 "INFO", f"dropped {bn.get('drop', 0)} tickers"])

    # ── Momentum funnel (feeds 02_Today_Momentum) ──────────────────────
    mf = _read_json(root / "reports" / "research" / "momentum_funnel" / market / "latest.json")
    if mf:
        mstages = mf.get("stages", {})
        m_raw = mstages.get("M1_universe_raw", 0)
        m_scanned = mstages.get("M4_actually_scanned", 0)
        rows.append(["Momentum scanned/raw", market, f"{m_scanned}/{m_raw}",
                     _status(m_scanned >= max(10, m_raw // 5), warn_only=True),
                     "M4/M1 · severe collapse if scanned << raw"])
        mbn = mf.get("bottleneck", {})
        rows.append(["Momentum bottleneck", market, mbn.get("transition", "?"),
                     "INFO", f"dropped {mbn.get('drop', 0)} tickers"])

    # ── P0 gate ────────────────────────────────────────────────────────
    p0 = _read_json(root / "reports" / "research" / "r2_upgrades" / f"p0_exit_bridge_replay_{market}.json")
    if p0:
        rows.append(["P0 exit-bridge gate", market,
                     p0.get("P0_GATE_STATUS") or ("PASS" if p0.get("P0_GATE_PASS") else "FAIL"),
                     _status(bool(p0.get("P0_GATE_PASS")), warn_only=True),
                     f"n={p0.get('n_positions', 0)} · delta={round(p0.get('mean_delta_pct', 0), 4)}"])

    # ── P1 calibration ─────────────────────────────────────────────────
    p1 = _read_json(root / "reports" / "research" / "r2_upgrades" / f"p1_calibration_{market}.json")
    if p1:
        rows.append(["P1 joint Platt calibration", market, p1.get("gate_status", "?"),
                     _status(bool(p1.get("gate_pass")), warn_only=True),
                     f"n={p1.get('n', 0)} ECE={p1.get('ece_after', '?')}"])

    # ── R3 baseline gate ───────────────────────────────────────────────
    r3g = _read_json(root / "reports" / "research" / "r3" / f"day30_gate_{market}.json")
    if r3g:
        rows.append(["R3 Day-30 kill gate", market, r3g.get("GATE_2_OF_3", "?"),
                     _status(r3g.get("GATE_2_OF_3") == "PASS", warn_only=True),
                     f"{r3g.get('n_criteria_passed', 0)}/3 criteria"])

    # ── R3 baseline replicate ──────────────────────────────────────────
    r3b = _read_json(root / "reports" / "research" / "r3" / f"baseline_replicate_{market}.json")
    if r3b:
        rows.append(["R3 baseline-replicate gate", market,
                     "PASS" if r3b.get("gate_pass") else "BLOCKED_TIER2",
                     _status(bool(r3b.get("gate_pass")), warn_only=True),
                     f"IC gap {r3b.get('gap', '?')} vs tol {r3b.get('tolerance', '?')}"])

    # ── Relaxation budget ──────────────────────────────────────────────
    from backend.research.governance import RelaxationTracker
    tr = RelaxationTracker(root)
    budget = tr.can_relax(datetime.now().strftime("%Y-%m-%d"))
    rows.append(["MVS relaxation budget", market, budget.get("remaining", "?"),
                 _status(budget.get("remaining", 0) > 0, warn_only=True),
                 f"used {budget.get('used_last_90d', 0)} of {budget.get('cap', 15)} · rolling 90d"])

    # ── Substrate row counts ───────────────────────────────────────────
    od = _read_json(root / "reports" / "research" / "outcome_dataset" / f"{market}.summary.json")
    if od:
        rows.append(["Outcome Dataset", market,
                     od.get("n_positions", 0),
                     _status(od.get("phase0_gate_50_closed", False)),
                     f"non-admin closed: {od.get('n_closed_non_admin', 0)}"])
    sl = _read_json(root / "reports" / "research" / "signal_ledger" / f"{market}.summary.json")
    if sl:
        rows.append(["Signal Ledger", market,
                     sl.get("n_rows", 0), "INFO",
                     f"snapshots: {sl.get('n_snapshots', 0)}"])

    # ── Data freshness ─────────────────────────────────────────────────
    from backend.research._paths import price_parquet_dir
    pdir = price_parquet_dir(root, market)
    if pdir.exists():
        files = list(pdir.glob("*_D1.parquet")) or list(pdir.glob("*.parquet"))
        if files:
            newest = max(f.stat().st_mtime for f in files)
            newest_str = datetime.fromtimestamp(newest).strftime("%Y-%m-%d")
            stale_days = (datetime.now() - datetime.fromtimestamp(newest)).days
            rows.append(["Price parquet freshness", market, newest_str,
                         _status(stale_days <= 3, warn_only=True),
                         f"{len(files)} files · newest mtime {stale_days}d ago"])

    return rows


def sheet_meta() -> dict:
    return {
        "sheet_name": "00_Health",
        "banner": HEALTH_BANNER,
        "columns": HEALTH_COLUMNS,
        "notes": ["Regenerated every workbook build",
                  "Green OK / Yellow WARN / Red FAIL"],
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
