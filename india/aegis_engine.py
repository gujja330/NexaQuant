# india/aegis_engine.py
"""
AEGIS RECOMMENDATION ENGINE v4 — the CONNECTED pipeline. Not another script: the wiring that turns the
research platform into a recommendation an investor can act on, and an EXPLANATION of what changed.

Everything already existed in pieces (regime, selection, HRP, the data-layer gate). v4 connects them:

   Market  ->  Sector  ->  Industry  ->  Company  ->  Data Layers  ->  Portfolio  ->  Recommendation
                                                            |
                                                     (only PRODUCTION layers
                                                      from the lifecycle ledger
                                                      are allowed to move picks)
                                                            v
                                                       EXPLANATION  ("what changed today, and why")

Layer LIFECYCLE (the user's PROMOTE idea), read from data/aegis_layer_registry.csv:
   rejected  ->  calibration  ->  experimental (KEPT, shadow only)  ->  production (moves real picks)
Only `production` layers change the recommendation. `experimental` run in SHADOW: the engine shows what
they WOULD change if promoted — so promotion is an informed decision, never a surprise.

Honest state today: 0 production layers (price-only optimisation is exhausted; no non-price source has
passed the gate yet). So today's recommendation = the validated portfolio + regime engine, unchanged,
and "what changed" says so plainly. The day earnings/flows are KEPT and PROMOTED, picks adapt with NO
new code — just a status flip. Use --demo to see the adaptation machinery end-to-end (clearly a
plumbing test, not real alpha — same spirit as the gate's ORACLE calibration).

Run:  python india/aegis_engine.py            (today, honest)
      python india/aegis_engine.py --demo     (inject a demo production layer to prove adaptation)
"""
import sys, warnings
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.arjuna_v2 import select_names, weights_for, LOOKBACK
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import SECTORS, sector_of
from india.confidence_engine import current_regime
from india.horizon_matrix import horizon_matrix, recommend
from india.dynamic_policy import choose_horizon, choose_topn
from india.data_layer_gate import REG as LAYER_REG, PITFileLayer, discover_file_layers

CFG = dict(topn=15, sector_cap=2, name_cap=0.30, default_capital=500000)
STATUSES = ["rejected", "calibration", "experimental", "production"]
DAYS = {"1W": 5, "2W": 10, "1M": 21, "2M": 42, "3M": 63, "6M": 126, "9M": 189, "1Y": 252}


# ----------------------------- layer lifecycle -----------------------------
def load_ledger():
    """The lifecycle ledger: every evaluated layer + its incremental value + its status."""
    if not LAYER_REG.exists():
        return pd.DataFrame(columns=["layer", "kind", "rqs_lift", "verdict", "status"])
    led = pd.read_csv(LAYER_REG)
    # map the gate's raw status into the lifecycle vocabulary
    if "status" in led:
        led["status"] = led["status"].replace({"pending-forward-paper": "experimental"})
    led["incr_value"] = led.get("rqs_lift", 0.0).fillna(0.0)
    return led


def set_status(layer_name, status):
    """PROMOTE / demote a layer. production = allowed to move real recommendations."""
    assert status in STATUSES, f"status must be one of {STATUSES}"
    led = load_ledger()
    if layer_name not in set(led["layer"]):
        raise ValueError(f"unknown layer '{layer_name}'")
    led.loc[led["layer"] == layer_name, "status"] = status
    led.drop(columns=[c for c in ["incr_value"] if c in led], errors="ignore").to_csv(LAYER_REG, index=False)
    return led


def active_layers(led, demo=False):
    """Production layers actually move picks; experimental run in shadow. Returns (production, experimental)."""
    prod = led[led["status"] == "production"]["layer"].tolist() if not led.empty else []
    exp = led[led["status"] == "experimental"]["layer"].tolist() if not led.empty else []
    if demo:
        prod = prod + ["DEMO sector-stability tilt"]            # plumbing test only — see _demo_layer
    return prod, exp


# ----------------------------- pipeline stages -----------------------------
@dataclass
class Stage:
    name: str
    action: str
    detail: str
    data: object = None


