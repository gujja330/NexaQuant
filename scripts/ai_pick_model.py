"""AI pick model - research only. python scripts/ai_pick_model.py --market both"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research.ai import pick_model as P  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=str(_ROOT))
    a = ap.parse_args()
    out = _ROOT / "reports" / "research"
    out.mkdir(parents=True, exist_ok=True)
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = P.evaluate(Path(a.root), m, a.asof)
        (out / ("ai_pick_model_%s.json" % m)).write_text(json.dumps(rep, indent=2, default=str),
                                                        encoding="utf-8")
        print("== %s · %s rows · %s tickers · %s dates (%s..%s)" % (
            m.upper(), rep.get("rows"), rep.get("tickers"), rep.get("dates"),
            rep.get("first_date"), rep.get("last_date")))
        print("   per-date mean 10d outcome · universe %s · top-decile baselines %s"
              % (rep.get("universe_mean"), rep.get("baselines_top_decile_mean")))
        for name, v in (rep.get("variants") or {}).items():
            print("   AI %-12s top-decile %+.3f vs %s %+.3f · excess %+.3f · beats on %.1f%% of dates · "
                  "%d/%d blocks · AUC %s · p=%.4g BH=%s · %s"
                  % (name, v["ai_top_decile_mean"], v["best_baseline"], v["baseline_top_decile_mean"],
                     v["excess_vs_baseline_mean"], v["dates_ai_beats_baseline_pct"],
                     v["blocks_ai_beats_baseline"], v["n_blocks"], v["auc_by_block"],
                     v["sign_test_p"], v.get("bh_fdr_significant"), v.get("verdict")))
        print("   VERDICT (pre-registered): %s" % rep.get("verdict"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
