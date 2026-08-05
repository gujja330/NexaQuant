"""Daily runner · fetch overnight moves for 8 global reference indices."""
from __future__ import annotations
import argparse, io, sys
from datetime import date as _date
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from backend.context.global_overnight import ingest as _o  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_date.today().isoformat())
    args = ap.parse_args()
    p = _o.ingest_daily(_ROOT, args.asof)
    print(f"[global_overnight] {p['n_available']}/{p['n_indices']} indices fetched")
    for yft, v in p["per_index"].items():
        pct = v["pct_change"]
        pct_str = f"{pct:+.2f}%" if pct is not None else "—"
        print(f"  {yft:<8} {v['name']:<16} {pct_str}")
    if p["sector_drag"]:
        print(f"\n  Sector drag (India):")
        for s, d in sorted(p["sector_drag"].items(), key=lambda x: x[1]):
            print(f"    {s:<25} {d:+.2f} pts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
