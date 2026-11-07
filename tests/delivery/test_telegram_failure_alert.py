"""The step said "sent". Nothing was sent. CEO 2026-11-07.

WHAT WENT WRONG
---------------
India failed for ~5 days and USA repeatedly. The operator received no
Telegram alert for any of them - and the alert step reported `success`
every time. Run 42196285388, 42186343714 and 42178889366 all show:

    27  India CI failure Telegram alert    success

The step body was:

    curl -sS -X POST ".../sendMessage" -d ... || true
    echo "[india_ci_alert] sent"

`|| true` swallowed any failure, and the step then printed "sent"
UNCONDITIONALLY, having never read Telegram's response. `continue-on-
error: true` guaranteed the step went green regardless. A 403, a wrong
chat id, a 429, a 5xx - all indistinguishable from delivery.

Same defect class as the freshness gate that certified `age 0` over
day-old bars: a check that passes without opening the thing it claims
to have checked.

A second, latent path: India's alert condition was gated on
`steps.guard.outputs.run == 'true'`, so a failure on a run the
once-per-IST-day guard had short-circuited would have alerted nobody.

WHAT IS ASSERTED HERE
---------------------
That "delivered" now means delivered: HTTP 200 AND body `ok: true` AND
a message_id. That transient faults retry within a bound and
configuration faults do not retry at all. That the token never reaches
a log line. That the receipt never claims an attachment. And that the
alert fires after an upstream failure but NOT on a clean run.

This does not make a failed pipeline pass. Reporting failure reliably
is not fixing it.
"""
from __future__ import annotations

import io
import json
import socket
import urllib.error
from pathlib import Path

import pytest
import yaml

import scripts.telegram_failure_alert as FA

_ROOT = Path(__file__).resolve().parents[2]
_IND_WF = _ROOT / ".github" / "workflows" / "aegis-daily.yml"
_USA_WF = _ROOT / ".github" / "workflows" / "aegis-usa.yml"

TOKEN = "123456:FAKE-TOKEN-NEVER-REAL"
CHAT = "-1001234567890"


class _Resp:
    def __init__(self, status, body):
        self.status = status
        self._b = body.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_body(mid=4242):
    return json.dumps({"ok": True, "result": {"message_id": mid}})


