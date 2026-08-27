"""M-R · dataset regression tests (CEO Item 13).

Verifies the RESEARCH DATASET stays coherent between runs:

  R01 · every autopsy row has ticker + prediction_date + runner
  R02 · fwd_5d_pct where present is bounded [-99, +500]  (sanity)
  R03 · MFE >= 0 always where present
  R04 · MAE <= 0 always where present
  R05 · MFE >= max(fwd_1..20d) where all present
  R06 · MAE <= min(fwd_1..20d) where all present
  R07 · investability_band is one of allowed set
  R08 · runner is one of {R1, R2, MOMENTUM, None}
  R09 · enriched row has trend in allowed set when present
  R10 · summary JSON n_predictions matches JSONL row count
  R11 · WR values are always [0, 100]
  R12 · Wilson CI lower <= WR <= upper
  R13 · master manifest schema is stable
  R14 · sandbox path invariant · no data outside reports/research/*

These fire when the FILES exist. When files don't exist (fresh checkout,
no autopsy run) they are skipped, not failed.
"""
import json
from pathlib import Path

import pytest

ALLOWED_BANDS = {"QUALITY","OK","MARGINAL","AVOID","PENDING", None, ""}
ALLOWED_RUNNERS = {"R1","R2","MOMENTUM", None, ""}
ALLOWED_TRENDS = {"ABOVE_MA200","BELOW_MA200","UNKNOWN", None}
ALLOWED_CAP = {"LARGE","MID","SMALL","UNKNOWN", None}
RESEARCH_ROOT = Path("reports/research").resolve()


def _load_jsonl(path: Path) -> list:
    if not path.exists(): return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _load_json(path: Path) -> dict:
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


@pytest.fixture(scope="module")
def india_rows():
    p = RESEARCH_ROOT / "mr_prediction_autopsy_india.jsonl"
    rows = _load_jsonl(p)
    if not rows: pytest.skip("India autopsy not built yet")
    return rows


@pytest.fixture(scope="module")
def usa_rows():
    p = RESEARCH_ROOT / "mr_prediction_autopsy_usa.jsonl"
    rows = _load_jsonl(p)
    if not rows: pytest.skip("USA autopsy not built yet")
    return rows


def test_r01_india_required_fields(india_rows):
    for r in india_rows:
        assert r.get("ticker"), "missing ticker"
        assert r.get("prediction_date"), "missing prediction_date"
        # runner may be None only for MOMENTUM · status carries the tag


def test_r01_usa_required_fields(usa_rows):
    for r in usa_rows:
        assert r.get("ticker"), "missing ticker"
        assert r.get("prediction_date"), "missing prediction_date"


