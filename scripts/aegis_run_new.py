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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--frozen", action="store_true", help="inspect retained evidence without refresh")
    mode.add_argument("--research-evaluate", action="store_true", help="evaluate the reviewed local research panel holdout")
    parser.add_argument("--force-rerun", action="store_true", help="recompute instead of reusing a verified report")
    mode.add_argument("--preflight", action="store_true", help="inspect release prerequisites without running engines")
    args = parser.parse_args()
    markets = ("india", "usa") if args.market == "both" else (args.market,)
    if args.research_evaluate:
        if args.force_rerun:
            parser.error("--research-evaluate cannot be combined with --force-rerun")
        from scripts.aegis_shadow.intelligence.integration import run_holdout

        return run_holdout(ROOT, markets)
    if args.preflight:
        if args.frozen or args.force_rerun:
            parser.error("--preflight cannot be combined with --frozen or --force-rerun")
        from scripts.aegis_shadow.preflight import run_preflight

        return run_preflight(ROOT, markets)
    if args.frozen:
        return run_frozen(ROOT, markets)
    return run_daily(ROOT, markets, force=args.force_rerun)


if __name__ == "__main__":
    raise SystemExit(main())
