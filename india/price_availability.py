"""Record session-specific India price exceptions for decision consumers."""
from datetime import date
from functools import lru_cache
import json
from pathlib import Path

from backend.shared.atomic_io import write_text_atomic

REPORT = Path("reports/context/india_price_availability.json")


def _ticker(symbol):
    return str(symbol or "").upper().removesuffix(".NS").removesuffix(".BO")


def audit_prices(root, session, tracked, exceptions):
    import pandas as pd
    from backend.pipeline.contract.readiness import _universe_list
    from backend.research.opportunity_registry import active_opportunities, load_all
    from india.data_nse import STOCKS

    universe = {_ticker(s) for s in (_universe_list(root, "india") or STOCKS)}
    held = {_ticker(p.ticker) for p in active_opportunities(load_all(root)) if p.market == "india"}
    symbols = sorted(universe | held | set(tracked))
    unavailable = {}
    for symbol in symbols:
        if symbol in {"NSEI", "NSEBANK", "INDIAVIX", "SP500"}:
            continue
        path = root / "data/raw/india" / f"{symbol}_D1.parquet"
        latest = None
        if path.is_file():
            try:
                last = pd.read_parquet(path, columns=[]).index.max()
                latest = None if pd.isna(last) else str(last)[:10]
            except (OSError, ValueError):
                pass
        if latest != session:
            reason = exceptions.get(symbol) or (
                "no local price history" if not path.is_file() else
                exceptions.get("_archive") or "completed-session price unavailable")
            if symbol == "PEL" and not path.is_file():
                reason = "legacy equity suspended under NSE/CML/70298"
            if symbol == "TATAMOTORS" and not path.is_file():
                reason = "legacy pre-demerger identity requires reconciled successor history"
            unavailable[symbol] = {"last_price_date": latest, "held": symbol in held, "reason": reason}
    report = {"session": session, "universe_count": len(universe), "held_count": len(held),
              "available_universe_count": len(universe - unavailable.keys()), "unavailable": unavailable}
    path = root / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(report, indent=2) + "\n")
    print(f"  price coverage: {report['available_universe_count']}/{len(universe)} universe securities")
    for symbol, item in unavailable.items():
        print(f"  {symbol}: {'held, decisions paused' if item['held'] else 'candidate excluded'}; {item['reason']}")
    return report


@lru_cache(maxsize=8)
def _load(path, mtime):
    return json.loads(path.read_text(encoding="utf-8"))


def unavailable_prices(root, asof):
    if asof != date.today().isoformat():
        return {}
    path = root / REPORT
    if not path.is_file():
        return {}
    from scripts.check_data_freshness import completed_nse_session

    report = _load(path, path.stat().st_mtime_ns)
    return report["unavailable"] if report["session"] == completed_nse_session().isoformat() else {}