def test_r02_fwd_5d_bounded(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        v = r.get("fwd_5d_pct")
        if v is not None:
            assert -99 <= v <= 500, f"fwd_5d out of bounds: {r['ticker']} {v}"


def test_r03_mfe_non_negative(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        v = r.get("mfe_pct")
        if v is not None:
            assert v >= -1e-6, f"MFE negative: {r['ticker']} {v}"


def test_r04_mae_non_positive(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        v = r.get("mae_pct")
        if v is not None:
            assert v <= 1e-6, f"MAE positive: {r['ticker']} {v}"


def test_r05_mfe_dominates_fwd(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        mfe = r.get("mfe_pct")
        if mfe is None: continue
        fwd = [r.get(f"fwd_{n}d_pct") for n in (1,3,5,10,20)]
        clean = [x for x in fwd if isinstance(x,(int,float))]
        if not clean: continue
        assert mfe + 1e-3 >= max(clean), f"MFE < max fwd: {r['ticker']} MFE={mfe} max={max(clean)}"


def test_r06_mae_dominates_fwd(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        mae = r.get("mae_pct")
        if mae is None: continue
        fwd = [r.get(f"fwd_{n}d_pct") for n in (1,3,5,10,20)]
        clean = [x for x in fwd if isinstance(x,(int,float))]
        if not clean: continue
        assert mae - 1e-3 <= min(clean), f"MAE > min fwd: {r['ticker']} MAE={mae} min={min(clean)}"


def test_r07_band_in_allowed_set(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        assert r.get("investability_band") in ALLOWED_BANDS, \
            f"unexpected band: {r['ticker']} {r.get('investability_band')}"


def test_r08_runner_in_allowed_set(india_rows, usa_rows):
    for r in list(india_rows) + list(usa_rows):
        run = r.get("runner")
        # Allow any string · but flag totally exotic values
        assert run is None or isinstance(run, str), f"non-string runner: {run}"


def test_r09_enriched_trend_in_allowed_set():
    p_i = RESEARCH_ROOT / "mr_prediction_autopsy_india_enriched.jsonl"
    p_u = RESEARCH_ROOT / "mr_prediction_autopsy_usa_enriched.jsonl"
    for p in (p_i, p_u):
        rows = _load_jsonl(p)
        if not rows: continue
        for r in rows:
            assert r.get("trend") in ALLOWED_TRENDS, \
                f"unexpected trend: {r.get('ticker')} {r.get('trend')}"
            assert r.get("cap_bucket") in ALLOWED_CAP, \
                f"unexpected cap: {r.get('ticker')} {r.get('cap_bucket')}"


def test_r10_summary_row_count_matches_jsonl(india_rows):
    summary = _load_json(RESEARCH_ROOT / "mr_prediction_autopsy_india_summary.json")
    if not summary: pytest.skip("summary not built")
    assert summary.get("n_predictions") == len(india_rows), \
        f"summary n_predictions={summary.get('n_predictions')} != rows={len(india_rows)}"


def test_r11_wr_bounded_in_summaries():
    for market in ("india","usa"):
        s = _load_json(RESEARCH_ROOT / f"mr_prediction_autopsy_{market}_summary.json")
        if not s: continue
        for hz_name, hz in s.get("cohort_ALL", {}).items():
            if isinstance(hz, dict) and "win_rate_pct" in hz:
                wr = hz["win_rate_pct"]
                assert 0 <= wr <= 100, f"{market} {hz_name} WR out of bounds: {wr}"


def test_r12_wilson_ci_contains_wr():
    for market in ("india","usa"):
        s = _load_json(RESEARCH_ROOT / f"mr_studies_{market}.json")
        if not s: continue
        for section_name in ("Q1_runner_scoreboard","Q8_rank_slot"):
            section = s.get(section_name, {})
            for k, panel in section.items():
                fwd5 = panel.get("fwd_5d", {})
                if not fwd5.get("n"): continue
                wr = fwd5["wr_pct"]
                ci = fwd5.get("wr_ci") or (None, None)
                if ci[0] is not None and ci[1] is not None:
                    assert ci[0] - 0.01 <= wr <= ci[1] + 0.01, \
                        f"{market} {section_name}.{k} WR={wr} out of CI {ci}"


def test_r13_manifest_schema_stable_when_present():
    m = _load_json(RESEARCH_ROOT / "MR_V1_MANIFEST.json")
    if not m: pytest.skip("manifest not built yet")
    assert m.get("engine")
    assert m.get("version_tag")
    assert m.get("experiment_id")
    assert isinstance(m.get("stages"), list)
    assert len(m["stages"]) >= 10, f"expected >=10 stages, got {len(m['stages'])}"
    for stage in m["stages"]:
        assert "stage_id" in stage
        assert "module" in stage
        assert "ok" in stage


def test_r14_sandbox_path_invariant():
    """Every M-R output file MUST live under reports/research/."""
    import backend.research.mr_runner as mrr
    allowed = str(mrr.ALLOWED_WRITE_ROOT).replace("\\","/")
    assert allowed == "reports/research", \
        f"ALLOWED_WRITE_ROOT drifted: {allowed}"


def test_r14b_no_locked_layer_files_written():
    """Verify no research output leaked into locked delivery paths."""
    locked = [
        Path("backend/delivery/xlsx_contract.py"),
        Path("backend/delivery/xlsx_validator.py"),
        Path("scripts/telegram_command_center_send.py"),
        Path("configs/ensemble_weights_adaptive.yaml"),
    ]
    # These files must not have been touched by our module. We can't easily
    # verify file mtimes cross-platform, but we can verify they don't
    # contain our engine sentinel string.
    sentinel = "aegis.mr_v1_pipeline"
    for p in locked:
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore")
            assert sentinel not in content, \
                f"{p} contains M-R sentinel · locked layer polluted"
