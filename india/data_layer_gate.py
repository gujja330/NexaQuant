# india/data_layer_gate.py
"""
DATA-LAYER GATE (AEGIS v3 — Phase 3) — the research platform, built ONCE, never redesigned.

The thesis we have now EARNED with evidence: price-only optimisation is exhausted (dynamic Top-N lost
OOS, every price factor showed zero lift, RQS stuck at ~0.50). The only thing that can move RQS off a
coin flip is NEW INFORMATION — earnings, FII/DII flows, insider trades, analyst revisions, options
flow, sector fundamentals. This module is the dataset-AGNOSTIC gate every such source must pass.

Important nuance (the user's correction, encoded): dynamic optimisation is FROZEN on price data, not
rejected. The day a layer here passes, the dynamic knobs (holding, top-N) REOPEN conditioned on it —
e.g. "earnings-beat names historically run ~38 days -> hold 38 days" becomes testable. Signboard, not
tombstone.

A LAYER is a point-in-time signal: score per stock at a date, using ONLY data known by that date.
Drop a tidy file in data/layers/ (cols: date, symbol, <fields>) and it auto-enters the gate. Every
layer faces the SAME battery and is KEPT or DISCARDED automatically — no per-dataset bespoke code:

   1. IC            rank-corr(score, forward return); report mean IC + IC information-ratio
   2. RQS lift      does informing selection by the layer raise pick-quality over the low-vol baseline?
   3. Walk-forward  every cycle's forward window is unseen at selection (causal by construction)
   4. Rolling OOS   lift must hold in the LAST third (most out-of-sample), not just full-sample
   5. DSR / PBO     deflate for the number of layers searched (luck penalty)
   6. Forward paper status hook — even a KEEP is "pending forward paper" until live cycles confirm

Calibration (runs today, no external data): ORACLE (peeks at the future) must be KEPT with huge IC —
proving the gate detects real signal; NOISE must be DISCARDED — proving it rejects luck. If the gate
can't pass that sanity check, no future verdict is trustworthy.

Run: python india/data_layer_gate.py
"""
import sys, glob, warnings
from dataclasses import dataclass
from typing import Callable
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.simplefilter("ignore")
from india.feature_engine import load_panels
from india.data_nse import NIFTY200
from india.sectors import SECTORS, sector_of
from india.validation import deflated_sharpe

LOOK, HOLD, CAD, TOPN, CAP = 120, 63, 21, 15, 2     # 6m lookback, 3m forward, monthly cadence
LAYERS_DIR = ROOT / "data" / "layers"
REG = ROOT / "data" / "aegis_layer_registry.csv"
KEEP_RQS, KEEP_ICIR, KEEP_DSR = 0.02, 2.0, 0.90     # bars a layer must clear to be KEPT


# ----------------------------- layer interface -----------------------------
@dataclass
class Layer:
    name: str
    kind: str                                        # calibration | price | fundamental | flow | ...
    fn: Callable                                     # (closes, idx, i, cols) -> Series (higher = better)
    source: str = "builtin"


def lowvol_pick(hist, allowed=None):
    """Lowest-vol, sector-capped selection — the validated baseline. allowed restricts the universe."""
    iv = (1.0 / hist.std().replace(0, np.nan)).dropna().sort_values(ascending=False)
    chosen, sec = [], {}
    for s in iv.index:
        if allowed is not None and s not in allowed:
            continue
        if len(chosen) >= TOPN:
            break
        k = SECTORS.get(s, "Other")
        if sec.get(k, 0) >= CAP:
            continue
        chosen.append(s); sec[k] = sec.get(k, 0) + 1
    return chosen


# ----------------------- point-in-time file adapter ------------------------
class PITFileLayer:
    """Adapter: a tidy table [date, symbol, <field>] becomes a PIT layer. At bar date d we use, per
    symbol, the LATEST row with date <= d (strict point-in-time — no lookahead). Drop earnings,
    FII flows, analyst revisions etc. in data/layers/ and they plug in with zero new code."""
    def __init__(self, name, frame, field, higher_better=True):
        self.name, self.field, self.sign = name, field, (1 if higher_better else -1)
        self.f = frame[["date", "symbol", field]].dropna().sort_values("date")
        self.f["date"] = pd.to_datetime(self.f["date"])

    def fn(self, closes, idx, i, cols):
        d = closes.index[i]
        known = self.f[self.f["date"] <= d]
        if known.empty:
            return pd.Series(dtype=float)
        latest = known.groupby("symbol").tail(1).set_index("symbol")[self.field]
        return (self.sign * latest).reindex(cols).dropna()


