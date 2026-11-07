"""Durable episode lineage · CEO 2026-11-06 · A23 accounting repair.

WHAT WENT WRONG
---------------
India run 41985177006 (2026-11-05) blocked delivery:

    A19 / A23   PASS / FAIL
    [A23] 3 Registry-CLOSED tickers silently lost (not in Exit History
    body AND not in orphan audit JSONL): BHARATFORG, HCLTECH, HEROMOTOCO
    FINAL: BLOCKED - No XLSX. No Telegram.

Nothing in the code changed. The CALENDAR moved.

A23's population is the WHOLE registry history of accountable CLOSED
episodes - it carries no date cutoff. Its evidence is a 90-day rolling
Exit History plus the orphan audit. An unbounded population measured
against bounded evidence has exactly one outcome: every accountable
close becomes "silently lost" on the day it ages out of the window,
unless something durable records it.

    asof 2026-11-04 -> window starts 2026-08-06 -> closes INSIDE  -> PASS
    asof 2026-11-05 -> window starts 2026-08-07 -> closes OUTSIDE -> FAIL

The three were closed on 2026-08-06 by the `should_rotate` rule removed
on 2026-09-08 (reason "-> GNFC.NS - +Npp alpha"). India's price coverage
begins 2026-08-04, so that cohort is the OLDEST accountable close there
is, which is why 2026-11-05 was the first day this could fire. It then
fires every day, on a growing set.

WHY THE EXISTING SINK COULD NOT HOLD THEM
-----------------------------------------
`_emit_orphan_audit_for_retired` in scripts/build_aegis_3sheet_workbook.py
is the orphan sink, and it has two properties that matter here:

  1. it reads `closed_retired_90d` / `closed_admin_90d` - both already
     90-day scoped, so an episode that has aged out can never enter it;
  2. it dedupes by TICKER, so a ticker's SECOND episode never gets a
     record even when its first one did.

(2) is the same ticker-versus-episode confusion that let A23 report 3
rather than 5 on 2026-11-05: INFY and VEDL had also aged out, but both
had re-entered, and a ticker-level set cannot tell a closed episode from
an active one wearing the same name.

WHAT THIS MODULE DOES
---------------------
It records an accountable CLOSED episode durably, keyed by
`opportunity_id`, in the SAME orphan-audit sink A23 already reads. No
parallel position model: the population comes from the registry and is
filtered by the very functions A23 uses (`retired_runners`,
`_is_administrative_exit`), so a second definition of "accountable
close" cannot drift into existence.

Historical facts are copied, never rewritten. The close date stays
2026-08-06 and the reason stays the rotation reason. An artifact that
lies about when something closed is worse than one that admits it is
missing.

THIS DOES NOT WEAKEN A23
------------------------
A23 still fails when an episode is genuinely unaccounted. This adds a
VALID accounting source for episodes that have aged out of the
operational window; it does not widen that window, and it does not
excuse an episode nobody can explain.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = "aegis.episode_lineage.v1"

#: One kind, with the disposition carried in its own field. A kind per
#: situation is how vocabularies fork.
KIND = "R2_LINEAGE_PRESERVED"

#: Exit History retention. Read, never changed, and deliberately equal to
#: the builder's window so this module cannot drift from it.
EXIT_HISTORY_WINDOW_DAYS = 90

CLOSE_TYPE_ROTATION = "ROTATION"
CLOSE_TYPE_REAL_EXIT = "REAL_EXIT"

STATUS_REPRESENTED = "REPRESENTED"
STATUS_ACCOUNTED_ADMIN = "ACCOUNTED_ADMINISTRATIVE"
STATUS_UNACCOUNTED = "UNACCOUNTED"

DISPOSITION_AGED_OUT = "AGED_OUT_OF_EXIT_HISTORY"

SOURCE_REGISTRY = "opportunity_registry"

#: The historical rotation reason, e.g. "-> GNFC.NS - +59.7pp alpha".
#: Matched on the arrow plus "alpha" so a normal exit reason that merely
#: mentions a peer is not mislabelled.
_ROTATION_RE = re.compile(r"(->|→).*alpha", re.IGNORECASE)


def canonical_path(root: Path, market: str) -> Path:
    """The durable ledger · written ONLY by this module.

    CEO 2026-11-07 · STRUCTURAL, not detected.

    Durable lineage first lived in orphan_audit_<market>.jsonl, which
    the Telegram sender rewrites with mode "w" from its own computed
    subset. On 2026-11-07 that deleted all 11 records (37 rows -> 26)
    and A23 failed again on a fix that had measured clean.

    Preserving the sender's write was the first repair, and it is not
    enough: it leaves the canonical ledger reachable by a destructive
    writer, so the next component to open that path with "w" reopens
    the same defect. A sender may CONSUME accounting history; it must
    never be able to destroy history a blocking invariant depends on.

    So the canonical record lives in its own file that no renderer,
    sender or workbook builder writes. orphan_audit stays exactly as it
    was - the sender's derived view - and A23 reads BOTH.
    """
    return (Path(root) / "reports" / "delivery"
            / ("episode_lineage_%s.jsonl" % str(market).lower()))


def derived_audit_path(root: Path, market: str) -> Path:
    """The sender's own derived view · read for accounting, never written."""
    return (Path(root) / "reports" / "delivery"
            / ("orphan_audit_%s.jsonl" % str(market).lower()))


