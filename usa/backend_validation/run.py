"""AEGIS USA · Backend Data Foundation Validator v1.0.

USA mirror of india/backend_validation/run.py. USD-native.
Emits usa/reports/backend_validation{.json,_summary.json,_history.jsonl}.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML required."); sys.exit(1)


_ROOT = Path(__file__).resolve().parents[2]
_USA  = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.validation.pipeline import BackendValidationPipeline                      # noqa: E402


def main() -> int:
    t0 = time.time()
    print("=" * 72)
    print("  AEGIS USA · Backend Data Foundation Validator v1.0")
    print("=" * 72)

    registry = Path(__file__).parent / "datasets.yaml"
    cfg = yaml.safe_load(registry.read_text(encoding="utf-8"))
    datasets = cfg.get("datasets") or []

    pipeline = BackendValidationPipeline(
        market="usa", datasets=datasets, root=_ROOT,
    )
    full = pipeline.run()
    summary = pipeline.summary(full)

    reports_dir = _USA / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "backend_validation.json").write_text(
        json.dumps(full, indent=2, default=str), encoding="utf-8")
    (reports_dir / "backend_validation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    pipeline.append_history(summary, reports_dir / "backend_validation_history.jsonl")

    print(f"\n  datasets:     {full['n_datasets']}")
    print(f"  verdict:      {full['verdict']}")
    print(f"  confidence:   {full['confidence']:.3f}")
    print(f"  counts:       PASS={full['counts']['PASS']}  "
          f"WARN={full['counts']['WARNING']}  "
          f"FAIL={full['counts']['FAIL']}  "
          f"N/A={full['counts']['NOT_APPLICABLE']}")
    print(f"  elapsed:      {full['elapsed_s']}s")

    if summary["top_issues"]:
        print("\n  Top issues:")
        for iss in summary["top_issues"][:8]:
            print(f"    [{iss['severity']:8s}] {iss['dataset']:<30s} · "
                  f"{iss['validator']:<12s} · {iss['message'][:80]}")

    print(f"\n  written: usa/reports/backend_validation{{.json,.summary.json,_history.jsonl}}")
    print(f"  total elapsed: {time.time() - t0:.2f}s")

    return 1 if full["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
