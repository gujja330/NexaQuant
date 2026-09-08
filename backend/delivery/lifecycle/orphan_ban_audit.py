"""AEGIS · ORPHAN-BAN RECONSTRUCTION · CEO ruling 2026-09-08.

> "I would NOT blindly release all 449. Instead, classify them:
>   A. Genuine historical position - real R2 admission -> real lifecycle ->
>      real exit. Keep cooling/history.
>   B. Phantom/orphan administrative record - no genuine investment
>      admission, created by the old broken registry/delivery path.
>      Release the ban.
>   C. Ambiguous - insufficient evidence. Keep blocked until reconstructed.
>  That gives us a defensible registry rather than another blanket reset."

WHY THESE BANS EXIST
--------------------
`_load_exited_set` bans a (runner, ticker) permanently once an EXIT row
appears in the history workbook. On 2026-08-26 a bulk cleanup closed 449
USA R2 positions with `ORPHAN_AUTO_CLOSE`, and every one produced an EXIT
row. 502 of USA's 516-name universe became permanently unrecommendable -
which is why NEW was structurally 0.

Blanket-releasing them would discard real exit history. Keeping them all
would keep 97% of the universe banned on the strength of one maintenance
operation. So each is reconstructed from what the registry actually
records.

CLASSIFICATION · evidence-ordered, first match wins
---------------------------------------------------
B_INVALID_ADMISSION_BUT_HELD
                         admitted on a non-BUY signal by the admission bug,
                         but then really held. 474 of USA's 509 sit here,
                         median 15 days, with real market exposure and real
                         P&L. The ADMISSION was invalid; the POSITION was
                         real. Ban released - but the outcome stays valid
                         prediction evidence. Releasing a ban never erases
                         a result.

B_PHANTOM_NO_HOLDING_PERIOD
                         admitted on a non-BUY signal with no holding
                         period · never a real position at all.

B_PHANTOM_SAME_DAY       BUY-family admission opened and closed on the same
                         date · the rotation-hypothetical signature.

A_GENUINE                BUY-family admission, held at least one day, and
                         a resolvable entry and exit price. A real
                         position that really exited · the ban stands and
                         normal cooling applies.

C_AMBIGUOUS              everything else · typically a BUY-family
                         admission whose prices cannot be resolved, so
                         neither a real lifecycle nor a phantom can be
                         demonstrated. Stays blocked, by design: the
                         directive says keep blocked until reconstructed.

Only the three B classes are released. A and C keep their bans.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "aegis.lifecycle.orphan_ban_audit.v1"

BUY_FAMILY = {"BUY", "STRONG BUY", "STRONG_BUY", "ACCUMULATE", "ADD",
              "BUY BIG"}

CLASS_A = "A_GENUINE"
# Both B classes share "no genuine investment admission", but they are NOT
# the same thing and must not be reported as one. 474 of USA's 509 were
# admitted on a HOLD and then really held for a median of 15 days with real
# market exposure and real P&L. Calling those "phantom" would be false:
# the ADMISSION was invalid, the POSITION was real. Their outcomes remain
# valid prediction evidence - releasing a ban does not erase a result.
CLASS_B_HELD = "B_INVALID_ADMISSION_BUT_HELD"
CLASS_B_NO_HOLD = "B_PHANTOM_NO_HOLDING_PERIOD"
CLASS_B_SAME_DAY = "B_PHANTOM_SAME_DAY"
CLASS_C = "C_AMBIGUOUS"
RELEASABLE = {CLASS_B_HELD, CLASS_B_NO_HOLD, CLASS_B_SAME_DAY}


def _hold_days(o) -> Optional[int]:
    try:
        return (date.fromisoformat(str(o.closed_date)[:10])
                - date.fromisoformat(str(o.created_date)[:10])).days
    except Exception:
        return None


def classify(root: Path, market: str) -> dict:
    from backend.research import opportunity_registry as oreg
    from scripts.build_aegis_3sheet_workbook import _close_on_or_before

    reg = oreg.load_all(root)
    rows = []
    for (mkt, runner, tk), opps in (reg or {}).items():
        if str(mkt).lower() != market.lower():
            continue
        if any(o.is_active() for o in opps):
            continue                     # currently held · not banned
        terminals = [o for o in opps if o.is_terminal()]
        if not terminals:
            continue
        latest = max(terminals, key=lambda o: str(o.closed_date or ""))
        sig = str(getattr(latest, "initial_signal", "") or "").upper().strip()
        days = _hold_days(latest)
        reason = str(getattr(latest, "closed_reason", "") or "")

        if sig not in BUY_FAMILY:
            if days is not None and days > 0:
                verdict, why = (
                    CLASS_B_HELD,
                    "admitted on %r · never a BUY-family admission, but the "
                    "position was really held %dd · ban released, outcome "
                    "remains valid evidence" % (sig or "<blank>", days))
            else:
                verdict, why = (
                    CLASS_B_NO_HOLD,
                    "admitted on %r with no holding period · never a real "
                    "position" % (sig or "<blank>"))
        elif days is not None and days <= 0:
            verdict, why = (CLASS_B_SAME_DAY,
                            "opened and closed the same day · no holding period")
        else:
            entry = _close_on_or_before(root, tk, market,
                                        str(latest.created_date or ""))
            exitp = _close_on_or_before(root, tk, market,
                                        str(latest.closed_date or ""))
            if entry and exitp and days:
                verdict = CLASS_A
                why = ("BUY-family admission held %dd with resolvable "
                       "entry/exit · a real position that really exited" % days)
            else:
                verdict = CLASS_C
                why = ("BUY-family admission but prices unresolvable · "
                       "neither a real lifecycle nor a phantom demonstrable")

        rows.append({
            "ticker": str(tk).upper(),
            "runner": str(runner).upper().replace("_NEW", ""),
            "verdict": verdict,
            "releasable": verdict in RELEASABLE,
            "initial_signal": sig,
            "created_date": str(getattr(latest, "created_date", "") or "")[:10],
            "closed_date": str(getattr(latest, "closed_date", "") or "")[:10],
            "holding_days": days,
            "closed_reason": reason[:60],
            "why": why,
        })

    tally = {}
    for r in rows:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "market": market.lower(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_banned_reconstructed": len(rows),
        "tally": tally,
        "n_releasable": sum(1 for r in rows if r["releasable"]),
        "n_kept": sum(1 for r in rows if not r["releasable"]),
        "rows": sorted(rows, key=lambda r: (r["verdict"], r["ticker"])),
    }


def releasable_keys(root: Path, market: str) -> set:
    """(runner, ticker) pairs whose ban class B says may be released."""
    d = load(root, market)
    if d is None:
        return set()
    return {(r["runner"], r["ticker"]) for r in d.get("rows") or []
            if r.get("releasable")}


def artifact_path(root: Path, market: str) -> Path:
    return (root / "reports" / "context"
            / f"orphan_ban_audit_{market.lower()}.json")


def emit(root: Path, rep: dict) -> Path:
    p = artifact_path(root, rep["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def load(root: Path, market: str) -> Optional[dict]:
    p = artifact_path(root, market)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def summary_line(rep: dict) -> str:
    t = rep["tally"]
    return (f"orphan_ban_audit:{rep['market']} · reconstructed "
            f"{rep['n_banned_reconstructed']} · A_GENUINE {t.get(CLASS_A, 0)} "
            f"· B_held {t.get(CLASS_B_HELD, 0)} · B_no_hold "
            f"{t.get(CLASS_B_NO_HOLD, 0)} · B_same_day "
            f"{t.get(CLASS_B_SAME_DAY, 0)} · C_AMBIGUOUS {t.get(CLASS_C, 0)} "
            f"· RELEASE {rep['n_releasable']} · KEEP {rep['n_kept']}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS · reconstruct and classify orphan bans")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    for m in (["india", "usa"] if a.market == "both" else [a.market]):
        rep = classify(root, m)
        p = emit(root, rep)
        print(summary_line(rep))
        print(f"    -> {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
