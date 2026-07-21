"""
Regression test for the Telegram HTTP 400 fix in india/telegram_notify.py.

Covers:
- HTML parse errors on any chunk trigger a plain-text fallback that delivers.
- The actual Telegram error description is surfaced (not just "HTTP Error 400").
- The `_strip_html` fallback produces something Telegram will accept.
"""
from __future__ import annotations
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import india.telegram_notify as tn


_passed = 0
_failed = 0


def _ok(msg):
    global _passed
    _passed += 1
    print(f"  [OK] {msg}")


def _fail(msg, e):
    global _failed
    _failed += 1
    print(f"  [FAIL] {msg}: {e}")


def _run(label, fn):
    try:
        fn(); _ok(label)
    except AssertionError as e:
        _fail(label, e)
    except Exception as e:
        _fail(label, e)


# ── _strip_html ────────────────────────────────────────────────

def test_strip_html_removes_bold_italic():
    text = "<b>NIFTY</b> <i>bull</i> · Rec <b>BUY</b>"
    out = tn._strip_html(text)
    assert "<b>" not in out and "<i>" not in out
    assert "NIFTY" in out and "bull" in out


def test_strip_html_preserves_ampersand_lt_gt():
    """Real message content: 'AT&T · P/E > 30' — plain-text fallback must render these literally."""
    text = "AT&amp;T · P/E &gt; 30 &lt; 40"
    out = tn._strip_html(text)
    assert "AT&T" in out
    assert "P/E > 30 < 40" in out


def test_strip_html_removes_anchor_tags():
    text = '<a href="https://sheets.google.com/xyz">sheet</a>'
    out = tn._strip_html(text)
    assert "<a" not in out and "</a>" not in out


# ── _read_telegram_error ───────────────────────────────────────

def test_read_telegram_error_extracts_description():
    body = json.dumps({
        "ok": False, "error_code": 400,
        "description": "Bad Request: can't parse entities: Character '<' can't be used here",
    }).encode()
    exc = MagicMock()
    exc.read.return_value = body
    desc, parsed = tn._read_telegram_error(exc)
    assert "parse entities" in desc
    assert parsed["error_code"] == 400


def test_read_telegram_error_survives_non_json_body():
    exc = MagicMock()
    exc.read.return_value = b"<html>gateway</html>"
    desc, parsed = tn._read_telegram_error(exc)
    assert desc  # non-empty
    assert parsed is None


# ── _post_chunk + send() fallback ───────────────────────────────

def _make_success_ctx():
    """Fake urlopen context that returns an ok Telegram response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps({"ok": True}).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def _make_http_error(code, body):
    """Fake HTTPError with a body that .read() will return."""
    err = urllib.error.HTTPError(
        url="https://api.telegram.org/bot/sendMessage",
        code=code, msg="Bad Request",
        hdrs=None, fp=io.BytesIO(body.encode() if isinstance(body, str) else body),
    )
    return err


def test_send_ok_html_first_try():
    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}), \
         patch("india.telegram_notify.urllib.request.urlopen", return_value=_make_success_ctx()):
        r = tn.send("<b>Hello</b>")
    assert r is True


def test_send_html_400_falls_back_to_plain_text():
    """The whole point of the fix: HTTP 400 (parse error) must trigger a plain-text retry that delivers."""
    call_count = {"n": 0}

    def fake_urlopen(url, data=None, timeout=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: raise HTTP 400 with the classic parse-entities body
            raise _make_http_error(400, json.dumps({
                "ok": False, "error_code": 400,
                "description": "Bad Request: can't parse entities: Character '<' can't be used here",
            }))
        # Second call (plain-text retry): success
        return _make_success_ctx()

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}), \
         patch("india.telegram_notify.urllib.request.urlopen", side_effect=fake_urlopen):
        r = tn.send("<b>Broken<b> HTML with & and <>")
    assert call_count["n"] == 2, f"expected 2 calls (HTML fail + plain retry), got {call_count['n']}"
    assert r is True, "plain-text fallback should deliver, so send() returns True"


def test_send_non_parse_400_does_not_retry_infinitely():
    """A 400 that ISN'T a parse error (e.g. empty text) should still surface via return False, no infinite loop."""
    call_count = {"n": 0}

    def fake_urlopen(url, data=None, timeout=None):
        call_count["n"] += 1
        raise _make_http_error(400, json.dumps({
            "ok": False, "error_code": 400,
            "description": "Bad Request: text is empty",
        }))

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}), \
         patch("india.telegram_notify.urllib.request.urlopen", side_effect=fake_urlopen):
        r = tn.send("<b>x</b>")
    # HTML attempt + plain-text fallback because is_parse_err triggers on "HTTP 400"
    # → both should fail; send() returns False without recursing.
    assert call_count["n"] <= 2, f"must not spin: got {call_count['n']} calls"
    assert r is False


def test_send_403_forbidden_returns_false_without_retry():
    """403 (bot blocked) should NOT trigger the plain-text fallback — that only helps parse errors."""
    call_count = {"n": 0}

    def fake_urlopen(url, data=None, timeout=None):
        call_count["n"] += 1
        raise _make_http_error(403, json.dumps({
            "ok": False, "error_code": 403,
            "description": "Forbidden: bot was blocked by the user",
        }))

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}), \
         patch("india.telegram_notify.urllib.request.urlopen", side_effect=fake_urlopen):
        r = tn.send("<b>x</b>")
    # HTML attempt only (403 is not a parse error, so no fallback)
    assert call_count["n"] == 1, f"403 should not trigger plain-text retry: got {call_count['n']} calls"
    assert r is False


def test_send_error_body_surfaced_in_output(capsys=None):
    """The actual Telegram description ('can't parse entities: Character <') must reach stdout for the workflow log."""
    def fake_urlopen(url, data=None, timeout=None):
        raise _make_http_error(400, json.dumps({
            "ok": False, "error_code": 400,
            "description": "Bad Request: can't parse entities: Character '<' can't be used here",
        }))

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}), \
         patch("india.telegram_notify.urllib.request.urlopen", side_effect=fake_urlopen):
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tn.send("<b>x</b>")
    out = buf.getvalue()
    assert "parse entities" in out, f"actual Telegram error must surface, got: {out}"


TESTS = [
    ("_strip_html removes <b>/<i>", test_strip_html_removes_bold_italic),
    ("_strip_html preserves &, <, > for plain text", test_strip_html_preserves_ampersand_lt_gt),
    ("_strip_html removes anchor tags", test_strip_html_removes_anchor_tags),
    ("_read_telegram_error extracts description", test_read_telegram_error_extracts_description),
    ("_read_telegram_error survives non-JSON body", test_read_telegram_error_survives_non_json_body),
    ("send() OK path: HTML succeeds first try", test_send_ok_html_first_try),
    ("send() falls back to plain-text on HTML 400 parse error", test_send_html_400_falls_back_to_plain_text),
    ("send() non-parse 400 does not spin", test_send_non_parse_400_does_not_retry_infinitely),
    ("send() 403 bot-blocked skips fallback", test_send_403_forbidden_returns_false_without_retry),
    ("send() surfaces actual Telegram error description", test_send_error_body_surfaced_in_output),
]


def main():
    print("=" * 70)
    print("  Telegram HTTP 400 fix · Regression Tests")
    print("=" * 70)
    for label, fn in TESTS:
        _run(label, fn)
    total = _passed + _failed
    print()
    print(f"  {_passed} passed, {_failed} failed of {total}")
    return 0 if _failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
