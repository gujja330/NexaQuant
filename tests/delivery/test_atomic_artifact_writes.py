"""A reader must never see a half-written canonical artifact.

CEO 2026-11-03 · WHERE THIS CAME FROM
-------------------------------------
A19 failed a full-suite run with `BadZipFile: File is not a zip file`
while passing in its own module, and I first called it order-dependent.
It was not. `workbook.save(path)` and `Path.write_text(path)` both
truncate the live artifact and then fill it, so for the duration of the
write the file on disk is a partial document. A single sequential pytest
session or pipeline run never reads in that window, which is why CI had
always been green. Two readers of one checkout do - in this case a
foreground pytest run regenerating the workbook while a background
full-suite run read it, a concurrency artifact of my own making.

The JSON case is the more dangerous of the two, because it fails QUIETLY:
`canonical_daily_lifecycle.load()` catches the parse error and returns
None, and a None lifecycle reads downstream as an empty portfolio rather
than as a failure.

Both writes now go to a sibling temp file and `os.replace` into place.
These tests hold that property under an actual concurrent reader rather
than asserting the implementation.

tmp_path-isolated · no live artifact is read or written.
"""
from __future__ import annotations

import json
import threading
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
from tests.delivery.conftest import _save_atomic


def _big_workbook(rows: int = 4000) -> Workbook:
    """Large enough that the write is not instantaneous."""
    wb = Workbook()
    ws = wb.active
    ws.title = "CURRENT"
    for i in range(rows):
        ws.append(["TICK%05d" % i, i * 1.5, "some padding text here", i])
    ws2 = wb.create_sheet("EXIT HISTORY")
    for i in range(rows // 2):
        ws2.append(["EXIT%05d" % i, i * 2.5, "more padding", i])
    return wb


class TestWorkbookAtomicSave:
    def test_a_concurrent_reader_never_sees_a_partial_zip(self, tmp_path):
        out = tmp_path / "aegis_history_usa.xlsx"
        _save_atomic(_big_workbook(800), out)        # a valid starting file

        errors: list = []
        stop = threading.Event()

        def _read():
            while not stop.is_set():
                try:
                    if out.exists():
                        wb = load_workbook(out, read_only=True)
                        assert "CURRENT" in wb.sheetnames
                        wb.close()
                except zipfile.BadZipFile as e:
                    errors.append("BadZipFile: %s" % e)
                except (OSError, KeyError):
                    pass          # a replaced handle is fine, a torn file is not

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        blocked = 0
        try:
            for _ in range(6):
                # On Windows MoveFileEx cannot displace a file another
                # handle holds open, and the reader above spins with no
                # pause, so it holds one ~100% of the time. A blocked
                # WRITE is acceptable and loud; a torn READ is not. See
                # test_a_realistic_reader_does_not_block_the_write for
                # the production duty cycle, where the retry wins.
                try:
                    _save_atomic(_big_workbook(4000), out)
                except PermissionError:
                    blocked += 1
        finally:
            stop.set()
            t.join(timeout=10)

        assert not errors, errors[:3]
        # whatever happened to the writes, the destination is intact
        wb = load_workbook(out)
        assert wb.sheetnames == ["CURRENT", "EXIT HISTORY"]
        wb.close()
        # No assertion on `blocked`: a 4000-row workbook save against a
        # reader that spins with no pause can legitimately be blocked
        # every time on Windows. Whether the retry EARNS its place is
        # proved against a production duty cycle in
        # TestTheRetryEarnsItsPlace, not here. What this test owns is
        # the read side: zero torn documents, destination still valid.

    def test_the_temp_file_is_a_sibling_not_in_the_system_temp(self, tmp_path):
        """os.replace is only atomic within one filesystem."""
        out = tmp_path / "wb.xlsx"
        seen: list = []
        real = Workbook.save

        def _spy(self, path):
            seen.append(Path(path))
            return real(self, path)

        Workbook.save = _spy
        try:
            _save_atomic(_big_workbook(50), out)
        finally:
            Workbook.save = real
        assert seen and seen[0].parent == out.parent
        assert seen[0] != out

    def test_a_failed_save_leaves_the_previous_file_intact(self, tmp_path):
        out = tmp_path / "wb.xlsx"
        _save_atomic(_big_workbook(40), out)
        before = out.read_bytes()

        class _Boom:
            def save(self, _p):
                raise RuntimeError("disk full")

        with pytest.raises(RuntimeError, match="disk full"):
            _save_atomic(_Boom(), out)
        assert out.read_bytes() == before

    def test_a_failed_save_leaves_no_temp_file_behind(self, tmp_path):
        out = tmp_path / "wb.xlsx"
        _save_atomic(_big_workbook(40), out)

        class _Boom:
            def save(self, p):
                Path(p).write_bytes(b"partial")
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            _save_atomic(_Boom(), out)
        leftovers = [p.name for p in out.parent.iterdir() if ".tmp-" in p.name]
        assert leftovers == []


class TestLifecycleAtomicEmit:
    @staticmethod
    def _rep(market="usa", n=3000):
        return {"market": market, "asof": "2026-11-03",
                "schema_version": "aegis.lifecycle.v1",
                "counts": {"current_total": n},
                "current": [{"ticker": "T%05d" % i, "entry_price": i * 1.0,
                             "note": "padding to make the write non-trivial"}
                            for i in range(n)],
                "exits": []}

    def test_a_concurrent_reader_never_sees_partial_json(self, tmp_path):
        """The quiet failure · `load()` returns None on a torn read."""
        lc.emit(tmp_path, self._rep(n=500))

        nones: list = []
        stop = threading.Event()

        def _read():
            while not stop.is_set():
                d = lc.load(tmp_path, "usa")
                if d is None:
                    nones.append(1)

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        blocked = 0
        try:
            for _ in range(8):
                try:
                    lc.emit(tmp_path, self._rep(n=3000))
                except PermissionError:
                    blocked += 1          # Windows sharing · see the ZIP case
        finally:
            stop.set()
            t.join(timeout=10)

        assert not nones, (
            "%d torn reads · a None lifecycle reads downstream as an empty "
            "portfolio, not as a failure" % len(nones))
        # and the artifact still parses afterwards
        assert lc.load(tmp_path, "usa") is not None

    def test_the_emitted_document_is_complete_and_parses(self, tmp_path):
        p = lc.emit(tmp_path, self._rep(n=100))
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["counts"]["current_total"] == 100
        assert len(d["current"]) == 100

    def test_emit_returns_the_destination_not_the_temp_path(self, tmp_path):
        p = lc.emit(tmp_path, self._rep(n=10))
        assert ".tmp-" not in p.name
        assert p.exists() and p == lc.artifact_path(tmp_path, "usa")

    def test_no_temp_files_remain_after_a_successful_emit(self, tmp_path):
        lc.emit(tmp_path, self._rep(n=10))
        d = lc.artifact_path(tmp_path, "usa").parent
        assert [p.name for p in d.iterdir() if ".tmp-" in p.name] == []

    def test_two_markets_do_not_collide(self, tmp_path):
        lc.emit(tmp_path, self._rep("india", n=20))
        lc.emit(tmp_path, self._rep("usa", n=30))
        assert lc.load(tmp_path, "india")["counts"]["current_total"] == 20
        assert lc.load(tmp_path, "usa")["counts"]["current_total"] == 30


class TestTheRetryEarnsItsPlace:
    """A production reader opens, reads and closes · the retry wins there.

    The spinning readers above prove no TORN read is possible. This
    proves the bounded retry actually completes the write against the
    duty cycle production has, so the retry is not decoration.
    """

    @staticmethod
    def _rep(n):
        # keyword, not positional · _rep's first parameter is `market`
        return TestLifecycleAtomicEmit._rep(n=n)

    def test_a_realistic_reader_does_not_block_the_write(self, tmp_path):
        import time
        lc.emit(tmp_path, self._rep(n=50))
        stop = threading.Event()
        nones: list = []

        def _read():
            while not stop.is_set():
                if lc.load(tmp_path, "usa") is None:
                    nones.append(1)
                time.sleep(0.01)      # a reader between pipeline stages

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        try:
            for _ in range(8):
                lc.emit(tmp_path, self._rep(n=200))   # must NOT raise
        finally:
            stop.set()
            t.join(timeout=10)

        assert not nones
        assert lc.load(tmp_path, "usa")["counts"]["current_total"] == 200

    def test_replace_with_retry_reraises_rather_than_losing_a_write(self,
                                                                    tmp_path):
        """A write that cannot land must be loud, never assumed done."""
        from backend.shared.atomic_io import replace_with_retry
        src = tmp_path / "src.txt"
        src.write_text("x", encoding="utf-8")
        dest = tmp_path / "sub" / "dest.txt"      # parent does not exist
        with pytest.raises(OSError):
            replace_with_retry(src, dest, attempts=2, base_delay=0.001)
