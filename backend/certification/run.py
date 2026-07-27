"""Certification runner · produces proof report + capability matrix."""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from dataclasses import asdict

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backend.certification.proof_report import generate_proof_report
from backend.certification.capability_matrix import compute_capability_maturity


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["proof", "matrix"], default=None)
    args = ap.parse_args()

    if args.only in (None, "proof"):
        rep = generate_proof_report(_ROOT)
        p = _ROOT / "reports" / "institutional_proof_report.json"
        p.write_text(json.dumps(asdict(rep), indent=2, default=str), encoding="utf-8")
        tm = rep.trade_metrics
        print(f"[proof] n_trades={tm.get('n_trades')} win_rate={tm.get('win_rate')} "
              f"profit_factor={tm.get('profit_factor')} verdict={rep.verdict} -> {p.name}")

    if args.only in (None, "matrix"):
        d = compute_capability_maturity(_ROOT)
        p = _ROOT / "reports" / "capability_maturity_matrix.json"
        p.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
        print(f"[matrix] n_capabilities={d['n_capabilities']} distribution={d['level_distribution']} -> {p.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
