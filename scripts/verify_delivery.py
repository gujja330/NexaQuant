#!/usr/bin/env python3
"""Local delivery-gate verifier · run BEFORE every commit.

Builds the XLSX in dry-run mode + runs every acceptance-gate check
+ prints ALL verdicts. Zero surprises when CI runs.

Usage:
    python scripts/verify_delivery.py                # India + USA
    python scripts/verify_delivery.py --market india # India only

Exit code:
    0  = would ALLOW delivery
    1  = would BLOCK · at least one FAIL

Run this after every code change touching the sender/guard/gate.
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                                    encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _verify_one(market: str, asof: str) -> tuple:
    """Return (n_fail, n_warn, n_pass, report_dict)."""
    print("=" * 78)
    print(f"  DELIVERY VERIFIER · {market.upper()} · asof {asof}")
    print("=" * 78)

    # 1. Build the XLSX (--build-only · fully generates sheets · skips Telegram)
    print(f"\n[1/3] Building {market} XLSX (sender --build-only) ...")
    r = subprocess.run(
        [sys.executable, "scripts/telegram_command_center_send.py",
             "--market", market, "--build-only"],
        cwd=str(_ROOT), capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        print(f"  BUILD FAILED · exit={r.returncode}")
        print(r.stderr[-1500:])
        return (1, 0, 0, {})
    print(f"  build ok · {r.stdout.count(chr(10))} lines emitted")

    # 2. Run wave_regression against the just-built XLSX
    print(f"\n[2/3] Running acceptance-gate checks (A1-A24) ...")
    from backend.research import wave_regression as _wreg
    rep = _wreg.compute(_ROOT, market, asof)
    _wreg.emit(_ROOT, rep)
    print(f"  verdict: {rep.verdict}  pass={rep.n_pass}  warn={rep.n_warn}  fail={rep.n_fail}")
    for chk in rep.checks:
        icon = {"PASS":"✅", "WARN":"⚠️", "FAIL":"❌"}.get(chk["status"], "?")
        print(f"  {icon} [{chk['code']:>4}] {chk['status']:4} {chk['name']:55}")
        if chk["status"] in ("WARN", "FAIL"):
            print(f"       {chk['detail'][:120]}")

    # 3. Run delivery_gate.decide
    print(f"\n[3/3] Running delivery-gate simulation ...")
    from backend.delivery.delivery_gate import decide as _decide
    from backend.delivery.delivery_gate import blocked_summary as _summary
    d = _decide(_ROOT, market)
    print(f"  gate verdict: {d.verdict}")
    print(f"  blocking codes: {d.blocking_codes}")
    if d.verdict == "BLOCK":
        print()
        print("  ── ALERT THAT WOULD SEND TO TELEGRAM ──")
        for line in _summary(d).split("\n"):
            print(f"    {line}")

    return (rep.n_fail, rep.n_warn, rep.n_pass,
                {"gate": d.verdict, "regression": rep.verdict})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india", "usa", "both"], default="india")
    ap.add_argument("--asof", default=date.today().isoformat())
    args = ap.parse_args()

    markets = ["india", "usa"] if args.market == "both" else [args.market]
    total_fail = 0
    for m in markets:
        n_fail, n_warn, n_pass, res = _verify_one(m, args.asof)
        total_fail += n_fail
        print()

    print("=" * 78)
    if total_fail > 0:
        print(f"  🚫 OVERALL · WOULD BLOCK · {total_fail} FAIL across markets")
        print(f"  Fix the FAIL rows above · run again · commit only when ALLOW.")
        return 1
    print(f"  ✅ OVERALL · WOULD ALLOW · safe to commit + push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
