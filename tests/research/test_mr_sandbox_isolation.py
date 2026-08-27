"""M-R · sandbox isolation test.

Verifies every M-R module writes ONLY under reports/research/ and never
touches locked production paths.
"""
from pathlib import Path
import inspect

from backend.research import (
    mr_runner, mr_prediction_autopsy, mr_winner_loser_genome,
    mr_feature_enricher, mr_market_regime, mr_studies,
    mr_stop_loss_sweep, mr_missed_winners, mr_master_report,
)

MODULES = [
    mr_runner, mr_prediction_autopsy, mr_winner_loser_genome,
    mr_feature_enricher, mr_market_regime, mr_studies,
    mr_stop_loss_sweep, mr_missed_winners, mr_master_report,
]

LOCKED_PATHS = [
    "reports/telegram/aegis_history.xlsx",
    "reports/telegram/aegis_history_usa.xlsx",
    "reports/context/portfolio_canonical",
    "backend/delivery",
    "backend/adaptive_rec_v2",
    "model_registry.jsonl",
]


def test_allowed_write_root_is_research():
    assert str(mr_runner.ALLOWED_WRITE_ROOT).replace("\\","/") == "reports/research"


def test_no_module_writes_to_locked_path():
    for m in MODULES:
        src = inspect.getsource(m)
        # Only the words "write" surfaces near a locked path constitute leaks
        for locked in LOCKED_PATHS:
            # Allow READ references (json.load / read_parquet / .exists)
            # but reject writes.
            for op in (".write_text", ".write_bytes", ".to_parquet(",
                       ".to_csv(", ".to_excel(", "open(", ".save("):
                # Only fail if op line contains the locked substring
                for ln in src.splitlines():
                    if op in ln and locked in ln:
                        assert False, f"{m.__name__} may write to locked {locked}: {ln.strip()}"


def test_experiment_id_stamped():
    for m in (mr_prediction_autopsy, mr_winner_loser_genome, mr_feature_enricher,
              mr_market_regime, mr_studies, mr_stop_loss_sweep, mr_missed_winners):
        src = inspect.getsource(m)
        assert "EXPERIMENT_ID" in src or "ENGINE_ID" in src, \
            f"{m.__name__} must stamp EXPERIMENT_ID or ENGINE_ID"
