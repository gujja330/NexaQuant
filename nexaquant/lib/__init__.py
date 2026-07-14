"""Shared utility primitives for the NexaQuant codebase.

Modules:
- `paths`        — canonical repo-root discovery + common data locations
- `env_loader`   — single `.env*` file loader consolidating three duplicates
- `metrics`      — pure Sharpe/MaxDD/annualization helpers with type hints
- `logging_setup` — standardized logger factory
- `timing`       — `@timed` decorator + `time_block` context manager

Every function here is:
- Pure (no I/O beyond what the caller passes in) except where the module name
  explicitly implies I/O (`env_loader`, `paths`)
- Fully type-annotated on public parameters and returns
- Docstring-covered
- Unit-tested in `nexaquant/tests/test_lib.py`

Explicit non-goals:
- Does NOT reimplement any strategy logic
- Does NOT read from `data/aegis_registry.csv` or any lab/monitoring evidence
- Does NOT import from the 5 MON001-sealed production files
"""

from . import paths, env_loader, metrics, logging_setup, timing

__all__ = ["paths", "env_loader", "metrics", "logging_setup", "timing"]
