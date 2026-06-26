# india/ai_lab/research_journal.py
"""
AEGIS RESEARCH JOURNAL — generate docs/RESEARCH_JOURNAL.md from the experiment registry.

Renders a RESEARCH LEADERBOARD (at-a-glance: which datasets earned their place) plus ONE PAGE per
experiment (question · dataset · coverage · IC · lift · walk-forward · forward-paper · decision · notes).
After a year of experiments this document is the lab's IP — a permanent record of what was tested,
what was rejected, and what (if anything) earned promotion into the frozen production engine.

Live IC/lift are pulled from the data-layer gate registry (data/aegis_layer_registry.csv) when present,
so the journal reflects real measurements, not hand-typed claims.

Run: python india/ai_lab/research_journal.py
"""
import sys, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REG = ROOT / "india" / "ai_lab" / "experiments.yaml"
LAYER_REG = ROOT / "data" / "aegis_layer_registry.csv"
OUT = ROOT / "docs" / "RESEARCH_JOURNAL.md"


def _v(x):
    return "—" if x is None or (isinstance(x, float) and pd.isna(x)) else (
        "YES" if x is True else ("NO" if x is False else str(x)))


def gate_results():
    if not LAYER_REG.exists():
        return {}
    df = pd.read_csv(LAYER_REG)
    out = {}
    for _, r in df.iterrows():
        out[str(r.get("layer", "")).split(":")[0].strip().lower()] = {
            "ic": r.get("mean_ic"), "lift": r.get("rqs_lift"), "verdict": r.get("verdict")}
    return out


def main():
    import yaml
    cfg = yaml.safe_load(REG.read_text(encoding="utf-8"))
    base = cfg.get("baseline", {}); labs = cfg.get("labs", [])
    gr = gate_results()
    for lab in labs:                                       # overlay live gate measurements
        live = gr.get(str(lab.get("gate_layer", "")).lower())
        if live:
            if live.get("ic") is not None:
                lab["ic"] = round(float(live["ic"]), 4)
            if live.get("lift") is not None:
                lab["lift"] = round(float(live["lift"]), 4)

    L = ["# AEGIS Research Journal", "",
         f"_Production baseline: **{base.get('name')}** · selection RQS **{base.get('selection_rqs')}** "
         "(the bar every experiment must beat out-of-sample). Production is frozen; nothing here reaches "
         "it without passing the full pipeline._", "",
         "## Research Leaderboard", "",
         "| LAB | Dataset | Status | IC | Lift | Walk-Fwd | Forward | Decision |",
         "|-----|---------|--------|----|------|----------|---------|----------|"]
    for lab in labs:
        L.append(f"| {lab['id']} | {lab['name']} | {_v(lab.get('status'))} | {_v(lab.get('ic'))} | "
                 f"{_v(lab.get('lift'))} | {_v(lab.get('walk_forward'))} | {_v(lab.get('forward_paper'))} "
                 f"| {_v(lab.get('decision'))} |")
    promoted = [l['id'] for l in labs if str(l.get('decision')).lower() == 'promote']
    L += ["", f"**Promoted to production:** {', '.join(promoted) if promoted else 'none yet'}  ·  "
          f"**Tested:** {sum(1 for l in labs if l.get('status') not in ('planned',))}  ·  "
          f"**Total experiments:** {len(labs)}", "",
          "_Success is measured by how many weak ideas were rejected before they could contaminate "
          "production — not by how many shipped._", "", "---", ""]

    # one page per experiment
    for lab in labs:
        L += [f"## {lab['id']} — {lab['name']}", "",
              f"**Question:** {lab.get('question','—')}", "",
              f"**Dataset:** {lab.get('dataset','—')}", "",
              "| Field | Value |", "|-------|-------|",
              f"| Status | {_v(lab.get('status'))} |",
              f"| Coverage | {_v(lab.get('coverage'))}{'%' if isinstance(lab.get('coverage'),(int,float)) else ''} |",
              f"| Missing % | {_v(lab.get('missing_pct'))} |",
              f"| IC | {_v(lab.get('ic'))} |",
              f"| Incremental lift (RQS) | {_v(lab.get('lift'))} |",
              f"| Walk-forward | {_v(lab.get('walk_forward'))} |",
              f"| Forward paper | {_v(lab.get('forward_paper'))} |",
              f"| **Decision** | **{_v(lab.get('decision'))}** |", "",
              f"**Notes:** {lab.get('notes','—')}", "",
              f"_Gate: drop the dataset in `data/layers/{lab.get('gate_layer','x')}.parquet` and run "
              "`python india/data_layer_gate.py`; record IC / lift here._", "", "---", ""]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"  Research Journal -> {OUT.relative_to(ROOT)}  ({len(labs)} experiments)")
    print(f"  Promoted: {', '.join(promoted) if promoted else 'none yet'}")


if __name__ == "__main__":
    main()
