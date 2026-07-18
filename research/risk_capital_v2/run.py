"""Risk & Capital Engine v2.0 · CLI."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from risk_capital_v2.compute import engine                                              # noqa: E402
from risk_capital_v2.publish import bundle as publish                                    # noqa: E402


def _banner(msg: str) -> None:
    print(); print("=" * 72); print(f"  {msg}"); print("=" * 72)


def main() -> int:
    t0 = time.time()
    _banner("RISK & CAPITAL ENGINE · v2.0 · POSITION SIZING + RISK BUDGET")

    _banner("STEP 1/2 · Size positions + compute portfolio risk")
    result = engine.run(top_k=20, verbose=True)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return 1

    _banner("STEP 2/2 · Publish 4 outputs")
    outcome = publish.build_and_publish(result)
    for name in outcome["written"]:
        print(f"  written: reports/{name}")

    _banner("TOP-10 SIZING DECISIONS")
    top = sorted(result["sizing"], key=lambda d: -d["target_weight"])[:10]
    print(f"  {'ticker':<12} {'target':>7} {'verdict':<8} {'why':<50}")
    for d in top:
        factors = " · ".join(f"{f['name'][:3]}={f['value']}" for f in d["factors"])
        print(f"  {d['ticker']:<12} {d['target_weight']*100:>6.2f}%  {d['verdict']:<8} {factors}")

    _banner("PORTFOLIO RISK")
    risk = result["portfolio_risk"]
    print(f"  annualised vol : {risk['portfolio_vol_annual']}")
    print(f"  VaR 95%        : {risk['var_95']}")
    print(f"  VaR 99%        : {risk['var_99']}")
    print(f"  CVaR 95%       : {risk['cvar_95']}")
    print(f"  verdict        : {risk['verdict']}")
    if risk["alerts"]:
        print("  alerts:")
        for a in risk["alerts"][:5]:
            print(f"    [{a['severity']}] {a['kind']} · {a['entity']}")

    _banner(f"RISK & CAPITAL v2.0 · DONE ({time.time() - t0:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
