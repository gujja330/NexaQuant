"""CUSUM_REGIME_SUPPLEMENT · real run against mr_market_regime source.

Per V2 §7: CUSUM tested as LEADING INDICATOR to existing classifier ·
never replaces classifier.

Reads mr_market_regime_{market}.json · derives daily market returns from
parquet · runs cusum_stream · compares flag dates against classifier
transition dates · reports lead_hit_rate + false_flag_rate.

Result: PASS / RESEARCH FURTHER / REJECT with explicit numbers.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from backend.research.r3.tier3.cusum_regime import cusum_stream, leading_indicator_test
from backend.research.enrichers.crash_recovery_detectors import _load_market_returns


def _classifier_transitions(root: Path, market: str) -> list[str]:
    p = root / "reports" / "research" / f"mr_market_regime_{market}.json"
    if not p.exists(): return []
    d = json.loads(p.read_text(encoding="utf-8"))
    regs = d.get("regimes") or {}
    dates = sorted(regs.keys())
    transitions = []
    prev = None
    for dt in dates:
        cur = regs[dt]
        if prev is not None and cur != prev:
            transitions.append(dt)
        prev = cur
    return transitions


def run(root: Path, market: str) -> dict:
    market_rets_map = _load_market_returns(root, market)
    if not market_rets_map:
        return {"market": market, "status": "MARKET_RETURN_UNAVAILABLE"}
    sorted_dates = sorted(market_rets_map.keys())
    returns = [market_rets_map[d] for d in sorted_dates]
    # k and h scaled to daily-return magnitudes
    stream = cusum_stream(returns, k=0.005, h=0.03)
    flag_dates = [sorted_dates[row["t"]] for row in stream if row["flagged"]]
    transitions = _classifier_transitions(root, market)
    li = leading_indicator_test(flag_dates, transitions, lead_window_days=5)

    passes_lead = li["lead_hit_rate"] >= 0.30
    passes_fp = li["false_flag_rate"] <= 0.30
    gate = "PASS" if (passes_lead and passes_fp) else "REJECT"

    result = {
        "market": market,
        "n_daily_returns": len(returns),
        "n_cusum_flags": len(flag_dates),
        "n_classifier_transitions": len(transitions),
        "leading_indicator_test": li,
        "gate_criteria": {
            "lead_hit_rate_ge_0.30": passes_lead,
            "false_flag_rate_le_0.30": passes_fp,
        },
        "GATE": gate,
        "parameters": {"k": 0.005, "h": 0.03, "lead_window_days": 5},
        "governance_note": ("Supplemental to existing regime classifier per V2 §7. "
                            "Does NOT replace classifier. REJECT means CUSUM doesn't "
                            "add leading information at these parameters."),
        "built_utc": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = root / "reports" / "research" / "r3" / "tier3"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"cusum_regime_{market}.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=("india","usa","both"), default="both")
    args = ap.parse_args()
    markets = ["india","usa"] if args.market == "both" else [args.market]
    for m in markets:
        r = run(_ROOT, m)
        print(f"[cusum-real] {m} · flags={r.get('n_cusum_flags',0)} · transitions={r.get('n_classifier_transitions',0)} · lead={r.get('leading_indicator_test',{}).get('lead_hit_rate','?')} · fp={r.get('leading_indicator_test',{}).get('false_flag_rate','?')} · GATE={r.get('GATE')}")


if __name__ == "__main__":
    main()