def audit_path(root: Path, market: str) -> Path:
    """Deprecated alias · kept so existing callers keep resolving.

    Returns the CANONICAL path. A reader that wants the sender's
    derived view must ask for it by name, because that is the
    distinction this whole defect turned on.
    """
    return canonical_path(root, market)


def window_start(asof) -> date:
    d = asof if isinstance(asof, date) else date.fromisoformat(str(asof)[:10])
    return d - timedelta(days=EXIT_HISTORY_WINDOW_DAYS)


def classify_close_type(reason: Optional[str]) -> str:
    return (CLOSE_TYPE_ROTATION if _ROTATION_RE.search(str(reason or ""))
            else CLOSE_TYPE_REAL_EXIT)


def recorded_episode_ids(root: Path, market: str) -> set:
    """Episode ids already present in the sink · keyed by EPISODE.

    The existing writer keys by ticker. Reading back by ticker is what
    makes a second episode invisible, so this reads by opportunity_id.
    """
    out: set = set()
    # Canonical first, then the sender's derived view. Both are valid
    # accounting evidence; only one of them is safe from truncation.
    for p in (canonical_path(root, market), derived_audit_path(root, market)):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8",
                                errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            oid = str(e.get("opportunity_id")
                      or e.get("position_id") or "").strip()
            if oid:
                out.add(oid)
    return out


def exit_history_episode_ids(root: Path, market: str) -> set:
    """Position IDs rendered in the Exit History sheet.

    The workbook's `Position ID` column carries the registry
    opportunity_id verbatim (measured 2026-11-06:
    IND-R2-AIAENG-20261016-4b46fa), which is what makes episode-level
    accounting possible at all.
    """
    xp = (Path(root) / "reports" / "telegram"
          / ("aegis_history_%s.xlsx" % str(market).lower()))
    out: set = set()
    if not xp.exists():
        return out
    try:
        from openpyxl import load_workbook
    except Exception:
        return out
    try:
        wb = load_workbook(xp, read_only=True)
    except Exception:
        return out
    try:
        sheet = next((wb[n] for n in wb.sheetnames
                      if "EXIT" in str(n).upper()), None)
        if sheet is None:
            return out
        hdr_row = pid_col = None
        for r in range(1, 13):
            for c in range(1, 30):
                if str(sheet.cell(r, c).value or "").strip() == "Position ID":
                    hdr_row, pid_col = r, c
                    break
            if hdr_row:
                break
        if not hdr_row or not pid_col:
            return out
        for r in range(hdr_row + 1, sheet.max_row + 1):
            v = sheet.cell(r, pid_col).value
            if v and str(v).strip():
                out.add(str(v).strip())
        return out
    finally:
        try:
            wb.close()
        except Exception:
            pass


def accountable_closed_episodes(root: Path, market: str) -> list:
    """Registry CLOSED episodes A23 holds to account.

    Deliberately delegates every exclusion to the functions A23 itself
    uses. Reimplementing "is this administrative" here would create the
    second definition that this whole repair exists to remove.
    """
    from backend.delivery.canonical.retirement import retired_runners
    from backend.research import opportunity_registry as _oreg
    try:
        from scripts.build_aegis_3sheet_workbook import (
            _close_on_or_before as _close_on,
            _is_administrative_exit as _is_admin)
    except Exception:
        _is_admin = None
        _close_on = None

    mk = str(market).lower()
    retired = retired_runners(root)
    out = []
    for opps in (_oreg.load_all(root) or {}).values():
        for o in opps:
            if str(o.market).lower() != mk or o.status != "CLOSED":
                continue
            if o.runner in retired:
                continue
            if _is_admin is not None and _close_on is not None:
                ep = _close_on(root, o.ticker, mk, o.created_date or "")
                xp = _close_on(root, o.ticker, mk, o.closed_date or "")
                if _is_admin(o, ep, xp):
                    continue
            out.append(o)
    return out


