# tools/trace.py
"""
AEGIS lineage tracer — answers cross-registry questions WITHOUT manual searching. No new IDs needed: the
natural slugs already ARE the keys (dataset slug in DATASET_REGISTRY.dataset == FEATURE_CATALOG.dataset;
feature slug == LEADERBOARD.factor_or_experiment; RC id == EXPERIMENT_REGISTRY.rc == LEADERBOARD.cycle prefix).
This tool just joins them.

  python tools/trace.py feature f_roe        # which dataset + experiments + results touch this feature
  python tools/trace.py dataset sec_companyfacts
  python tools/trace.py promoted             # which datasets produced promoted/investigate features
  python tools/trace.py rc RC001             # lineage of one experiment
  python tools/trace.py graph                # knowledge-graph rollup (writes KNOWLEDGE_GRAPH.md)
"""
import csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "markets" / "research"
def rows(p): return list(csv.DictReader((RES / p).open())) if (RES / p).exists() else []

LB = rows("LEADERBOARD.csv")
FEAT = rows("registry/FEATURE_CATALOG.csv")
DS = rows("registry/DATASET_REGISTRY.csv")
EXP = rows("registry/EXPERIMENT_REGISTRY.csv")


def feature(slug):
    f = next((r for r in FEAT if r["feature"] == slug), None)
    if not f:
        print(f"  unknown feature: {slug}"); return
    print(f"FEATURE {slug}  [{f['status']}]  dataset={f['dataset']}  program={f['program']}")
    res = [r for r in LB if r["factor_or_experiment"] == slug]
    print(f"  used in {len(res)} result(s):")
    for r in res:
        print(f"    {r['cycle']:9s} IC {r['IC'] or '-':>7} IR {r['IC_IR'] or '-':>6}  {r['status']}")


def dataset(slug):
    d = next((r for r in DS if r["dataset"] == slug), None)
    if not d:
        print(f"  unknown dataset: {slug}"); return
    print(f"DATASET {slug}  [{d['status']}]  program={d['program']}  pit={d['pit']}  coverage={d['coverage']}")
    feats = [r for r in FEAT if r["dataset"] == slug]
    print(f"  produced {len(feats)} feature(s): " + ", ".join(f"{r['feature']}({r['status']})" for r in feats))


def promoted():
    print("Datasets -> their promoted/investigate features (the ones earning their keep):")
    for d in DS:
        good = [r for r in FEAT if r["dataset"] == d["dataset"] and r["status"] in ("production", "investigate", "promoted", "kept")]
        if good:
            print(f"  {d['dataset']:20s} -> " + ", ".join(f"{r['feature']}({r['status']})" for r in good))


def rc(rid):
    e = next((r for r in EXP if r["rc"] == rid), None)
    if e:
        print(f"EXPERIMENT {rid}  [{e['status']}]  {e['title']}  program={e['program']}  needs={e['depends_on']}")
    res = [r for r in LB if r["cycle"].startswith(rid)]
    print(f"  {len(res)} result row(s):")
    for r in res:
        print(f"    {r['cycle']:9s} {r['factor_or_experiment']:26s} {r['status']}")


def graph():
    """Knowledge-graph rollup over the chain dataset -> feature -> experiment -> result -> promotion.
    Answers the standing lineage questions from the relationships already in the registries."""
    from collections import Counter, defaultdict
    L = ["# AEGIS Knowledge Graph (lineage rollup)", "",
         "Auto-generated (`python tools/trace.py graph`) from the registries + leaderboard. The entity chain:",
         "`Dataset -> Feature -> Experiment -> Leaderboard result -> Promotion -> Production`.", ""]

    # datasets ranked by promoted/investigate features produced
    score = []
    for d in DS:
        good = [r for r in FEAT if r["dataset"] == d["dataset"] and r["status"] in ("production", "investigate", "promoted", "kept")]
        score.append((d["dataset"], len(good), [r["feature"] for r in good]))
    score.sort(key=lambda x: -x[1])
    L.append("## Which datasets produced the most kept/promoted/investigate features")
    for name, n, fs in score:
        if n:
            L.append(f"- **{name}** ({n}): {', '.join(fs)}")

    # program success rate
    L.append("\n## Program success rate (promoted+investigate / results)")
    by_prog = defaultdict(lambda: [0, 0])
    for r in LB:
        by_prog[r["program"]][0] += r["status"] in ("kept", "promoted", "investigate")
        by_prog[r["program"]][1] += 1
    for p, (hit, tot) in sorted(by_prog.items(), key=lambda x: -(x[1][0] / x[1][1])):
        L.append(f"- {p}: {hit}/{tot} ({100*hit//tot}%)")

    # most-tested factors
    L.append("\n## Most-tested factors")
    cnt = Counter(r["factor_or_experiment"] for r in LB)
    for f, c in cnt.most_common(5):
        L.append(f"- {f}: {c}")

    # low-confidence results
    L.append("\n## Results held back by LOW confidence (need more power)")
    for r in LB:
        if "Low" in r.get("confidence", "") and r["status"] in ("investigate", "not-promoted", "weak"):
            L.append(f"- {r['cycle']} {r['factor_or_experiment']} — {r.get('confidence','')} ({r['status']})")

    # production lineage
    L.append("\n## Production features and their origin dataset")
    for r in FEAT:
        if r["status"] == "production":
            L.append(f"- {r['feature']} <- {r['dataset']} (program {r['program']})")

    out = RES / "KNOWLEDGE_GRAPH.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\n  wrote {out.relative_to(ROOT.parent / ROOT.name)}")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "feature" and len(a) > 1: feature(a[1])
    elif cmd == "dataset" and len(a) > 1: dataset(a[1])
    elif cmd == "promoted": promoted()
    elif cmd == "rc" and len(a) > 1: rc(a[1])
    elif cmd == "graph": graph()
    else: print(__doc__)


if __name__ == "__main__":
    main()
