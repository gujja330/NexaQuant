"""AEGIS · R3 identity · canonical shadow Position IDs.

CEO 2026-09-07 · Phase R3-0 requires "separate R3 Position IDs using the
canonical runner=`R3`". The R3-1 audit found NEITHER shadow ledger carried
a `runner` field or a Position ID at all, so an R3 record was
indistinguishable from an R2 one by schema alone. If such a record ever
reached a production consumer it could not be rejected on identity.

WHY THIS IS NOT IMPORTED FROM opportunity_registry
--------------------------------------------------
`opportunity_registry.make_opportunity_id` produces exactly this format
and reserves the "R3" runner tag already. R3 nonetheless mints its own IDs
here, because the isolation contract is easier to keep true when the R3
tree has no import path at all into the module that owns Registry
mutation. The format is deliberately identical so an R3 id is recognisable
to a human and to any auditor, and the parity is pinned by a test.

An R3 Position ID can never collide with an R2/R1 one: the runner tag is
part of the hashed signature AND of the visible prefix.

    IND-R3-TATASTEEL-20260907-a1b2c3
    USA-R3-PLTR-20260907-d4e5f6
"""
from __future__ import annotations

import hashlib

R3_RUNNER = "R3"


def _bare_ticker(ticker: str) -> str:
    """Strip exchange suffixes · mirrors the canonical helper."""
    return (str(ticker or "").upper()
            .replace(".NS", "").replace(".BO", "")
            .split(".", 1)[0].strip())


def _mkt_tag(market: str) -> str:
    return "USA" if str(market or "").lower() == "usa" else "IND"


def r3_position_id(market: str, ticker: str, asof: str) -> str:
    """Deterministic R3 shadow Position ID · same inputs = same id.

    Idempotent by construction so re-running a day's shadow feed does not
    mint duplicate identities for the same (market, ticker, day).
    """
    tk = _bare_ticker(ticker)
    mkt = _mkt_tag(market)
    ds = (str(asof or ""))[:10].replace("-", "")
    sig = hashlib.sha256(
        f"{mkt}-{R3_RUNNER}-{tk}-{ds}".encode()).hexdigest()[:6]
    return f"{mkt}-{R3_RUNNER}-{tk}-{ds}-{sig}"


def stamp_identity(record: dict, market: str, ticker: str, asof: str) -> dict:
    """Attach R3 identity to a shadow-ledger record, in place.

    Every shadow record must carry `runner` and `opportunity_id` so that:
      · an R3 row is self-identifying wherever it travels
      · a production consumer can reject it on identity alone
      · the Day-30/60/90 gates can group outcomes by position
    """
    record["runner"] = R3_RUNNER
    record["opportunity_id"] = r3_position_id(market, ticker, asof)
    record["shadow_only"] = True
    return record
