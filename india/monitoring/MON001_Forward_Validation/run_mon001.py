"""
MON001 daily orchestration entrypoint.

Runs the forward-monitoring pass exactly once. Deterministic; does not modify production
configuration, does not place orders, does not increment cumulative_strategy_search.

Steps (all read-only against production):
1. Load mon001.yaml.
2. Compute current production fingerprint; compare against sealed fingerprint.
3. Load-or-cache the LAB009-derived baseline envelope.
4. Ingest new forward-eligible recommendations from `data/aegis_registry.csv` into the
   append-only forward ledger. Rows already in the ledger are NOT re-appended (idempotent).
5. Verify ledger hash-chain integrity.
6. Reconstruct paper equity curve from ledger snapshots.
7. Evaluate metric evidence and drift alerts against the sealed envelope + thresholds.
8. Assemble global state, HALT_REVIEW_REQUIRED evaluation.
9. Write dated diagnostics JSON + markdown report; append active alerts to alerts JSONL.
10. Return exit code 0 always (monitoring failures do not break upstream automation; the
    report and alerts communicate any failure).

Run:  python india/monitoring/MON001_Forward_Validation/run_mon001.py
      [--seal-init]   # first-time run to seal the fingerprint + envelope
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone, date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.forward_ledger import (
    ForwardLedger, make_observation_row, DataIntegrityFailure,
)
from india.monitoring.MON001_Forward_Validation.fingerprint import (
    compute_fingerprint, format_drift_report,
)
from india.monitoring.MON001_Forward_Validation.baseline_envelope import load_or_cache
from india.monitoring.MON001_Forward_Validation.broker_layer import make_broker_layer
from india.monitoring.MON001_Forward_Validation.monitor import (
    MonitorReport, MetricEvidence, DriftAlert,
    forward_coverage, _forward_daily_returns, evaluate_metric_evidence,
    evaluate_concentration, evaluate_data_drift, assemble_global_state,
)
from india.monitoring.MON001_Forward_Validation.report import (
    write_diagnostics_json, write_markdown, append_alert,
)


HERE = Path(__file__).resolve().parent
SEALED_FINGERPRINT_PATH = HERE / "reports" / "sealed_fingerprint.json"


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_config() -> dict:
    with (HERE / "mon001.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _seal_or_verify_fingerprint(cfg: dict, seal_init: bool) -> tuple[dict, dict, str]:
    """Return (current_fp, sealed_fp, status) where status in {"OK","DRIFT","SEALED_NOW"}."""
    current_fp = compute_fingerprint(
        ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    if not SEALED_FINGERPRINT_PATH.exists():
        if not seal_init:
            SEALED_FINGERPRINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            SEALED_FINGERPRINT_PATH.write_text(
                json.dumps(current_fp, sort_keys=True, indent=2), encoding="utf-8")
            return current_fp, current_fp, "SEALED_NOW"
        SEALED_FINGERPRINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SEALED_FINGERPRINT_PATH.write_text(
            json.dumps(current_fp, sort_keys=True, indent=2), encoding="utf-8")
        return current_fp, current_fp, "SEALED_NOW"
    sealed_fp = json.loads(SEALED_FINGERPRINT_PATH.read_text(encoding="utf-8"))
    status = "OK" if current_fp["hash"] == sealed_fp["hash"] else "DRIFT"
    return current_fp, sealed_fp, status


def _ingest_new_recs(cfg: dict, ledger: ForwardLedger, current_fp_hash: str) -> int:
    """Append forward-eligible recs from data/aegis_registry.csv into the ledger.
    Idempotent: rows already present (same rec_id + fingerprint_hash) are skipped."""
    reg_path = ROOT / cfg["registry_path"]
    if not reg_path.exists():
        return 0
    df = pd.read_csv(reg_path)
    df["asof"] = pd.to_datetime(df["asof"]).dt.strftime("%Y-%m-%d")
    df = df[df["asof"] >= cfg["forward_boundary_asof"]]
    if df.empty:
        return 0
    # Deduplicate by rec_id — one snapshot per rec_id under the current fingerprint.
    existing = {(r["rec_id"], r["fingerprint_hash"]) for r in ledger.rows()}
    new_count = 0
    for _, r in df.iterrows():
        key = (str(r["rec_id"]), current_fp_hash)
        if key in existing:
            continue
        try:
            from india.sectors import sector_of
            sector = sector_of(str(r["symbol"]))
        except Exception:
            sector = "UNKNOWN"
        data_quality = "OK" if pd.notna(r.get("buy_price")) else "MISSING_PRICE"
        obs = make_observation_row(
            asof=str(r["asof"]),
            rec_id=str(r["rec_id"]),
            fingerprint_hash=current_fp_hash,
            symbol=str(r["symbol"]),
            portfolio_cycle=str(r.get("rec_id_group", f"{r['asof']}_63"))
            if "rec_id_group" in df.columns else f"{r['asof']}_63",
            buy_price=float(r.get("buy_price", 0.0) or 0.0),
            intended_weight=float(r.get("weight", 0.0) or 0.0),
            sector=sector,
            regime_label=str(r.get("regime", "")),
            exposure_multiplier=_regime_to_exp(str(r.get("regime", ""))),
            benchmark_ref=None,
            source_mode="PAPER",
            data_quality=data_quality,
        )
        ledger.append(obs)
        new_count += 1
    return new_count


def _regime_to_exp(label: str) -> float:
    # Coarse mapping — the actual exp_series is float. For forward observations we know
    # only the label; use midpoint of each bucket as a proxy. Divergence is detected against
    # the actual backtest distribution, not this proxy.
    return {"Strong": 1.0, "Neutral": 0.75, "Weak": 0.6}.get(label, 0.75)


def _load_market_data() -> tuple[pd.DataFrame, pd.Series | None]:
    """Load closes panel and primary benchmark. Failures return empty structures."""
    try:
        from india.feature_engine import load_panels
        closes, _, _, _, idx, _, _ = load_panels()
        return closes, idx
    except Exception as exc:
        print(f"[MON001] WARN load_panels failed: {exc}", file=sys.stderr)
        return pd.DataFrame(), None


def _count_consecutive_weekly(alerts_history_path: Path, dimension: str,
                              today: date) -> tuple[int, str | None]:
    """Walk alerts history from newest to oldest; count consecutive weekly windows in which
    `dimension` was DIVERGED. Return (count, first_seen_iso or None)."""
    if not alerts_history_path.exists():
        return 0, None
    weeks: dict[str, set[str]] = {}
    with alerts_history_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("dimension") != dimension or r.get("level") != "DIVERGED":
                continue
            day = r.get("appended_at_utc", "")[:10]
            if not day:
                continue
            iso_year, iso_week, _ = date.fromisoformat(day).isocalendar()
            weeks.setdefault(f"{iso_year}-W{iso_week:02d}", set()).add(day)
    if not weeks:
        return 0, None
    current_year, current_week, _ = today.isocalendar()
    ordered = sorted(weeks.keys(), reverse=True)
    consecutive = 0
    first_seen = None
    y, w = current_year, current_week
    for key in ordered:
        expect = f"{y}-W{w:02d}"
        if key == expect:
            consecutive += 1
            first_seen = min(weeks[key])
            w -= 1
            if w <= 0:
                y -= 1
                w = 52
        else:
            break
    return consecutive, first_seen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal-init", action="store_true",
                        help="First-time seal of the production fingerprint and envelope.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute report but do not append to ledger or alerts.")
    args = parser.parse_args()

    cfg = _load_config()
    reports_dir = ROOT / cfg["reporting"]["output_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 1-2. Fingerprint
    current_fp, sealed_fp, fp_status = _seal_or_verify_fingerprint(cfg, args.seal_init)

    # 3. Envelope
    diag_csv = ROOT / cfg["baseline_envelope"]["source_diagnostics"]
    cache = ROOT / cfg["baseline_envelope"]["cache_path"]
    envelope = load_or_cache(cache, diag_csv,
                              cfg["baseline_envelope"]["candidate"],
                              cfg["baseline_envelope"]["horizon_days"],
                              cfg["baseline_envelope"]["canonical_cost_bps"],
                              cfg["baseline_envelope"]["cash_grid"])

    # 4. Ledger ingestion
    ledger = ForwardLedger(
        ROOT / cfg["forward_ledger"]["path"],
        ROOT / cfg["forward_ledger"]["corrections_path"],
        cfg["forward_boundary_asof"])
    if not args.dry_run:
        new_recs = _ingest_new_recs(cfg, ledger, current_fp["hash"])
    else:
        new_recs = 0

    # 5. Integrity
    integrity = ledger.verify_chain()

    # 6-7. Coverage + metrics
    closes, benchmark_idx = _load_market_data()
    ledger_rows = ledger.rows()
    coverage = forward_coverage(ledger_rows, date.today(),
                                 closes.index if not closes.empty else pd.Index([]))
    daily = pd.Series(dtype=float)
    if not closes.empty and ledger_rows:
        daily, _bench, _n = _forward_daily_returns(
            ledger_rows, closes, benchmark_idx, date.today())
    metric_evidence = evaluate_metric_evidence(daily, envelope, cfg["min_evidence"])

    # 8. Alerts
    alerts: list[DriftAlert] = []
    if fp_status == "DRIFT":
        alerts.append(DriftAlert("D1_CONFIG_DRIFT", "DIVERGED",
                                  format_drift_report(current_fp, sealed_fp)))
    conc = evaluate_concentration(
        ledger_rows, cfg["baseline_constants"]["name_cap"],
        cfg["baseline_constants"]["sector_cap"],
        cfg["drift"]["D7_concentration"]["name_cap_tolerance"],
        cfg["drift"]["D7_concentration"]["sector_cap_over_by"])
    if conc is not None:
        alerts.append(conc)
    data = evaluate_data_drift(
        ledger_rows,
        cfg["drift"]["D8_data"]["watch_missing_prices_pct"],
        cfg["drift"]["D8_data"]["diverged_missing_prices_pct"],
        cfg["drift"]["D8_data"]["watch_stale_recs_pct"],
        cfg["drift"]["D8_data"]["diverged_stale_recs_pct"])
    if data is not None:
        alerts.append(data)

    alerts_path = ROOT / cfg["reporting"]["alerts_path"]
    for a in alerts:
        cnt, first_seen = _count_consecutive_weekly(alerts_path, a.dimension, date.today())
        a.consecutive_reports = cnt + 1 if a.level == "DIVERGED" else a.consecutive_reports
        a.first_seen = first_seen

    # 9. Global state
    global_state, halt, reason = assemble_global_state(
        fp_status, integrity, metric_evidence, alerts)

    if halt is False:
        halt_thresh = int(cfg["halt"]["consecutive_weekly_reports_for_halt"])
        for a in alerts:
            if a.level == "DIVERGED" and a.consecutive_reports >= halt_thresh:
                global_state = "HALT_REVIEW_REQUIRED"
                halt = True
                reason = (f"{a.dimension} DIVERGED for {a.consecutive_reports} consecutive "
                          f"weekly reports (threshold {halt_thresh})")
                break

    # Broker status
    broker = make_broker_layer()
    bstatus = broker.status()

    report = MonitorReport(
        run_date_utc=_iso_utc(),
        forward_boundary_asof=cfg["forward_boundary_asof"],
        forward_days_accumulated=int(coverage["forward_days_from_first_obs"]),
        forward_recs_ingested=len(ledger_rows),
        completed_cycles=int(coverage["completed_cycles"]),
        fingerprint_status=fp_status,
        fingerprint_hash_current=current_fp["hash"],
        fingerprint_hash_sealed=sealed_fp["hash"],
        ledger_integrity=integrity,
        baseline_envelope_hash=envelope["envelope_hash"],
        broker_status={"available": bstatus.available, "reason": bstatus.reason,
                        "fills_count": bstatus.fills_count},
        metric_evidence=metric_evidence,
        drift_alerts=alerts,
        global_state=global_state,
        halt_review_required=halt,
        reason=reason,
    )

    # 10. Persist
    today_str = date.today().isoformat()
    diag_path = reports_dir / cfg["reporting"]["json_diagnostics_template"].format(date=today_str)
    md_path = reports_dir / cfg["reporting"]["markdown_template"].format(date=today_str)
    write_diagnostics_json(report, diag_path)
    write_markdown(report, md_path)
    if not args.dry_run:
        for a in alerts:
            append_alert(a.as_dict(), alerts_path)

    print(f"[MON001] state={global_state} halt={halt} "
          f"forward_recs={len(ledger_rows)} new_ingested={new_recs} "
          f"fingerprint={fp_status} envelope={envelope['envelope_hash'][:12]}")
    print(f"[MON001] diagnostics -> {diag_path}")
    print(f"[MON001] markdown    -> {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
