# india/ops_check.py
"""
AEGIS OPERATIONS HEALTH CHECK — the 30-second morning runbook, automated.

Phase 2 (Operations) is about proving the system runs RELIABLY before we change any model. This reads
the day's artifacts (no production logic touched) and prints a PASS / WARN / FAIL board over the
operational KPIs: data freshness, pipeline outputs, recommendation count, universe size, matured/scored
recommendations, evidence freshness, and the recommendation database. Exit code 0 = all green.

Run:  python india/ops_check.py
"""
import sys, glob, warnings
from datetime import datetime, date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
RAW = ROOT / "data" / "raw" / "india"
checks = []


def add(name, level, detail):           # level: PASS | WARN | FAIL
    checks.append((name, level, detail))


def _age_days(p):
    return (datetime.now() - datetime.fromtimestamp(Path(p).stat().st_mtime)).days


def main():
    today = date.today()
    biz = today.weekday() < 5

    # 1. Data freshness — latest bar in the price panels
    try:
        sample = sorted(glob.glob(str(RAW / "RELIANCE_D1.parquet")))
        last = pd.read_parquet(sample[0]).index[-1].date()
        gap = (today - last).days
        add("Data freshness", "PASS" if gap <= 4 else ("WARN" if gap <= 7 else "FAIL"),
            f"latest bar {last} ({gap}d old)")
    except Exception as e:
        add("Data freshness", "FAIL", f"cannot read panels: {type(e).__name__}")

    # 2. Workbook produced + recent
    wbs = sorted(glob.glob(str(ROOT / "reports" / "AEGIS_*.xlsx")))
    if wbs:
        add("Workbook generated", "PASS" if _age_days(wbs[-1]) <= 1 else "WARN",
            f"{Path(wbs[-1]).name} ({_age_days(wbs[-1])}d old)")
    else:
        add("Workbook generated", "FAIL", "no AEGIS workbook found")

    # 3. Recommendation count + universe size
    canon = ROOT / "data" / "aegis_today.csv"
    if canon.exists():
        t = pd.read_csv(canon)
        add("Recommendation count", "PASS" if len(t) > 0 else "FAIL", f"{len(t)} holdings")
        prof = t["Profile"].iloc[0] if "Profile" in t and len(t) else "—"
        add("Profile", "PASS", str(prof))
    else:
        add("Recommendation count", "FAIL", "aegis_today.csv missing")
    try:
        from india.universe import build_universe
        from india.feature_engine import load_panels
        cl, _, _, vo, _, _, _ = load_panels()
        n_uni = len(build_universe(cl, vo))
        add("Universe size", "PASS" if n_uni >= 50 else "WARN", f"{n_uni} tradable names")
    except Exception as e:
        add("Universe size", "WARN", f"not computed: {type(e).__name__}")

    # 4. Matured / scored recommendations (the evidence is updating)
    reg = ROOT / "data" / "aegis_registry.csv"
    if reg.exists():
        r = pd.read_csv(reg)
        scored = int((r.get("scored", 0) == 1).sum())
        add("Scored recommendations", "PASS" if scored > 0 else "WARN", f"{scored} scored in registry")
    else:
        add("Scored recommendations", "WARN", "no registry yet")

    # 5. Evidence (scorecard) freshness
    sc = ROOT / "data" / "aegis_scorecard.csv"
    if sc.exists():
        s = pd.read_csv(sc)
        wr = s["win_rate"].iloc[0] if "win_rate" in s and len(s) else "—"
        add("Evidence updated", "PASS" if _age_days(sc) <= 1 else "WARN",
            f"win rate {wr}% (scorecard {_age_days(sc)}d old)")
    else:
        add("Evidence updated", "WARN", "no scorecard yet")

    # 6. Recommendation database lifecycle
    db = ROOT / "data" / "aegis_recommendation_db.csv"
    if db.exists():
        d = pd.read_csv(db)
        days = d["recommended_date"].nunique() if "recommended_date" in d else 0
        add("Recommendation DB", "PASS" if len(d) > 0 else "WARN", f"{len(d)} rows over {days} day(s)")
    else:
        add("Recommendation DB", "WARN", "no DB yet")

    # ---- board ----
    sym = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}
    print("=" * 68)
    print(f"  AEGIS OPERATIONS HEALTH — {today}  ({'business day' if biz else 'weekend/holiday'})")
    print("=" * 68)
    for name, level, detail in checks:
        print(f"  [{sym[level]:<4}] {name:<26} {detail}")
    fails = [c for c in checks if c[1] == "FAIL"]
    warns = [c for c in checks if c[1] == "WARN"]
    print("-" * 68)
    if fails:
        print(f"  RESULT: FAIL — {len(fails)} issue(s) need attention (see OPERATIONS.md playbook).")
    elif warns:
        print(f"  RESULT: OK with {len(warns)} warning(s) — usually fine on weekends / fresh installs.")
    else:
        print("  RESULT: ALL GREEN — production is operationally healthy.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
