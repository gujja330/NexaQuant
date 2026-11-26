"""Independent workbook publication and explicitly gated shadow notification."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from scripts.aegis_local_state import contained, digest
from scripts.aegis_shadow.pipeline import _atomic, _json


SHEETS = ["RUN SUMMARY", "NEW CURRENT", "NEW EXIT HISTORY"]


def publish(root, attempt, summary):
    if summary["status"] != "SHADOW_CERTIFIED":
        raise ValueError("only certified shadow candidates can publish")
    market, asof = summary["market"], summary["asof"]
    folder = contained(root, Path("reports/unified") / market)
    folder.mkdir(parents=True, exist_ok=True)
    original = contained(attempt, Path("shadow.xlsx"))
    data = original.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    stem = f"aegis_new_{market}_{asof}"
    path = contained(folder, Path(f"{stem}.xlsx"))
    if path.exists() and digest(path) != checksum:
        path = contained(folder, Path(f"{stem}-{checksum[:12]}.xlsx"))
    if path.exists():
        if digest(path) != checksum:
            raise ValueError("shadow workbook version collision")
    else:
        _atomic(folder, path.name, data)
    manifest = contained(folder, Path(path.stem + ".manifest.json"))
    record = {
        "runner": "new", "market": market, "asof": asof,
        "market_data_asof": summary["market_data_asof"], "status": summary["status"],
        "published_utc": datetime.now(timezone.utc).isoformat(), "sha256": checksum,
        "schema": "aegis.unified.workbook.v1", "workbook": path.relative_to(root).as_posix(),
    }
    if not manifest.exists():
        _atomic(folder, manifest.name, json.dumps(record, indent=2).encode())
    elif _json(manifest).get("sha256") != checksum:
        raise ValueError("shadow workbook manifest mismatch")
    return record


def notify(root, record, send=None):
    config = contained(root, Path(".aegis-local/unified/delivery.json"))
    if not config.is_file():
        return "DISABLED"
    options = _json(config)
    if options.get("enabled") is not True or options.get("isolation_owner_verified") is not True:
        return "DISABLED"
    from scripts.aegis_workbook_continuity import discover
    from scripts import telegram_command_center_send as telegram

    market = record["market"]
    verified = discover(root, market, "new")
    if not verified or any(verified[key] != record[key] for key in ("sha256", "workbook", "market_data_asof")):
        raise ValueError("notification attachment is not the latest verified shadow publication")
    path = contained(root, Path(record["workbook"]))
    folder = path.parent
    receipt = contained(folder, Path(f"telegram-{record['sha256']}.json"))
    if receipt.exists() and _json(receipt)["status"] in {"DELIVERED", "SENDING", "UNCERTAIN"}:
        return _json(receipt)["status"]
    token = os.environ.get("AEGIS_NEW_TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("AEGIS_NEW_TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "MISSING_CONFIGURATION"
    caption = (f"AEGIS NEW | {market.upper()} | SHADOW\n"
               f"Report {record['asof']} · Market session {record['market_data_asof']}\n"
               f"{record['status']}")
    state = {"status": "SENDING", "sha256": record["sha256"]}
    _atomic(folder, receipt.name, json.dumps(state).encode())
    try:
        success, _ = (send or telegram._send_document)(token, chat, path, caption=caption)
        api = telegram._LAST_SEND
        verified_send = (success and api.get("telegram_ok") is True
                         and api.get("http_status") == 200 and api.get("message_id")
                         and api.get("document_filename") == path.name
                         and api.get("document_bytes") == path.stat().st_size)
        state.update(status="DELIVERED" if verified_send else "UNCERTAIN",
                     message_id=api.get("message_id"))
    except Exception:
        state["status"] = "UNCERTAIN"
    _atomic(folder, receipt.name, json.dumps(state).encode())
    return state["status"]
