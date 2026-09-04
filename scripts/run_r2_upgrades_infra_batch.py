"""Run the buildable-now R2 upgrade infrastructure batch:
  P5.1 · Ensemble disagreement (both markets)
  P5.3 · Turnover cap simulator (registry-wide)
  P4  · Cap × Sector interaction table + LR test

Each produces a JSON report under reports/research/r2_upgrades/.
Nothing here changes R2 production behavior.
"""
from __future__ import annotations
import io, json, sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass


from backend.research.r2_upgrades import p5_1_ensemble_disagreement as p51
from backend.research.r2_upgrades import p4_cap_sector_interaction as p4
from backend.research.r2_upgrades import p5_3_turnover_cap_simulator as p53


def main():
    print("=== P5.1 · ensemble disagreement ===")
    for m in ("india","usa"):
        out = p51.emit_report(_ROOT, m)
        r = json.loads(out.read_text(encoding="utf-8"))
        print(f"  {m}: status={r.get('status')} n_scored={r.get('n_candidates_scored')} "
                f"median_disagreement={r.get('aggregate_median_disagreement')}")
    print()
    print("=== P4 · Cap × Sector interaction ===")
    out = p4.emit_report(_ROOT)
    r = json.loads(out.read_text(encoding="utf-8"))
    print(f"  status={r.get('status')}")
    if r.get("status") == "OK":
        lr = r["likelihood_ratio_test"]
        print(f"  n_closed={r['n_closed_positions']} · n_cells={r['n_cells']}")
        print(f"  LR lr_stat={lr['lr_stat']} · df={lr['df']} · p_approx={lr['p_value_approx']}")
        print(f"  sector adds info at p<0.05: {lr['sector_adds_info_beyond_cap_at_p_0.05']}")
    print()
    print("=== P5.3 · turnover cap simulator ===")
    out = p53.emit_report(_ROOT, cap_pct=0.05)
    r = json.loads(out.read_text(encoding="utf-8"))
    print(f"  status={r.get('status')}")
    if r.get("status") == "OK":
        print(f"  rotation days observed: {r['n_rotation_days']}")
        print(f"  mean daily turnover: {r['mean_daily_turnover_frac']}")
        print(f"  days exceeding 5% cap: {r['n_days_exceeding_cap']} ({r['pct_days_exceeding_cap']*100:.1f}%)")
        print(f"  est. slippage savings if capped: {r['estimated_slippage_savings_pct_of_nav']}% of NAV")


if __name__ == "__main__":
    main()
