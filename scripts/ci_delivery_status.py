"""The workflow's final conclusion, as one of six states with evidence.

CEO 2026-11-03 · WHY
--------------------
"A green GitHub Actions run is not proof of a delivered workbook." The USA
workflow has reported success for weeks while the operator received
nothing, because success meant "no step raised", and the steps that decide
delivery either carry continue-on-error or leave no record.

Two specific holes this closes:

1. The send step records its outcome to
   reports/telegram_command_center_<date>.jsonl via
   _append_delivery_ledger(). `git ls-files` matches ZERO of those files -
   no workflow has ever committed one. The single artefact proving whether
   Telegram accepted the upload is written to the runner's disk and
   destroyed with the runner. After the fact, delivery is unprovable, which
   is exactly the position we have been in.

2. Nothing checked the workbook itself. A file can exist, be the wrong
   market, be dated last week, or contain a header row and nothing else,
   and every gate upstream would still pass.

STATES · first failing condition wins, because a later state cannot be
true if an earlier one is false:

    XLSX_GENERATION_FAILURE      no workbook, empty, wrong market, wrong
                                 date, missing sheets, or no data rows
    ARTIFACT_PERSISTENCE_FAILURE the workbook exists but was never
                                 committed, so it does not survive the run
    DELIVERY_BLOCKED             a BLOCK invariant refused the send
    DELIVERY_FAILURE             the send was attempted and did not succeed,
                                 or left no record at all
    DELIVERY_SUCCESS             the ledger records a successful upload of
                                 THIS market's workbook
    PIPELINE_SUCCESS             everything verifiable passed and delivery
                                 was not expected on this run

Exit 0 only for DELIVERY_SUCCESS and PIPELINE_SUCCESS.

This script asserts nothing it has not read. Every state carries the
evidence that produced it, including the workbook's sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# `python scripts/x.py` puts scripts/ on sys.path, not the repo root, so
# `from backend...` fails. The first version of this file caught that
# ImportError alongside genuine resolve failures and reported
# XLSX_GENERATION_FAILURE on two perfectly good workbooks - a guard that
# failed closed for the wrong reason is still a wrong answer.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

XLSX_GENERATION_FAILURE = "XLSX_GENERATION_FAILURE"
ARTIFACT_PERSISTENCE_FAILURE = "ARTIFACT_PERSISTENCE_FAILURE"
DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
DELIVERY_FAILURE = "DELIVERY_FAILURE"
DELIVERY_SUCCESS = "DELIVERY_SUCCESS"
PIPELINE_SUCCESS = "PIPELINE_SUCCESS"

PASSING = (DELIVERY_SUCCESS, PIPELINE_SUCCESS)

#: Sheets the two-sheet contract requires. Resolved through the alias layer
#: rather than by literal name, because consumers holding private copies of
#: a sheet name is its own documented bug class in this repository.
REQUIRED_LOGICAL_SHEETS = ("Portfolio", "Exit History (90d)")


def workbook_path(root: Path, market: str) -> Path:
    return root / "reports" / "telegram" / ("aegis_history_%s.xlsx"
                                            % str(market).lower())


def status_path(root: Path, market: str) -> Path:
    return root / "reports" / "context" / ("delivery_status_%s.json"
                                           % str(market).lower())


def ledger_path(root: Path, on: str) -> Path:
    return root / "reports" / ("telegram_command_center_%s.jsonl" % on[:10])


def sha256(p: Path) -> Optional[str]:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return None


def _git(root: Path, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True)
        return r.returncode, r.stdout.decode("utf-8", "replace").strip()
    except Exception as exc:                          # pragma: no cover
        return 1, "%s: %s" % (type(exc).__name__, exc)


def inspect_workbook(root: Path, market: str, asof: str) -> dict:
    """Open the workbook and report what is actually in it."""
    p = workbook_path(root, market)
    ev = {"path": p.as_posix(), "exists": p.exists(), "bytes": None,
          "sha256": None, "sheets": [], "market_ok": None, "asof_ok": None,
          "data_rows": None, "problems": []}
    if not p.exists():
        ev["problems"].append("workbook does not exist")
        return ev
    ev["bytes"] = p.stat().st_size
    ev["sha256"] = sha256(p)
    if not ev["bytes"]:
        ev["problems"].append("workbook is zero bytes")
        return ev
    try:
        from openpyxl import load_workbook
        wb = load_workbook(p, read_only=True, data_only=True)
    except Exception as exc:
        ev["problems"].append("cannot open workbook: %s: %s"
                              % (type(exc).__name__, exc))
        return ev
    try:
        ev["sheets"] = list(wb.sheetnames)
        try:
            from backend.delivery.xlsx_contract import (
                resolve_portfolio_sheet, resolve_exit_history_sheet)
        except Exception as exc:
            # Not a workbook defect · say so rather than blaming the file.
            ev["problems"].append("cannot import the sheet alias resolver "
                                  "(%s: %s) · this is an environment fault, "
                                  "not a workbook fault"
                                  % (type(exc).__name__, exc))
            return ev
        try:
            resolved = [resolve_portfolio_sheet(wb),
                        resolve_exit_history_sheet(wb)]
        except Exception as exc:
            ev["problems"].append("sheet resolution raised %s: %s"
                                  % (type(exc).__name__, exc))
            return ev
        for logical, name in zip(REQUIRED_LOGICAL_SHEETS, resolved):
            if name is None:
                ev["problems"].append("required sheet %r not resolvable "
                                      "(present: %s)" % (logical, ev["sheets"]))
        ws = wb[resolved[0]] if resolved[0] else wb[wb.sheetnames[0]]
        banner = " ".join(str(ws.cell(r, c).value or "")
                          for r in (1, 2, 3) for c in range(1, 8)).upper()
        want = "INDIA" if str(market).lower() == "india" else "USA"
        other = "USA" if want == "INDIA" else "INDIA"
        ev["market_ok"] = (want in banner) and (other not in banner)
        if not ev["market_ok"]:
            ev["problems"].append("market identity not confirmed for %s "
                                  "(banner did not name it exclusively)" % want)
        ev["asof_ok"] = asof[:10] in banner
        if not ev["asof_ok"]:
            ev["problems"].append("workbook banner does not carry asof %s"
                                  % asof[:10])
        rows = 0
        for r in range(5, min(ws.max_row, 4000) + 1):
            v = ws.cell(r, 2).value
            if v not in (None, ""):
                rows += 1
        ev["data_rows"] = rows
        if rows <= 0:
            ev["problems"].append("no data rows in the portfolio sheet")
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return ev


def inspect_persistence(root: Path, market: str, wb_sha: Optional[str]) -> dict:
    """Is the workbook committed, and is the committed copy THIS copy?"""
    rel = workbook_path(root, market).relative_to(root).as_posix()
    ev = {"path": rel, "tracked": False, "committed_matches": None,
          "problems": []}
    rc, out = _git(root, "ls-files", "--error-unmatch", rel)
    ev["tracked"] = (rc == 0 and bool(out))
    if not ev["tracked"]:
        ev["problems"].append("workbook is not tracked by git · it does not "
                              "survive the runner")
        return ev
    rc, head_sha = _git(root, "rev-parse", "HEAD:%s" % rel)
    if rc != 0:
        ev["problems"].append("workbook tracked but absent from HEAD")
        return ev
    rc, local_sha = _git(root, "hash-object", rel)
    ev["committed_matches"] = (rc == 0 and local_sha == head_sha)
    if not ev["committed_matches"]:
        ev["problems"].append("the committed workbook differs from the one on "
                              "disk · this run's workbook was not persisted")
        return ev

    # CEO 2026-11-03 · "survives runner termination" is the actual criterion,
    # and matching local HEAD does not prove it. The artifact step commits
    # AND pushes, with retries; if that push ultimately fails, the commit
    # exists only on the runner and dies with it, while a HEAD comparison
    # still says PERSISTED. So check the remote-tracking ref too.
    #
    # Absent origin/main (a developer tree, a shallow clone) is NOT a
    # failure - it is an unanswerable question, and reporting it as a
    # workbook defect would be the same category error that made the first
    # version of this file fail two good workbooks.
    rc, origin_sha = _git(root, "rev-parse", "origin/main:%s" % rel)
    if rc != 0:
        ev["pushed_matches"] = None
        ev["pushed_detail"] = ("origin/main unavailable · cannot confirm the "
                               "artifact left the runner")
        return ev
    ev["pushed_matches"] = (origin_sha == local_sha)
    if not ev["pushed_matches"]:
        ev["problems"].append("the workbook is committed locally but "
                              "origin/main holds a different copy · the "
                              "artifact commit was not pushed and does not "
                              "survive runner termination")
    return ev


def inspect_validator(root: Path, market: str) -> dict:
    p = root / "reports" / "context" / ("xlsx_validation_%s.json"
                                        % str(market).lower())
    ev = {"path": p.as_posix(), "exists": p.exists(), "verdict": None,
          "blocked": False, "block_fail": [], "block_skip": [],
          "problems": []}
    if not p.exists():
        ev["problems"].append("no validator verdict was emitted")
        return ev
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        ev["problems"].append("verdict unreadable: %s" % type(exc).__name__)
        return ev
    ev["verdict"] = d.get("verdict")
    for inv in (d.get("invariants") or []):
        if str(inv.get("severity")) != "BLOCK":
            continue
        st = str(inv.get("status"))
        if st == "FAIL":
            ev["block_fail"].append(inv.get("code"))
        elif st == "SKIP":
            ev["block_skip"].append(inv.get("code"))
    ev["blocked"] = bool(ev["block_fail"])
    return ev


def inspect_delivery(root: Path, market: str, asof: str, on: str) -> dict:
    """Did the send actually happen, for THIS market's workbook?"""
    p = ledger_path(root, on)
    want = workbook_path(root, market).name
    ev = {"path": p.as_posix(), "exists": p.exists(), "records": 0,
          "market_records": 0, "ok": None, "last": None, "problems": []}
    if not p.exists():
        ev["problems"].append("no delivery ledger for %s · the send left no "
                              "record (note: these files are untracked, so a "
                              "CI run's record dies with the runner)" % on[:10])
        return ev
    recs = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            recs.append(json.loads(ln))
        except Exception:
            continue
    ev["records"] = len(recs)
    mine = [r for r in recs if want in str(r.get("file") or "")]
    ev["market_records"] = len(mine)
    if not mine:
        ev["problems"].append("ledger has %d record(s) but none for %s"
                              % (len(recs), want))
        return ev
    last = mine[-1]
    ev["last"] = last
    ev["ok"] = bool(last.get("ok"))
    if not ev["ok"]:
        ev["problems"].append("the last send of %s reported ok=%r"
                              % (want, last.get("ok")))
    return ev


