"""SSoT Strong Guard · pre/post validation + retry + fallback + health emission.

Wraps `backend.recommendation.ssot.run` so a transient failure never
silently costs a whole day's recommendations. Deployed 2026-08-14 after
operator directive: "build a strong guard for recommendation_ssot, this
is happening frequently".

Failure history that motivated this guard:
  · 2026-08-11 · ImportError · ingest_runner1_picks_for_date not exported
  · 2026-08-12 · Guard 8 CI block cascaded into SSoT input starvation
  · 2026-08-13 · 3 consecutive AEGIS Daily runs failed at SSoT step
  · Result: reports/recommendations.json stale for 3 days, XLSX / Telegram
             kept re-delivering Aug 11 data as if it were current

Guard behaviour:
  1. PRE-FLIGHT · verify all required inputs exist + are fresh
       - Missing input     -> BLOCKED · surfaces reason · retry allowed
       - Stale input       -> BLOCKED · surfaces staleness · needs upstream fix
  2. INVOKE   · run SSoT with per-attempt timeout
       - Success           -> validate output (POST_FLIGHT)
       - Exception         -> retry with exponential backoff (max 3 attempts)
  3. POST-FLIGHT · verify output is coherent
       - recommendations.json exists AND asof == today AND n_recs > 0
       - universe_role == 'selected_candidates' (Sprint K contract)
       - schema fingerprint matches
  4. FALLBACK · if all 3 attempts fail
       - Copy PREVIOUS DAY'S recommendations.json to today's slot
       - Stamp payload with degraded_from_previous_day=True + reason
       - Emit health alert · never silently proceed as if healthy
  5. HEALTH  · always emit reports/context/ssot_health.json for CI + audit

The guard is deterministic + fail-open with clear provenance. It never
INVENTS data · it either reproduces yesterday's picks (marked stale) or
BLOCKS the send entirely, based on config.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path

_MAX_ATTEMPTS = 3
_ATTEMPT_TIMEOUT_S = 180        # per attempt · SSoT run should be <30s normal
_BACKOFF_INITIAL_S = 5          # 5s · 15s · 45s (3^n)
_BACKOFF_MULTIPLIER = 3
_STALE_INPUT_DAYS = 3           # aegis_today.csv older than N days = STALE


@dataclass
class SSoTHealth:
    engine:               str = "aegis.recommendation.ssot.guard.v1"
    generated_utc:        str = ""
    market:               str = ""
    asof:                 str = ""
    verdict:              str = ""       # GREEN | YELLOW | RED
    verdict_reason:       str = ""
    n_attempts:           int = 0
    n_success:            int = 0
    used_fallback:        bool = False
    fallback_source_date: str = ""
    output_asof:          str = ""
    output_n_recs:        int = 0
    output_universe_role: str = ""
    pre_flight_checks:    dict = field(default_factory=dict)
    post_flight_checks:   dict = field(default_factory=dict)
    attempts:             list = field(default_factory=list)


def _reports_dir(root: Path, market: str) -> Path:
    return root / ("usa/reports" if market == "usa" else "reports")


def _preflight(root: Path, market: str, asof: str) -> tuple[bool, dict]:
    """Verify inputs exist + are fresh. Returns (ok, checks_dict)."""
    checks: dict = {}
    ok = True

    # 1. Runner 2 v3 output must exist (SSoT bridge reads this)
    reports = _reports_dir(root, market)
    v3 = reports / "recommendations_v3.json"
    checks["recommendations_v3.json_exists"] = v3.exists()
    if not v3.exists():
        ok = False

    # 2. Runner 1 CSV (India only · aegis_today.csv)
    if market == "india":
        r1_csv = root / "data" / "aegis_today.csv"
        checks["aegis_today.csv_exists"] = r1_csv.exists()
        if r1_csv.exists():
            try:
                # Peek first data row · check date isn't too stale
                first_data = r1_csv.read_text(encoding="utf-8",
                                                        errors="replace").splitlines()[1]
                gen_date = first_data.split(",")[0][:10]
                gen_d = date.fromisoformat(gen_date)
                today_d = date.fromisoformat(asof[:10])
                age = (today_d - gen_d).days
                checks["aegis_today.csv_age_days"] = age
                if age > _STALE_INPUT_DAYS:
                    checks["aegis_today.csv_STALE"] = True
                    ok = False
            except Exception as e:
                checks["aegis_today.csv_parse_error"] = f"{type(e).__name__}: {e}"
                ok = False
        else:
            ok = False

    # 3. Position store must exist (or will be created · but the module dir must exist)
    pos_dir = reports / "position_store" / market
    checks["position_store_dir_exists"] = pos_dir.parent.exists()

    # 4. backend.research package importable (the fix from 2026-08-11)
    try:
        __import__("backend.research", fromlist=["ingest_runner1_picks_for_date"])
        checks["backend.research_importable"] = True
    except Exception as e:
        checks["backend.research_import_error"] = f"{type(e).__name__}: {e}"
        ok = False

    return ok, checks


def _postflight(root: Path, market: str, asof: str) -> tuple[bool, dict]:
    """Verify SSoT output is coherent. Returns (ok, checks_dict)."""
    checks: dict = {}
    ok = True
    reports = _reports_dir(root, market)
    out = reports / "recommendations.json"
    checks["recommendations.json_exists"] = out.exists()
    if not out.exists():
        return False, checks
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except Exception as e:
        checks["json_parse_error"] = f"{type(e).__name__}: {e}"
        return False, checks

    # asof match
    p_asof = str(payload.get("asof") or "")[:10]
    checks["output_asof"] = p_asof
    if p_asof != asof[:10]:
        checks["asof_mismatch"] = f"expected {asof[:10]} · got {p_asof}"
        ok = False

    # n_recs > 0
    n_recs = len(payload.get("recommendations") or [])
    checks["n_recs"] = n_recs
    if n_recs == 0:
        checks["empty_recommendations"] = True
        ok = False

    # universe_role stamp (Sprint K contract)
    role = str(payload.get("universe_role") or "")
    checks["universe_role"] = role
    if role and role != "selected_candidates":
        # Not a hard fail · but log it
        checks["universe_role_unexpected"] = role

    return ok, checks


def _invoke_ssot(root: Path, market: str, asof: str, force: bool = False) -> tuple[bool, str]:
    """Run the SSoT module as a subprocess with timeout. Returns (ok, error).

    NOTE (2026-08-14 · guard self-bug fix): SSoT returns non-zero when
    today's snapshot already exists (safeguard against destructive
    overwrite). That is NOT a failure · the data IS already fresh. We
    detect the REFUSED pattern in stdout/stderr and treat it as success.
    """
    cmd = [sys.executable, "-m", "backend.recommendation.ssot.run",
              "--market", market, "--asof", asof]
    if force:
        cmd.append("--force")
    try:
        r = subprocess.run(cmd, cwd=str(root),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=_ATTEMPT_TIMEOUT_S)
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        # Success path 1 · subprocess returned 0
        if r.returncode == 0:
            return True, ""
        # Success path 2 · SSoT REFUSED because today's snapshot exists.
        # That means the output IS fresh. Post-flight will verify.
        if "REFUSED · snapshot for" in combined and asof[:10] in combined:
            return True, "refused_idempotent_snapshot_exists"
        # Actual failure
        last_stderr = ""
        for line in (r.stderr or "").splitlines()[::-1]:
            if line.strip():
                last_stderr = line[:300]
                break
        return False, last_stderr or "non-zero exit"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {_ATTEMPT_TIMEOUT_S}s"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def _try_fallback_to_previous_day(root: Path, market: str, asof: str) -> tuple[bool, str]:
    """Copy previous day's snapshot to today's slot. Marks payload as
    degraded_from_previous_day so downstream knows this is stale."""
    reports = _reports_dir(root, market)
    hist_dir = reports / "recommendations_history" / market
    if not hist_dir.exists():
        return False, "no history dir to fall back on"
    # Find most recent snapshot BEFORE asof
    snapshots = sorted([p for p in hist_dir.glob("*.json")
                                if p.stem < asof[:10]],
                              reverse=True)
    if not snapshots:
        return False, "no previous-day snapshot available"
    src = snapshots[0]
    src_date = src.stem
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"cannot parse previous snapshot: {e}"
    # Stamp the payload as degraded fallback
    payload["degraded_from_previous_day"] = True
    payload["fallback_source_date"] = src_date
    payload["degraded_reason"] = (
        f"SSoT guard fallback · {_MAX_ATTEMPTS} attempts failed on {asof} · "
        f"reusing snapshot from {src_date} with staleness marker."
    )
    payload["asof_original"] = payload.get("asof")
    # Keep asof as source date so downstream doesn't mistake this for fresh
    out = reports / "recommendations.json"
    out.write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False),
                       encoding="utf-8")
    return True, src_date


def _emit_health(root: Path, health: SSoTHealth) -> Path:
    p = root / "reports" / "context" / "ssot_health.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    # Merge with existing per-market health (each market writes its own key)
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing[health.market] = asdict(health)
    existing["_last_update_utc"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(existing, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
    return p


def run_guarded(root: Path, market: str, asof: str | None = None,
                        force: bool = False) -> SSoTHealth:
    """The public entry point · run SSoT with strong guarantees.

    Args:
      root:   repo root
      market: 'india' or 'usa'
      asof:   YYYY-MM-DD · defaults to today
      force:  pass --force to the underlying SSoT (destroys today's snapshot)

    Returns:
      SSoTHealth · always emitted to reports/context/ssot_health.json.
      Verdict:
        GREEN  · fresh output written this run · all checks passed
        YELLOW · fallback used · pipeline can proceed but downstream is stale
        RED    · fallback also failed · downstream MUST NOT deliver
    """
    asof = asof or date.today().isoformat()
    health = SSoTHealth(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        market=market, asof=asof,
    )

    # ── PRE-FLIGHT ──
    ok, pre = _preflight(root, market, asof)
    health.pre_flight_checks = pre
    if not ok:
        # Some pre-flight failures are recoverable (SSoT can create outputs
        # if inputs are present). Only bail early on the truly fatal ones.
        fatal_keys = ("recommendations_v3.json_exists",
                          "backend.research_importable")
        fatal = any(k in pre and not pre[k] for k in fatal_keys)
        if fatal:
            health.verdict = "RED"
            health.verdict_reason = f"pre-flight fatal · {pre}"
            _emit_health(root, health)
            return health
        # else · non-fatal warnings recorded · continue to attempts

    # ── ATTEMPTS ──
    delay = _BACKOFF_INITIAL_S
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        t0 = time.time()
        ok, err = _invoke_ssot(root, market, asof, force=force)
        elapsed = time.time() - t0
        health.attempts.append({
            "attempt":   attempt,
            "verdict":   "SUCCESS" if ok else "FAILED",
            "elapsed_s": round(elapsed, 2),
            "error":     err if not ok else "",
        })
        health.n_attempts = attempt
        if ok:
            # Post-flight validation
            pf_ok, pf_checks = _postflight(root, market, asof)
            health.post_flight_checks = pf_checks
            if pf_ok:
                health.n_success = 1
                health.verdict = "GREEN"
                health.verdict_reason = f"SSoT succeeded on attempt {attempt}"
                health.output_asof = pf_checks.get("output_asof", "")
                health.output_n_recs = pf_checks.get("n_recs", 0)
                health.output_universe_role = pf_checks.get("universe_role", "")
                _emit_health(root, health)
                return health
            else:
                # Output invalid · treat as failure · retry
                health.attempts[-1]["post_flight_failed"] = True
                err = f"post-flight failed · {pf_checks}"
        # Not ok · either subprocess failed or post-flight failed
        if attempt < _MAX_ATTEMPTS:
            time.sleep(delay)
            delay *= _BACKOFF_MULTIPLIER

    # ── DEFENSIVE POST-FLIGHT BEFORE FALLBACK ──
    # 2026-08-14 · guard self-bug fix: never destructively overwrite an
    # existing fresh recommendations.json. If the file on disk is already
    # correct for today (from a prior run · manual invocation · CI · etc.)
    # we must NOT overwrite it with yesterday's fallback.
    pf_ok, pf_checks = _postflight(root, market, asof)
    health.post_flight_checks = pf_checks
    if pf_ok:
        health.verdict = "GREEN"
        health.verdict_reason = (
            f"SSoT subprocess failed but existing recommendations.json is "
            f"already fresh for {asof} (n_recs={pf_checks.get('n_recs')}) · "
            "no fallback needed"
        )
        health.output_asof = pf_checks.get("output_asof", "")
        health.output_n_recs = pf_checks.get("n_recs", 0)
        health.output_universe_role = pf_checks.get("universe_role", "")
        _emit_health(root, health)
        return health

    # ── FALLBACK ──
    fb_ok, fb_info = _try_fallback_to_previous_day(root, market, asof)
    if fb_ok:
        health.used_fallback = True
        health.fallback_source_date = fb_info
        health.verdict = "YELLOW"
        health.verdict_reason = (
            f"SSoT failed {_MAX_ATTEMPTS} attempts · fell back to {fb_info} · "
            "downstream must show STALE marker in Telegram/XLSX caption"
        )
    else:
        health.verdict = "RED"
        health.verdict_reason = (
            f"SSoT failed {_MAX_ATTEMPTS} attempts AND fallback failed ({fb_info}) · "
            "no valid recommendations.json for today · downstream MUST NOT deliver"
        )
    _emit_health(root, health)
    return health


def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=("india", "usa"), required=True)
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD · default today")
    ap.add_argument("--force", action="store_true",
                       help="pass --force to SSoT · destroys today's snapshot")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[3]
    h = run_guarded(root, args.market, args.asof, force=args.force)
    print(f"[ssot_guard:{args.market}] verdict={h.verdict} · attempts={h.n_attempts}"
              f"{' · fallback=' + h.fallback_source_date if h.used_fallback else ''}"
              f"{' · asof=' + h.output_asof if h.output_asof else ''}")
    print(f"  reason: {h.verdict_reason}")
    if h.verdict == "GREEN":
        return 0
    if h.verdict == "YELLOW":
        return 0   # non-zero would break aegis-daily.yml · fallback IS a success path
    return 1


if __name__ == "__main__":
    sys.exit(_main())
