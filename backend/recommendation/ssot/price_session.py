"""Connect India recommendation snapshots to the verified NSE session."""
from datetime import date, datetime
from pathlib import Path


def expected_session(root: Path, market: str, asof: str) -> str | None:
    if market != "india" or asof != date.today().isoformat():
        return None
    from india.nse_market_cap import artifact
    from scripts.check_data_freshness import completed_nse_session

    session = completed_nse_session().isoformat()
    return session if artifact(root, session).is_file() else None


def snapshot_session(snapshot: dict) -> str | None:
    if snapshot.get("price_session"):
        return snapshot["price_session"]
    from scripts.check_data_freshness import completed_nse_session

    try:
        moment = datetime.fromisoformat(snapshot.get("run_utc") or "")
    except ValueError:
        return None
    return completed_nse_session(moment).isoformat() if moment.tzinfo else None
