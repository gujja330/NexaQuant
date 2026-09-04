"""
Sprint 7.6 · Replay Controller.

Deterministically replays a per-market date range through the pipeline stages
that CAN operate historically today:

    features   → build_and_persist(asof=D) for each historical D not already snapshotted
    macro      → skipped-with-note (macro raw prices not in repo history — Sprint 7.7 will
                 add a yfinance fetcher for CL=F, GC=F, ^TNX, etc.)
    factor     → skipped-with-note (depends on macro)
    learning   → backfilled ONLY where recommendation_history has rows (empty on day 1)

Runners for Rec/Risk/Portfolio/Execution do not yet accept --asof (they read
"latest" from the Feature Store). Full-pipeline replay is deferred to Sprint
7.7. This sprint delivers the framework + feature-snapshot backfill (which
IS the biggest unlock) + integrity + reports + quality scoring.

CLI:
    python -m backend.replay backfill --from 2026-05-01 --to 2026-07-21 \
        --market usa --steps features,macro,factor,learning --resume
"""
from __future__ import annotations
import argparse
import io
import json
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import pandas as pd

from .types import (
    ReplayPlan, ReplayResult, HistoryValidation, WalkForwardReadiness,
    TARGET_HISTORY_FILES,
)
from .integrity import (
    validate_history, enumerate_trading_days, trading_days_from_raw,
)
from .data_quality import (
    compute_row_quality_score, quality_verdict, batch_average_quality,
)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _market_paths(repo_root: Path, market: str) -> Dict[str, Path]:
    """Standardize path roots per market."""
    if market == "india":
        return {
            "reports":   repo_root / "reports",
            "features":  repo_root / "features" / "india",
            "raw":       repo_root / "data" / "raw" / "india",
            "reference": repo_root / "data" / "raw" / "india" / "NSEI_D1.parquet",
        }
    else:
        return {
            "reports":   repo_root / "usa" / "reports",
            "features":  repo_root / "features" / "usa",
            "raw":       repo_root / "usa" / "data" / "raw" / "us",
            "reference": repo_root / "usa" / "data" / "raw" / "us" / "_IDX_GSPC_D1.parquet",
        }


