"""Canonical repo-root discovery + common data locations.

Eliminates the 129 `sys.path.insert(...)` idioms scattered across the codebase.
Any caller that needs the repo root or a well-known data path should import
from here rather than reinventing `Path(__file__).resolve().parents[N]`.

Reads-only. Never mutates `sys.path`.
"""
from __future__ import annotations

from pathlib import Path


# Anchor: the top of the repo. Discovered by walking up from THIS file's path
# until we find a marker file we can rely on. The marker is `run_daily.bat`
# (always at repo root; not a test/fixture path). Falls back to two levels up.
def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "run_daily.bat").exists() and (candidate / "india").is_dir():
            return candidate
    # Fallback: our own package's parent-of-parent
    return here.parents[2]


REPO_ROOT: Path = _find_repo_root()

# Well-known subtrees. Do NOT read/write from here — this module exposes
# locations only.
INDIA_DIR: Path = REPO_ROOT / "india"
DATA_DIR: Path = REPO_ROOT / "data"
DATA_RAW_INDIA: Path = DATA_DIR / "raw" / "india"
REPORTS_DIR: Path = REPO_ROOT / "reports"
DOCS_DIR: Path = REPO_ROOT / "docs"
LOGS_DIR: Path = REPO_ROOT / "logs"

# AI Lab + MON001 anchors — READ-ONLY consumers only.
AI_LAB_DIR: Path = INDIA_DIR / "ai_lab"
MON001_DIR: Path = INDIA_DIR / "monitoring" / "MON001_Forward_Validation"

# Registry (production evidence DB — do not modify without a preregistered lab)
AEGIS_REGISTRY_CSV: Path = DATA_DIR / "aegis_registry.csv"
AEGIS_LAYER_REGISTRY_CSV: Path = DATA_DIR / "aegis_layer_registry.csv"
AEGIS_RECOMMENDATION_DB_CSV: Path = DATA_DIR / "aegis_recommendation_db.csv"

# Trial manifest — read-only signal of research search burden
TRIAL_MANIFEST: Path = AI_LAB_DIR / "trial_manifest.md"


def repo_relative(path: Path | str) -> Path:
    """Return `path` as a repo-relative Path, or the absolute path if outside repo."""
    p = Path(path).resolve()
    try:
        return p.relative_to(REPO_ROOT)
    except ValueError:
        return p


def ensure_dir(path: Path | str) -> Path:
    """Create the directory if it does not exist. Returns the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_latest_workbook(reports_dir: Path | str | None = None,
                          pattern: str = "AEGIS_*.xlsx") -> Path | None:
    """Return the newest matching workbook under `reports_dir` (default: repo `reports/`).

    Consolidates the identical glob idiom repeated in:
    - `india/aegis_dashboard.py:31-33`
    - `india/recommendation_db.py:32-34`
    - `india/sheets_sync.py:40-42`

    Returns None if no file matches. Sort is by filename (ISO-like naming makes this
    equivalent to chronological order for AEGIS_YYYY-MM-DD.xlsx files). Callers that
    require modification-time ordering should sort themselves.
    """
    root = Path(reports_dir) if reports_dir is not None else REPORTS_DIR
    if not root.exists():
        return None
    files = sorted(root.glob(pattern))
    return files[-1] if files else None
