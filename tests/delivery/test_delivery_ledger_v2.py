"""The delivery ledger must carry a receipt. CEO 2026-11-04.

THE RECORD THAT PROMPTED THIS
-----------------------------
The entire delivery evidence for the certified India run of 2026-11-04
(Actions 41782641136) was one line:

    {"ts_utc": "2026-11-04T06:45:03.419830+00:00",
     "engine": "aegis.delivery.telegram.xlsx.v1",
     "kind":   "unified_xlsx",
     "file":   "reports/telegram/aegis_history.xlsx",
     "ok":     true, "gsheets": false}

Three defects, none of them a mis-send:

  * it names `aegis_history.xlsx`, the ONE workbook the delivery
    contract forbids sending (AEGIS_MASTER_PROMPT.md:318, "Telegram
    receives only the per-market XLSX - never the unified"). The actual
    sends are per-market, so the ledger contradicted the behaviour it
    was recording, and an auditor reading it would conclude the
    opposite;
  * no `market`, so which attachments went is unknowable;
  * `ok: true` is the SENDER'S boolean. `_send_document` receives a
    Telegram response carrying `message_id` and the ledger discarded it.
    The receipt was produced and thrown away.

ACCEPTANCE CRITERION
--------------------
"A future delivery record must let an auditor identify exactly which
file was sent and retrieve its actual Telegram API receipt."

The tests below check precisely that, and that a claim of delivery
without a receipt is visibly marked as such rather than reading green.

No network. No live ledger is written.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

tcc = importlib.import_module("scripts.telegram_command_center_send")


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Redirect the ledger append into tmp_path and read it back."""
    written: list = []

    def _append(record):
        written.append(record)
        p = tmp_path / "ledger.jsonl"
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    monkeypatch.setattr(tcc, "_append_delivery_ledger", _append)
    return written


@pytest.fixture
def attachment(tmp_path):
    p = tmp_path / "aegis_india_2026-11-04.xlsx"
    p.write_bytes(b"PK\x03\x04 pretend workbook bytes")
    return p


def _receipt(message_id=4242, http=200, ok=True, error=None):
    return {"http_status": http, "telegram_ok": ok,
            "message_id": message_id, "error_code": error,
            "raw": json.dumps({"ok": ok, "result": {"message_id": message_id}})}


