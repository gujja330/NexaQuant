"""
MON001 standalone health check — read-only verification.

Verifies every invariant that must hold since the MON001 seal:
- production baseline fingerprint matches the sealed hash
- forward ledger hash chain is intact
- ledger has no rows with asof < forward_boundary_asof (leakage guard)
- baseline envelope is byte-identical to the cached seal
- broker layer is PAPER_ONLY (interface refuses order placement)
- cumulative_strategy_search remains 38
- HOLD = 63, rebal = 63

Exit codes:
- 0: all checks pass
- 1: at least one check WARNs but MON001 can still run
- 2: HALT-worthy — MON001 refuses to run under this condition

Run: python -m india.monitoring.MON001_Forward_Validation.ops.health_check
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from india.monitoring.MON001_Forward_Validation.forward_ledger import ForwardLedger
from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
from india.monitoring.MON001_Forward_Validation.baseline_envelope import load_or_cache
from india.monitoring.MON001_Forward_Validation.broker_layer import (
    make_broker_layer, PaperOnlyBrokerLayer,
)


HERE = Path(__file__).resolve().parent.parent
CFG_PATH = HERE / "mon001.yaml"
SEALED_FP_PATH = HERE / "reports" / "sealed_fingerprint.json"


@dataclass
class CheckResult:
    name: str
    ok: bool
    severity: str = "INFO"   # INFO / WARN / HALT
    detail: str = ""


@dataclass
class HealthReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def worst_severity(self) -> str:
        order = {"INFO": 0, "WARN": 1, "HALT": 2}
        return max((c.severity for c in self.checks), key=lambda s: order.get(s, 0))

    @property
    def exit_code(self) -> int:
        return {"INFO": 0, "WARN": 1, "HALT": 2}[self.worst_severity]

    def as_dict(self) -> dict:
        return {
            "worst_severity": self.worst_severity,
            "exit_code": self.exit_code,
            "checks": [c.__dict__ for c in self.checks],
        }


def run_health_checks() -> HealthReport:
    report = HealthReport()

    # 1. Config loads
    try:
        with CFG_PATH.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        report.checks.append(CheckResult(
            "config_loads", True, "INFO", f"mon001.yaml loaded ({len(cfg)} top-level keys)"))
    except Exception as e:
        report.checks.append(CheckResult(
            "config_loads", False, "HALT", f"mon001.yaml failed to load: {e}"))
        return report

    # 2. Sealed fingerprint exists
    if not SEALED_FP_PATH.exists():
        report.checks.append(CheckResult(
            "sealed_fingerprint_exists", False, "HALT",
            f"{SEALED_FP_PATH} missing — MON001 has not been seal-initialized"))
        return report
    sealed_fp = json.loads(SEALED_FP_PATH.read_text(encoding="utf-8"))
    report.checks.append(CheckResult(
        "sealed_fingerprint_exists", True, "INFO",
        f"sealed hash = {sealed_fp['hash'][:16]}..."))

    # 3. Current fingerprint matches sealed
    try:
        current_fp = compute_fingerprint(
            ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    except FileNotFoundError as e:
        report.checks.append(CheckResult(
            "fingerprint_computable", False, "HALT",
            f"baseline file missing: {e}"))
        return report
    if current_fp["hash"] == sealed_fp["hash"]:
        report.checks.append(CheckResult(
            "fingerprint_matches_seal", True, "INFO",
            f"production baseline unchanged (hash {current_fp['hash'][:16]}...)"))
    else:
        report.checks.append(CheckResult(
            "fingerprint_matches_seal", False, "HALT",
            f"CONFIG_DRIFT — sealed {sealed_fp['hash'][:16]}... "
            f"vs current {current_fp['hash'][:16]}..."))

    # 4. Envelope byte-identity
    diag_csv = ROOT / cfg["baseline_envelope"]["source_diagnostics"]
    cache = ROOT / cfg["baseline_envelope"]["cache_path"]
    try:
        env = load_or_cache(cache, diag_csv,
                             cfg["baseline_envelope"]["candidate"],
                             cfg["baseline_envelope"]["horizon_days"],
                             cfg["baseline_envelope"]["canonical_cost_bps"],
                             cfg["baseline_envelope"]["cash_grid"])
        report.checks.append(CheckResult(
            "envelope_byte_identical", True, "INFO",
            f"envelope hash = {env['envelope_hash'][:16]}..."))
    except RuntimeError as e:
        report.checks.append(CheckResult(
            "envelope_byte_identical", False, "HALT", str(e)))
    except Exception as e:
        report.checks.append(CheckResult(
            "envelope_byte_identical", False, "HALT",
            f"envelope build failed: {e}"))

    # 5. Ledger hash-chain integrity
    ledger = ForwardLedger(
        ROOT / cfg["forward_ledger"]["path"],
        ROOT / cfg["forward_ledger"]["corrections_path"],
        cfg["forward_boundary_asof"])
    integrity = ledger.verify_chain()
    if integrity["ok"]:
        report.checks.append(CheckResult(
            "ledger_integrity", True, "INFO",
            f"chain intact, {integrity['rows_checked']} rows"))
    else:
        report.checks.append(CheckResult(
            "ledger_integrity", False, "HALT",
            f"ledger corrupted: {integrity['reason']}"))

    # 6. No duplicate rec_ids under same fingerprint
    dups = ledger.duplicate_rec_ids()
    if not dups:
        report.checks.append(CheckResult(
            "no_duplicate_recs", True, "INFO",
            "no duplicate rec_id under a single fingerprint"))
    else:
        report.checks.append(CheckResult(
            "no_duplicate_recs", False, "WARN",
            f"{len(dups)} duplicate rec_ids found — investigate: {dups[:5]}"))

    # 7. Broker layer is PAPER_ONLY
    broker = make_broker_layer()
    if isinstance(broker, PaperOnlyBrokerLayer) and not broker.available():
        report.checks.append(CheckResult(
            "broker_paper_only", True, "INFO",
            "broker layer is PAPER_ONLY (read-only enforcement holds)"))
    else:
        report.checks.append(CheckResult(
            "broker_paper_only", False, "WARN",
            "broker layer is not PAPER_ONLY — verify authorization exists"))

    # 8. Trial manifest unchanged (38)
    trial_manifest = ROOT / "india/ai_lab/trial_manifest.md"
    try:
        text = trial_manifest.read_text(encoding="utf-8", errors="ignore")
        if "cumulative_strategy_search: 38" in text:
            report.checks.append(CheckResult(
                "cumulative_strategy_search_38", True, "INFO",
                "trial count unchanged at 38"))
        else:
            report.checks.append(CheckResult(
                "cumulative_strategy_search_38", False, "HALT",
                "cumulative_strategy_search != 38 — trial manifest has been mutated"))
    except Exception as e:
        report.checks.append(CheckResult(
            "cumulative_strategy_search_38", False, "WARN",
            f"could not read trial_manifest.md: {e}"))

    # 9. Production HOLD / rebal unchanged
    try:
        reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
        gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
        hold_ok = "HOLD = 63" in reg
        rebal_ok = "rebal=63" in gen
        if hold_ok and rebal_ok:
            report.checks.append(CheckResult(
                "production_constants", True, "INFO",
                "HOLD=63 and rebal=63 unchanged"))
        else:
            report.checks.append(CheckResult(
                "production_constants", False, "HALT",
                f"HOLD or rebal changed: HOLD_ok={hold_ok}, rebal_ok={rebal_ok}"))
    except Exception as e:
        report.checks.append(CheckResult(
            "production_constants", False, "WARN",
            f"could not read production files: {e}"))

    return report


def format_report(report: HealthReport) -> str:
    lines = ["MON001 health check", "=" * 60]
    icon = {"INFO": "[ OK ]", "WARN": "[WARN]", "HALT": "[HALT]"}
    for c in report.checks:
        lines.append(f"{icon.get(c.severity, '[  ? ]')} {c.name:<32}  {c.detail}")
    lines.append("=" * 60)
    lines.append(f"worst severity: {report.worst_severity}  exit code: {report.exit_code}")
    return "\n".join(lines)


def main() -> int:
    report = run_health_checks()
    print(format_report(report))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