@dataclass
class Reco:
    asof: str
    exposure: float
    regime: str
    horizon: str
    picks: pd.DataFrame
    stages: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    ledger: pd.DataFrame = None


def _demo_layer(closes, cols, i):
    """DEMO ONLY — a deterministic 'sector-stability' score (lower dispersion = higher). Proves the
    engine ADAPTS picks when a production layer exists. NOT alpha; never enabled outside --demo."""
    rets = closes.pct_change()
    sec_disp = {}
    for s in set(sector_of(c) for c in cols):
        names = [c for c in cols if sector_of(c) == s]
        sec_disp[s] = rets[names].iloc[i - 60:i].std(axis=0).mean()
    rank = pd.Series({s: -v for s, v in sec_disp.items()}).rank(pct=True)
    return pd.Series({c: rank[sector_of(c)] for c in cols})


def run(capital=None, demo=False):
    capital = capital or CFG["default_capital"]
    closes, _, _, _, idx, _, _ = load_panels()
    closes = closes[[c for c in closes.columns if c in set(NIFTY200)]]
    rets = closes.pct_change()
    i = len(closes) - 1
    hist = rets.tail(LOOKBACK).dropna(axis=1, how="any")
    cols = list(hist.columns)
    asof = str(closes.index[i].date())
    led = load_ledger()
    prod, exp_layers = active_layers(led, demo=demo)
    stages = []

    # 1. MARKET — validated regime exposure (+ dynamic policy derived from it)
    exposure, regime, rconf = current_regime()
    stages.append(Stage("Market", f"regime {regime}", f"deploy {exposure:.0%} (confidence {rconf})"))
    topn_dyn, breadth = choose_topn(hist, closes, exposure, cap=CFG["sector_cap"])
    try:
        hmat = horizon_matrix()
    except Exception:
        hmat = None
    hl, hconf = choose_horizon(hmat, exposure)

    # 2. SECTOR — forced diversification (fixed cap; a production sector layer would tilt here)
    stages.append(Stage("Sector", f"cap {CFG['sector_cap']}/sector",
                        f"{len(set(sector_of(c) for c in cols))} sectors · breadth {breadth:.0%} above 200-DMA"))

    # 3. INDUSTRY — not separately modelled yet (approximated by sector). Honest gap.
    stages.append(Stage("Industry", "approximated by sector", "no separate industry taxonomy yet"))

    # 4. COMPANY — baseline validated selection (lowest-vol, sector-capped, DYNAMIC N from breadth+regime)
    base_sel = select_names(hist, topn_dyn, CFG["sector_cap"])
    stages.append(Stage("Company", f"{len(base_sel)} low-vol names (dynamic N={topn_dyn})",
                        "validated baseline selection"))

    # 5. DATA LAYERS — only PRODUCTION layers may move picks; experimental run in shadow
    final_sel = list(base_sel)
    if prod:
        allowed_all = set(cols)
        for lyr in prod:
            if lyr == "DEMO sector-stability tilt":
                score = _demo_layer(closes, cols, i)
            else:
                fl = next((f for f in discover_file_layers() if f.name == lyr), None)
                score = fl.fn(closes, idx, i, cols) if fl else pd.Series(dtype=float)
            score = score.reindex(cols).dropna()
            if len(score) >= 12:
                allowed_all &= set(score[score >= score.median()].index)
        # re-run selection restricted to layer-allowed names, at the DYNAMIC basket size
        iv = (1.0 / hist[cols].std().replace(0, np.nan)).dropna().sort_values(ascending=False)
        chosen, sec = [], {}
        for s in iv.index:
            if s not in allowed_all:
                continue
            if len(chosen) >= topn_dyn:
                break
            k = SECTORS.get(s, "Other")
            if sec.get(k, 0) >= CFG["sector_cap"]:
                continue
            chosen.append(s); sec[k] = sec.get(k, 0) + 1
        final_sel = chosen or base_sel
        stages.append(Stage("Data Layers", f"{len(prod)} production layer(s)",
                            f"applied: {', '.join(prod)}", data=prod))
    else:
        stages.append(Stage("Data Layers", "0 production layers",
                            "no non-price source has passed the gate + been promoted yet"))

    # 6. PORTFOLIO — HRP weights, name cap
    w = weights_for("hrp", hist[final_sel]); w = (w / w.sum()).clip(upper=CFG["name_cap"]); w = w / w.sum()
    stages.append(Stage("Portfolio", "HRP weights", f"name cap {CFG['name_cap']:.0%}"))

    # 7. RECOMMENDATION + horizon (dynamic hl/hconf computed in stage 1)
    invest = capital * exposure
    picks = pd.DataFrame({"Stock": w.index, "Sector": [sector_of(s) for s in w.index],
                          "Weight %": (w.values * 100).round(1),
                          "Allocation Rs": (w.values * invest).round(0).astype(int)})
    picks = picks.sort_values("Weight %", ascending=False).reset_index(drop=True)

    # 8. EXPLANATION — what changed today, and why
    changed = []
    added = [s for s in final_sel if s not in base_sel]
    dropped = [s for s in base_sel if s not in final_sel]
    if prod:
        for s in added:
            changed.append(f"+ {s} ({sector_of(s)}) entered — favoured by {', '.join(prod)}")
        for s in dropped:
            changed.append(f"- {s} ({sector_of(s)}) left — filtered out by {', '.join(prod)}")
        if not added and not dropped:
            changed.append("Production layers active but did not alter the baseline selection today.")
    else:
        changed.append("No change from data layers — none in production. Recommendation reflects the "
                       "validated portfolio + regime engine only.")
    for lyr in exp_layers:
        changed.append(f"(shadow) experimental layer '{lyr}' is KEPT but not promoted — not moving picks.")

    return Reco(asof, exposure, regime, f"{hl} ({hconf})", picks, stages, changed, led)


