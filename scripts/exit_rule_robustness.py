"""Exit rules across 5-6 years and every regime. Research only.

    python scripts/exit_rule_robustness.py --market both

Writes reports/research/exit_rule_robustness_<market>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from backend.research import exit_rule_robustness as X  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=str(_ROOT))
    a = ap.parse_args()
    out = _ROOT / "reports" / "research"
    out.mkdir(parents=True, exist_ok=True)
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = X.run(Path(a.root), m, a.asof)
        (out / ("exit_rule_robustness_%s.json" % m)).write_text(
            json.dumps(rep, indent=2, default=str), encoding="utf-8")
        print("== %s · %d tickers · %d episodes · %d entry dates from %s · regimes %s"
              % (m.upper(), rep["tickers"], rep["episodes"], rep["entry_dates"],
                 rep["first_entry"], rep["regime_counts"]))
        for key in ("ALL/ALL", "TREND_UP/ALL", "CHOP/ALL", "TREND_DOWN/ALL", "ALL/MOMENTUM",
                    "TREND_UP/MOMENTUM", "CHOP/MOMENTUM"):
            row = rep["results"].get(key)
            if not row:
                continue
            b, r_, s = row["BOOK_ALL"], row["RUN_ALL"], row["SPLIT"]
            print("  %-19s dates %-4d | BOOK %+5.2f%% %4.1fd sev %4.1f | RUN %+5.2f%% %4.1fd sev %4.1f "
                  "| SPLIT %+5.2f%% %4.1fd sev %4.1f wst %6.1f | split>book %5.1f%% of dates"
                  % (key, b["dates"], b["date_mean"], b["days"], b["severe"],
                     r_["date_mean"], r_["days"], r_["severe"],
                     s["date_mean"], s["days"], s["severe"], s["worst"],
                     row["split_beats_book_on_dates"]))
        print("  by year (date-mean BOOK / RUN / SPLIT):",
              {y: "%+.2f/%+.2f/%+.2f" % (v["BOOK_ALL"], v["RUN_ALL"], v["SPLIT"])
               for y, v in rep["results"]["by_year"].items()})
        print("  VERDICT (pre-registered): %s" % rep["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
