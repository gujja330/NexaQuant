"""One canonical mapping from a decision status to a configured tier.

CEO 2026-11-03 · THE DEFECT THIS REPLACES
-----------------------------------------
`scripts/telegram_command_center_send.py` classified rows for sorting with
its own private tier vocabulary:

    closed · exit · new · strong_buy · buy · hold

`configs/decision_colors.yaml` defines three tiers:

    new (1) · active (2) · exit (3)

So four of the six private keys resolved to nothing and fell through to
`tier_rank 99`: closed, strong_buy, buy and hold. Only `new` and `exit`
matched. The consequence is an inverted order - EXIT rows at rank 3 sorted
ABOVE every held position at 99, and STRONG BUY, BUY, HOLD and closed
artifacts were collapsed into one undifferentiated bucket - while the
config plainly intends new < active < exit.

It is the alias-drift class again: a consumer holding a private copy of a
vocabulary that lives in config. The same shape as the sheet-name aliases
and the `.NS` ticker mismatch.

WHAT THIS MODULE GUARANTEES
---------------------------
- One owner. The status -> tier map is DATA, in
  configs/decision_colors.yaml under `status_tiers`, so a new status is a
  config edit and a code change is a bug.
- The hard-locked decision vocabulary [NEW, ACTIVE, ACTIVE+, EXIT] is
  unchanged. This maps richer wire statuses ONTO those tiers; it does not
  add a fifth decision.
- An unknown status is never favourable. It resolves to
  `unknown_tier_rank`, which the config sets higher than every real tier,
  and `tier_for_status` reports it as UNKNOWN rather than quietly
  returning a real tier. Silence is what let four statuses sit at 99
  unnoticed.
- Importable and therefore testable, unlike the closure it replaces.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

#: Reported instead of a tier key when nothing matches.
UNKNOWN_TIER = "UNKNOWN"

#: Used when the config omits `unknown_tier_rank`. Deliberately far above
#: any real tier so an unmapped status sorts LAST, never first.
DEFAULT_UNKNOWN_RANK = 99

_CACHE: dict = {}


def config_path(root: Path) -> Path:
    return Path(root) / "configs" / "decision_colors.yaml"


def load(root: Path) -> dict:
    """Parsed decision_colors.yaml · cached on (path, mtime)."""
    p = config_path(root)
    if not p.exists():
        return {}
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    key = (str(p), mt)
    if key in _CACHE:
        return _CACHE[key]
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    _CACHE[key] = cfg
    return cfg


def tiers(root: Path) -> dict:
    return load(root).get("tiers") or {}


def status_tiers(root: Path) -> dict:
    """{UPPERCASE status -> tier key} from config."""
    raw = load(root).get("status_tiers") or {}
    return {str(k).upper().strip(): str(v) for k, v in raw.items()}


def unknown_rank(root: Path) -> int:
    v = load(root).get("unknown_tier_rank")
    try:
        return int(v)
    except (TypeError, ValueError):
        return DEFAULT_UNKNOWN_RANK


def tier_for_status(root: Path, status) -> Tuple[str, bool]:
    """(tier_key_or_UNKNOWN, is_known).

    Returns the flag rather than a bare string so a caller cannot mistake
    a fallback for a match - which is exactly how four statuses sat at
    rank 99 without anyone noticing.
    """
    s = str(status or "").upper().strip()
    if not s:
        return UNKNOWN_TIER, False
    mapped = status_tiers(root).get(s)
    if mapped and mapped in tiers(root):
        return mapped, True
    return UNKNOWN_TIER, False


def tier_rank(root: Path, status) -> int:
    """Sort rank for a status · lower sorts first.

    An unknown status gets `unknown_tier_rank`, so it sorts after every
    configured tier. It is never given a favourable position.
    """
    key, known = tier_for_status(root, status)
    if not known:
        return unknown_rank(root)
    try:
        return int((tiers(root).get(key) or {}).get("tier_rank"))
    except (TypeError, ValueError):
        return unknown_rank(root)


def supported_statuses(root: Path) -> list:
    """Every status the config maps · for coverage tests and diagnostics."""
    return sorted(status_tiers(root))


def unmapped_statuses(root: Path, statuses) -> list:
    """Which of `statuses` the config does not cover.

    The diagnostic that would have caught the original defect: feed it the
    statuses the renderer can actually produce and it names the gaps.
    """
    known = status_tiers(root)
    out = []
    for s in statuses or []:
        u = str(s or "").upper().strip()
        if u and u not in known:
            out.append(u)
    return sorted(set(out))


def audit(root: Path, statuses: Optional[list] = None) -> dict:
    """Machine-readable mapping report."""
    t = tiers(root)
    st = status_tiers(root)
    rows = {}
    for s in sorted(st):
        key, known = tier_for_status(root, s)
        rows[s] = {"tier": key, "known": known, "rank": tier_rank(root, s)}
    return {
        "tiers": {k: (v or {}).get("tier_rank") for k, v in t.items()},
        "unknown_tier_rank": unknown_rank(root),
        "n_statuses_mapped": len(st),
        "statuses": rows,
        "unmapped": unmapped_statuses(root, statuses or []),
        "orphan_targets": sorted({v for v in st.values() if v not in t}),
    }
