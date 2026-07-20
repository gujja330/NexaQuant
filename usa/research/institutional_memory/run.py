"""AEGIS USA · Institutional Memory v1.0.

Archives every daily run into usa/data/archive/YYYY/MM/DD/bundle/ and
maintains reports/recommendation_lifecycle.json + missed_opportunities.json
+ recommendation_history.json.

USD everywhere. Content-addressed manifests. Never overwrites.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


_ROOT    = Path(__file__).resolve().parents[3]
_USA     = Path(__file__).resolve().parents[2]
ARCHIVE  = _USA / "data" / "archive"
REPORTS  = _USA / "reports"

BUNDLE = [
    "recommendations.json",
    "investment_intelligence.json",
    "intelligence_summary.json",
    "intelligence_conflicts.json",
    "price_context.json",
    "risk_latest.json",
    "validation_latest.json",
    "stock_validation.json",
    "universe.json",
]


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 15), b""):
            h.update(chunk)
    return h.hexdigest()


def _code_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_ROOT),
                             capture_output=True, text=True, timeout=5)
        return r.stdout.strip()[:12] if r.returncode == 0 else "(unknown)"
    except Exception:
        return "(unknown)"


def archive_bundle() -> dict:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    y, m, d = day.split("-")
    target = ARCHIVE / y / m / d / "bundle"
    if target.exists():
        # Immutable — return existing manifest
        mp = target.parent / "manifest.json"
        if mp.exists():
            return {"already_archived": True, **json.loads(mp.read_text(encoding="utf-8"))}
    target.mkdir(parents=True, exist_ok=True)

    files = []
    total = 0
    for name in BUNDLE:
        src = REPORTS / name
        if not src.exists():
            files.append({"name": name, "present": False, "sha256": None, "bytes": 0})
            continue
        dst = target / name
        shutil.copy2(src, dst)
        h = _sha256(dst); b = dst.stat().st_size
        total += b
        files.append({"name": name, "present": True, "sha256": h, "bytes": b})

    manifest = {
        "market":       "USA",
        "run_date":     day,
        "run_utc":      datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "code_sha":     _code_sha(),
        "engine":       "usa_institutional_memory",
        "version":      "v1.0",
        "n_files":      sum(1 for f in files if f["present"]),
        "total_bytes":  total,
        "files":        files,
        "immutable":    True,
    }
    (target.parent / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def list_days() -> list[str]:
    days = []
    if not ARCHIVE.exists(): return days
    for y in sorted(ARCHIVE.iterdir()):
        if not y.is_dir(): continue
        for mo in sorted(y.iterdir()):
            if not mo.is_dir(): continue
            for d in sorted(mo.iterdir()):
                if (d / "manifest.json").exists():
                    days.append(f"{y.name}-{mo.name}-{d.name}")
    return sorted(days)


def build_lifecycle() -> dict:
    """Walk archive → per-ticker state machine (day 1 → all ACTIVE)."""
    days = list_days()
    if not days:
        return {"n_total": 0, "empty": True, "by_ticker": {}, "coverage": {"n_days_archived": 0}}

    first_seen = {}
    last_snap  = {}
    today_set  = set()

    for day in days:
        y, m, d = day.split("-")
        bpath = ARCHIVE / y / m / d / "bundle" / "recommendations.json"
        if not bpath.exists(): continue
        j = json.loads(bpath.read_text(encoding="utf-8"))
        snap = {str(r.get("ticker")): r for r in (j.get("recommendations") or []) if r.get("ticker")}
        for t, r in snap.items():
            last_snap[t] = r
            if t not in first_seen:
                first_seen[t] = day
        if day == days[-1]:
            today_set = set(snap.keys())

    by_ticker: dict[str, dict] = {}
    for t in sorted(first_seen.keys()):
        fs = first_seen[t]
        state = "ACTIVE" if t in today_set else "REMOVED"
        # Days active
        try:
            days_active = (datetime.strptime(days[-1], "%Y-%m-%d") -
                             datetime.strptime(fs, "%Y-%m-%d")).days + 1
        except Exception:
            days_active = 1
        by_ticker[t] = {
            "first_seen_date": fs,
            "days_active":     days_active,
            "state":           state,
            "realized_return": None,
            "alpha_capture":   None,
        }

    return {
        "n_total":     len(by_ticker),
        "by_state":    {"ACTIVE": sum(1 for v in by_ticker.values() if v["state"] == "ACTIVE")},
        "n_active":    sum(1 for v in by_ticker.values() if v["state"] == "ACTIVE"),
        "n_exited":    0,
        "coverage":    {"n_days_archived": len(days), "first_day": days[0], "last_day": days[-1]},
        "by_ticker":   by_ticker,
    }


def build_recommendation_history() -> dict:
    """Per-ticker recommendation timeline across all archived days."""
    days = list_days()
    universe = json.loads((_USA / "reports" / "universe.json").read_text(encoding="utf-8"))
    universe_set = {str(t.get("symbol")) for t in (universe.get("tickers") or [])}

    tickers_out: dict[str, dict] = {}
    for t in sorted(universe_set):
        timeline = []
        for day in days:
            y, m, d = day.split("-")
            bp = ARCHIVE / y / m / d / "bundle"
            rp = bp / "recommendations.json"
            pp = bp / "price_context.json"
            if not rp.exists(): continue
            j = json.loads(rp.read_text(encoding="utf-8"))
            rec = next((r for r in (j.get("recommendations") or []) if str(r.get("ticker")) == t), None)
            price = None
            if pp.exists():
                pj = json.loads(pp.read_text(encoding="utf-8"))
                price = (pj.get("tickers") or {}).get(t, {}).get("cmp")
            if rec:
                ee = rec.get("entry_exit") or {}
                timeline.append({
                    "date":       day,
                    "action":     rec.get("recommendation"),
                    "score":      rec.get("composite_decision_score"),
                    "confidence": rec.get("confidence"),
                    "cmp":        price or ee.get("latest_close"),
                    "target_1":   ee.get("target_1"),
                    "stop_loss":  ee.get("stop_loss"),
                    "in_universe": True,
                })
        tickers_out[t] = {
            "ticker":        t,
            "n_days_seen":   len(timeline),
            "timeline":      timeline,
            "closed_trades": [],
            "n_closed":      0,
            "accuracy":      {
                "n_recommendations": 0,
                "n_correct":         0,
                "n_incorrect":       0,
                "accuracy":          None,
                "avg_return_pct":    None,
                "median_return_pct": None,
                "best_return_pct":   None,
                "worst_return_pct":  None,
            },
        }

    return {
        "market":           "USA",
        "n_tickers":        len(tickers_out),
        "n_days_archived":  len(days),
        "coverage_days":    days,
        "tickers":          tickers_out,
        "n_tickers_with_history": 0,
        "global_avg_accuracy":     None,
    }


def build_missed() -> dict:
    """Day 1 baseline: no forward returns yet."""
    return {
        "engine":         "usa_missed_opportunities",
        "version":        "v1.0",
        "n_days_scanned": len(list_days()),
        "lookbacks":      [5, 20, 60],
        "threshold_pct":  0.08,
        "n_events":       0,
        "reason_breakdown": {},
        "top_missed":     [],
    }


def main() -> int:
    t0 = time.time()
    print("=" * 70)
    print("  AEGIS USA · Institutional Memory v1.0")
    print("=" * 70)

    # 1. archive
    m = archive_bundle()
    print(f"[1/4] archive       · run_date={m['run_date']}  files={m['n_files']}  size={m['total_bytes']/1024:.1f} KB")

    # 2. lifecycle
    lc = build_lifecycle()
    lc["engine"] = "usa_recommendation_lifecycle"; lc["version"] = "v1.0"
    lc["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
    (REPORTS / "recommendation_lifecycle.json").write_text(json.dumps(lc, indent=2, default=str), encoding="utf-8")
    print(f"[2/4] lifecycle     · n_total={lc.get('n_total', 0)}  active={lc.get('n_active', 0)}  days_archived={lc['coverage']['n_days_archived']}")

    # 3. missed opportunities
    mo = build_missed()
    mo["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
    (REPORTS / "missed_opportunities.json").write_text(json.dumps(mo, indent=2, default=str), encoding="utf-8")
    print(f"[3/4] missed opps   · n_events={mo['n_events']} across {mo['n_days_scanned']} days")

    # 4. recommendation history
    rh = build_recommendation_history()
    rh["engine"] = "usa_recommendation_history"; rh["version"] = "v1.0"
    rh["run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
    (REPORTS / "recommendation_history.json").write_text(json.dumps(rh, indent=2, default=str), encoding="utf-8")
    print(f"[4/4] rec history   · tickers={rh['n_tickers']}  days_archived={rh['n_days_archived']}")

    print(f"\n  elapsed: {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