def account(root: Path, market: str, asof) -> dict:
    """Classify every accountable closed episode · the §accounting model.

    REPRESENTED               in Exit History
    ACCOUNTED_ADMINISTRATIVE  in durable lineage
    UNACCOUNTED               neither
    """
    eh = exit_history_episode_ids(root, market)
    aud = recorded_episode_ids(root, market)
    by_status = {STATUS_REPRESENTED: [], STATUS_ACCOUNTED_ADMIN: [],
                 STATUS_UNACCOUNTED: []}
    no_identity = []
    for o in accountable_closed_episodes(root, market):
        oid = str(o.opportunity_id or "").strip()
        if not oid:
            # Fails CLOSED. An episode without identity cannot be matched,
            # and guessing by ticker is the defect being removed.
            no_identity.append(o)
            by_status[STATUS_UNACCOUNTED].append(o)
            continue
        if oid in eh:
            by_status[STATUS_REPRESENTED].append(o)
        elif oid in aud:
            by_status[STATUS_ACCOUNTED_ADMIN].append(o)
        else:
            by_status[STATUS_UNACCOUNTED].append(o)
    return {
        "market": str(market).lower(),
        "asof": str(asof)[:10],
        "window_start": window_start(asof).isoformat(),
        "n_exit_history_ids": len(eh),
        "n_lineage_ids": len(aud),
        "by_status": by_status,
        "episodes_without_identity": no_identity,
        "counts": {k: len(v) for k, v in by_status.items()},
    }


def _record_for(o, market: str) -> dict:
    oid = str(o.opportunity_id or "").strip()
    reason = str(getattr(o, "closed_reason", "") or "")
    ctype = classify_close_type(reason)
    return {
        "kind": KIND,
        "schema": SCHEMA,
        "market": str(market).lower(),
        "ticker": str(o.ticker or "").upper(),
        "runner": o.runner,
        "opportunity_id": oid,
        # Same value, under the name each consumer already uses. The
        # workbook calls it Position ID, the registry calls it
        # opportunity_id, and a reader should not have to know that.
        "position_id": oid,
        "created_date": str(o.created_date or "")[:10],
        # HISTORICAL FACTS · copied, never rewritten. Making an old close
        # look recent so a gate goes green is the one thing this must not do.
        "closed_date": str(o.closed_date or "")[:10],
        "closed_reason": reason,
        "close_type": ctype,
        "disposition": DISPOSITION_AGED_OUT,
        "source": SOURCE_REGISTRY,
        "accounting_status": STATUS_ACCOUNTED_ADMIN,
        "recorded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rationale": (
            "Accountable R2 %s close that has aged out of the %d-day Exit "
            "History window. Recorded durably so A23 can account for the "
            "episode without widening the window or weakening the gate."
            % (ctype.lower(), EXIT_HISTORY_WINDOW_DAYS)),
    }


