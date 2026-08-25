"""Zero-Tolerance Delivery Gate · blocks Telegram send when guards FAIL.

Operator 2026-08-25: "u r showing many, but when i see final reports,
i am question u? u shouldnt give me a chance to question right"

Design: the sender MUST call `decide()` before posting the XLSX to
Telegram. If the acceptance gate or data-quality gate reports FAIL,
this gate returns BLOCK. The sender then:
  1. Does NOT send the XLSX
  2. Sends a plain-text alert instead ("BLOCKED · A17 FAIL · ...")
  3. Exits with non-zero so CI logs are visibly red

Config in configs/delivery_gate.yaml (auto-created with sane defaults
on first read).

The list of BLOCKING check codes lives in this file · easy to tune
without touching the acceptance gate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Codes from wave_regression.py that FAIL → BLOCK delivery.
# Everything else stays advisory (WARN in banner).
BLOCKING_CODES: set = {
    "A5",    # duplicate Position IDs
    "A11",   # classifier + vocab unit tests
    "A17",   # EXIT rows leaking into ACTIVE section
    "A18",   # exit reasons plain-English (no jargon)
    "A19",   # Exit History has Sector column
    # 2026-08-25 · lifecycle sync + dedup (operator IEX-in-both bug)
    "A22",   # dedup · no ticker in both Portfolio + Exit History
    "A23",   # sync · every Registry-CLOSED ticker in Exit History
    "A24",   # sync · no Registry-CLOSED ticker in Portfolio
}

# Data-quality gate hard fails always block.
BLOCK_ON_DQ_FAIL = True

# Emergency escape hatch · when true, gate ALLOWS despite FAILs.
# Operator flips manually in configs/delivery_gate.yaml when a fix is
# in-flight but yesterday's XLSX is still needed.
DEFAULT_OVERRIDE_ALLOW = False


@dataclass
class GateDecision:
    verdict:        str = "ALLOW"          # ALLOW | BLOCK
    generated_utc:  str = ""
    market:         str = ""
    reasons:        list = field(default_factory=list)   # human-readable
    blocking_codes: list = field(default_factory=list)   # ["A17", "DQ2", ...]
    override_used:  bool = False


def _load_config(root: Path) -> dict:
    p = root / "configs" / "delivery_gate.yaml"
    if not p.exists():
        # Write sane defaults so operator can find + edit
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                "version: 1.0\n"
                "# Zero-tolerance delivery gate config.\n"
                "# Flip override_allow to true to temporarily bypass ALL blocks\n"
                "# (e.g., yesterday's XLSX is still needed while a fix is in-flight).\n"
                "# NEVER commit override_allow: true · always revert after use.\n"
                "override_allow: false\n"
                "# Add codes here to make additional checks blocking.\n"
                "extra_blocking_codes: []\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_json(p: Path) -> dict:
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}


def decide(root: Path, market: str) -> GateDecision:
    """Consult every guard's output and return ALLOW / BLOCK."""
    market = market.lower()
    cfg = _load_config(root)
    override = bool(cfg.get("override_allow", DEFAULT_OVERRIDE_ALLOW))
    extra_block = set(cfg.get("extra_blocking_codes") or [])
    blocking = BLOCKING_CODES | extra_block

    d = GateDecision(
        market=market,
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    ctx = root / "reports" / "context"

    # Acceptance gate (wave_regression)
    _wr = _load_json(ctx / f"wave_regression_{market}.json")
    for chk in _wr.get("checks", []):
        if chk.get("status") == "FAIL" and chk.get("code") in blocking:
            d.blocking_codes.append(chk.get("code"))
            d.reasons.append(f"[{chk['code']}] {chk.get('name','')} · {chk.get('detail','')}")

    # Data quality gate
    if BLOCK_ON_DQ_FAIL:
        _dq = _load_json(ctx / f"data_quality_gate_{market}.json")
        for chk in _dq.get("checks", []):
            if chk.get("severity") == "FAIL":
                _code = f"DQ:{chk.get('code','')}"
                d.blocking_codes.append(_code)
                d.reasons.append(f"[{_code}] {chk.get('name','')} · {chk.get('detail','')}")

    # NEW-Opp Guard hard RED
    _guard = _load_json(ctx / f"new_opp_guard_health_{market}.json")
    if _guard.get("verdict") == "RED":
        d.blocking_codes.append("GUARD:RED")
        d.reasons.append(f"[GUARD:RED] {_guard.get('notes','')}")

    # 2026-08-25 · Price Integrity Guard · CEO directive.
    # OBSERVATION PERIOD · start with all PI checks NON-BLOCKING so we
    # can measure real-world drift base rate over 2-3 days BEFORE
    # promoting PI1/PI2/PI5 to BLOCK. Rationale: 0.5% tolerance may
    # legitimately fire on corporate actions or intraday-vs-close price
    # mismatches; blocking without a baseline could ship zero XLSX.
    # After base-rate observation, uncomment the BLOCK set below.
    _pig = _load_json(ctx / f"price_integrity_{market}.json")
    _PIG_BLOCKING: set = set()   # {"PI1", "PI2", "PI5"} · promote after calibration
    for chk in _pig.get("checks", []):
        if chk.get("status") == "FAIL" and chk.get("code") in _PIG_BLOCKING:
            d.blocking_codes.append(chk.get("code"))
            d.reasons.append(
                f"[{chk['code']}] {chk.get('name','')} · "
                f"{chk.get('detail','')}")

    # Overall verdict
    if d.blocking_codes and not override:
        d.verdict = "BLOCK"
    elif d.blocking_codes and override:
        d.verdict = "ALLOW"
        d.override_used = True
        d.reasons.append("⚠️ OVERRIDE_ALLOW=true · gate bypassed despite failures")
    else:
        d.verdict = "ALLOW"
    return d


def emit(root: Path, market: str, d: GateDecision) -> Path:
    p = (root / "reports" / "context"
             / f"delivery_gate_{market.lower()}.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    from dataclasses import asdict
    p.write_text(json.dumps(asdict(d), indent=2, default=str, ensure_ascii=False),
                     encoding="utf-8")
    return p


def blocked_summary(d: GateDecision) -> str:
    """Plain-text alert to send to Telegram in place of the XLSX when blocked."""
    lines = [
        "🚫 AEGIS DELIVERY BLOCKED",
        f"market: {d.market.upper()} · {d.generated_utc[:19]}",
        f"blocking checks: {len(d.blocking_codes)}",
        "",
        "Reasons:",
    ]
    for r in d.reasons[:8]:
        lines.append(f"  · {r[:180]}")
    lines.append("")
    lines.append("Fix the issues + rerun the pipeline · no XLSX shipped this cycle.")
    lines.append("Emergency override: set override_allow: true in configs/delivery_gate.yaml")
    return "\n".join(lines)
