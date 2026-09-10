"""AEGIS RUN · the one execution path.

Manual morning, manual evening and scheduled CI all call this. There is no
separate "CI logic" - a second path is how two answers to the same
question start to exist, and only one of them stays true.

    acquire (PARALLEL across markets/sources)
        |
        +--- join
        |
    GATE 1 DATA READY        <-- fail-closed from here down
        |
    materialise features (PARALLEL where independent)
        |
    GATE 2 FEATURES READY
        |
    score full universe
        |
    GATE 3 SCORES READY
        |
    eligibility + lifecycle
        |
    GATE 4 DECISION READY
        |
    GATE 5 DELIVERY READY
        |
    XLSX + Telegram

PARALLELISM RULE
----------------
Parallelise independent work; never parallelise across a dependency
boundary. India and USA acquisition are independent, so they run together.
Scoring cannot start before its own market's features exist, so it does
not. Speed comes from the first kind of concurrency only - the second kind
is how race conditions get introduced while claiming to be an optimisation.

REFRESH IS PART OF THE RUN
--------------------------
`--refresh` produces today's feature snapshot BEFORE the gates, because a
gate that only ever reports "yesterday's data" is an alarm nobody can act
on. The gate still decides; refresh only gives it something current to
judge.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from backend.pipeline.contract import certification as cert
from backend.pipeline.contract import (completeness, intermarket,
                                        readiness, scoring)
from backend.pipeline.contract.run_context import RunContext, resolve_asof

SCHEMA_VERSION = "aegis.pipeline.contract.runner.v1"

MARKETS = ("india", "usa")


def _sh(cmd: list, cwd: Path, timeout: int = 3600) -> tuple:
    import subprocess
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout or "")[-2000:], (r.stderr or "")[-800:]
    except Exception as e:
        return 1, "", "%s: %s" % (type(e).__name__, e)


# ── stage 0 · acquisition + materialisation (parallelisable) ────────────

# Every mandatory domain, per market, in dependency order.
#
# `--refresh` used to cover feature_store and model_factory only, and the
# other domains were refreshed by hand. That is precisely how
# india/global_risk.py went three months without running: a producer
# nobody calls is indistinguishable from one that does not exist. If a
# domain is mandatory it belongs in this table, not in someone's memory.
_REFRESH = {
    "india": (
        # ── context · independent of each other, all feed the gate ──
        # --fetch or it silently no-ops when the parquets already exist.
        ("global_context", ["python", "-W", "ignore", "india/global_risk.py",
                            "--fetch"]),
        ("macro_intel", ["python", "-W", "ignore", "india/macro_intel/run.py"]),
        ("market_intel", ["python", "-W", "ignore",
                          "india/market_intelligence/run.py"]),
        ("fii_dii", ["python", "-W", "ignore", "india/fii_dii.py"]),
        # ── substrate · features then the models that read them ──
        ("feature_store", ["python", "-W", "ignore",
                           "india/feature_store/run.py"]),
        ("model_factory", ["python", "-W", "ignore",
                           "india/model_factory/run.py"]),
        ("recommendations", ["python", "-W", "ignore",
                             "india/recommendation_intelligence/run.py"]),
        ("ssot", ["python", "-W", "ignore", "-m",
                  "backend.recommendation.ssot.run",
                  "--market", "india", "--force"]),
    ),
    "usa": (
        ("market_data", ["python", "-W", "ignore",
                         "usa/scripts/refresh_market_data.py"]),
        ("macro_intel", ["python", "-W", "ignore",
                         "usa/research/macro_intel/run.py"]),
        ("market_intel", ["python", "-W", "ignore",
                          "usa/research/market_intelligence/run.py"]),
        ("feature_store", ["python", "-W", "ignore", "-c",
                           "from datetime import date;from pathlib import Path;"
                           "from backend.feature_store.feature_snapshot import build_and_persist;"
                           "from backend.canonical.model import USA_PROFILE;"
                           "print(build_and_persist(Path('.'),USA_PROFILE,date.today())"
                           ".get('verdict'))"]),
        ("model_factory", ["python", "-W", "ignore",
                           "usa/research/model_factory/run.py"]),
        ("recommendations", ["python", "-W", "ignore",
                             "usa/research/recommendation_intelligence/run.py"]),
        ("ssot", ["python", "-W", "ignore", "-m",
                  "backend.recommendation.ssot.run",
                  "--market", "usa", "--force"]),
    ),
}

# Runs once for both markets · reads each market's registry.
#
# The two reconciliation audits were NOT in this table and had frozen at
# 2026-09-08 while the certification went green for two more days. They
# are the artifacts the A23 "UNACCOUNTED = 0" proof is built on, so a
# stale copy means the proof is about a state that no longer exists.
#
# Order matters: materialize first (it can admit positions into the
# registry), then audit the orphans that materialisation leaves behind.
_REFRESH_SHARED = (
    # MUST precede dynamic_risk: a position admitted today does not exist
    # when stops are computed, so it arrives with `stop none` and can
    # never appear on its own day (JIOFIN, 2026-09-08). Idempotent -
    # get_or_create returns an existing ACTIVE opportunity unchanged, and
    # the module owns no decision logic.
    ("registry_materializer", ["python", "-W", "ignore", "-m",
                               "backend.delivery.lifecycle."
                               "registry_materializer", "--market", "both"]),
    ("dynamic_risk", ["python", "-W", "ignore",
                      "scripts/run_dynamic_risk_v2.py", "--market", "both"]),
    # Audits what materialisation left behind · read-only.
    ("orphan_ban_audit", ["python", "-W", "ignore", "-m",
                          "backend.delivery.lifecycle.orphan_ban_audit",
                          "--market", "both"]),
)


def refresh_market(root: Path, market: str, asof: str) -> dict:
    """Produce TODAY's substrate for one market · safe to run in parallel.

    Steps run IN ORDER within a market because each reads what the last
    wrote. Markets run concurrently because they share nothing.

    A failure is recorded and the market STOPS. Continuing would let the
    next stage read yesterday's artifact and report itself healthy - the
    exact failure mode this whole contract exists to remove.
    """
    t0 = time.time()
    steps, ok = [], True
    for label, cmd in _REFRESH.get(market.lower(), ()):
        t1 = time.time()
        rc, out, err = _sh(cmd, root)
        # Per-stage timing · USA acquisition is 313s and "it must be the
        # network" is a hypothesis. Recording each stage makes the
        # dominant term visible instead of assumed.
        steps.append({"step": label, "returncode": rc,
                      "elapsed_s": round(time.time() - t1, 1),
                      "tail": (out or err).strip().splitlines()[-1:]})
        if rc != 0:
            ok = False
            break
    return {"market": market, "ok": ok, "steps": steps,
            "elapsed_s": round(time.time() - t0, 2)}


def acquire(root: Path, markets: tuple, asof: str,
            parallel: bool = True) -> dict:
    """India and USA are independent · run them together."""
    t0 = time.time()
    if parallel and len(markets) > 1:
        with ThreadPoolExecutor(max_workers=len(markets)) as ex:
            res = list(ex.map(lambda m: refresh_market(root, m, asof), markets))
    else:
        res = [refresh_market(root, m, asof) for m in markets]
    # Shared steps run AFTER both markets · dynamic_risk reads each
    # market's registry, so it cannot start before they are materialised.
    shared = []
    for label, cmd in _REFRESH_SHARED:
        rc, out, err = _sh(cmd, root)
        shared.append({"step": label, "returncode": rc})
    return {"results": {r["market"]: r for r in res}, "shared": shared,
            "elapsed_s": round(time.time() - t0, 2),
            "parallel": parallel}


# ── stage N · scoring / lifecycle (per market, after its own gates) ─────

def score_universe(root: Path, market: str) -> dict:
    t0 = time.time()
    rc, out, err = _sh(["python", "-W", "ignore", "-m",
                        "backend.research.shadow.full_universe_shadow",
                        "--market", market], root)
    return {"returncode": rc, "elapsed_s": round(time.time() - t0, 2),
            "tail": (out or err).strip().splitlines()[-1:]}


def build_lifecycle(root: Path, market: str, asof: str) -> dict:
    t0 = time.time()
    steps = []
    # ORDER MATTERS · CEO 2026-09-09.
    #
    # why_not_current assigns `L10_in_current`, which it can only know by
    # reading CURRENT. Run before the lifecycle, it describes the PREVIOUS
    # state: on 2026-09-09 it called AMGN in-CURRENT while the rebuilt
    # lifecycle no longer held it, and Gate 4's conservation check then
    # compared two different days to each other.
    #
    # The lifecycle produces the state; the funnel explains it. That is
    # the only order in which both artifacts describe the same as-of.
    for label, cmd in (
        ("lifecycle", ["python", "-W", "ignore", "-m",
                       "backend.delivery.lifecycle.canonical_daily_lifecycle",
                       "--market", market, "--asof", asof]),
        ("why_not_current", ["python", "-W", "ignore", "-m",
                             "backend.delivery.lifecycle.why_not_current",
                             "--market", market]),
        ("r3_shadow", ["python", "-W", "ignore", "-m",
                       "backend.research.r3_program.shadow",
                       "--market", market, "--score"]),
        # § "research status update" · the last step of the daily run.
        # The registry is DERIVED from the artifacts each branch actually
        # produced, so "which branch is ready" is arithmetic rather than
        # an opinion someone has to maintain by hand.
        ("r3_evidence_registry",
         ["python", "-W", "ignore", "-m",
          "backend.research.r3_program.evidence_registry"]),
        # The clock answers what the registry cannot: did today MOVE
        # anything, and did anything go backwards. A pipeline can certify
        # green every morning while the evidence base sits still.
        ("r3_evidence_clock",
         ["python", "-W", "ignore", "-m",
          "backend.research.r3_program.evidence_clock"]),
    ):
        rc, out, err = _sh(cmd, root)
        steps.append({"step": label, "returncode": rc})
    return {"steps": steps, "elapsed_s": round(time.time() - t0, 2)}


def build_workbook(root: Path, market: str, asof: str) -> dict:
    t0 = time.time()
    try:
        from backend.delivery.sheets.workbook_two import build_two_sheet_workbook
        r = build_two_sheet_workbook(root, market, asof)
        r["workbook"].save(root / "reports" / "telegram"
                           / ("aegis_history_%s.xlsx" % market))
        dated = (root / "reports" / "telegram"
                 / ("AEGIS_%s_%s.xlsx" % (market.upper(), asof)))
        r["workbook"].save(dated)
        return {"ok": True, "dated": str(dated.name),
                "current_rows": r["current_rows"],
                "elapsed_s": round(time.time() - t0, 2)}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                "elapsed_s": round(time.time() - t0, 2)}


def validate(root: Path, market: str, asof: str) -> dict:
    t0 = time.time()
    try:
        from backend.delivery import delivery_gate as dg
        from backend.research.wave_regression import compute, emit
        rep = compute(root, market, asof)
        emit(root, rep)
        d = dg.decide(root, market)
        dg.emit(root, market, d)
        return {"regression": rep.verdict, "n_fail": rep.n_fail,
                "gate": d.verdict, "override": d.override_used,
                "elapsed_s": round(time.time() - t0, 2)}
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e),
                "elapsed_s": round(time.time() - t0, 2)}


# ── the run ─────────────────────────────────────────────────────────────

def run_market(root: Path, market: str, asof: str, trigger: str,
               do_refresh: bool, do_send: bool) -> RunContext:
    ctx = RunContext(market=market, requested_asof=asof, root=root,
                     trigger=trigger)

    readiness.check_data_ready(ctx)
    if ctx.blocked:
        return ctx
    # The world the stock trades inside · checked before it is scored.
    intermarket.check_intermarket(ctx)
    if ctx.blocked:
        return ctx
    readiness.check_features_ready(ctx)
    if ctx.blocked:
        return ctx

    score_universe(root, market)
    scoring.check_scores_ready(ctx)
    if ctx.blocked:
        return ctx

    build_lifecycle(root, market, asof)
    scoring.check_decision_ready(ctx)
    if ctx.blocked:
        return ctx

    cert.check_lifecycle_ready(ctx)
    if ctx.blocked:
        return ctx

    build_workbook(root, market, asof)
    # Field completeness is checked on the RENDERED sheet, after the
    # workbook exists and before anything is sent.
    completeness.check_fields_complete(ctx)
    if ctx.blocked:
        return ctx
    validate(root, market, asof)
    cert.check_delivery_ready(ctx)
    return ctx


def _load_telegram_env(root: Path) -> tuple:
    """Read credentials from .env.telegram the way every other sender does.

    The runner previously read os.environ only, so `--send` from a plain
    shell reported `message=False xlsx=False` and stopped there - a
    delivery that fails without saying why is the exact silent-failure
    pattern this whole contract exists to remove.
    """
    import os
    for name in (".env.telegram", ".env"):
        f = Path(root) / name
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(),
                                      v.strip().strip('"').strip("'"))
    return (os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("TELEGRAM_CHAT_ID", ""))


def send(root: Path, market: str, asof: str) -> dict:
    """Only reached when every gate passed."""
    out = {}
    tok, chat = _load_telegram_env(root)
    if not tok or not chat:
        why = ("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not found in the "
               "environment or in .env.telegram")
        return {"message": {"ok": False, "detail": why},
                "xlsx": {"ok": False, "detail": why}}
    try:
        from backend.delivery.telegram import canonical_message as cm
        ok, detail = cm.send(root, market)
        out["message"] = {"ok": ok, "detail": str(detail)[:120]}
    except Exception as e:
        out["message"] = {"ok": False, "detail": str(e)[:120]}
    try:
        import os
        import sys
        sys.path.insert(0, str(root))
        from scripts.telegram_command_center_send import _send_document
        p = (root / "reports" / "telegram"
             / ("AEGIS_%s_%s.xlsx" % (market.upper(), asof)))
        if not p.exists():
            out["xlsx"] = {"ok": False, "detail": "workbook not found: %s"
                           % p.name}
        else:
            ok, d = _send_document(tok, chat, p,
                                   "AEGIS %s · %s" % (market.upper(), asof))
            out["xlsx"] = {"ok": ok, "file": p.name,
                           "detail": ("" if ok else str(d)[:160])}
    except Exception as e:
        out["xlsx"] = {"ok": False, "detail": str(e)[:120]}
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS certified run")
    ap.add_argument("--market", choices=["india", "usa", "both"], default="both")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--trigger", default="manual",
                    choices=["manual", "scheduled", "ci"])
    ap.add_argument("--refresh", action="store_true",
                    help="produce today's substrate before the gates")
    ap.add_argument("--send", action="store_true",
                    help="deliver only if every gate passes")
    ap.add_argument("--no-parallel", action="store_true")
    ap.add_argument("--root", default=None)
    a = ap.parse_args()

    root = Path(a.root) if a.root else Path(__file__).resolve().parents[3]
    asof = resolve_asof(a.asof)
    markets = MARKETS if a.market == "both" else (a.market,)

    t0 = time.time()
    if a.refresh:
        acq = acquire(root, markets, asof, parallel=not a.no_parallel)
        print("acquisition · %.1fs · parallel=%s"
              % (acq["elapsed_s"], acq["parallel"]))
        for m, r in acq["results"].items():
            print("   %-6s ok=%s  %.1fs" % (m, r["ok"], r["elapsed_s"]))
            for st in r.get("steps", []):
                print("      %-16s %6.1fs  rc=%s"
                      % (st["step"], st.get("elapsed_s", 0.0),
                         st["returncode"]))

    rc = 0
    for m in markets:
        ctx = run_market(root, m, asof, a.trigger, a.refresh, a.send)
        text = cert.render(ctx)
        cert.emit(ctx, text)
        print("\n" + text)
        if ctx.blocked:
            rc = 1
            continue
        if a.send:
            s = send(root, m, asof)
            msg, xl = s.get("message", {}), s.get("xlsx", {})
            if msg.get("ok") and xl.get("ok"):
                print("  DELIVERED · message ✓ · xlsx %s ✓" % xl.get("file"))
            else:
                # Never report a bare False · say which half failed and why.
                print("  DELIVERY FAILED")
                if not msg.get("ok"):
                    print("    message: %s" % (msg.get("detail") or "unknown"))
                if not xl.get("ok"):
                    print("    xlsx   : %s" % (xl.get("detail") or "unknown"))
                rc = 1
    print("\nWALL CLOCK %.1fs" % (time.time() - t0))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