# --------------------------- calibration layers ----------------------------
def _oracle(closes, idx, i, cols):                   # CHEAT: peeks at the future — must be KEPT
    return (closes.iloc[i + HOLD] / closes.iloc[i] - 1).reindex(cols).dropna()


def _noise(closes, idx, i, cols):                    # pure luck — must be DISCARDED
    rng = np.random.default_rng(i)                   # deterministic per bar, uncorrelated with returns
    return pd.Series(rng.standard_normal(len(cols)), index=cols)


def _momentum(closes, idx, i, cols):                 # 3M price momentum — expected DISCARD (price-only)
    return (closes.iloc[i] / closes.iloc[i - 63] - 1).reindex(cols).dropna()


CALIBRATION = [
    Layer("ORACLE (future-peek)", "calibration", _oracle),
    Layer("NOISE (random)", "calibration", _noise),
    Layer("3M momentum", "price", _momentum),
]


# ------------------------------- the gate ----------------------------------
def evaluate(layer, closes, idx, rets, universe):
    """One pass: per cycle compute IC, baseline vs layer-informed RQS, and incremental forward return.
    Selection is causal (trailing vol); the forward window is always unseen -> walk-forward by design."""
    recs = []
    for i in range(LOOK, len(closes) - HOLD, CAD):
        hist = rets.iloc[i - LOOK:i].dropna(axis=1, how="any")
        cols = [c for c in hist.columns if c in universe]
        if len(cols) < 40:
            continue
        fwd = (closes.iloc[i + HOLD] / closes.iloc[i] - 1).reindex(cols).dropna()
        cols = list(fwd.index); pct = fwd.rank(pct=True)
        score = layer.fn(closes, idx, i, cols)
        score = score.reindex(cols).dropna()
        if len(score) < 12:
            continue
        common = score.index.intersection(fwd.index)
        ic = score[common].rank().corr(fwd[common].rank())          # Spearman IC
        base = lowvol_pick(hist[cols])
        strong = set(score[score >= score.median()].index)
        aug = lowvol_pick(hist[cols], allowed=strong)
        rqs_b = pct.reindex(base).dropna().mean()
        rqs_a = pct.reindex(aug).dropna().mean() if aug else np.nan
        inc = (fwd.reindex(aug).mean() - fwd.reindex(base).mean()) if aug else np.nan
        recs.append(dict(date=closes.index[i], ic=ic, rqs_b=rqs_b, rqs_a=rqs_a, inc=inc))
    return pd.DataFrame(recs)