class ReplayController:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def run(self, plan: ReplayPlan) -> ReplayResult:
        p = _market_paths(self.repo_root, plan.market)
        canonical = trading_days_from_raw(p["reference"], plan.date_from, plan.date_to)
        trading_days = sorted(canonical) if canonical else enumerate_trading_days(
            plan.date_from, plan.date_to)

        print(f"[replay] market={plan.market} range={plan.date_from}..{plan.date_to} "
              f"steps={plan.steps} n_trading_days={len(trading_days)}")

        step_results: Dict[str, Dict[str, Any]] = {}

        if "features" in plan.steps:
            step_results["features"] = self._backfill_features(
                plan.market, p, trading_days, resume=plan.resume)

        if "macro" in plan.steps:
            step_results["macro"] = self._backfill_macro_placeholder(plan.market, p, trading_days)

        if "factor" in plan.steps:
            step_results["factor"] = self._backfill_factor_placeholder(plan.market, p, trading_days)

        if "recommendation" in plan.steps or "risk" in plan.steps or "portfolio" in plan.steps:
            step_results["pipeline_replay"] = self._backfill_pipeline(
                plan.market, p, trading_days, plan.steps, resume=plan.resume)

        if "learning" in plan.steps:
            step_results["learning"] = self._backfill_learning(plan.market, p, trading_days)

        if "walkforward" in plan.steps:
            step_results["walkforward"] = self._run_walk_forward(
                plan.market, plan.date_from, plan.date_to)

        integrity = self._validate_all_histories(plan.market, p, set(trading_days))
        readiness = self._walk_forward_readiness(plan.market, p, trading_days, integrity)

        result = ReplayResult(
            market=plan.market,
            date_from=plan.date_from, date_to=plan.date_to,
            n_trading_days=len(trading_days),
            step_results=step_results,
            integrity=integrity,
            walk_forward_readiness=readiness,
            notes=[],
        )

        self._write_reports(plan.market, p, result)
        return result

    # ── steps ────────────────────────────────────────────────

    def _backfill_features(self, market: str, p: Dict[str, Path],
                              trading_days: List[date], *, resume: bool) -> Dict[str, Any]:
        """Feature Store's build_and_persist(asof=D) writes features/<market>/<D>.parquet."""
        from backend.canonical import INDIA_PROFILE, USA_PROFILE
        from backend.feature_store import build_and_persist

        profile = INDIA_PROFILE if market == "india" else USA_PROFILE
        n_ok = n_skipped = n_failed = 0
        failed_dates: List[str] = []
        t0 = time.time()

        for d in trading_days:
            target = p["features"] / f"{d.isoformat()}.parquet"
            if resume and target.exists():
                n_skipped += 1
                continue
            try:
                build_and_persist(self.repo_root, profile, asof=d)
                n_ok += 1
            except Exception as e:
                n_failed += 1
                failed_dates.append(f"{d.isoformat()}: {type(e).__name__}: {str(e)[:80]}")

        elapsed = round(time.time() - t0, 2)
        print(f"[replay/features] {market}: ok={n_ok} skipped={n_skipped} "
              f"failed={n_failed} elapsed={elapsed}s")
        return {
            "n_ok": n_ok, "n_skipped": n_skipped, "n_failed": n_failed,
            "elapsed_s": elapsed, "failed_samples": failed_dates[:10],
        }

    def _backfill_macro_placeholder(self, market: str, p: Dict[str, Path],
                                       trading_days: List[date]) -> Dict[str, Any]:
        """
        Macro backfill needs historical raw prices for CL=F, GC=F, ^TNX, UUP, etc.
        Those symbols are not persisted in the raw store today (only ^VIX for USA).
        Sprint 7.7 will add a yfinance-backed fetcher; Sprint 7.6 leaves a
        placeholder + honest reporting.
        """
        hist = p["reports"] / "macro_history.parquet"
        n_existing = 0
        if hist.exists():
            try:
                df = pd.read_parquet(hist)
                if "market" in df.columns:
                    n_existing = int((df["market"] == market).sum())
                else:
                    n_existing = len(df)
            except Exception:
                n_existing = 0
        return {
            "backfilled_rows": 0,
            "existing_rows": n_existing,
            "status": "deferred-to-sprint-7.7",
            "reason": "historical raw prices for macro symbols (CL=F, GC=F, ^TNX, UUP, ...) "
                        "not present in repo; needs yfinance fetcher first",
        }

    def _backfill_factor_placeholder(self, market: str, p: Dict[str, Path],
                                        trading_days: List[date]) -> Dict[str, Any]:
        """Factor library depends on macro history; same deferral."""
        hist = p["reports"] / "factor_library_history.parquet"
        n_existing = 0
        if hist.exists():
            try:
                df = pd.read_parquet(hist)
                if "market" in df.columns:
                    n_existing = int((df["market"] == market).sum())
                else:
                    n_existing = len(df)
            except Exception:
                n_existing = 0
        return {
            "backfilled_rows": 0,
            "existing_rows": n_existing,
            "status": "deferred-to-sprint-7.7",
            "reason": "factor library depends on macro history",
        }

    def _backfill_pipeline(self, market: str, p: Dict[str, Path],
                               trading_days: List[date], steps: List[str],
                               *, resume: bool) -> Dict[str, Any]:
        """
        Sprint 7.7 · Full-pipeline replay per historical asof.

        For each date D in `trading_days`, load features/<market>/<D>.parquet
        and drive Rec → Risk → Portfolio engines with `asof=D`, appending each
        result to its respective history parquet.

        Lookahead guard runs on every payload before append. Any payload with
        `asof > D` fails the row (fail-open: row skipped, guardrail counter++).
        """
        from backend.persistence import append_snapshot_row
        from backend.replay.engine_drivers import (
            drive_recommendation, drive_risk, drive_portfolio,
        )
        from backend.replay.lookahead_guard import validate_payload_no_future

        do_rec  = "recommendation" in steps
        do_risk = "risk" in steps
        do_port = "portfolio" in steps

        n_ok_rec = n_ok_risk = n_ok_port = 0
        n_fail_rec = n_fail_risk = n_fail_port = 0
        n_leak = n_skip_no_features = 0
        first_errors: List[str] = []
        t0 = time.time()

        for d in trading_days:
            feat_path = p["features"] / f"{d.isoformat()}.parquet"
            if not feat_path.exists():
                n_skip_no_features += 1
                continue
            try:
                features_df = pd.read_parquet(feat_path)
            except Exception as e:
                n_skip_no_features += 1
                if len(first_errors) < 5:
                    first_errors.append(f"{d}: features unreadable: {e}")
                continue

            rec_payload = None
            if do_rec:
                rec_payload = drive_recommendation(
                    repo_root=self.repo_root, market=market, asof=d, features_df=features_df)
                if not rec_payload or "__error__" in rec_payload:
                    n_fail_rec += 1
                    if rec_payload and len(first_errors) < 5:
                        first_errors.append(f"{d} rec: {rec_payload['__error__'][:120]}")
                else:
                    leaks = validate_payload_no_future(rec_payload, replay_asof=d)
                    if leaks:
                        n_leak += 1
                        if len(first_errors) < 5:
                            first_errors.append(f"{d} rec leaks: {leaks[:2]}")
                    else:
                        append_snapshot_row(rec_payload,
                            p["reports"] / "recommendation_history.parquet")
                        n_ok_rec += 1

            risk_payload = None
            if do_risk and rec_payload and "__error__" not in rec_payload:
                risk_payload = drive_risk(
                    repo_root=self.repo_root, market=market, asof=d,
                    features_df=features_df, recommendations_payload=rec_payload)
                if not risk_payload or "__error__" in risk_payload:
                    n_fail_risk += 1
                    if risk_payload and len(first_errors) < 5:
                        first_errors.append(f"{d} risk: {risk_payload['__error__'][:120]}")
                else:
                    persisted = {k: v for k, v in risk_payload.items() if not k.startswith("_")}
                    leaks = validate_payload_no_future(persisted, replay_asof=d)
                    if leaks:
                        n_leak += 1
                    else:
                        append_snapshot_row(persisted,
                            p["reports"] / "risk_history.parquet")
                        n_ok_risk += 1

            if do_port and risk_payload and "__error__" not in risk_payload:
                port_payload = drive_portfolio(
                    repo_root=self.repo_root, market=market, asof=d,
                    risk_payload=risk_payload)
                if not port_payload or "__error__" in port_payload:
                    n_fail_port += 1
                    if port_payload and len(first_errors) < 5:
                        first_errors.append(f"{d} port: {port_payload['__error__'][:120]}")
                else:
                    leaks = validate_payload_no_future(port_payload, replay_asof=d)
                    if leaks:
                        n_leak += 1
                    else:
                        append_snapshot_row(port_payload,
                            p["reports"] / "portfolio_history.parquet")
                        n_ok_port += 1

        elapsed = round(time.time() - t0, 2)
        print(f"[replay/pipeline] {market}: rec={n_ok_rec}/{n_ok_rec+n_fail_rec} "
              f"risk={n_ok_risk}/{n_ok_risk+n_fail_risk} "
              f"port={n_ok_port}/{n_ok_port+n_fail_port} "
              f"skipped(no-features)={n_skip_no_features} leaks={n_leak} elapsed={elapsed}s")
        return {
            "n_ok_recommendation": n_ok_rec, "n_failed_recommendation": n_fail_rec,
            "n_ok_risk": n_ok_risk, "n_failed_risk": n_fail_risk,
            "n_ok_portfolio": n_ok_port, "n_failed_portfolio": n_fail_port,
            "n_skipped_no_features": n_skip_no_features,
            "n_lookahead_leaks_blocked": n_leak,
            "elapsed_s": elapsed,
            "first_errors": first_errors[:5],
        }

    def _run_walk_forward(self, market: str, date_from: date, date_to: date) -> Dict[str, Any]:
        from backend.replay.walk_forward import run_walk_forward
        try:
            result = run_walk_forward(
                repo_root=self.repo_root, market=market,
                date_from=date_from, date_to=date_to,
            )
            summary = result.get("summary", {})
            metrics = result.get("metrics", {})
            print(f"[replay/walkforward] {market}: verdict={summary.get('verdict')} "
                  f"n_recs={metrics.get('n_recommendations')} "
                  f"n_closed={metrics.get('n_closed_positions')} "
                  f"win_rate={metrics.get('win_rate_pct')} sharpe={metrics.get('sharpe')}")
            return {"status": "executed", **summary,
                     "sharpe": metrics.get("sharpe"),
                     "annual_return_pct": metrics.get("annual_return_pct"),
                     "max_drawdown_pct": metrics.get("max_drawdown_pct"),
                     "win_rate_pct": metrics.get("win_rate_pct")}
        except Exception as e:
            print(f"[replay/walkforward] {market}: ERROR {e}")
            return {"status": "failed", "error": str(e)}

    def _backfill_learning(self, market: str, p: Dict[str, Path],
                              trading_days: List[date]) -> Dict[str, Any]:
        """
        Sprint 7.7 · Learning corpus backfill from historical rec ledger.

        For every row in recommendation_history.parquet whose (asof + horizon)
        has already closed by today's wall-clock, compute the realized return
        from the raw ticker parquets and append to learning_corpus.parquet.
        """
        from backend.replay.engine_drivers import drive_learning_outcomes
        from backend.persistence import append_snapshot_row

        rec_hist = p["reports"] / "recommendation_history.parquet"
        corpus_path = p["reports"] / "learning_corpus.parquet"

        n_rec = 0
        rec_payloads: List[Dict[str, Any]] = []
        if rec_hist.exists():
            try:
                df = pd.read_parquet(rec_hist)
                if "market" in df.columns:
                    df = df[df["market"] == market]
                n_rec = len(df)
                # Reconstruct payloads: recommendations column was JSON-encoded by history_writer
                for _, row in df.iterrows():
                    recs_raw = row.get("recommendations")
                    if isinstance(recs_raw, str):
                        try:
                            recs_list = json.loads(recs_raw)
                        except Exception:
                            recs_list = []
                    elif isinstance(recs_raw, list):
                        recs_list = recs_raw
                    else:
                        recs_list = []
                    rec_payloads.append({
                        "market": market,
                        "asof": str(row.get("asof")),
                        "regime": row.get("regime"),
                        "recommendations": recs_list,
                    })
            except Exception:
                pass

        n_before = 0
        if corpus_path.exists():
            try:
                df = pd.read_parquet(corpus_path)
                if "market" in df.columns:
                    n_before = int((df["market"] == market).sum())
                else:
                    n_before = len(df)
            except Exception:
                pass

        outcomes = drive_learning_outcomes(
            repo_root=self.repo_root, market=market,
            rec_payloads=rec_payloads, horizon_days=20,
        )

        # Append each closed outcome to learning_corpus.parquet
        n_new = 0
        for row in outcomes.get("outcomes", []):
            # Add dedup key so persistence's (market, asof) rule targets rec_asof
            row_out = {**row, "asof": row["rec_asof"]}
            r = append_snapshot_row(row_out, corpus_path)
            if r is not None:
                n_new += 1

        n_after = 0
        if corpus_path.exists():
            try:
                df = pd.read_parquet(corpus_path)
                if "market" in df.columns:
                    n_after = int((df["market"] == market).sum())
                else:
                    n_after = len(df)
            except Exception:
                pass

        return {
            "recommendation_history_rows": n_rec,
            "learning_corpus_rows_before": n_before,
            "learning_corpus_rows_after": n_after,
            "outcomes_computed": outcomes.get("n_outcomes", 0),
            "open_positions": outcomes.get("n_open_positions", 0),
            "horizon_days": outcomes.get("horizon_days", 20),
            # CEO 2026-09-04 · honesty guard · outcomes-backfilled is NOT the same
            # as "learning step in production". Report "deferred-to-sprint-7.7"
            # regardless of outcome count · n_outcomes above conveys the count separately.
            "status": "deferred-to-sprint-7.7",
        }

    # ── integrity + readiness ────────────────────────────────

    def _validate_all_histories(self, market: str, p: Dict[str, Path],
                                    expected_dates: Set[date]) -> Dict[str, Any]:
        files = [
            "macro_history.parquet",
            "factor_library_history.parquet",
            "recommendation_history.parquet",
            "risk_history.parquet",
            "portfolio_history.parquet",
            "execution_history.parquet",
            "learning_history.parquet",
        ]
        validations: List[HistoryValidation] = []
        for fname in files:
            v = validate_history(
                p["reports"] / fname, market=market,
                expected_dates=expected_dates if fname == "macro_history.parquet" else None,
            )
            validations.append(v)

        return {
            "validated_utc": _now_utc(),
            "market": market,
            "n_files_checked": len(validations),
            "n_pass": sum(1 for v in validations if v.verdict == "PASS"),
            "n_warn": sum(1 for v in validations if v.verdict == "WARN"),
            "n_fail": sum(1 for v in validations if v.verdict == "FAIL"),
            "per_file": [asdict(v) for v in validations],
        }

    def _walk_forward_readiness(self, market: str, p: Dict[str, Path],
                                   trading_days: List[date],
                                   integrity: Dict[str, Any]) -> Dict[str, Any]:
        def _rows(fname: str) -> int:
            path = p["reports"] / fname
            if not path.exists():
                return 0
            try:
                df = pd.read_parquet(path)
                if "market" in df.columns:
                    return int((df["market"] == market).sum())
                return len(df)
            except Exception:
                return 0

        rec_rows   = _rows("recommendation_history.parquet")
        exec_rows  = _rows("execution_history.parquet")
        learn_rows = _rows("learning_corpus.parquet")
        factor_rows= _rows("factor_library_history.parquet")
        macro_rows = _rows("macro_history.parquet")

        # Feature snapshots — how many days do we actually have?
        feats = sorted(p["features"].glob("*.parquet")) if p["features"].exists() else []
        feats = [f for f in feats if not f.stem.endswith("_rebuilt") and "rebuilt" not in f.stem]
        historical_days = len(feats)

        n_missing = sum(v.get("n_missing_trading_days", 0) for v in integrity.get("per_file", []))
        n_dup     = sum(v.get("n_duplicate_dates", 0)      for v in integrity.get("per_file", []))

        # Verdict: READY only if we have enough history AND ledgers exist.
        # Sprint 7.6 is expected to produce PARTIAL — features backfilled but rec/risk/portfolio
        # awaiting Sprint 7.7 runner refactor.
        if historical_days >= 60 and rec_rows >= 60:
            verdict = "READY"
        elif historical_days >= 20:
            verdict = "PARTIAL"
        else:
            verdict = "NOT_READY"

        notes = []
        if rec_rows == 0:
            notes.append("recommendation_history empty — Sprint 7.7 runner-driver work required")
        if macro_rows == 0:
            notes.append("macro_history empty — Sprint 7.7 yfinance macro-symbol fetcher required")
        if historical_days > 0:
            notes.append(f"feature snapshots backfilled: {historical_days} days")

        return {
            "market": market,
            "historical_days": historical_days,
            "recommendation_rows": rec_rows,
            "execution_rows": exec_rows,
            "learning_corpus_rows": learn_rows,
            "factor_library_rows": factor_rows,
            "macro_history_rows": macro_rows,
            "missing_dates": n_missing,
            "duplicate_dates": n_dup,
            "data_quality_score_avg": 0.0,        # populated when macro/factor rows carry it
            "verdict": verdict,
            "notes": notes,
        }

    # ── reports ──────────────────────────────────────────────

    def _write_reports(self, market: str, p: Dict[str, Path],
                          result: ReplayResult) -> None:
        outdir = p["reports"]
        outdir.mkdir(parents=True, exist_ok=True)

        def _write(name: str, payload: Dict[str, Any]) -> None:
            path = outdir / name
            path.write_text(json.dumps(payload, indent=2, default=str),
                              encoding="utf-8")
            print(f"[replay] wrote {path.relative_to(self.repo_root)}")

        _write("backfill_summary.json", {
            "engine": "aegis.replay.v1", "version": "1.0.0",
            "market": market,
            "run_utc": _now_utc(),
            "asof": result.date_to.isoformat(),
            "date_range": f"{result.date_from.isoformat()}..{result.date_to.isoformat()}",
            "n_trading_days": result.n_trading_days,
            "step_results": result.step_results,
            "notes": result.notes,
        })

        _write("history_validation.json", {
            "engine": "aegis.replay.v1", "version": "1.0.0",
            "market": market, "run_utc": _now_utc(),
            "asof": result.date_to.isoformat(),
            **(result.integrity or {}),
        })

        _write("walkforward_readiness.json", {
            "engine": "aegis.replay.v1", "version": "1.0.0",
            "run_utc": _now_utc(),
            "asof": result.date_to.isoformat(),
            **(result.walk_forward_readiness or {}),
        })

        # Factor library summary + learning backfill summary — even for the
        # deferred steps we emit an honest empty-report so downstream tooling
        # (Sprint 8 + Sprint 9) can rely on the files being present.
        _write("factor_library_summary.json", {
            "engine": "aegis.replay.v1", "version": "1.0.0",
            "market": market, "run_utc": _now_utc(),
            "asof": result.date_to.isoformat(),
            "step_result": result.step_results.get("factor", {}),
        })
        _write("learning_backfill_summary.json", {
            "engine": "aegis.replay.v1", "version": "1.0.0",
            "market": market, "run_utc": _now_utc(),
            "asof": result.date_to.isoformat(),
            "step_result": result.step_results.get("learning", {}),
        })


