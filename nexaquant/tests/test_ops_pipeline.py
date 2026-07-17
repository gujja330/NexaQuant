"""OPS001-A tests · 30 scenarios covering notification, pipeline, service,
metrics, status, retry, and governance invariants.

Run: python nexaquant/tests/test_ops_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexaquant.ops.events import Event, Severity, StageEvent
from nexaquant.ops.retry import RetryPolicy, RetryOutcome
from nexaquant.ops.notify.base import Notification, NotificationChannel
from nexaquant.ops.notify.file import FileChannel
from nexaquant.ops.notify.manager import NotificationManager, DeliveryResult
from nexaquant.ops.notify.telegram import TelegramChannel
from nexaquant.ops.metrics import MetricsLedger
from nexaquant.ops.status import StatusSnapshot, StatusWriter
from nexaquant.ops.config import PipelineConfig, StageDefinition, load_pipeline
from nexaquant.ops.pipeline import Pipeline, StageResult, PipelineResult


# ------------------ helpers ------------------


class _RecordingChannel(NotificationChannel):
    """Test double: records every notification, always succeeds."""
    def __init__(self, name: str = "recording",
                 min_severity: Severity = Severity.INFO,
                 fail_next: bool = False):
        self._name = name
        self._min_severity = min_severity
        self.received: list[Notification] = []
        self.fail_next = fail_next

    @property
    def name(self) -> str: return self._name
    @property
    def min_severity(self) -> Severity: return self._min_severity

    def send(self, notification: Notification) -> bool:
        if self.fail_next:
            self.fail_next = False
            return False
        self.received.append(notification)
        return True


def _fake_runner_success(stage, timeout_s):
    return 0, "ok\nready\n", ""


def _fake_runner_fail(exit_code=1):
    def _r(stage, timeout_s):
        return exit_code, "", f"fake error exit {exit_code}\n"
    return _r


def _flaky_runner(fails_first_n: int):
    counter = {"n": 0}
    def _r(stage, timeout_s):
        counter["n"] += 1
        if counter["n"] <= fails_first_n:
            return 1, "", "flaky failure\n"
        return 0, "recovered\n", ""
    return _r


def _make_stage(name: str, retries: int = 0, backoff=(), timeout=60.0,
                depends: list[str] | None = None,
                continue_on_failure: bool = False) -> StageDefinition:
    return StageDefinition(
        name=name, command=[sys.executable, "-c", "print('unused-in-tests')"],
        retry=RetryPolicy(max_attempts=retries + 1, backoff_s=tuple(backoff),
                          timeout_per_attempt_s=timeout),
        depends_on=list(depends or []),
        continue_on_failure=continue_on_failure,
    )


# ---------------- events + retry ----------------


def test_1_event_serializes_cleanly():
    ev = Event.new(StageEvent.SUCCESS, stage="s1", pipeline="p1", attempt=2, duration_s=1.5)
    d = ev.as_dict()
    assert d["kind"] == "SUCCESS"
    assert d["stage"] == "s1"
    assert d["pipeline"] == "p1"
    assert d["attempt"] == 2
    print("  TEST  1 PASS: Event serializes cleanly")


def test_2_severity_ordering():
    assert Severity.INFO.value == "INFO"
    assert Severity.WARN.value == "WARN"
    assert Severity.CRITICAL.value == "CRITICAL"
    print("  TEST  2 PASS: Severity enum has expected values")


def test_3_retry_policy_backoff_extends():
    p = RetryPolicy(max_attempts=5, backoff_s=(1.0, 2.0))
    assert p.sleep_before_attempt(1) == 0.0
    assert p.sleep_before_attempt(2) == 1.0
    assert p.sleep_before_attempt(3) == 2.0
    assert p.sleep_before_attempt(4) == 2.0    # extends
    assert p.sleep_before_attempt(5) == 2.0
    print("  TEST  3 PASS: RetryPolicy extends short backoff schedule")


def test_4_retry_policy_validates():
    try:
        RetryPolicy(max_attempts=0)
    except ValueError as e:
        assert "max_attempts" in str(e)
    else:
        raise AssertionError("expected ValueError on max_attempts=0")
    try:
        RetryPolicy(backoff_s=(-1.0,))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on negative backoff")
    print("  TEST  4 PASS: RetryPolicy validates input")


# ---------------- notify ----------------


def test_5_file_channel_writes_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "alerts.jsonl"
        ch = FileChannel(p)
        n = Notification.new(Severity.WARN, "test.src", "hello", "body")
        assert ch.send(n)
        text = p.read_text(encoding="utf-8").strip()
        row = json.loads(text)
        assert row["severity"] == "WARN" and row["title"] == "hello"
    print("  TEST  5 PASS: FileChannel writes JSONL row")


def test_6_file_channel_severity_filter():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "alerts.jsonl"
        ch = FileChannel(p, min_severity=Severity.CRITICAL)
        n_low = Notification.new(Severity.INFO, "src", "low")
        n_high = Notification.new(Severity.CRITICAL, "src", "high")
        assert ch.send(n_low)     # filtered but not a failure
        assert ch.send(n_high)
        rows = [l for l in p.read_text().splitlines() if l.strip()]
        assert len(rows) == 1     # only the CRITICAL made it
    print("  TEST  6 PASS: FileChannel respects min_severity")


def test_7_notification_manager_routes_to_all():
    a = _RecordingChannel("a")
    b = _RecordingChannel("b")
    mgr = NotificationManager([a, b])
    n = Notification.new(Severity.WARN, "src", "title")
    results = mgr.emit(n)
    assert len(results) == 2 and all(r.ok for r in results)
    assert len(a.received) == 1 and len(b.received) == 1
    print("  TEST  7 PASS: NotificationManager fans out to all channels")


def test_8_notification_manager_isolates_channel_failure():
    a = _RecordingChannel("a")
    b = _RecordingChannel("b", fail_next=True)
    c = _RecordingChannel("c")
    mgr = NotificationManager([a, b, c])
    n = Notification.new(Severity.WARN, "src", "title")
    results = mgr.emit(n)
    ok_by_name = {r.channel: r.ok for r in results}
    assert ok_by_name["a"] is True and ok_by_name["b"] is False and ok_by_name["c"] is True
    # a and c still received it despite b failing
    assert len(a.received) == 1 and len(c.received) == 1
    print("  TEST  8 PASS: NotificationManager isolates channel failure")


def test_9_notification_manager_requires_at_least_one_channel():
    try:
        NotificationManager([])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on empty channel list")
    print("  TEST  9 PASS: NotificationManager requires >=1 channel")


def test_10_telegram_channel_unconfigured_returns_false():
    ch = TelegramChannel(token=None, chat_id=None)
    n = Notification.new(Severity.CRITICAL, "src", "critical")
    assert not ch.configured
    assert ch.send(n) is False
    print("  TEST 10 PASS: unconfigured TelegramChannel returns False (no raise)")


def test_11_telegram_channel_severity_filter_default_warn():
    ch = TelegramChannel(token="x", chat_id="1")
    n_info = Notification.new(Severity.INFO, "src", "info")
    # accepts returns False for INFO because min_severity default = WARN
    assert not ch.accepts(Severity.INFO)
    assert ch.accepts(Severity.WARN)
    assert ch.accepts(Severity.CRITICAL)
    print("  TEST 11 PASS: TelegramChannel default min_severity=WARN")


# ---------------- metrics ----------------


def test_12_metrics_ledger_append_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        led.record_stage("p", "s1", success=True, attempts=1, duration_s=0.5)
        led.record_stage("p", "s2", success=False, attempts=3, duration_s=1.2,
                         exit_code=2, exception_type="TimeoutExpired")
        rows = led.rows()
        assert len(rows) == 2
        assert rows[0]["stage"] == "s1" and rows[0]["success"] is True
        assert rows[1]["retry_count"] == 2
    print("  TEST 12 PASS: MetricsLedger append + read")


def test_13_metrics_ledger_pipeline_row():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        led.record_pipeline("p", success=True, duration_s=10.0,
                            stages_ok=3, stages_total=3)
        rows = led.rows()
        assert len(rows) == 1
        assert rows[0]["kind"] == "pipeline" and rows[0]["success"] is True
    print("  TEST 13 PASS: MetricsLedger pipeline row")


def test_14_metrics_ledger_recent():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        for i in range(20):
            led.record_stage("p", f"s{i}", success=True, attempts=1, duration_s=0.1)
        r = led.recent(5)
        assert len(r) == 5
        assert r[-1]["stage"] == "s19"
    print("  TEST 14 PASS: MetricsLedger.recent slices tail")


# ---------------- status ----------------


def test_15_status_writer_atomic():
    with tempfile.TemporaryDirectory() as tmp:
        w = StatusWriter(Path(tmp) / "ops_status.json", ROOT)
        snap = StatusSnapshot(pipeline_name="p", last_pipeline_success=True,
                              stages_ok=3, stages_total=3, ops_version="test")
        p = w.write(snap)
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["pipeline_name"] == "p"
        assert d["schema_version"] == 1
        assert "written_at_utc" in d and "git_sha" in d and "ops_uptime_s" in d
    print("  TEST 15 PASS: StatusWriter writes atomic JSON with schema v1")


def test_16_status_writer_survives_missing_reads():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "does_not_exist.json"
        w = StatusWriter(p, ROOT)
        assert w.read() == {}
    print("  TEST 16 PASS: StatusWriter.read() returns {} for missing file")


# ---------------- pipeline ----------------


def test_17_pipeline_single_stage_success():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        mgr = NotificationManager([rec])
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1")])
        pipeline = Pipeline(cfg, mgr, led, runner=_fake_runner_success,
                             sleeper=lambda _t: None)
        r = pipeline.run()
        assert r.success is True and r.stages_ok == 1
        assert r.stages[0].attempts == 1
    print("  TEST 17 PASS: single-stage pipeline success")


def test_18_pipeline_retries_then_succeeds():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1", retries=3, backoff=(0.0, 0.0))])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_flaky_runner(fails_first_n=2),
                             sleeper=lambda _t: None)
        r = pipeline.run()
        assert r.success is True
        assert r.stages[0].attempts == 3
    print("  TEST 18 PASS: pipeline retries and eventually succeeds")


def test_19_pipeline_exhausts_retries():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1", retries=2, backoff=(0.0,))])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_fake_runner_fail(exit_code=3),
                             sleeper=lambda _t: None)
        r = pipeline.run()
        assert r.success is False
        assert r.stages[0].attempts == 3
        assert r.stages[0].exit_code == 3
    print("  TEST 19 PASS: pipeline exhausts retries and reports failure")


def test_20_pipeline_short_circuits_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1"), _make_stage("s2"), _make_stage("s3")])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_fake_runner_fail(),
                             sleeper=lambda _t: None)
        r = pipeline.run()
        # s1 fails → s2 and s3 skipped
        assert r.stages[0].success is False
        assert r.stages[1].skipped is True and r.stages[2].skipped is True
    print("  TEST 20 PASS: pipeline short-circuits on stage failure")


def test_21_pipeline_continue_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        cfg = PipelineConfig(name="p", description="", stages=[
            _make_stage("s1", continue_on_failure=True),
            _make_stage("s2"),
        ])
        outcomes = {"s1_done": False}
        def _mixed_runner(stage, timeout_s):
            if stage.name == "s1":
                outcomes["s1_done"] = True
                return 5, "", "expected non-fatal fail\n"
            return 0, "ok\n", ""
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_mixed_runner, sleeper=lambda _t: None)
        r = pipeline.run()
        assert outcomes["s1_done"]
        assert r.stages[0].success is False
        assert r.stages[1].success is True
    print("  TEST 21 PASS: continue_on_failure lets downstream stages run")


def test_22_pipeline_emits_lifecycle_events():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel(min_severity=Severity.INFO)
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1")])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_fake_runner_success, sleeper=lambda _t: None)
        pipeline.run()
        kinds = [n.context.get("kind") for n in rec.received]
        # At minimum: STARTED, RUNNING, SUCCESS, COMPLETE + terminal summary
        assert "STARTED" in kinds and "RUNNING" in kinds
        assert "SUCCESS" in kinds and "COMPLETE" in kinds
    print(f"  TEST 22 PASS: pipeline emits STARTED/RUNNING/SUCCESS/COMPLETE events")


def test_23_pipeline_depends_on_gating():
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        cfg = PipelineConfig(name="p", description="", stages=[
            _make_stage("s1"),
            _make_stage("s2", depends=["s1"]),
        ])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_fake_runner_fail(),
                             sleeper=lambda _t: None)
        r = pipeline.run()
        # s1 fails → s2 is treated as skipped (depends_on unmet OR upstream failure)
        assert r.stages[1].skipped is True
    print("  TEST 23 PASS: depends_on gating causes downstream skip")


def test_24_pipeline_never_raises():
    """Even a runner that raises must not blow up the pipeline."""
    with tempfile.TemporaryDirectory() as tmp:
        led = MetricsLedger(Path(tmp) / "metrics.jsonl")
        rec = _RecordingChannel()
        def _raising_runner(stage, timeout_s):
            raise RuntimeError("boom from runner")
        cfg = PipelineConfig(name="p", description="",
                              stages=[_make_stage("s1", retries=0)])
        pipeline = Pipeline(cfg, NotificationManager([rec]), led,
                             runner=_raising_runner, sleeper=lambda _t: None)
        r = pipeline.run()
        assert r.success is False
        assert "boom" in r.stages[0].exception.lower()
    print("  TEST 24 PASS: pipeline catches runner exceptions")


# ---------------- config ----------------


def test_25_load_pipeline_yaml():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "pipe.yaml"
        p.write_text("""
