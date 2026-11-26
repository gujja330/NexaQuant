"""Failure injection against isolated local publication roots."""
from pathlib import Path
import json
import os
import subprocess
import sys

import pytest

from scripts import aegis_local_state as state


def fixture(tmp_path: Path):
    root = tmp_path / "production"
    (root / "reports/telegram").mkdir(parents=True)
    (root / "reports/decision_india.json").write_text("old")
    (root / "reports/decision_usa.json").write_text("old USA")
    (root / "reports/telegram/aegis_history_india.xlsx").write_bytes(b"previous")
    (root / ".env.telegram").write_text("fixture")
    return root


def test_staged_failure_and_market_isolation(tmp_path):
    root = fixture(tmp_path)
    with state.locked(root) as storage:
        india = state.Attempt(root, storage, "india", "2026-11-24")
        rel = Path("reports/decision_india.json")
        (india.workspace / rel).write_text("invalid")
        assert not (india.workspace / ".env.telegram").exists()
        india.status("failed")
        usa = state.Attempt(root, storage, "usa", "2026-11-24")
        (usa.workspace / rel).write_text("wrong market")
        (usa.workspace / "reports/decision_usa.json").write_text("new USA")
        usa.publish(certified=True)
        assert (root / rel).read_text() == "old"
        assert (root / "reports/decision_usa.json").read_text() == "new USA"


def test_windows_lock_reports_owner_and_reacquires(tmp_path):
    root = fixture(tmp_path)
    code = """
import sys
from pathlib import Path
from scripts.aegis_local_state import locked
try:
    with locked(Path(sys.argv[1]), 'usa'):
        pass
except RuntimeError as error:
    print(error)
    sys.exit(3)
"""
    with state.locked(root, "india") as storage:
        assert storage.parent == root
        child = subprocess.run([sys.executable, "-c", code, str(root)],
                               capture_output=True, text=True, timeout=20)
        assert child.returncode == 3
        assert f'"pid": {os.getpid()}' in child.stdout and '"market": "india"' in child.stdout
        attempt = state.Attempt(root, storage, "india", "2026-11-25")
        assert not (attempt.workspace / storage.name).exists()
    with state.locked(root, "usa"):
        assert (storage / "owner.json").is_file()


def test_publication_exception_rolls_back(tmp_path, monkeypatch):
    root = fixture(tmp_path)
    decision = root / "reports/decision_india.json"
    os.utime(decision, (1700000000, 1700000000))
    original_mtime = decision.stat().st_mtime_ns
    real_copy = state._atomic_copy

    def fail_workbook(source, destination, temporary):
        if source.suffix == ".xlsx":
            raise OSError("injected workbook write failure")
        real_copy(source, destination, temporary)

    with state.locked(root) as storage:
        attempt = state.Attempt(root, storage, "india", "2026-11-24")
        rel = Path("reports/decision_india.json")
        workbook = Path("reports/telegram/aegis_history_india.xlsx")
        (attempt.workspace / rel).write_text("new")
        (attempt.workspace / workbook).write_bytes(b"new workbook")
        monkeypatch.setattr(state, "_atomic_copy", fail_workbook)
        with pytest.raises(OSError, match="injected"):
            attempt.publish(certified=True)
        assert (root / rel).read_text() == "old"
        assert decision.stat().st_mtime_ns == original_mtime
        assert (root / workbook).read_bytes() == b"previous"
        assert json.loads(attempt.journal.read_text())["status"] == "rolled_back"


def test_market_and_research_share_publication_rollback(tmp_path, monkeypatch):
    root = fixture(tmp_path)
    market_output = Path("reports/decision_india.json")
    research_output = Path("reports/research/india/outcome_dataset_summary.json")
    real_copy = state._atomic_copy

    def fail_research(source, destination, temporary):
        if source.name == research_output.name:
            raise OSError("research publish failed")
        real_copy(source, destination, temporary)

    with state.locked(root) as storage:
        india = state.Attempt(root, storage, "india", "2026-11-25")
        research = state.Attempt(root, storage, "research", "2026-11-25")
        (india.workspace / market_output).write_text("new market data")
        staged_research = research.workspace / research_output
        staged_research.parent.mkdir(parents=True)
        staged_research.write_text("new research data")
        monkeypatch.setattr(state, "_atomic_copy", fail_research)
        with pytest.raises(OSError, match="research publish failed"):
            research.publish(certified=True, related=(india,))
        assert (root / market_output).read_text() == "old"
        assert not (root / research_output).exists()
        assert json.loads(research.journal.read_text())["status"] == "rolled_back"


def test_crashed_publisher_recovers_and_releases_lock(tmp_path):
    root = fixture(tmp_path)
    code = """
import os
import sys
from pathlib import Path
from scripts import aegis_local_state as state
root = Path(sys.argv[1])
with state.locked(root) as storage:
    attempt = state.Attempt(root, storage, "india", "2026-11-24")
    (attempt.workspace / "reports/decision_india.json").write_text("new")
    (attempt.workspace / "reports/new_india.json").write_text("new file")
    real_copy = state._atomic_copy
    def first_copy_then_exit(source, dest, temporary):
        real_copy(source, dest, temporary)
        if dest.name == "new_india.json":
            os._exit(17)
    state._atomic_copy = first_copy_then_exit
    attempt.publish(certified=True)
"""
    child = subprocess.run([sys.executable, "-c", code, str(root)], timeout=30)
    assert child.returncode == 17
    assert (root / "reports/decision_india.json").read_text() == "new"
    assert (root / "reports/new_india.json").exists()
    with state.locked(root) as storage:
        state.recover(root, storage)
        state.recover(root, storage)
    assert not (root / "reports/new_india.json").exists()
    assert (root / "reports/decision_india.json").read_text() == "old"


