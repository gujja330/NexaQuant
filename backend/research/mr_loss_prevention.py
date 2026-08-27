"""AEGIS · M-R2 · Loss Prevention Report · Sprint M.

For every LOSER prediction (fwd_5d < -0.5% OR final realized loss < -3%),
answers:

  L1 · Was information available BEFORE entry that should have flagged it?
       - RSI overbought at entry?
       - vol_20d > 3%?
       - trend below MA200 while runner marked BUY?
       - band=OK or AVOID?
       - confidence in the anti-signal bucket (India 70-85)?
       - top-3 slot in India (known inversion)?

  L2 · Would a tighter/wider stop have helped?
       - Compare CURRENT stop distance vs FIXED_5, FIXED_7_5, TRAILING_10
       - MFE_prior_to_MAE_pct · how much profit was left on table

  L3 · Would waiting 1/3/5 days have improved entry?
       - fwd_1/3/5 vs entry ratio · did stock drop then bounce?

  L4 · Classification bucket:
       - PREVENTABLE_HIGH_CONF     · anti-signal features present at entry
       - PREVENTABLE_STOP_WIDE     · alternative stop would have saved capital
       - PREVENTABLE_TIMING        · waiting would have been better
       - MARKET_WIDE               · lost when regime was BEAR
       - UNAVOIDABLE               · none of the above · genuine adverse outcome

Emits reports/research/mr_loss_prevention_{market}.json + per-loss ledger.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Optional

from backend.research.mr_runner import EXPERIMENT_ID, ALLOWED_WRITE_ROOT

ENGINE_ID = "aegis.mr_loss_prevention.v0.1"

LOSS_THRESHOLD = -0.5


def _load_rows(root: Path, market: str) -> list:
    p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}_enriched.jsonl"
    if not p.exists():
        p = root / ALLOWED_WRITE_ROOT / f"mr_prediction_autopsy_{market.lower()}.jsonl"
    if not p.exists(): return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _load_regime(root: Path, market: str) -> dict:
    p = root / ALLOWED_WRITE_ROOT / f"mr_market_regime_{market.lower()}.json"
    if not p.exists(): return {}
    try: return json.loads(p.read_text(encoding="utf-8")).get("regimes", {})
    except Exception: return {}


def _anti_signal_flags(r: dict, market: str) -> list:
    flags = []
    rsi = r.get("rsi_14")
    if isinstance(rsi, (int,float)) and rsi >= 70:
        flags.append("RSI_OVERBOUGHT")
    vol = r.get("vol_20d_pct")
    if isinstance(vol, (int,float)) and vol >= 3.0:
        flags.append("HIGH_VOL_GE3PCT")
    tr = r.get("trend")
    if tr == "BELOW_MA200":
        flags.append("BELOW_MA200")
    band = r.get("investability_band")
    if band in ("OK","AVOID"):
        flags.append(f"BAND_{band}")
    conf = r.get("confidence_pct")
    # India-specific anti-signal: high confidence
    if market.lower() == "india" and isinstance(conf, (int,float)) and 70 <= conf <= 85:
        flags.append("INDIA_CONFIDENCE_ANTI_SIGNAL_70_85")
    # India-specific: top-3 rank
    rk = r.get("rank")
    if market.lower() == "india" and isinstance(rk, int) and rk <= 3:
        flags.append("INDIA_TOP3_RANK_INVERSION")
    ma20 = r.get("ma20_dist_pct")
    if isinstance(ma20, (int,float)) and ma20 <= -5:
        flags.append("DEEP_BELOW_MA20")
    return flags


def _stop_alternatives_helped(r: dict) -> Optional[str]:
    mae = r.get("mae_pct"); mfe = r.get("mfe_pct")
    if mae is None or mfe is None: return None
    # if MFE ~2%+ before MAE hit, wider trailing might have banked profit
    if mfe >= 2.0 and mae <= -5.0:
        return "TRAILING_STOP_WOULD_HAVE_BANKED_GAINS"
    if mae <= -7.5:
        return "FIXED_5_WOULD_HAVE_CAPPED_LOSS"
    return None


def _timing_helped(r: dict) -> Optional[str]:
    f1 = r.get("fwd_1d_pct"); f3 = r.get("fwd_3d_pct"); f5 = r.get("fwd_5d_pct")
    if not all(isinstance(x,(int,float)) for x in (f1,f3,f5)): return None
    # If day1 dropped -2%+ but day3 or day5 recovered above 0, entry timing was bad
    if f1 <= -2.0 and (f5 is not None and f5 > 0):
        return "WAITING_5D_WOULD_HAVE_CAPTURED_BOUNCE"
    if f1 <= -1.0 and (f3 is not None and f3 > 0):
        return "WAITING_3D_WOULD_HAVE_CAPTURED_BOUNCE"
    return None


def classify(r: dict, market: str, regime: str) -> dict:
    anti = _anti_signal_flags(r, market)
    stop = _stop_alternatives_helped(r)
    timing = _timing_helped(r)
    if regime == "BEAR":
        base = "MARKET_WIDE"
    elif len(anti) >= 3:
        base = "PREVENTABLE_HIGH_CONF"
    elif stop:
        base = "PREVENTABLE_STOP_WIDE"
    elif timing:
        base = "PREVENTABLE_TIMING"
    elif anti:
        base = "PREVENTABLE_MODERATE"
    else:
        base = "UNAVOIDABLE"
    return {
        "classification":   base,
        "anti_signal_flags": anti,
        "stop_suggestion":   stop,
        "timing_suggestion": timing,
        "regime_at_entry":   regime,
    }


def run_market(root: Path, market: str) -> dict:
    rows = _load_rows(root, market)
    if not rows: return {}
    regimes = _load_regime(root, market)
    losses = []
    for r in rows:
        f5 = r.get("fwd_5d_pct")
        mae = r.get("mae_pct")
        # Loss condition: forward 5D < -0.5% OR MAE hit -3%
        loss5d = isinstance(f5, (int,float)) and f5 < LOSS_THRESHOLD
        loss_mae = isinstance(mae, (int,float)) and mae <= -3.0
        if not (loss5d or loss_mae): continue
        regime = regimes.get(r.get("prediction_date",""), "UNKNOWN")
        cls = classify(r, market, regime)
        losses.append({
            "prediction_date":     r.get("prediction_date"),
            "ticker":              r.get("ticker"),
            "runner":              r.get("runner"),
            "rank":                r.get("rank"),
            "confidence_pct":      r.get("confidence_pct"),
            "investability_band":  r.get("investability_band"),
            "sector":              r.get("sector"),
            "cap_bucket":          r.get("cap_bucket"),
            "rsi_14":              r.get("rsi_14"),
            "vol_20d_pct":         r.get("vol_20d_pct"),
            "ma20_dist_pct":       r.get("ma20_dist_pct"),
            "trend":               r.get("trend"),
            "entry_price_at_pred": r.get("entry_price_at_pred"),
            "stop_at_pred":        r.get("stop_at_pred"),
            "fwd_1d_pct":          r.get("fwd_1d_pct"),
            "fwd_3d_pct":          r.get("fwd_3d_pct"),
            "fwd_5d_pct":          r.get("fwd_5d_pct"),
            "fwd_10d_pct":         r.get("fwd_10d_pct"),
            "mfe_pct":             r.get("mfe_pct"),
            "mae_pct":             r.get("mae_pct"),
            "classification":      cls["classification"],
            "anti_signal_flags":   cls["anti_signal_flags"],
            "stop_suggestion":     cls["stop_suggestion"],
            "timing_suggestion":   cls["timing_suggestion"],
            "regime_at_entry":     cls["regime_at_entry"],
        })
    # Aggregates
    total = len(losses)
    by_class = Counter(l["classification"] for l in losses)
    by_runner = defaultdict(int)
    for l in losses: by_runner[l["runner"]] += 1
    # Most-common anti-signals
    anti_counter: Counter = Counter()
    for l in losses:
        for f in l["anti_signal_flags"]: anti_counter[f] += 1
    preventable_pct = round(
        sum(v for k, v in by_class.items() if k.startswith("PREVENTABLE"))
        / max(1, total) * 100, 2)
    return {
        "engine":            ENGINE_ID,
        "experiment_id":     EXPERIMENT_ID,
        "generated_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market":            market.upper(),
        "n_predictions":     len(rows),
        "n_losses":          total,
        "loss_rate_pct":     round(total / max(1, len(rows)) * 100, 2),
        "by_classification": dict(by_class),
        "preventable_pct":   preventable_pct,
        "by_runner":         dict(by_runner),
        "top_anti_signals":  dict(anti_counter.most_common(20)),
        "losses":            losses,
    }


def emit(root: Path, market: str, res: dict) -> Path:
    p = root / ALLOWED_WRITE_ROOT / f"mr_loss_prevention_{market.lower()}.json"
    p.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def render_console(res: dict):
    if not res: return
    print(f"\n======== LOSS PREVENTION · {res['market']} · "
          f"n_losses={res['n_losses']}/{res['n_predictions']} "
          f"loss_rate={res['loss_rate_pct']}% ========")
    print(f"  preventable_pct  = {res['preventable_pct']}%")
    print(f"  by_classification: {res['by_classification']}")
    print(f"  by_runner: {res['by_runner']}")
    print(f"  top anti-signals present in losers:")
    for f, n in res["top_anti_signals"].items():
        print(f"    {f:40s} n={n}")
    print(f"\n  Sample losses (10):")
    for l in res["losses"][:10]:
        f5 = l.get('fwd_5d_pct')
        f5s = f"{f5:+.2f}%" if isinstance(f5, (int,float)) else "—"
        print(f"    {l['prediction_date']} · {str(l['ticker']):12s} · "
              f"{str(l['runner']):3s} · rk={l['rank']} · conf={l['confidence_pct']} · "
              f"band={l['investability_band']} · fwd5d={f5s} · "
              f"MAE={l['mae_pct']}% · class={l['classification']}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", choices=["india","usa","both"], default="both")
    args = ap.parse_args()
    root = Path(".").resolve()
    for m in (["india","usa"] if args.market=="both" else [args.market]):
        res = run_market(root, m)
        p = emit(root, m, res)
        render_console(res)
        print(f"\n[loss_prevention:{m}] -> {p.name}")
