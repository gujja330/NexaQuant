# india/recommendation_db.py
"""
AEGIS RECOMMENDATION DATABASE — the "operating system" backbone (Feedback Loop 1: system learning).

The engine is frozen; this is the memory around it. Every run SNAPSHOTS today's recommendations into
one growing database (data/aegis_recommendation_db.csv) — nothing is ever deleted. From that we get,
for free: a full recommendation history, a lifecycle for every pick (LIVE -> REVIEW-DUE -> EXPIRED ->
ARCHIVED), and a daily DIFF (what was added / removed / increased / reduced vs the previous snapshot).

This is presentation/operations only — it reads the validated workbook and records it. It changes
METRICS over time, never the production model (that's Loop 2: the AI Lab, gated against the frozen
baseline). The two loops stay separate on purpose.

Run:  python india/recommendation_db.py            # snapshot the latest workbook + show the diff
      python india/recommendation_db.py --status   # lifecycle summary only (no new snapshot)
"""
import sys, glob, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
DB = ROOT / "data" / "aegis_recommendation_db.csv"
REPORTS = ROOT / "reports"

COLS = ["recommended_date", "symbol", "action", "horizon", "entry", "target", "review_date",
        "expiry_date", "confidence", "weight", "status"]


def _latest_workbook():
    fs = sorted(glob.glob(str(REPORTS / "AEGIS_*.xlsx")))
    return fs[-1] if fs else None


def load_db():
    if not DB.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(DB)


def _today_rows():
    """Map the latest workbook's Today's Recommendations into database rows (one per pick)."""
    f = _latest_workbook()
    if not f:
        return pd.DataFrame(columns=COLS), None
    t = pd.read_excel(f, sheet_name="Today's Recommendations")
    if t.empty:
        return pd.DataFrame(columns=COLS), None
    # the sheet stacks two blocks (clean recs + factor breakdown) separated by a blank row;
    # keep ONLY the first (clean) block so the DB ingests one row per recommendation.
    blanks = t.index[t.isna().all(axis=1)]
    if len(blanks):
        t = t.iloc[:blanks[0]]
    t = t[t["Stock"].notna()] if "Stock" in t else t
    snap = str(t["Generated"].iloc[0]) if "Generated" in t else str(pd.Timestamp.now().date())

    def g(row, *names, default=""):
        for n in names:
            if n in row and pd.notna(row[n]):
                return row[n]
        return default
    rows = []
    for _, r in t.iterrows():
        rows.append({
            "recommended_date": snap, "symbol": g(r, "Stock"), "action": g(r, "Strength"),
            "horizon": g(r, "Recommended Holding"), "entry": g(r, "Current Price"),
            "target": g(r, "Hist Target"), "review_date": g(r, "Review Date"),
            "expiry_date": g(r, "Valid Until"), "confidence": g(r, "Rec Confidence %"),
            "weight": g(r, "Weight %"), "status": "LIVE"})
    return pd.DataFrame(rows, columns=COLS), snap


def lifecycle(df, today=None):
    """Status for each row from its dates: ARCHIVED (expired) · REVIEW-DUE · LIVE."""
    if df.empty:
        return df
    today = pd.Timestamp(today or pd.Timestamp.now().date())
    df = df.copy()
    rev = pd.to_datetime(df["review_date"], errors="coerce")
    exp = pd.to_datetime(df["expiry_date"], errors="coerce")
    st = np.where(exp.notna() & (exp < today), "ARCHIVED",
                  np.where(rev.notna() & (rev <= today), "REVIEW-DUE", "LIVE"))
    df["status"] = st
    return df


def snapshot(today=None):
    """Append today's recommendations to the DB (idempotent per recommended_date). Returns (db, snap)."""
    rows, snap = _today_rows()
    if snap is None:
        return load_db(), None
    db = load_db()
    if not db.empty and snap in set(db["recommended_date"].astype(str)):
        return db, snap                                    # already snapshotted today -> idempotent
    db = pd.concat([db, rows], ignore_index=True)
    db = lifecycle(db, today)                              # refresh lifecycle on the whole DB
    DB.parent.mkdir(exist_ok=True)
    db.to_csv(DB, index=False)
    return db, snap


def daily_diff(db):
    """Compare the two most recent snapshots: NEW, REMOVED, INCREASED, REDUCED (by weight)."""
    if db.empty:
        return {}
    snaps = sorted(db["recommended_date"].astype(str).unique())
    if len(snaps) < 2:
        return {"note": "only one snapshot so far — diff begins from the next run"}
    prev, cur = db[db.recommended_date.astype(str) == snaps[-2]], db[db.recommended_date.astype(str) == snaps[-1]]
    pw = dict(zip(prev.symbol, pd.to_numeric(prev.weight, errors="coerce")))
    cw = dict(zip(cur.symbol, pd.to_numeric(cur.weight, errors="coerce")))
    new = [s for s in cw if s not in pw]
    removed = [s for s in pw if s not in cw]
    inc = [f"{s} {pw[s]:.0f}->{cw[s]:.0f}%" for s in cw if s in pw and cw[s] - pw[s] > 0.5]
    red = [f"{s} {pw[s]:.0f}->{cw[s]:.0f}%" for s in cw if s in pw and pw[s] - cw[s] > 0.5]
    return {"from": snaps[-2], "to": snaps[-1], "new": new, "removed": removed,
            "increased": inc, "reduced": red}


def main():
    if "--status" in sys.argv:
        db = lifecycle(load_db())
    else:
        db, snap = snapshot()
        print(f"  snapshot: {snap or 'no workbook'}  ·  DB now holds {len(db)} rows across "
              f"{db['recommended_date'].nunique() if not db.empty else 0} days")
    print("=" * 70)
    print("  AEGIS RECOMMENDATION DATABASE")
    print("=" * 70)
    if db.empty:
        print("  empty — generate a workbook first (india/recommendation_generator.py)."); return
    counts = db["status"].value_counts().to_dict()
    print("  Lifecycle:", "  ".join(f"{k}={v}" for k, v in counts.items()))
    d = daily_diff(db)
    if d.get("note"):
        print(f"  Daily diff: {d['note']}")
    elif d:
        print(f"  Daily diff {d['from']} -> {d['to']}:")
        print(f"    NEW: {d['new'] or '—'}")
        print(f"    REMOVED: {d['removed'] or '—'}")
        print(f"    INCREASED: {d['increased'] or '—'}")
        print(f"    REDUCED: {d['reduced'] or '—'}")
    print(f"\n  DB -> {DB.relative_to(ROOT)}  (nothing is ever deleted; history accumulates)")


if __name__ == "__main__":
    main()
