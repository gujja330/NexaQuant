"""DEV028 versioning — detect when a recommendation has changed and needs a new version."""
from __future__ import annotations

from .dna_schema import DNARecord


VERSION_TRIGGERING_FIELDS = [
    "recommendation_type", "action", "classification",
    "target_1", "target_2", "stop_loss", "trailing_stop",
]


def has_changed(prev: dict | None, new: dict) -> tuple[bool, list[str]]:
    """Compare prev vs new record. Return (changed, list_of_changed_fields)."""
    if prev is None:
        return True, ["initial"]

    changed = []
    for field in VERSION_TRIGGERING_FIELDS:
        pv = prev.get(field)
        nv = new.get(field)
        if pv != nv:
            changed.append(field)

    return len(changed) > 0, changed


def next_version(prev: dict | None) -> int:
    if prev is None:
        return 1
    return int(prev.get("version", 0)) + 1
