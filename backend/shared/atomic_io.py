"""Atomic file replacement that also works on Windows.

CEO 2026-11-04.

WHY THIS EXISTS
---------------
Artifacts are written to a sibling temp file and moved into place, so a
concurrent reader sees either the whole previous file or the whole new
one and never a half-written ZIP or JSON. That fix was added after a
`BadZipFile` traceback that looked like test order-dependence and was
really a torn read.

`os.replace` delivers that guarantee on POSIX unconditionally: `rename`
succeeds even when another process holds the destination open, and the
reader keeps reading the old inode.

Windows is different. `MoveFileEx` fails with ERROR_ACCESS_DENIED (5)
when the destination is open without `FILE_SHARE_DELETE`, which Python's
`open()` does not request. So on Windows the move raises exactly when a
reader is active - the case the atomic write exists to handle:

    PermissionError: [WinError 5] Access is denied:
      '...canonical_lifecycle_usa.json.tmp-11096' ->
      '...canonical_lifecycle_usa.json'

The data is never corrupted - the destination is untouched and the temp
is removed - but a legitimate write fails because somebody was reading.

Readers hold these files for milliseconds, so a bounded retry closes the
window. The retry is deliberately NOT infinite and NOT silent: if every
attempt fails the original error is raised, because a lost artifact must
be loud rather than inferred later from a stale timestamp.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

#: Windows ERROR_ACCESS_DENIED / ERROR_SHARING_VIOLATION.
_WINDOWS_SHARING_ERRNOS = {5, 13, 32}

DEFAULT_ATTEMPTS = 10
DEFAULT_BASE_DELAY_S = 0.02


def replace_with_retry(src, dest, attempts: int = DEFAULT_ATTEMPTS,
                       base_delay: float = DEFAULT_BASE_DELAY_S) -> Path:
    """`os.replace(src, dest)`, retried while the destination is held open.

    Returns `dest`. Raises the final OSError if every attempt fails, so a
    caller can never mistake a dropped write for a successful one.

    Backoff is linear and small (20ms, 40ms, ... ~1.1s total over ten
    attempts) because the contended window is a reader's single
    `read_bytes`, not a long-held lock.
    """
    src, dest = Path(src), Path(dest)
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            os.replace(str(src), str(dest))
            return dest
        except PermissionError as e:          # Windows sharing violation
            last = e
        except OSError as e:
            if getattr(e, "winerror", None) in _WINDOWS_SHARING_ERRNOS \
                    or e.errno in _WINDOWS_SHARING_ERRNOS:
                last = e
            else:
                raise
        time.sleep(base_delay * (i + 1))
    assert last is not None
    raise last


def write_text_atomic(dest, text: str, encoding: str = "utf-8",
                      **retry) -> Path:
    """Write `text` to `dest` so no reader observes a partial file."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp-%d" % os.getpid())
    try:
        tmp.write_text(text, encoding=encoding)
        return replace_with_retry(tmp, dest, **retry)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_bytes_atomic(dest, data: bytes, **retry) -> Path:
    """Byte equivalent of `write_text_atomic`, for workbooks and parquet."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp-%d" % os.getpid())
    try:
        tmp.write_bytes(data)
        return replace_with_retry(tmp, dest, **retry)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