def reconcile(root: Path, market: str, asof, dry_run: bool = False) -> dict:
    """Record durable lineage for episodes that have aged out.

    Idempotent: keyed by opportunity_id, so running twice adds nothing
    the second time. Only episodes that are UNACCOUNTED and genuinely
    outside the Exit History window are recorded - an episode missing
    from a window it still belongs to is a real defect and must keep
    failing.
    """
    root = Path(root)
    state = account(root, market, asof)
    wstart = state["window_start"]
    already = recorded_episode_ids(root, market)

    # CANDIDATES COME FROM THE DATA, NOT FROM A RENDERED ARTIFACT.
    #
    # The first version of this selected from `by_status[UNACCOUNTED]`,
    # which is derived by reading the workbook. That made the backfill
    # depend on whichever as-of the workbook happened to be built with:
    # a sheet rendered at 2026-11-04 still lists the 2026-08-06 cohort,
    # so the reconciler saw nothing to do while CI - rendering at
    # 2026-11-05 - was blocking on exactly those episodes.
    #
    # An episode closed before the retention window CANNOT be in Exit
    # History, by construction. That is an arithmetic fact about the
    # registry, reproducible on any machine regardless of which
    # workbook is lying around, so selection is made from it.
    selected, excluded = [], []
    _already_represented = {
        str(o.opportunity_id or "").strip()
        for o in state["by_status"][STATUS_REPRESENTED]}
    for o in accountable_closed_episodes(root, market):
        oid = str(o.opportunity_id or "").strip()
        cd = str(o.closed_date or "")[:10]
        if not oid:
            excluded.append({"ticker": str(o.ticker or "").upper(),
                             "opportunity_id": None,
                             "reason": "no episode identity · fails closed "
                                       "rather than being guessed by ticker"})
            continue
        if not cd:
            excluded.append({"ticker": str(o.ticker or "").upper(),
                             "opportunity_id": oid,
                             "reason": "no closed_date · cannot prove it is "
                                       "outside the retention window"})
            continue
        if cd >= wstart:
            # Still inside retention. If it is missing from Exit History
            # that is a REAL defect (USA/PLD on 2026-11-04 was exactly
            # this) and must keep failing A23 rather than being quietly
            # accounted for here.
            excluded.append({"ticker": str(o.ticker or "").upper(),
                             "opportunity_id": oid, "closed_date": cd,
                             "reason": "inside the %s-day window · absence "
                                       "from Exit History is a real defect, "
                                       "not an accounting gap"
                                       % EXIT_HISTORY_WINDOW_DAYS,
                             "currently_represented":
                                 oid in _already_represented})
            continue
        if oid in already:
            excluded.append({"ticker": str(o.ticker or "").upper(),
                             "opportunity_id": oid,
                             "reason": "already recorded · idempotent"})
            continue
        selected.append(o)

    records = [_record_for(o, market) for o in selected]
    if records and not dry_run:
        p = audit_path(root, market)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    after = (account(root, market, asof) if (records and not dry_run)
             else state)
    return {
        "schema": "aegis.episode_lineage.backfill_manifest.v1",
        "market": str(market).lower(),
        "asof": str(asof)[:10],
        "window_start": wstart,
        "dry_run": bool(dry_run),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_population": {
            "n_accountable_closed": sum(state["counts"].values()),
            "n_represented": state["counts"][STATUS_REPRESENTED],
            "n_accounted_administrative":
                state["counts"][STATUS_ACCOUNTED_ADMIN],
            "n_unaccounted": state["counts"][STATUS_UNACCOUNTED],
            "source": SOURCE_REGISTRY,
            "exit_history_ids": state["n_exit_history_ids"],
            "lineage_ids": state["n_lineage_ids"],
        },
        "selected": [
            {k: r[k] for k in ("opportunity_id", "position_id", "ticker",
                               "runner", "created_date", "closed_date",
                               "closed_reason", "close_type", "disposition",
                               "accounting_status")}
            for r in records],
        "n_selected": len(records),
        "excluded": excluded,
        "n_excluded": len(excluded),
        "destination": str(audit_path(root, market).relative_to(root).as_posix()),
        "unaccounted_before": state["counts"][STATUS_UNACCOUNTED],
        "unaccounted_after": after["counts"][STATUS_UNACCOUNTED],
    }


def summary_line(man: dict) -> str:
    return ("episode_lineage:%s · accountable %d · represented %d · "
            "lineage %d · unaccounted %d -> %d · recorded %d%s"
            % (man["market"],
               man["source_population"]["n_accountable_closed"],
               man["source_population"]["n_represented"],
               man["source_population"]["n_accounted_administrative"],
               man["unaccounted_before"], man["unaccounted_after"],
               man["n_selected"], " (dry-run)" if man["dry_run"] else ""))


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="AEGIS · durable episode lineage for aged-out closes")
    ap.add_argument("--market", choices=["india", "usa", "both"],
                    default="both")
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--root", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="classify and report · write nothing")
    ap.add_argument("--manifest", default=None,
                    help="write the backfill manifest to this path")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    markets = ["india", "usa"] if a.market == "both" else [a.market]

    worst = 0
    mans = {}
    for m in markets:
        man = reconcile(root, m, a.asof, dry_run=a.dry_run)
        mans[m] = man
        print("  " + summary_line(man))
        for s in man["selected"][:15]:
            print("      + %-34s %-12s closed %s  %s"
                  % (s["opportunity_id"], s["ticker"], s["closed_date"],
                     s["close_type"]))
        if man["unaccounted_after"]:
            print("::warning::[episode_lineage] %s still has %d unaccounted "
                  "episode(s) · A23 will block, which is correct"
                  % (m, man["unaccounted_after"]))
            worst = 1
    if a.manifest:
        Path(a.manifest).write_text(
            json.dumps(mans, indent=2, default=str), encoding="utf-8")
        print("  manifest -> %s" % a.manifest)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