name: test_pipeline
description: unit-test
stages:
  - name: stage1
    command: [echo, hello]
    timeout_s: 30
    retries: 2
    backoff_s: [1, 3, 5]
""", encoding="utf-8")
        cfg = load_pipeline(p)
        assert cfg.name == "test_pipeline"
        assert len(cfg.stages) == 1
        assert cfg.stages[0].retry.max_attempts == 3
        assert cfg.stages[0].retry.backoff_s == (1, 3, 5)
    print("  TEST 25 PASS: load_pipeline parses YAML into structured config")


def test_26_load_pipeline_rejects_duplicate_stage_names():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "pipe.yaml"
        p.write_text("""
name: p
stages:
  - {name: a, command: [true]}
  - {name: a, command: [true]}
""", encoding="utf-8")
        try:
            load_pipeline(p)
        except ValueError as e:
            assert "duplicate" in str(e).lower()
        else:
            raise AssertionError("expected duplicate-stage-name error")
    print("  TEST 26 PASS: load_pipeline rejects duplicate stage names")


def test_27_load_pipeline_rejects_unknown_depends_on():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "pipe.yaml"
        p.write_text("""
name: p
stages:
  - {name: a, command: [true], depends_on: [does_not_exist]}
""", encoding="utf-8")
        try:
            load_pipeline(p)
        except ValueError as e:
            assert "does_not_exist" in str(e)
        else:
            raise AssertionError("expected unknown-depends-on error")
    print("  TEST 27 PASS: load_pipeline rejects unknown depends_on target")


def test_28_shipped_aegis_daily_yaml_loads():
    """The reference pipeline shipped with OPS001-A must be parseable."""
    p = ROOT / "nexaquant" / "ops" / "pipelines" / "aegis_daily.yaml"
    assert p.exists()
    cfg = load_pipeline(p)
    assert cfg.name == "aegis_daily"
    assert len(cfg.stages) >= 5
    # Every stage's command must include python
    for s in cfg.stages:
        assert s.command[0] in ("python", "python3", sys.executable), s.command
    print(f"  TEST 28 PASS: shipped aegis_daily.yaml loads ({len(cfg.stages)} stages)")


# ---------------- governance invariants ----------------


def test_29_no_sealed_file_modifications():
    """OPS001-A does NOT touch any of the 5 MON001-sealed baseline files or
    any MON001 sealed core file."""
    import subprocess
    r = subprocess.run(["git", "diff", "HEAD", "--name-only"],
                       cwd=str(ROOT), capture_output=True, text=True)
    changed = set(l.strip().replace("\\", "/") for l in r.stdout.splitlines() if l.strip())
    forbidden = {
        "india/recommendation_registry.py",
        "india/recommendation_generator.py",
        "india/confidence_engine.py",
        "india/arjuna_v2.py",
        "india/data_nse.py",
        "india/monitoring/MON001_Forward_Validation/preregistration.md",
        "india/monitoring/MON001_Forward_Validation/mon001.yaml",
        "india/monitoring/MON001_Forward_Validation/monitor.py",
        "india/monitoring/MON001_Forward_Validation/forward_ledger.py",
        "india/monitoring/MON001_Forward_Validation/fingerprint.py",
        "india/monitoring/MON001_Forward_Validation/baseline_envelope.py",
        "india/monitoring/MON001_Forward_Validation/broker_layer.py",
        # 2026-07-17 OPS001-I: india/telegram_notify.py explicitly REMOVED from
        # this forbidden set. It is NOT in the MON001 fingerprint. The redesign
        # authorised by the operator (docs/OPS001I_IMPLEMENTATION.md) modified
        # its presentation layer. Presentation code is not sealed.
    }
    touched = forbidden & changed
    assert not touched, f"OPS001-A modified sealed files: {sorted(touched)}"
    print("  TEST 29 PASS: no sealed file modification in current diff")


def test_30_production_constants_still_unchanged():
    reg = (ROOT / "india/recommendation_registry.py").read_text(encoding="utf-8")
    gen = (ROOT / "india/recommendation_generator.py").read_text(encoding="utf-8")
    manifest = (ROOT / "india/ai_lab/trial_manifest.md").read_text(
        encoding="utf-8", errors="ignore")
    assert "HOLD = 63" in reg
    assert "rebal=63" in gen
    assert "cumulative_strategy_search: 38" in manifest
    print("  TEST 30 PASS: HOLD=63, rebal=63, cumulative_strategy_search=38 unchanged")


def test_31_mon001_fingerprint_still_matches_seal():
    import yaml as _yaml
    with (ROOT / "india/monitoring/MON001_Forward_Validation/mon001.yaml").open() as f:
        cfg = _yaml.safe_load(f)
    sealed = json.loads(
        (ROOT / "india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json")
        .read_text(encoding="utf-8"))
    from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
    current = compute_fingerprint(ROOT, cfg["baseline_files"], cfg["baseline_constants"])
    assert current["hash"] == sealed["hash"]
    assert current.get("algorithm_version") == 2
    print(f"  TEST 31 PASS: MON001 fingerprint v{current['algorithm_version']} matches seal")


TESTS = [
    test_1_event_serializes_cleanly,
    test_2_severity_ordering,
    test_3_retry_policy_backoff_extends,
    test_4_retry_policy_validates,
    test_5_file_channel_writes_jsonl,
    test_6_file_channel_severity_filter,
    test_7_notification_manager_routes_to_all,
    test_8_notification_manager_isolates_channel_failure,
    test_9_notification_manager_requires_at_least_one_channel,
    test_10_telegram_channel_unconfigured_returns_false,
    test_11_telegram_channel_severity_filter_default_warn,
    test_12_metrics_ledger_append_and_read,
    test_13_metrics_ledger_pipeline_row,
    test_14_metrics_ledger_recent,
    test_15_status_writer_atomic,
    test_16_status_writer_survives_missing_reads,
    test_17_pipeline_single_stage_success,
    test_18_pipeline_retries_then_succeeds,
    test_19_pipeline_exhausts_retries,
    test_20_pipeline_short_circuits_on_failure,
    test_21_pipeline_continue_on_failure,
    test_22_pipeline_emits_lifecycle_events,
    test_23_pipeline_depends_on_gating,
    test_24_pipeline_never_raises,
    test_25_load_pipeline_yaml,
    test_26_load_pipeline_rejects_duplicate_stage_names,
    test_27_load_pipeline_rejects_unknown_depends_on,
    test_28_shipped_aegis_daily_yaml_loads,
    test_29_no_sealed_file_modifications,
    test_30_production_constants_still_unchanged,
    test_31_mon001_fingerprint_still_matches_seal,
]


def main():
    print("=" * 70)
    print("  OPS001-A · PIPELINE / NOTIFY / METRICS / STATUS — 31 tests")
    print("=" * 70)
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__} FAIL: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed of {len(TESTS)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
