"""Coverage report generator · per CEO 2026-09-03 13-stage discipline.

Emits reports/research/coverage/coverage_report.json · consumed by scorecard.
"""
from __future__ import annotations
import io, json, sys
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from backend.research.coverage import (
    STAGES, coverage_summary, coverage_full, coverage_by_domain,
)
from backend.research.coverage.tracker import domain_readiness_score


def main():
    summary = coverage_summary()
    by_domain = coverage_by_domain()
    readiness = {d: domain_readiness_score(d) for d in sorted(by_domain.keys())}
    full = coverage_full()

    payload = {
        "generated_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages_ordered": STAGES,
        "summary": summary,
        "domain_readiness": readiness,
        "signals_by_domain": by_domain,
        "all_signals": full,
        "governance_note": (
            "13-stage coverage tracker per CEO 2026-09-03. "
            "ONLY 'Production' means AEGIS is using it in R2. "
            "Everything else is a degree of NOT USED. "
            "This prevents 'schema exists' from looking like 'fundamentals integrated'."
        ),
    }
    out = _ROOT / "reports" / "research" / "coverage" / "coverage_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[coverage] wrote {out.relative_to(_ROOT)}")
    print(f"  total signals tracked: {summary['total_signals_tracked']}")
    print(f"  in production: {summary['counts_per_stage']['Production']} ({summary['in_production_pct']}%)")
    print(f"  per stage: {summary['counts_per_stage']}")


if __name__ == "__main__":
    main()
