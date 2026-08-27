"""CEO 2026-08-27 · topology v3 mirror + finding-bucket mapping tests."""
import json
from pathlib import Path

from backend.research.mr_research_topology import _ceo_v3_mirror


def _mk_experiment_json(dst_dir: Path, name: str, status: str,
                        title: str = "test"):
    fp = dst_dir / f"{name}.json"
    fp.write_text(json.dumps({
        "experiment_id":  name,
        "current_status": status,
        "market":         "INDIA",
        "title":          title,
    }), encoding="utf-8")


def test_ceo_v3_mirror_creates_all_four_top_level_dirs(tmp_path):
    root = tmp_path
    # Fake the writable roots
    (root / "reports" / "research" / "experiments").mkdir(parents=True)
    (root / "reports" / "research" / "evidence" / "india").mkdir(parents=True)
    (root / "reports" / "research" / "evidence" / "usa").mkdir(parents=True)
    _mk_experiment_json(root / "reports" / "research" / "experiments",
                        "aegis_mr_experiment_20260827_x", "ACTIVE_SHADOW")
    dst = root / "reports" / "research" / "topology"
    # Pre-seed MR_V1/active/E1 slot so mirror can copy from it
    (dst / "MR_V1" / "active" / "E1_india_r1_filter").mkdir(parents=True)
    (dst / "MR_V1" / "active" / "E2_india_r2_boost").mkdir(parents=True)
    (dst / "MR_V1" / "active" / "E3_stop_loss").mkdir(parents=True)
    (dst / "historical" / "45d").mkdir(parents=True)
    _ceo_v3_mirror(root, dst)
    assert (dst / "evidence" / "india").is_dir()
    assert (dst / "evidence" / "usa").is_dir()
    for b in ("validated","promising","failed","insufficient_evidence"):
        assert (dst / "findings" / b).is_dir(), f"missing findings/{b}"
    for e in ("E1","E2","E3"):
        assert (dst / "experiments" / "MR_V1" / e).is_dir()
    assert (dst / "historical" / "45d_research_archive").is_dir()


def test_ceo_v3_findings_bucket_active_shadow_goes_to_promising(tmp_path):
    root = tmp_path
    exp_dir = root / "reports" / "research" / "experiments"
    exp_dir.mkdir(parents=True)
    _mk_experiment_json(exp_dir, "aegis_mr_experiment_20260827_a",
                        "ACTIVE_SHADOW")
    dst = root / "reports" / "research" / "topology"
    (dst / "MR_V1" / "active").mkdir(parents=True)
    _ceo_v3_mirror(root, dst)
    cards = list((dst / "findings" / "promising").glob("*.card.json"))
    assert len(cards) == 1


def test_ceo_v3_findings_bucket_superseded_goes_to_insufficient(tmp_path):
    root = tmp_path
    exp_dir = root / "reports" / "research" / "experiments"
    exp_dir.mkdir(parents=True)
    _mk_experiment_json(exp_dir, "aegis_mr_experiment_20260827_a",
                        "SUPERSEDED_BY")
    dst = root / "reports" / "research" / "topology"
    (dst / "MR_V1" / "active").mkdir(parents=True)
    _ceo_v3_mirror(root, dst)
    cards = list((dst / "findings" / "insufficient_evidence").glob("*.card.json"))
    assert len(cards) == 1