# --------------------------------- view ------------------------------------
def show(r: Reco, demo=False):
    print("=" * 84)
    print(f"  AEGIS RECOMMENDATION ENGINE v4 — connected pipeline   ·   as-of {r.asof}"
          + ("   [DEMO]" if demo else ""))
    print("=" * 84)
    print("  PIPELINE")
    for s in r.stages:
        print(f"    {s.name:<13} {s.action:<26} {s.detail}")
    print(f"\n  RECOMMENDATION — regime {r.regime} · deploy {r.exposure:.0%} · horizon {r.horizon}")
    print(f"    {'Stock':<13}{'Sector':<16}{'Weight%':>8}{'Alloc Rs':>12}")
    for _, p in r.picks.head(15).iterrows():
        print(f"    {p['Stock']:<13}{p['Sector']:<16}{p['Weight %']:>8.1f}{p['Allocation Rs']:>12,}")

    print("\n  WHAT CHANGED TODAY")
    for c in r.changed:
        print(f"    • {c}")

    print("\n  LAYER LIFECYCLE LEDGER  (incremental value = RQS lift over 0.50 baseline)")
    if r.ledger is None or r.ledger.empty:
        print("    (no layers evaluated yet)")
    else:
        print(f"    {'Layer':<26}{'kind':<12}{'IncrValue':>10}   Status")
        for _, l in r.ledger.iterrows():
            iv = l.get("incr_value", 0.0)
            print(f"    {str(l['layer']):<26}{str(l['kind']):<12}{(f'{iv:+.3f}' if iv else '—'):>10}"
                  f"   {l.get('status', '—')}")
    n_prod = 0 if r.ledger is None or r.ledger.empty else int((r.ledger['status'] == 'production').sum())
    print(f"\n  STATUS: {n_prod} production layer(s). " + (
        "Picks reflect validated portfolio + regime only — awaiting first promoted non-price layer."
        if n_prod == 0 else "Production layers are actively shaping the recommendation above."))
    print("  Promote a KEPT layer with: aegis_engine.set_status('<layer>', 'production')  (after forward paper).")


def main():
    demo = "--demo" in sys.argv
    show(run(demo=demo), demo=demo)


if __name__ == "__main__":
    main()
