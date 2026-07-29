"""Regression: HTML→plain-text fallback must not be misclassified as FAILURE.

The 2026-07-29 CI incident: sealed india/telegram_notify.py emits an
intentional "HTML send failed → falling back to plain-text → plain-text
delivered → sent (N)" sequence on every message Telegram's HTML parser
rejects. The retry wrapper's failure-first classifier matched the
intermediate "send failed" line and wrongly declared FAILURE. Result:
4× retries, up to 8× duplicate messages delivered, CI step visibly failed.

This test locks the fix: SUCCESS marker + exit_code=0 always wins.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.telegram_send_with_retry import _classify  # noqa: E402


REAL_CI_LOG = """\
freshness check: aegis_today.csv Generated=2026-07-29 matches today IST=2026-07-29
[notify]  chunk 1/2 - HTML send failed: HTTP 400: Bad Request: can't parse entities: Unsupported start tag "3" at byte offset 2272
[notify]  chunk 1/2 - falling back to plain-text
[notify]  chunk 1/2 - plain-text delivered
[notify]  sent (2 messages).
"""


def test_html_fallback_then_delivered_is_SUCCESS_not_FAILURE():
    """The exact log that caused CI to fail 4/4 times must classify SUCCESS."""
    verdict, marker = _classify(REAL_CI_LOG, exit_code=0)
    assert verdict == "SUCCESS", (
        f"HTML→plain-text fallback with terminal 'sent (N)' MUST be SUCCESS, "
        f"got {verdict} (marker={marker}). This is the exact scenario that "
        f"caused the 2026-07-29 CI incident."
    )


def test_pure_failure_still_classified_FAILURE():
    """Real failures (no terminal 'sent' marker) must still be FAILURE."""
    log = ("[notify] chunk 1/2 - HTML send failed: HTTP 400\n"
             "[notify] chunk 1/2 - falling back to plain-text\n"
             "[notify] chunk 1/2 - plain-text send failed: HTTP 500\n"
             "[notify] cannot send any format\n")
    verdict, _ = _classify(log, exit_code=1)
    assert verdict == "FAILURE"


def test_non_zero_exit_code_is_always_FAILURE():
    """Even if 'sent (' appears somewhere, non-zero exit is authoritative."""
    log = "misleading: sent (0 messages)\n"
    verdict, marker = _classify(log, exit_code=2)
    assert verdict == "FAILURE"
    assert "exit_code=2" in marker or marker in ("send failed", "cannot send",
                                                     "returned not-ok",
                                                     "MISSING TELEGRAM")


def test_exit_zero_with_no_markers_is_UNKNOWN():
    verdict, marker = _classify("nothing meaningful here\n", exit_code=0)
    assert verdict == "UNKNOWN"
    assert marker == ""


def test_missing_telegram_secrets_still_flagged_FAILURE():
    log = "MISSING TELEGRAM secrets — cannot proceed\n"
    verdict, marker = _classify(log, exit_code=1)
    assert verdict == "FAILURE"
    assert marker == "MISSING TELEGRAM"


def test_delivered_after_fallback_across_both_chunks():
    """Both chunks fall back to plain-text · terminal 'sent (2)' → SUCCESS."""
    log = ("[notify] chunk 1/2 - HTML send failed: HTTP 400\n"
             "[notify] chunk 1/2 - plain-text delivered\n"
             "[notify] chunk 2/2 - HTML send failed: HTTP 400\n"
             "[notify] chunk 2/2 - plain-text delivered\n"
             "[notify] sent (2 messages).\n")
    verdict, marker = _classify(log, exit_code=0)
    assert verdict == "SUCCESS"
    assert "sent (" in marker


def test_partial_delivery_still_reports_success_when_sender_says_so():
    """If the sealed sender chose to emit 'sent (1 messages)' after 1/2 chunks
    landed, we trust its judgement rather than second-guess."""
    log = ("[notify] chunk 1/2 - HTML send failed: HTTP 400\n"
             "[notify] chunk 1/2 - plain-text delivered\n"
             "[notify] chunk 2/2 - HTML send failed: HTTP 400\n"
             "[notify] chunk 2/2 - plain-text send failed: HTTP 500\n"
             "[notify] sent (1 messages).\n")
    verdict, _ = _classify(log, exit_code=0)
    # sender says SUCCESS with partial delivery → we honor exit_code=0
    assert verdict == "SUCCESS"