class TestTheAuditorCanIdentifyTheFile:
    def test_the_record_names_the_attachment_actually_sent(self, ledger,
                                                            attachment,
                                                            monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        rec = tcc.record_attachment_delivery("India", attachment, True,
                                              chat_id="-1001234567890")
        assert rec["attachment_filename"] == "aegis_india_2026-11-04.xlsx"
        assert rec["market"] == "india"
        assert rec["kind"] == "per_market_xlsx"

    def test_the_record_carries_the_hash_of_the_bytes_delivered(self, ledger,
                                                                attachment,
                                                                monkeypatch):
        import hashlib
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        rec = tcc.record_attachment_delivery("India", attachment, True)
        assert rec["attachment_sha256"] == hashlib.sha256(
            attachment.read_bytes()).hexdigest()
        assert rec["attachment_bytes"] == attachment.stat().st_size

    def test_a_changed_file_produces_a_different_hash(self, ledger,
                                                       attachment, monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        first = tcc.record_attachment_delivery("India", attachment, True)
        attachment.write_bytes(b"PK\x03\x04 different bytes entirely")
        second = tcc.record_attachment_delivery("India", attachment, True)
        assert first["attachment_sha256"] != second["attachment_sha256"]

    def test_both_markets_get_their_own_record(self, ledger, tmp_path,
                                                monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        for m in ("India", "USA"):
            p = tmp_path / ("aegis_%s_2026-11-04.xlsx" % m.lower())
            p.write_bytes(b"x" + m.encode())
            tcc.record_attachment_delivery(m, p, True)
        assert [r["market"] for r in ledger] == ["india", "usa"]
        assert len({r["attachment_sha256"] for r in ledger}) == 2


class TestTheAuditorCanRetrieveTheReceipt:
    def test_the_message_id_and_http_status_are_recorded(self, ledger,
                                                          attachment,
                                                          monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt(message_id=9876,
                                                         http=200))
        rec = tcc.record_attachment_delivery("India", attachment, True)
        assert rec["message_id"] == 9876
        assert rec["http_status"] == 200
        assert rec["telegram_ok"] is True
        assert rec["receipt_verified"] is True

    def test_a_send_without_a_message_id_is_not_receipt_verified(self, ledger,
                                                                  attachment,
                                                                  monkeypatch):
        """The exact v1 failure · ok=true with nothing behind it."""
        monkeypatch.setattr(tcc, "_LAST_SEND",
                            {"http_status": None, "telegram_ok": None,
                             "message_id": None, "error_code": None})
        rec = tcc.record_attachment_delivery("India", attachment, True)
        assert rec["sender_ok"] is True
        assert rec["receipt_verified"] is False, (
            "a delivery claim with no receipt must not read as verified")

    def test_an_http_error_is_recorded_with_its_code(self, ledger, attachment,
                                                      monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND",
                            _receipt(message_id=None, http=429, ok=False,
                                      error=429))
        rec = tcc.record_attachment_delivery("India", attachment, False,
                                              detail="HTTP 429: Too Many")
        assert rec["http_status"] == 429
        assert rec["error_code"] == 429
        assert rec["telegram_ok"] is False
        assert rec["receipt_verified"] is False
        assert rec["delivered_at_utc"] is None
        assert "429" in rec["detail"]

    def test_a_failed_send_does_not_stamp_a_delivery_time(self, ledger,
                                                           attachment,
                                                           monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt(ok=False,
                                                         message_id=None))
        rec = tcc.record_attachment_delivery("India", attachment, False)
        assert rec["delivered_at_utc"] is None


class TestTheDestinationIsProtected:
    def test_the_raw_chat_id_is_never_written(self, ledger, attachment,
                                               monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        rec = tcc.record_attachment_delivery("India", attachment, True,
                                              chat_id="-1001234567890")
        blob = json.dumps(rec)
        assert "-1001234567890" not in blob
        assert rec["telegram_chat_id"].startswith("sha256:")

    def test_the_same_destination_fingerprints_identically(self):
        a = tcc._chat_fingerprint("-1001234567890")
        b = tcc._chat_fingerprint("-1001234567890")
        c = tcc._chat_fingerprint("-1009999999999")
        assert a == b and a != c

    def test_an_absent_chat_id_is_marked_not_fabricated(self):
        assert tcc._chat_fingerprint("") == "absent"


class TestTheUnifiedWorkbookIsNoLongerMislabelled:
    def test_no_record_kind_claims_the_unified_workbook_was_sent(self):
        """`kind: unified_xlsx` must not come back by edit."""
        import ast
        src = Path(tcc.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert "unified_xlsx" not in literals, (
            "a ledger record still classifies the delivery as the unified "
            "workbook, which the delivery contract forbids sending")

    def test_the_summary_record_says_the_source_was_not_sent_as_is(self):
        src = Path(tcc.__file__).read_text(encoding="utf-8")
        assert "split_and_send_summary" in src
        assert "never sent as-is" in src

    def test_the_schema_is_versioned(self):
        assert tcc.DELIVERY_LEDGER_SCHEMA == "aegis.delivery.ledger.v2"


class TestTheLedgerSurvivesAJsonRoundTrip:
    def test_every_field_is_serialisable(self, ledger, attachment,
                                          monkeypatch, tmp_path):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        tcc.record_attachment_delivery("India", attachment, True,
                                        chat_id="-100123")
        back = [json.loads(l) for l in
                (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if l.strip()]
        assert len(back) == 1
        for f in ("market", "attachment_filename", "attachment_sha256",
                  "telegram_chat_id", "message_id", "http_status",
                  "telegram_ok", "delivered_at_utc", "error_code",
                  "receipt_verified", "schema"):
            assert f in back[0], "ledger v2 is missing %s" % f

    def test_a_missing_attachment_is_reported_not_hashed(self, ledger,
                                                          tmp_path,
                                                          monkeypatch):
        monkeypatch.setattr(tcc, "_LAST_SEND", _receipt())
        rec = tcc.record_attachment_delivery("India", tmp_path / "absent.xlsx",
                                              False)
        assert rec["attachment_sha256"] is None
        assert rec["attachment_bytes"] is None
        assert rec["receipt_verified"] is False
