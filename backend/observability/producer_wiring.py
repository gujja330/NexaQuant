"""AEGIS · PRODUCER WIRING AUDIT · find runnable producers nobody runs.

CEO 2026-09-08 · "can u investigate such files first which are not wired
and useful".

THE PATTERN
-----------
Orphaned producers keep surfacing one at a time, each after it has already
caused damage:

  short_term_momentum        no pipeline step · frozen 11 days
  r3_daily_shadow_feed       no pipeline step · ledger never accumulated
  backend/context/fii_dii    no pipeline step · 27 days stale
  mr_prediction_autopsy      no pipeline step · forward outcomes frozen
                             12 days · USA fwd_5d only 18% populated

Each was found by tripping over it. This enumerates them instead.

The companion module `data_freshness` answers "is the OUTPUT current?".
This answers the prior question: "is anything even RUNNING this?" A
producer with no caller cannot have a fresh output, and its artifact will
sit at whatever value it had the day someone last ran it by hand.

METHOD
------
  1. A PRODUCER is a module with a __main__ entry point that writes under
     reports/ or data/.
  2. It is WIRED if a pipeline STEPS entry, a GitHub workflow, or another
     runnable script invokes it.
  3. Everything else is ORPHANED · reported with what it writes, whether
     that artifact exists, how stale it is, and whether anything READS it.

The last column is what matters: an orphan whose artifact is CONSUMED is
actively feeding stale values into something downstream. An orphan nobody
reads is merely dead code.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

SCAN_DIRS = ("backend", "scripts", "usa", "india", "research")
SKIP_PARTS = ("__pycache__", "/tests/", "\\tests\\", "/archive/", "\\archive\\")

_WRITE_RE = re.compile(
    r"""(reports/[A-Za-z0-9_./{}-]+|data/[A-Za-z0-9_./{}-]+)""")
_WRITE_VERB = ("write_text", "write_bytes", "to_json", "to_parquet", "to_csv",
               "json.dump", "open(", ".to_excel", "savefig")


def _is_runnable(text: str) -> bool:
    return "__main__" in text and ("argparse" in text or "def main" in text)


_DATA_EXT = (".json", ".jsonl", ".parquet", ".csv", ".xlsx", ".md")
_FNAME_RE = re.compile(
    r"[\"']([A-Za-z0-9_.{}/-]+?"
    r"(?:\.json|\.jsonl|\.parquet|\.csv|\.xlsx|\.md))[\"']")


def _artifacts_written(text: str) -> list:
    """Artifact filenames a runnable module writes.

    Path literals are rarely complete on one line · modules build them as
    `root / ALLOWED_WRITE_ROOT / f"name_{market}.json"`. Matching only
    `reports/...` prefixes therefore found almost nothing (1 producer in
    the whole repo). Collect any data-file NAME in a module that also
    performs a write; the name is enough to locate and age the artifact.
    """
    if not any(v in text for v in _WRITE_VERB):
        return []
    out = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        norm = line.replace("\\", "/")
        for m in _WRITE_RE.finditer(norm):
            a = m.group(1)
            # Keep only real data files · a directory is not an artifact.
            if a.endswith(_DATA_EXT):
                out.add(a)
        for m in _FNAME_RE.finditer(norm):
            a = m.group(1)
            if a.endswith(".py"):
                continue
            out.add(a)
    return sorted(out)


def _python_files(root: Path):
    for d in SCAN_DIRS:
        base = root / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            s = str(p)
            if any(x in s for x in SKIP_PARTS):
                continue
            yield p


def _wired_targets(root: Path) -> set:
    """Everything invoked by a pipeline step, a workflow, or another script."""
    wired = set()

    def _add(tok: str):
        tok = tok.strip().strip("\"'")
        if not tok:
            return
        wired.add(tok)
        wired.add(tok.replace("\\", "/"))
        wired.add(Path(tok).name)
        wired.add(Path(tok).stem)

    # 1 · pipeline STEPS (script= and module=)
    for rel in ("scripts/aegis_daily_v2.py", "usa/scripts/usa_daily.py"):
        p = root / rel
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"script"\s*:\s*"([^"]+)"', t):
            _add(m.group(1))
        for m in re.finditer(r'"module"\s*:\s*"([^"]+)"', t):
            _add(m.group(1))
            _add(m.group(1).split(".")[-1])

    # 2 · GitHub workflows
    wf = root / ".github" / "workflows"
    if wf.exists():
        for p in wf.glob("*.yml"):
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"python\s+(?:-m\s+)?([A-Za-z0-9_./\\-]+)", t):
                _add(m.group(1))
                _add(m.group(1).split(".")[-1])

    # 3 · invoked by any other runnable script (subprocess or import+main)
    for p in _python_files(root):
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"python\s+(?:-m\s+)?([A-Za-z0-9_./\\-]+)", t):
            _add(m.group(1))
        for m in re.finditer(r'"script"\s*:\s*"([^"]+)"', t):
            _add(m.group(1))
    return wired


def _readers_of(root: Path, artifact: str) -> int:
    """How many modules READ this artifact · an orphan that feeds something
    is far more dangerous than one nobody reads."""
    # Only DATA FILES count. A bare directory like "data/raw/india" appears
    # in hundreds of modules and would swamp the ranking with noise.
    if not artifact.endswith(_DATA_EXT):
        return 0
    stem = Path(artifact).name
    # Strip a {market} style placeholder so the search still matches.
    stem = re.sub(r"\{[^}]*\}", "", stem).strip("_.")
    if len(stem) < 8:
        return 0
    n = 0
    for p in _python_files(root):
        try:
            if stem in p.read_text(encoding="utf-8", errors="replace"):
                n += 1
        except Exception:
            continue
    return max(0, n - 1)          # discount the writer itself


def _age_days(root: Path, artifact: str, today: date):
    p = root / artifact
    if "{" in artifact or not p.exists():
        return None, False
    return (today - date.fromtimestamp(p.stat().st_mtime)).days, True


def audit(root: Path, today: str | None = None) -> dict:
    today_d = date.fromisoformat(today) if today else date.today()
    wired = _wired_targets(root)
    producers, orphans = [], []
    for p in _python_files(root):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if not _is_runnable(t):
            continue
        rel = p.relative_to(root).as_posix()
        arts = _artifacts_written(t)
        if not arts:
            continue                      # runnable but writes nothing
        mod = rel[:-3].replace("/", ".")
        is_wired = any(k in wired for k in (rel, p.name, p.stem, mod))
        rec = {"module": rel, "n_artifacts": len(arts),
               "artifacts": arts[:6], "wired": is_wired}
        producers.append(rec)
        if not is_wired:
            ages, exists_n, readers = [], 0, 0
            for a in arts[:6]:
                d, ex = _age_days(root, a, today_d)
                if ex:
                    exists_n += 1
                    ages.append(d)
                readers += _readers_of(root, a)
            rec = dict(rec)
            rec.update({"artifacts_existing": exists_n,
                        "max_artifact_age_days": max(ages) if ages else None,
                        "n_downstream_readers": readers})
            orphans.append(rec)

    # Rank: consumed AND stale first · those are actively harmful.
    orphans.sort(key=lambda r: (-(r["n_downstream_readers"] or 0),
                                -(r["max_artifact_age_days"] or -1)))
    return {
        "engine": "aegis.observability.producer_wiring.v1",
        "today": today_d.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_producers": len(producers),
        "n_wired": sum(1 for r in producers if r["wired"]),
        "n_orphaned": len(orphans),
        "orphans": orphans,
    }


def emit(root: Path, rep: dict) -> Path:
    p = root / "reports" / "context" / "producer_wiring.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    return p


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AEGIS producer wiring audit")
    ap.add_argument("--root", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--min-readers", type=int, default=0,
                    help="only show orphans with at least N downstream readers")
    a = ap.parse_args()
    root = Path(a.root) if a.root else Path(__file__).resolve().parents[2]
    rep = audit(root, a.today)
    emit(root, rep)
    print(f"producers={rep['n_producers']} wired={rep['n_wired']} "
          f"ORPHANED={rep['n_orphaned']}")
    print("\nORPHANS · nothing runs these (ranked: consumed + stale first)")
    for o in rep["orphans"]:
        if o["n_downstream_readers"] < a.min_readers:
            continue
        age = o["max_artifact_age_days"]
        print(f"  readers={o['n_downstream_readers']:>3} "
              f"age={str(age):>5}d  exists={o['artifacts_existing']}/{o['n_artifacts']}  "
              f"{o['module']}")
        for art in o["artifacts"][:2]:
            print(f"        -> {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
