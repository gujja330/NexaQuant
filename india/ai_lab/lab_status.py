# india/ai_lab/lab_status.py
"""
AEGIS RESEARCH LAB — status dashboard.

Reads experiments.yaml (the registry) and renders the LAB board: every dataset/model experiment, where
it is in the promotion pipeline, and its measured IC / lift / walk-forward / forward-paper / promotion.
Where a gate result exists (data/aegis_layer_registry.csv from india/data_layer_gate.py), it is pulled
in live so the board reflects real measurements, not hand-typed claims.

This is the RESEARCH dashboard (not the investor one). Production stays frozen; this tracks the work
that might one day earn promotion into it.

Run: python india/ai_lab/lab_status.py
"""
import sys, warnings
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
REG = ROOT / "india" / "ai_lab" / "experiments.yaml"
LAYER_REG = ROOT / "data" / "aegis_layer_registry.csv"


def _fmt(v):
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def load():
    import yaml
    return yaml.safe_load(REG.read_text(encoding="utf-8"))


def gate_results():
    """Pull live IC / lift / verdict per gate_layer from the data-layer gate's registry, if present."""
    if not LAYER_REG.exists():
        return {}
    df = pd.read_csv(LAYER_REG)
    out = {}
    for _, r in df.iterrows():
        key = str(r.get("layer", "")).split(":")[0].strip().lower()
        out[key] = {"ic": r.get("mean_ic"), "lift": r.get("rqs_lift"), "verdict": r.get("verdict")}
    return out


def main():
    cfg = load()
    base = cfg.get("baseline", {})
    gr = gate_results()
    print("=" * 96)
    print("  AEGIS RESEARCH LAB — experiment board   (Production 1.x FROZEN; promote only on evidence)")
    print("=" * 96)
    print(f"  Baseline: {base.get('name')}  ·  selection RQS {base.get('selection_rqs')} "
          f"(the bar every LAB must beat OOS)\n")
    print(f"  {'LAB':<8}{'Name':<24}{'Status':<15}{'IC':>8}{'Lift':>8}{'WalkFwd':>9}{'Forward':>9}{'Promote':>9}")
    print("  " + "-" * 90)
    def _yn(v):                                          # YAML reads NO/YES as booleans -> normalise
        return "YES" if v is True else ("NO" if v is False else _fmt(v))
    for lab in cfg.get("labs", []):
        live = gr.get(str(lab.get("gate_layer", "")).lower(), {})
        ic = live.get("ic", lab.get("ic")); lift = live.get("lift", lab.get("lift"))
        print(f"  {lab['id']:<8}{lab['name'][:23]:<24}{lab['status']:<15}"
              f"{_fmt(round(ic,3) if isinstance(ic,(int,float)) else ic):>8}"
              f"{_fmt(round(lift,3) if isinstance(lift,(int,float)) else lift):>8}"
              f"{_yn(lab.get('walk_forward')):>9}{_yn(lab.get('forward_paper')):>9}"
              f"{_yn(lab.get('promotion')):>9}")
    promoted = [l['id'] for l in cfg.get("labs", []) if l.get("promotion") is True or l.get("promotion") == "YES"]
    print("\n  Promoted to production:", ", ".join(promoted) if promoted else "none yet "
          "(price-only experiments cannot beat the baseline — that is the expected, honest result).")
    print("  Pipeline per LAB: Raw -> Validation -> Feature-Eng -> IC -> Lift -> Walk-Forward -> "
          "Forward-Paper -> Gate.")
    print("  Drop a dataset in data/layers/ and run india/data_layer_gate.py to populate IC/Lift live.")


if __name__ == "__main__":
    main()