def classify(root: Path, market: str, asof: str, on: Optional[str] = None,
             expect_delivery: bool = True) -> dict:
    root = Path(root)
    on = on or asof
    wb = inspect_workbook(root, market, asof)
    out = {"market": str(market).lower(), "asof": asof[:10],
           "workbook": wb, "sha256": wb.get("sha256")}

    if wb["problems"]:
        out["state"] = XLSX_GENERATION_FAILURE
        out["reason"] = wb["problems"][0]
        return out

    pers = inspect_persistence(root, market, wb.get("sha256"))
    out["persistence"] = pers
    if pers["problems"]:
        out["state"] = ARTIFACT_PERSISTENCE_FAILURE
        out["reason"] = pers["problems"][0]
        return out

    val = inspect_validator(root, market)
    out["validator"] = val
    if val["blocked"]:
        out["state"] = DELIVERY_BLOCKED
        out["reason"] = ("BLOCK invariant(s) refused the send: %s"
                         % ", ".join(str(c) for c in val["block_fail"]))
        return out

    if not expect_delivery:
        out["state"] = PIPELINE_SUCCESS
        out["reason"] = ("workbook verified and persisted · delivery was not "
                         "expected on this run")
        return out

    dly = inspect_delivery(root, market, asof, on)
    out["delivery"] = dly
    if dly["ok"]:
        out["state"] = DELIVERY_SUCCESS
        out["reason"] = "Telegram accepted %s" % wb["path"]
    else:
        out["state"] = DELIVERY_FAILURE
        out["reason"] = dly["problems"][0] if dly["problems"] else \
            "the send did not report success"
    # BLOCK invariants that did not evaluate never change the state, but a
    # clean verdict resting on gates that never ran must say so.
    if val.get("block_skip"):
        out["inert_block_invariants"] = val["block_skip"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["india", "usa", "both"], required=True)
    ap.add_argument("--asof", default=date.today().isoformat())
    ap.add_argument("--on", default=None, help="ledger date (default: asof)")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--no-delivery-expected", action="store_true")
    ap.add_argument("--report-only", action="store_true",
                    help="record and annotate but always exit 0")
    a = ap.parse_args(argv)

    root = Path(a.root)
    markets = ("india", "usa") if a.market == "both" else (a.market,)
    worst = 0
    for m in markets:
        st = classify(root, m, a.asof, a.on,
                      expect_delivery=not a.no_delivery_expected)
        try:
            p = status_path(root, m)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(st, indent=2, default=str),
                         encoding="utf-8")
        except Exception:
            pass
        wb = st.get("workbook") or {}
        print("  [delivery] %-6s %-28s %s" % (m, st["state"], st["reason"]))
        print("             workbook sha256=%s bytes=%s rows=%s"
              % (str(st.get("sha256"))[:16], wb.get("bytes"),
                 wb.get("data_rows")))
        if st.get("inert_block_invariants"):
            print("::warning::[delivery] %s verdict rests on %d BLOCK "
                  "invariant(s) that did not evaluate: %s"
                  % (m, len(st["inert_block_invariants"]),
                     ", ".join(str(c) for c in st["inert_block_invariants"])))
        if st["state"] not in PASSING:
            print("%s[delivery] %s %s · %s"
                  % ("::warning::" if a.report_only else "::error::",
                     m, st["state"], st["reason"]))
            if not a.report_only:
                worst = 1
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