def run_backfill(*, repo_root: Path, market: str,
                    date_from: date, date_to: date,
                    steps: Sequence[str] = ("features", "macro", "factor", "learning"),
                    resume: bool = True, parallel: int = 1) -> ReplayResult:
    plan = ReplayPlan(
        market=market, date_from=date_from, date_to=date_to,
        steps=list(steps), resume=resume, parallel=parallel,
    )
    return ReplayController(repo_root).run(plan)


# ── CLI ───────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(prog="python -m backend.replay",
                                        description="AEGIS Sprint 7.6 · historical backfill controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bf = sub.add_parser("backfill", help="run a per-market backfill window")
    bf.add_argument("--from", dest="date_from", required=True, type=_parse_date, help="YYYY-MM-DD")
    bf.add_argument("--to",   dest="date_to",   required=True, type=_parse_date, help="YYYY-MM-DD")
    bf.add_argument("--market", required=True, choices=["india", "usa"])
    bf.add_argument("--steps", default="features,macro,factor,recommendation,risk,portfolio,learning,walkforward",
                     help="comma-separated: features,macro,factor,recommendation,risk,portfolio,learning,walkforward")
    bf.add_argument("--resume", action="store_true", default=True,
                     help="skip already-persisted snapshots (default true)")
    bf.add_argument("--no-resume", action="store_false", dest="resume",
                     help="force recompute even if snapshots exist")
    bf.add_argument("--parallel", type=int, default=1)
    bf.add_argument("--repo-root", default=".")

    args = parser.parse_args(argv)
    if args.cmd == "backfill":
        steps = [s.strip() for s in args.steps.split(",") if s.strip()]
        result = run_backfill(
            repo_root=Path(args.repo_root).resolve(),
            market=args.market,
            date_from=args.date_from, date_to=args.date_to,
            steps=steps, resume=args.resume, parallel=args.parallel,
        )
        rd = result.walk_forward_readiness or {}
        print(f"[replay] verdict={rd.get('verdict')} · historical_days={rd.get('historical_days')} "
              f"· rec={rd.get('recommendation_rows')} · macro={rd.get('macro_history_rows')} "
              f"· factor={rd.get('factor_library_rows')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
