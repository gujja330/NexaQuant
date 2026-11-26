"""Run the independent AEGIS candidate in a private market workspace."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from scripts.aegis_shadow.daily import run_daily
from scripts.aegis_shadow.pipeline import run as run_frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", choices=("india", "usa", "both"), required=True)
    parser.add_argument("--frozen", action="store_true", help="inspect retained evidence without refresh")
    parser.add_argument("--force-rerun", action="store_true", help="recompute instead of reusing a verified report")
    args = parser.parse_args()
    markets = ("india", "usa") if args.market == "both" else (args.market,)
    if args.frozen:
        return run_frozen(ROOT, markets)
    return run_daily(ROOT, markets, force=args.force_rerun)


if __name__ == "__main__":
    raise SystemExit(main())
