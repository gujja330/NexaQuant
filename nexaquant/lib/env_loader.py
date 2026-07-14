"""Single `.env*` file loader.

Consolidates the three near-identical implementations in the audited codebase:
- `india/broker_angelone.py:36-50` (`_load_dotenv`)
- `india/telegram_notify.py:42-64` (`load_env`)
- `india/sheets_sync.py:27-37` (`load_env`)

All three parse `KEY=value` lines, strip surrounding quotes, and set os.environ
only if the key is not already set (existing env wins). This module offers the
same semantics as a single pure function.

I/O: reads files from disk. Never writes. Never modifies caller's environment
outside of the sanctioned `os.environ.setdefault` behaviour.
"""
from __future__ import annotations

import os
from pathlib import Path


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_env_file(path: Path | str) -> dict[str, str]:
    """Parse a `.env`-style file and return the dict of KEY -> value.

    Ignores blank lines and lines starting with `#`. Strips wrapping quotes.
    Raises FileNotFoundError if the path does not exist. Does NOT modify
    `os.environ`.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"env file not found: {p}")
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        out[key] = _strip_wrapping_quotes(value.strip())
    return out


def load_env_files(*paths: Path | str, override: bool = False) -> dict[str, str]:
    """Load one or more `.env*` files and merge them into `os.environ`.

    - If `override` is False (default), existing environment values win.
    - If `override` is True, later loaded values overwrite earlier ones.

    Silently skips paths that do not exist. Returns the DICT that was applied
    (before merge decisions) for logging/audit purposes.

    Order rules:
    - Later paths in the arg list win ties among the loaded files themselves.
    - Existing `os.environ` values ALWAYS win unless `override=True`.
    """
    applied: dict[str, str] = {}
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            continue
        applied.update(parse_env_file(pp))
    for k, v in applied.items():
        if override:
            os.environ[k] = v
        else:
            os.environ.setdefault(k, v)
    return applied
