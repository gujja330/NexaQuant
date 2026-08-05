"""Daily runner · compute market breadth from existing bar parquets."""
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
from backend.context.market_breadth import compute as _b  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=_date.today().isoformat())
    ap.add_argument("--market", choices=["india", "usa"], default="india")
    args = ap.parse_args()
    payload = _b.compute_breadth(_ROOT, args.market, args.asof)
    if not payload.get("available"):
        print(f"[breadth:{args.market}] not available · {payload.get('reason')}")
        return 0
    _b.emit(_ROOT, payload)
    print(f"[breadth:{args.market}] {payload['total_tickers']} tickers · "
          f"AD={payload['overall_ad_ratio_pct']}% · "
          f">50DMA={payload['overall_above_50dma_pct']}%")
    print(f"\n  Per-sector (worst 5):")
    ps = payload.get("per_sector", {})
    for sect, s in sorted(ps.items(), key=lambda x: x[1].get("score", 0))[:5]:
        print(f"    {sect:<25} AD {s['ad_ratio_pct']}% · "
              f">50DMA {s['above_50dma_pct']}% · score {s['score']:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
