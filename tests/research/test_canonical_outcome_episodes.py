from openpyxl import Workbook

from backend.research.canonical_outcome_dataset import _load_exit_events_index


def test_exit_index_preserves_reentry_episodes_and_first_exit(tmp_path):
    path = tmp_path / "reports/telegram/aegis_history.xlsx"
    path.parent.mkdir(parents=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "AEGIS Daily"
    ws.append(["Country", "Run_Type", "Ticker", "Status", "Recommended", "Date"])
    ws.append(["USA", "R2", "COMP", "EXIT", "2026-08-01", "2026-08-14"])
    ws.append(["USA", "R2", "COMP", "EXIT", "2026-08-01", "2026-08-16"])
    ws.append(["USA", "R2", "COMP", "EXIT", "2026-09-02", "2026-09-18"])
    ws.append(["USA", "R2", "COMP", "EXIT", "2026-11-02", "2026-10-18"])
    wb.save(path)

    exits = _load_exit_events_index(tmp_path)
    assert len(exits) == 2
    assert exits["usa", "R2", "COMP", "2026-08-01"]["exit_date"] == "2026-08-14"
    assert exits["usa", "R2", "COMP", "2026-09-02"]["exit_date"] == "2026-09-18"