def test_publication_rejects_history_rewrite(tmp_path):
    root = fixture(tmp_path)
    registry = root / state.REGISTRY
    registry.parent.mkdir()
    registry.write_text('{"market":"india","opportunity_id":"first"}\n')
    with state.locked(root) as storage:
        attempt = state.Attempt(root, storage, "india", "2026-11-24")
        (attempt.workspace / state.REGISTRY).write_text(
            '{"market":"india","opportunity_id":"replacement"}\n'
        )
        with pytest.raises(RuntimeError, match="rewrote"):
            attempt.publish(certified=True)
    assert '"first"' in registry.read_text()


def test_runner_timeout_preserves_live_artifact(tmp_path, monkeypatch):
    from scripts import aegis_run_all as runner

    root = fixture(tmp_path)
    monkeypatch.setattr(runner, "_ROOT", root)
    rel = Path("reports/decision_india.json")
    with state.locked(root) as storage:
        attempt = state.Attempt(root, storage, "india", "2026-11-24")
        code = f"from pathlib import Path; Path({rel.as_posix()!r}).write_text('partial'); import time; time.sleep(60)"
        ok, _ = runner._run([sys.executable, "-c", code], cwd=attempt.workspace, timeout=2)
        assert not ok
        assert (attempt.workspace / rel).read_text() == "partial"
        assert (root / rel).read_text() == "old"


def test_publication_detects_concurrent_edit(tmp_path):
    root = fixture(tmp_path)
    rel = Path("reports/decision_india.json")
    with state.locked(root) as storage:
        attempt = state.Attempt(root, storage, "india", "2026-11-24")
        (attempt.workspace / rel).write_text("staged")
        (root / rel).write_text("external")
        with pytest.raises(RuntimeError, match="production changed"):
            attempt.publish(certified=True)
        assert (root / rel).read_text() == "external"


def test_child_output_roots_cannot_escape_staging(tmp_path, monkeypatch):
    from scripts import aegis_run_all as runner

    monkeypatch.setattr(runner, "_ROOT", tmp_path)
    monkeypatch.setenv("AEGIS_OUT_ROOT", str(tmp_path / "live"))
    monkeypatch.setenv("AEGIS_FEATURE_OUT_ROOT", str(tmp_path / "live"))
    monkeypatch.setenv("SEND_FORCE_STALE", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fixture")
    code = (
        "import os; "
        "assert os.environ['AEGIS_OUT_ROOT'] == os.getcwd(); "
        "assert os.environ['AEGIS_FEATURE_OUT_ROOT'] == os.getcwd(); "
        "assert 'TELEGRAM_BOT_TOKEN' not in os.environ; "
        "assert 'SEND_FORCE_STALE' not in os.environ"
    )
    ok, _ = runner._run([sys.executable, "-c", code], cwd=tmp_path)
    assert ok


def test_recovery_rejects_path_traversal(tmp_path):
    root = fixture(tmp_path)
    with state.locked(root) as storage:
        journal = storage / "interrupted" / "publication.json"
        journal.parent.mkdir()
        journal.write_text(json.dumps({"status": "publishing", "files": [
            {"path": "../outside.json", "before": None, "after": "unexpected"},
        ]}))
        with pytest.raises(RuntimeError, match="invalid project-relative path"):
            state.recover(root, storage)


def test_isolated_staging_checks_pending_journal_without_applying_it(tmp_path):
    with state.locked(tmp_path) as storage:
        journal = storage / "interrupted" / "publication.json"
        journal.parent.mkdir()
        text = '{"status":"publishing","files":[]}'
        journal.write_text(text, encoding="utf-8")
        with pytest.raises(RuntimeError, match="Publication recovery is pending"):
            state.require_clean_publication_state(storage)
        assert journal.read_text(encoding="utf-8") == text


def test_usa_research_outputs_are_owned_by_research_publication():
    artifact = Path("reports/research/usa/outcome_dataset.parquet")
    assert state._output(artifact, "research")
    assert not state._output(artifact, "usa")
    assert not state._output(artifact, "india")


def test_registry_preserves_admission_and_requires_documented_exit():
    opened = {"opportunity_id": "IND-R2-A-20261124-example", "market": "india",
              "ticker": "A", "runner": "R2", "created_date": "2026-11-24", "status": "ACTIVE"}
    closed = {**opened, "status": "CLOSED", "closed_date": "2026-11-25", "closed_reason": "STOP_LOSS_HIT"}
    state._validate_registry_events([opened], [closed], "india")
    with pytest.raises(RuntimeError, match="invalid registry dates or reason"):
        state._validate_registry_events([opened], [{**closed, "closed_reason": ""}], "india")
    with pytest.raises(RuntimeError, match="altered the admission identity"):
        state._validate_registry_events([opened], [{**closed, "created_date": "2026-11-23"}], "india")
    with pytest.raises(RuntimeError, match="reopened or reclassified"):
        state._validate_registry_events([closed], [opened], "india")
