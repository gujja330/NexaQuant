"""Point-in-time provenance for universe and sector membership.

WHY THIS EXISTS
---------------
`FeatureBuilder._universe()` and `._ticker_sector()` read today's files with
no `asof`. Every historical snapshot therefore silently used present-day
membership: the 228-name India list (authored 2026-06-19) was applied to
snapshots back to 2026-03-02, and USA's 516-name list was applied to dates
when the universe was the Dow 30.

WHAT PROVENANCE IS USED
-----------------------
Git. These membership files are version-controlled, so `git show <rev>:<path>`
returns exactly the list AEGIS was configured with on that date. That is a
real historical record, not a reconstruction.

WHAT THIS IS NOT
----------------
It is NOT exchange index membership. It answers "which names was AEGIS
scoring on date D", which is the correct question for replaying AEGIS's own
decisions. It must never be described as NSE/S&P constituent history.

Before a file's first commit there is no record, so the answer is
PIT_UNAVAILABLE — never a guess, never today's list.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

PIT_UNAVAILABLE = "PIT_UNAVAILABLE"

_UNIVERSE_FILE = {"india": "india/data_nse.py", "usa": "usa/reports/universe.json"}
_SECTOR_FILE = {"india": "india/sectors.py", "usa": "usa/reports/universe.json"}


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args],
                                       text=True, errors="replace",
                                       stderr=subprocess.DEVNULL)
    except Exception:
        return None


@lru_cache(maxsize=256)
def _rev_at(root_s: str, path: str, asof_s: str) -> Optional[str]:
    """Last commit touching `path` on or before `asof` (end of that day)."""
    # Explicit UTC boundary. Git resolves a bare timestamp in LOCAL time; on an
    # IST machine "2026-08-10 23:59:59" is 18:29 UTC, which silently skipped the
    # 2026-08-10 21:39 UTC universe change (918 -> 516).
    out = _git(Path(root_s), "log", "-1", "--format=%H",
               "--before=%sT23:59:59+00:00" % asof_s, "--", path)
    out = (out or "").strip()
    return out or None


@lru_cache(maxsize=256)
def _blob(root_s: str, rev: str, path: str) -> Optional[str]:
    return _git(Path(root_s), "show", "%s:%s" % (rev, path))


def _parse_india_universe(src: str) -> list[str]:
    lines = src.splitlines()
    try:
        i = next(k for k, l in enumerate(lines) if l.startswith("UNIVERSE"))
    except StopIteration:
        return []
    out: list[str] = []
    for l in lines[i:]:
        s = l.strip()
        if s.startswith("]"):
            break
        out.extend(re.findall(r'"([A-Za-z0-9&._-]+\.NS)"', l))
    return out


def _parse_india_sectors(src: str) -> dict[str, str]:
    """india/sectors.py is a FLAT map: {"HDFCBANK": "Financials", ...}."""
    i = src.find("SECTORS")
    if i < 0:
        return {}
    return {k: v for k, v in re.findall(
        r'"([A-Za-z0-9&._-]+)"\s*:\s*"([^"]+)"', src[i:])}


def universe_asof(root: Path, market: str, asof: date):
    """Return (members, provenance). members is PIT_UNAVAILABLE if no record."""
    m = market.lower()
    path = _UNIVERSE_FILE[m]
    rev = _rev_at(str(root), path, asof.isoformat())
    if not rev:
        return PIT_UNAVAILABLE, {"source": path, "rev": None, "asof": asof.isoformat(),
                                 "status": PIT_UNAVAILABLE,
                                 "reason": "no commit to %s on or before %s" % (path, asof)}
    blob = _blob(str(root), rev, path)
    if blob is None:
        return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                 "reason": "blob unreadable"}
    if m == "india":
        members = sorted(_parse_india_universe(blob))
    else:
        try:
            members = sorted({t["symbol"] for t in json.loads(blob).get("tickers", [])
                              if t.get("symbol")})
        except Exception:
            return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                     "reason": "unparseable json"}
    if not members:
        return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                 "reason": "empty membership"}
    cdate = (_git(root, "log", "-1", "--format=%ad", "--date=short", rev) or "").strip()
    return members, {"source": path, "rev": rev[:12], "commit_date": cdate,
                     "asof": asof.isoformat(), "n": len(members), "status": "PIT_OK",
                     "semantics": "AEGIS-configured universe at asof (NOT exchange index membership)"}


def sector_asof(root: Path, market: str, asof: date):
    m = market.lower()
    path = _SECTOR_FILE[m]
    rev = _rev_at(str(root), path, asof.isoformat())
    if not rev:
        return PIT_UNAVAILABLE, {"source": path, "rev": None, "status": PIT_UNAVAILABLE,
                                 "reason": "no commit to %s on or before %s" % (path, asof)}
    blob = _blob(str(root), rev, path)
    if blob is None:
        return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                 "reason": "blob unreadable"}
    if m == "india":
        mapping = _parse_india_sectors(blob)
    else:
        try:
            mapping = {t["symbol"]: t.get("sector", "") for t in
                       json.loads(blob).get("tickers", []) if t.get("symbol")}
        except Exception:
            return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                     "reason": "unparseable json"}
    if not mapping:
        return PIT_UNAVAILABLE, {"source": path, "rev": rev, "status": PIT_UNAVAILABLE,
                                 "reason": "empty sector map"}
    cdate = (_git(root, "log", "-1", "--format=%ad", "--date=short", rev) or "").strip()
    return mapping, {"source": path, "rev": rev[:12], "commit_date": cdate,
                     "asof": asof.isoformat(), "n": len(mapping), "status": "PIT_OK"}
