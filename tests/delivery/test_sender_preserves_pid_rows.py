"""The sender must not drop audit rows keyed by `pid`. CEO 2026-11-26.

USA's orphan_audit_usa.jsonl went 504 -> 39 rows in one send: the
August rows store their episode under `pid`, the foreign-row filter
read only opportunity_id / position_id, so their id resolved to "" and
`if _oid and ...` discarded all 490. The publication guard
(aegis_local_state.validate_history) then correctly refused to copy
the workspace back, and USA never reached Telegram.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2] / "scripts"
        / "telegram_command_center_send.py").read_text(encoding="utf-8")


def _block() -> str:
    i = _SRC.find("_foreign_rows = []")
    assert i > 0, "foreign-row preservation block not found"
    return _SRC[i:i + 2500]


def test_pid_is_read_as_an_episode_id():
    assert '_obj.get("pid")' in _block()


def test_a_row_without_a_readable_id_is_kept_not_dropped():
    b = _block()
    assert "if not _oid or _oid not in _own_ids:" in b
    assert "if _oid and _oid not in _own_ids:" not in b, (
        "an unreadable id must never mean 'delete this audit row'")