def _http_error(code, body='{"ok":false,"description":"nope"}'):
    return urllib.error.HTTPError(
        "https://api.telegram.org/", code, "err", {},
        io.BytesIO(body.encode("utf-8")))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Bounded retries must be provable without waiting for them."""
    monkeypatch.setattr(FA.time, "sleep", lambda *_: None)


# ─────────────────────────────────────────────────────────────
# delivered means delivered
# ─────────────────────────────────────────────────────────────

class TestVerifiedDelivery:

    def test_200_with_ok_and_message_id_is_DELIVERED(self, monkeypatch):
        monkeypatch.setattr(FA.urllib.request, "urlopen",
                            lambda *a, **k: _Resp(200, _ok_body(99)))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_DELIVERED
        assert r["telegram_ok"] is True
        assert r["message_id"] == 99
        assert r["http_status"] == 200
        assert r["delivered_at_utc"]
        assert r["attempts"] == 1

    def test_200_with_ok_false_is_NOT_delivered(self, monkeypatch):
        """The case the old curl path could not see at all."""
        monkeypatch.setattr(
            FA.urllib.request, "urlopen",
            lambda *a, **k: _Resp(200, json.dumps(
                {"ok": False, "description": "chat not found"})))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] != FA.OUTCOME_DELIVERED
        assert r["telegram_ok"] is False

    def test_200_without_message_id_is_NOT_delivered(self, monkeypatch):
        monkeypatch.setattr(FA.urllib.request, "urlopen",
                            lambda *a, **k: _Resp(200,
                                                  json.dumps({"ok": True})))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] != FA.OUTCOME_DELIVERED
        assert r["message_id"] is None

    def test_unparseable_body_is_NOT_delivered(self, monkeypatch):
        monkeypatch.setattr(FA.urllib.request, "urlopen",
                            lambda *a, **k: _Resp(200, "<html>nope"))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] != FA.OUTCOME_DELIVERED


# ─────────────────────────────────────────────────────────────
# configuration faults · loud, and never retried
# ─────────────────────────────────────────────────────────────

class TestConfigurationFaults:

    @pytest.mark.parametrize("code", sorted(FA.CONFIG_STATUSES))
    def test_config_status_is_reported_and_not_retried(self, monkeypatch,
                                                        code):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise _http_error(code)

        monkeypatch.setattr(FA.urllib.request, "urlopen", boom)
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_CONFIG_ERROR
        assert calls["n"] == 1, (
            "retrying a wrong token or chat id forever is how a "
            "misconfiguration stays invisible")

    def test_missing_token_is_a_config_error(self):
        r = FA.send_verified("", CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_CONFIG_ERROR
        assert "TELEGRAM_BOT_TOKEN" in r["error"]
        assert r["attempts"] == 0

    def test_missing_chat_id_is_a_config_error(self):
        r = FA.send_verified(TOKEN, "", "hi")
        assert r["outcome"] == FA.OUTCOME_CONFIG_ERROR
        assert "TELEGRAM_CHAT_ID" in r["error"]

    def test_403_the_known_unverifiable_case(self, monkeypatch):
        """A 403 is what the old path hid behind "sent"."""
        monkeypatch.setattr(
            FA.urllib.request, "urlopen",
            lambda *a, **k: (_ for _ in ()).throw(
                _http_error(403, '{"ok":false,"description":"bot blocked"}')))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_CONFIG_ERROR
        assert r["http_status"] == 403


# ─────────────────────────────────────────────────────────────
# transient faults · bounded retry
# ─────────────────────────────────────────────────────────────

class TestTransientFaults:

    @pytest.mark.parametrize("code", [429, 500, 502, 503])
    def test_transient_status_retries_to_the_bound(self, monkeypatch, code):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise _http_error(code)

        monkeypatch.setattr(FA.urllib.request, "urlopen", boom)
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_TRANSIENT_FAILED
        assert calls["n"] == FA.MAX_ATTEMPTS
        assert r["attempts"] == FA.MAX_ATTEMPTS

    @pytest.mark.parametrize("exc", [
        socket.timeout("t"),
        urllib.error.URLError("conn reset"),
        ConnectionResetError("reset"),
    ])
    def test_network_faults_retry_to_the_bound(self, monkeypatch, exc):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise exc

        monkeypatch.setattr(FA.urllib.request, "urlopen", boom)
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_TRANSIENT_FAILED
        assert calls["n"] == FA.MAX_ATTEMPTS

    def test_retry_is_bounded_not_infinite(self):
        assert 1 < FA.MAX_ATTEMPTS <= 6
        assert len(FA.BACKOFF_S) >= 1

    def test_a_transient_fault_that_then_succeeds_is_DELIVERED(self,
                                                                monkeypatch):
        state = {"n": 0}

        def flaky(*a, **k):
            state["n"] += 1
            if state["n"] == 1:
                raise _http_error(503)
            return _Resp(200, _ok_body(7))

        monkeypatch.setattr(FA.urllib.request, "urlopen", flaky)
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert r["outcome"] == FA.OUTCOME_DELIVERED
        assert r["message_id"] == 7
        assert r["attempts"] == 2


# ─────────────────────────────────────────────────────────────
# the token never leaks
# ─────────────────────────────────────────────────────────────

class TestSecretsNeverLeak:

    def test_an_error_body_echoing_the_token_is_redacted(self, monkeypatch):
        leaky = '{"ok":false,"description":"bad bot %s"}' % TOKEN
        monkeypatch.setattr(
            FA.urllib.request, "urlopen",
            lambda *a, **k: (_ for _ in ()).throw(_http_error(401, leaky)))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert TOKEN not in str(r)
        assert "REDACTED" in r["error"]

    def test_network_error_text_is_redacted(self, monkeypatch):
        monkeypatch.setattr(
            FA.urllib.request, "urlopen",
            lambda *a, **k: (_ for _ in ()).throw(
                urllib.error.URLError("failed for %s" % TOKEN)))
        r = FA.send_verified(TOKEN, CHAT, "hi")
        assert TOKEN not in str(r)

    def test_chat_id_is_hashed_not_disclosed(self):
        fp = FA._chat_fingerprint(CHAT)
        assert fp.startswith("sha256:")
        assert CHAT not in fp

    def test_the_script_never_prints_the_raw_token(self):
        src = (_ROOT / "scripts"
               / "telegram_failure_alert.py").read_text(encoding="utf-8")
        import ast
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                dumped = ast.dump(node)
                assert "TELEGRAM_BOT_TOKEN" not in dumped
                assert "'token'" not in dumped


# ─────────────────────────────────────────────────────────────
# receipt · auditable, and never a delivery claim
# ─────────────────────────────────────────────────────────────

class TestAlertReceipt:

    def _rec(self, tmp_path, res):
        ctx = {"gate": "DELIVERY_GATE_BLOCK", "reason": "[A23] ...",
               "stage": "DELIVERY_READY", "asof": "2026-11-07",
               "delivery_state": "DELIVERY_BLOCKED"}
        p = FA.record_alert(tmp_path, "india", res, CHAT, "42", "abc",
                            "DELIVERY BLOCKED", ctx)
        return json.loads(p.read_text(encoding="utf-8").splitlines()[-1])

    def test_a_delivered_alert_is_receipt_verified(self, tmp_path):
        rec = self._rec(tmp_path, {
            "outcome": FA.OUTCOME_DELIVERED, "http_status": 200,
            "telegram_ok": True, "message_id": 55, "attempts": 1,
            "delivered_at_utc": FA._utc(), "error": None})
        assert rec["receipt_verified"] is True
        assert rec["message_id"] == 55
        assert rec["telegram_ok"] is True
        assert rec["delivered_at_utc"]

    def test_an_undelivered_alert_is_NOT_receipt_verified(self, tmp_path):
        rec = self._rec(tmp_path, {
            "outcome": FA.OUTCOME_CONFIG_ERROR, "http_status": 403,
            "telegram_ok": False, "message_id": None, "attempts": 1,
            "error": "blocked"})
        assert rec["receipt_verified"] is False
        assert rec["message_id"] is None

    def test_the_receipt_never_claims_an_attachment(self, tmp_path):
        rec = self._rec(tmp_path, {
            "outcome": FA.OUTCOME_DELIVERED, "http_status": 200,
            "telegram_ok": True, "message_id": 1, "attempts": 1,
            "delivered_at_utc": FA._utc(), "error": None})
        assert rec["attachment"] is None
        assert rec["attachment_sha256"] is None
        assert rec["attachment_bytes"] is None
        assert rec["kind"] == "failure_alert", (
            "this must never be read as an XLSX delivery receipt")

    def test_the_receipt_carries_the_hashed_chat_not_the_chat(self, tmp_path):
        rec = self._rec(tmp_path, {
            "outcome": FA.OUTCOME_DELIVERED, "http_status": 200,
            "telegram_ok": True, "message_id": 1, "attempts": 1,
            "delivered_at_utc": FA._utc(), "error": None})
        assert rec["chat_fingerprint"].startswith("sha256:")
        assert CHAT not in json.dumps(rec)


# ─────────────────────────────────────────────────────────────
# message · factual or explicitly unavailable
# ─────────────────────────────────────────────────────────────

class TestMessageIsFactual:

    def test_unknown_fields_say_unavailable_rather_than_being_invented(self):
        msg = FA.build_message("usa", "", "", "", "FAILED",
                               {"gate": FA.UNAVAILABLE,
                                "reason": FA.UNAVAILABLE,
                                "stage": FA.UNAVAILABLE,
                                "asof": FA.UNAVAILABLE})
        assert msg.count(FA.UNAVAILABLE) >= 4
        assert "Reason: unavailable" in msg

    def test_the_alert_states_the_xlsx_was_not_sent(self):
        msg = FA.build_message("india", "1", "a", "W", "FAILED", {})
        assert "Normal XLSX: NOT SENT" in msg

    def test_required_operator_fields_are_present(self):
        msg = FA.build_message("india", "42", "deadbeefcafe", "AEGIS Daily",
                               "DELIVERY BLOCKED",
                               {"gate": "A23", "reason": "3 lost",
                                "stage": "DELIVERY_READY",
                                "asof": "2026-11-07"})
        for frag in ("AEGIS INDIA", "STATUS: DELIVERY BLOCKED", "Run: 42",
                     "SHA: deadbeefcafe", "As-of: 2026-11-07",
                     "Gate: A23", "Reason: 3 lost",
                     "Workflow: AEGIS Daily", "ACTION: investigate"):
            assert frag in msg, frag

    def test_markets_are_labelled_distinctly(self):
        assert "AEGIS INDIA" in FA.build_message(
            "india", "1", "a", "W", "FAILED", {})
        assert "AEGIS USA" in FA.build_message(
            "usa", "1", "a", "W", "FAILED", {})


# ─────────────────────────────────────────────────────────────
# workflow graph · the notifier must actually run
# ─────────────────────────────────────────────────────────────

class TestWorkflowExecutionGraph:

    @staticmethod
    def _alert(path: Path, job: str) -> dict:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for st in d["jobs"][job]["steps"]:
            if "failure Telegram alert" in str(st.get("name") or ""):
                return st
        raise AssertionError("%s: no alert step" % path.name)

    @pytest.mark.parametrize("wf,job,market", [
        (_IND_WF, "refresh", "india"),
        (_USA_WF, "usa-pipeline", "usa"),
    ])
    def test_the_alert_runs_on_always_not_success(self, wf, job, market):
        st = self._alert(wf, job)
        cond = str(st.get("if") or "")
        assert "always()" in cond, (
            "without always() the implicit success() gate skips the "
            "notifier precisely when it is needed")
        assert "failure()" in cond

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_a_failed_notification_is_visible_not_green(self, wf, job):
        st = self._alert(wf, job)
        assert not st.get("continue-on-error"), (
            "continue-on-error made every failed alert report success · "
            "if the operator could not be told, that must be visible")

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_the_alert_uses_the_verified_notifier_not_raw_curl(self, wf, job):
        st = self._alert(wf, job)
        run = str(st.get("run") or "")
        assert "telegram_failure_alert.py" in run
        assert "curl" not in run, (
            "the raw curl path could not read Telegram's response")
        assert "|| true" not in run, (
            "|| true is what swallowed five days of failures")

    def test_india_alerts_on_failure_even_when_the_daily_guard_is_false(self):
        """The latent second path.

        The condition used to be gated wholly on
        `steps.guard.outputs.run == 'true'`, so a failure on a run the
        once-per-IST-day guard had short-circuited would have alerted
        nobody at all.
        """
        cond = str(self._alert(_IND_WF, "refresh").get("if") or "")
        head = cond.split("||")[0]
        assert "failure()" in cond
        assert "guard.outputs.run" not in head, (
            "failure() must reach the notifier independently of the "
            "once-per-day guard")

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_the_alert_never_attaches_the_workbook(self, wf, job):
        run = str(self._alert(wf, job).get("run") or "")
        for frag in ("sendDocument", ".xlsx", "aegis_history"):
            assert frag not in run, (
                "this is an alert path · the XLSX belongs to the "
                "verified delivery path only")

    @pytest.mark.parametrize("wf,job", [(_IND_WF, "refresh"),
                                        (_USA_WF, "usa-pipeline")])
    def test_secrets_are_passed_by_reference_only(self, wf, job):
        st = self._alert(wf, job)
        env = st.get("env") or {}
        assert "TELEGRAM_BOT_TOKEN" in env and "TELEGRAM_CHAT_ID" in env
        for v in env.values():
            assert "secrets." in str(v)


class TestTheXlsxSuccessPathUsesTheSameContract:
    """One Telegram acceptance contract, not two. CEO 2026-11-07.

    The alert path was fixed to require HTTP 200 AND ok==true AND a
    message_id. The XLSX SUCCESS path still returned True on HTTP 200
    alone - the same hole, one layer over. Telegram answers 200 with
    {"ok": false} for a wrong chat id or a blocked bot, so a
    status-only check reports success for a message nobody received.
    """

    @staticmethod
    def _mod():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tcc_contract", _ROOT / "scripts"
            / "telegram_command_center_send.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_200_with_ok_and_message_id_is_accepted(self):
        m = self._mod()
        ok, mid, why = m._telegram_accepted(
            json.dumps({"ok": True, "result": {"message_id": 7}}))
        assert ok is True and mid == 7 and "message_id=7" in why

    def test_200_with_ok_false_is_refused(self):
        m = self._mod()
        ok, mid, why = m._telegram_accepted(
            json.dumps({"ok": False, "description": "chat not found"}))
        assert ok is False and mid is None
        assert "chat not found" in why

    def test_200_without_message_id_is_refused(self):
        m = self._mod()
        ok, mid, _ = m._telegram_accepted(json.dumps({"ok": True}))
        assert ok is False and mid is None

    def test_a_malformed_response_is_refused(self):
        m = self._mod()
        for body in ("<html>down</html>", "", "null", "[1,2]"):
            ok, mid, _ = m._telegram_accepted(body)
            assert ok is False, body
            assert mid is None

    def test_an_http_error_never_reaches_the_accepted_path(self):
        """5xx/4xx are raised by urlopen, so they cannot return True."""
        src = (_ROOT / "scripts"
               / "telegram_command_center_send.py").read_text(
                   encoding="utf-8")
        i = src.find("def _send_markdown")
        body = src[i: i + 2600]
        assert "_telegram_accepted(body)" in body, (
            "the markdown path must verify, not trust the status")
        assert 'return True, body[:120]' not in body, (
            "HTTP 200 alone must no longer be treated as delivery")

    def test_the_plain_text_fallback_also_verifies(self):
        src = (_ROOT / "scripts"
               / "telegram_command_center_send.py").read_text(
                   encoding="utf-8")
        i = src.find("def _send_markdown")
        body = src[i: i + 2600]
        assert "plain fallback not accepted by" in body, (
            "the markdown-parse fallback had the same hole")
        assert 'return True, "markdown-failed-plain-delivered: " + body'             not in body

    def test_both_paths_share_one_definition(self):
        """Two copies of an acceptance rule is how they diverge."""
        src = (_ROOT / "scripts"
               / "telegram_command_center_send.py").read_text(
                   encoding="utf-8")
        assert src.count("def _telegram_accepted") == 1
        assert src.count("_telegram_accepted(body)") == 2


class TestNormalDeliveryPathUnchanged:
    """The success path keeps its own acceptance criteria."""

    @staticmethod
    def _send(path: Path, job: str, name_frag: str) -> dict:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        for st in d["jobs"][job]["steps"]:
            if name_frag in str(st.get("name") or ""):
                return st
        raise AssertionError("%s: no %s step" % (path.name, name_frag))

    def test_india_send_still_requires_contract_and_delivery_tests(self):
        cond = str(self._send(_IND_WF, "refresh",
                              "Telegram Command Center").get("if") or "")
        assert "steps.run_contract.outcome == 'success'" in cond
        assert "steps.delivery_tests.outcome == 'success'" in cond

    def test_usa_send_still_requires_contract_and_delivery_tests(self):
        cond = str(self._send(_USA_WF, "usa-pipeline",
                              "Telegram Command Center").get("if") or "")
        assert "steps.run_contract_usa.outcome == 'success'" in cond
        assert "steps.delivery_tests_usa.outcome == 'success'" in cond

    def test_a_blocked_delivery_still_blocks(self):
        """The gate steps must remain, unweakened."""
        for wf, job in ((_IND_WF, "refresh"), (_USA_WF, "usa-pipeline")):
            names = [str(s.get("name") or "")
                     for s in yaml.safe_load(
                         wf.read_text(encoding="utf-8"))["jobs"][job]["steps"]]
            assert any("Fail the run if delivery was blocked" in n
                       for n in names), wf.name
            assert any("Delivery status" in n for n in names), wf.name
