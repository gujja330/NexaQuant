from datetime import date
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.aegis_shadow.daily import _artifacts, _missing_sessions, _plan


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("market", ("india", "usa"))
def test_executable_plan_resolves_engines_and_orders_certification(market):
    plan = _plan(ROOT, market, "2026-11-26")
    names = [stage.name for stage in plan]
    for producer, consumer in (
        ("session_checkpoint", "registry"), ("registry", "dynamic_risk"),
        ("dynamic_risk", "dynamic_exits"), ("dynamic_exits", "canonical_lifecycle"),
        ("canonical_lifecycle", "workbook"), ("workbook", "backend_validation"),
        ("backend_validation", "certify"),
    ):
        assert names.index(producer) < names.index(consumer)
    assert "telegram" not in names
    assert "multi_layer_forward_outcomes" in names


def test_missed_sessions_exclude_thanksgiving_weekend_and_latest_session():
    assert _missing_sessions("usa", date(2026, 11, 25), date(2026, 11, 30)) == ["2026-11-27"]
    assert _missing_sessions("india", date(2026, 11, 23), date(2026, 11, 26)) == ["2026-11-25"]


def test_artifact_contract_rejects_parent_paths_and_empty_output(tmp_path):
    artifact = tmp_path / "report_2026-11.json"
    artifact.touch()
    assert not _artifacts(tmp_path, ("report_{month}.json",), "2026-11-26")
    artifact.write_bytes(b"{}")
    assert _artifacts(tmp_path, ("report_{month}.json",), "2026-11-26") == {artifact}
    with pytest.raises(ValueError, match="invalid artifact"):
        _artifacts(tmp_path, ("../protected",), "2026-11-26")


def test_engine_worker_rejects_external_write_and_launch(tmp_path):
    work = tmp_path / "work"
    worker = work / "scripts/aegis_shadow/worker.py"
    worker.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/aegis_shadow/worker.py", worker)
    outside = tmp_path / "protected.txt"
    outside.write_text("unchanged", encoding="utf-8")
    (work / "fixture.py").write_text(
        "from pathlib import Path\n"
        "import subprocess, sys\n"
        "try:\n"
        "    Path(sys.argv[1]).write_text('wrong')\n"
        "except PermissionError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('external write succeeded')\n"
        "try:\n"
        "    subprocess.run([sys.executable, '-c', 'pass'])\n"
        "except PermissionError:\n"
        "    Path('inside.txt').write_text('allowed')\n"
        "else:\n"
        "    raise AssertionError('external launch succeeded')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(worker), "fixture.py", str(outside)],
        cwd=work, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert (work / "inside.txt").read_text(encoding="utf-8") == "allowed"
