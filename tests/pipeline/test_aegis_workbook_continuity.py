import json
from pathlib import Path

from openpyxl import Workbook

from scripts.aegis_local_state import digest
from scripts.aegis_shadow.publication import SHEETS, notify, publish
from scripts.aegis_workbook_continuity import discover


def _book(path, titles):
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    book.remove(book.active)
    for title in titles:
        book.create_sheet(title)
    book.save(path)
    book.close()


def test_discovery_ignores_failed_and_corrupt_workbooks(tmp_path):
    for day, status in (("24", "delivered"), ("25", "failed"), ("26", "certified")):
        asof = f"2026-11-{day}"
        folder = tmp_path / f".aegis-local/202611{day}-india-fixture"
        relative = Path(f"reports/telegram/aegis_india_{asof}.xlsx")
        path = tmp_path / relative
        _book(path, ["CURRENT", "EXIT HISTORY"])
        if day == "26":
            path.write_bytes(b"invalid workbook")
        identity = {"market": "india", "asof": asof, "market_data_asof": asof}
        lifecycle = folder / "work/reports/context/canonical_lifecycle_india.json"
        lifecycle.parent.mkdir(parents=True)
        lifecycle.write_text(json.dumps(identity), encoding="utf-8")
        (folder / "attempt.json").write_text(json.dumps(dict(
            identity, scope="india", status=status, updated_utc=asof + "T23:00:00+00:00",
            workbook=relative.as_posix(), sha256=digest(path),
        )), encoding="utf-8")
    assert discover(tmp_path, "india")["asof"] == "2026-11-24"
    assert discover(tmp_path, "usa") is None


def test_new_publication_is_distinct_and_notification_defaults_to_disabled(tmp_path):
    work = tmp_path / "private"
    _book(work / "shadow.xlsx", SHEETS)
    record = publish(tmp_path, work, {"status": "SHADOW_CERTIFIED", "market": "usa",
                     "asof": "2026-11-26", "market_data_asof": "2026-11-25"})
    assert record["workbook"] == "reports/unified/usa/aegis_new_usa_2026-11-26.xlsx"
    assert discover(tmp_path, "usa", "new")["sha256"] == record["sha256"]
    assert discover(tmp_path, "usa") is None
    assert notify(tmp_path, record) == "DISABLED"


def test_shadow_delivery_retries_explicit_rejection_once(tmp_path, monkeypatch):
    from scripts import telegram_command_center_send as telegram

    work = tmp_path / "private"
    _book(work / "shadow.xlsx", SHEETS)
    record = publish(tmp_path, work, {"status": "SHADOW_CERTIFIED", "market": "usa",
                     "asof": "2026-11-26", "market_data_asof": "2026-11-25"})
    config = tmp_path / ".aegis-local/unified/delivery.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"enabled": True, "isolation_owner_verified": True}), encoding="utf-8")
    monkeypatch.setenv("AEGIS_NEW_TELEGRAM_BOT_TOKEN", "fixture-token")
    monkeypatch.setenv("AEGIS_NEW_TELEGRAM_CHAT_ID", "fixture-chat")
    calls = []

    def send(token, chat, path, *, caption):
        calls.append(path)
        assert caption.startswith("AEGIS NEW | USA | SHADOW")
        if len(calls) == 1:
            monkeypatch.setattr(telegram, "_LAST_SEND", {"telegram_ok": False, "http_status": 429})
            return False, "explicit rejection"
        monkeypatch.setattr(telegram, "_LAST_SEND", {"telegram_ok": True, "http_status": 200,
                            "message_id": 42, "document_filename": path.name, "document_bytes": path.stat().st_size})
        return True, "accepted"

    assert notify(tmp_path, record, send=send) == "FAILED"
    assert notify(tmp_path, record, send=send) == "DELIVERED"
    assert notify(tmp_path, record, send=send) == "DELIVERED"
    assert len(calls) == 2
