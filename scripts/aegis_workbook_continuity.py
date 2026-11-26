"""Discover successful workbooks by receipts and integrity, independently per market."""
from datetime import date, datetime
import json
from pathlib import Path
from zipfile import BadZipFile

from scripts.aegis_local_state import contained, digest


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def discover(root, market, runner="legacy"):
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    if market not in {"india", "usa"} or runner not in {"legacy", "new"}:
        raise ValueError("unknown market or runner")
    if runner == "legacy":
        folder = contained(root, Path(".aegis-local"))
        candidates = folder.glob(f"*-{market}-*/attempt.json")
        allowed, sheets = {"certified", "delivered"}, ["CURRENT", "EXIT HISTORY"]
    else:
        folder = contained(root, Path("reports/unified") / market)
        candidates = folder.glob("*.manifest.json")
        allowed, sheets = {"SHADOW_CERTIFIED"}, ["RUN SUMMARY", "NEW CURRENT", "NEW EXIT HISTORY"]

    best = None
    for candidate in candidates:
        try:
            receipt = contained(root, candidate.relative_to(root))
            record = _read(receipt)
            if not isinstance(record, dict):
                continue
            if record.get("scope", record.get("market")) != market or record.get("status") not in allowed:
                continue
            asof = date.fromisoformat(record["asof"])
            session = date.fromisoformat(record["market_data_asof"])
            updated = datetime.fromisoformat(record.get("updated_utc", record.get("published_utc")))
            rel = Path(record["workbook"])
            prefix = Path("reports/telegram") if runner == "legacy" else Path("reports/unified") / market
            stem = f"aegis_{market}_{asof}" if runner == "legacy" else f"aegis_new_{market}_{asof}"
            if (session > asof or updated.utcoffset() is None or rel.parent != prefix
                    or rel.suffix != ".xlsx" or (rel.stem != stem
                    and not (runner == "new" and rel.stem.startswith(stem + "-")))):
                continue
            if runner == "legacy":
                lifecycle = contained(root, receipt.parent.relative_to(root) / "work/reports/context"
                                      / f"canonical_lifecycle_{market}.json")
                related = _read(lifecycle)
                if not isinstance(related, dict):
                    continue
                if (related.get("market"), related.get("market_data_asof"), related.get("asof")) != (
                        market, session.isoformat(), asof.isoformat()):
                    continue
            elif record.get("runner") != "new":
                continue
            key = (session, asof, updated)
            if best and key <= best[0]:
                continue
            path = contained(root, rel)
            if not path.is_file() or digest(path) != record["sha256"]:
                continue
            book = load_workbook(path, read_only=True)
            try:
                if book.sheetnames != sheets:
                    continue
            finally:
                book.close()
            best = (key, dict(record, runner=runner, market=market, receipt=str(receipt.relative_to(root))))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, BadZipFile, InvalidFileException):
            continue
    return best[1] if best else None