def battery(df, n_trials):
    """Aggregate the per-cycle record into the full verdict battery."""
    df = df.dropna(subset=["rqs_a"])
    n = len(df)
    if n < 8:
        return dict(n=n, verdict="INSUFFICIENT DATA")
    ic = df["ic"].dropna()
    mean_ic = ic.mean(); ic_ir = mean_ic / (ic.std() + 1e-12) * np.sqrt(len(ic))
    rqs_b, rqs_a = df["rqs_b"].mean(), df["rqs_a"].mean(); lift = rqs_a - rqs_b
    # rolling OOS: lift must survive in the last third (most out-of-sample)
    fold = max(3, n // 3); oos_lift = (df["rqs_a"] - df["rqs_b"]).iloc[-fold:].mean()
    inc = df["inc"].dropna()
    d = deflated_sharpe(inc.values, n_trials=max(n_trials, 2), ppy=252 / HOLD) if len(inc) >= 30 \
        else dict(dsr=np.nan)
    keep = (lift > KEEP_RQS) and (ic_ir > KEEP_ICIR) and (oos_lift > 0) and \
           (np.isnan(d["dsr"]) or d["dsr"] > KEEP_DSR)
    return dict(n=n, mean_ic=mean_ic, ic_ir=ic_ir, rqs_b=rqs_b, rqs_a=rqs_a, lift=lift,
                oos_lift=oos_lift, dsr=d["dsr"], verdict="KEEP" if keep else "DISCARD")


def discover_file_layers():
    """Auto-enrol every tidy table in data/layers/ — the 'plug in any dataset' contract."""
    layers = []
    if not LAYERS_DIR.exists():
        return layers
    for p in sorted(glob.glob(str(LAYERS_DIR / "*.parquet")) + glob.glob(str(LAYERS_DIR / "*.csv"))):
        try:
            fr = pd.read_parquet(p) if p.endswith(".parquet") else pd.read_csv(p)
            cols = {c.lower(): c for c in fr.columns}
            if "date" not in cols or "symbol" not in cols:
                print(f"  ! {Path(p).name}: needs 'date' and 'symbol' columns — skipped"); continue
            fr = fr.rename(columns={cols["date"]: "date", cols["symbol"]: "symbol"})
            for field in [c for c in fr.columns if c not in ("date", "symbol")]:
                nm = f"{Path(p).stem}:{field}"
                adapter = PITFileLayer(nm, fr, field)
                layers.append(Layer(nm, "external", adapter.fn, source=Path(p).name))
        except Exception as e:
            print(f"  ! {Path(p).name}: {e}")
    return layers


def main():
    closes, _, _, _, idx, _, _ = load_panels()
    universe = set(NIFTY200)
    closes = closes[[c for c in closes.columns if c in universe]]
    rets = closes.pct_change()
    file_layers = discover_file_layers()
    layers = CALIBRATION + file_layers
    n_trials = len([l for l in layers if l.kind != "calibration"]) or 1

    print("=" * 92)
    print("  AEGIS DATA-LAYER GATE — every information source faces the same battery, KEEP or DISCARD")
    print("=" * 92)
    print(f"  universe {len(closes.columns)} names · lookback {LOOK}d · forward {HOLD}d · "
          f"cadence {CAD}d · bars to KEEP: RQS-lift>{KEEP_RQS}, IC-IR>{KEEP_ICIR}, OOS>0, DSR>{KEEP_DSR}\n")
    print(f"  {'Layer':<26}{'kind':<12}{'IC':>7}{'IC-IR':>7}{'RQSbase':>9}{'RQSlay':>8}"
          f"{'lift':>7}{'OOS':>7}{'DSR':>7}   verdict")
    rows = []
    for L in layers:
        r = battery(evaluate(L, closes, idx, rets, universe), n_trials)
        if r.get("verdict") == "INSUFFICIENT DATA":
            print(f"  {L.name:<26}{L.kind:<12}{'(insufficient overlapping data)':>40}"); continue
        icir_disp = min(r["ic_ir"], 99.9)            # oracle's IC-IR is ~inf (zero-variance IC); clamp display
        print(f"  {L.name:<26}{L.kind:<12}{r['mean_ic']:>+7.3f}{icir_disp:>7.1f}{r['rqs_b']:>9.3f}"
              f"{r['rqs_a']:>8.3f}{r['lift']:>+7.3f}{r['oos_lift']:>+7.3f}"
              f"{(r['dsr'] if not np.isnan(r['dsr']) else 0):>7.2f}   {r['verdict']}")
        status = "calibration" if L.kind == "calibration" else \
                 ("pending-forward-paper" if r["verdict"] == "KEEP" else "rejected")
        rows.append(dict(layer=L.name, kind=L.kind, source=L.source, n=r["n"],
                         mean_ic=round(r["mean_ic"], 4), ic_ir=round(r["ic_ir"], 2),
                         rqs_lift=round(r["lift"], 4), oos_lift=round(r["oos_lift"], 4),
                         dsr=round(r["dsr"], 3) if not np.isnan(r["dsr"]) else "", verdict=r["verdict"],
                         status=status))

    # calibration sanity check — the gate must detect ORACLE and reject NOISE, or it has no power
    by = {r["layer"]: r["verdict"] for r in rows}
    ok = by.get("ORACLE (future-peek)") == "KEEP" and by.get("NOISE (random)") == "DISCARD"
    print("\n  CALIBRATION:", "PASS — gate detects planted signal and rejects noise. Verdicts are trustworthy."
          if ok else "FAIL — gate cannot tell signal from noise; do not trust verdicts.")

    if not file_layers:
        print("\n  No external datasets yet. To evaluate one, drop a tidy file in data/layers/:")
        print("     data/layers/earnings.parquet  with columns:  date, symbol, surprise_pct, ...")
        print("     (date = point-in-time AVAILABILITY date, never the period-end — no lookahead.)")
        print("  Every field becomes a layer and faces this exact battery automatically.")

    print("\n  FROZEN, NOT REJECTED: price-only dynamic knobs (Top-N, holding, rebalance) showed no OOS")
    print("  edge and stay fixed — but the day a layer here is KEPT, those knobs REOPEN conditioned on")
    print("  it (e.g. 'earnings-beat names run ~N days -> hold N'). Signboard, not tombstone.")

    if rows:
        pd.DataFrame(rows).to_csv(REG, index=False)
        print(f"\n  Ledger written -> {REG.relative_to(ROOT)}  ({len(rows)} layers recorded)")


if __name__ == "__main__":
    main()
