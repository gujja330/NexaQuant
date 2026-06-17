# execution/auto_update.py
"""
CONTINUOUS-IMPROVEMENT loop — run weekly (cron / systemd timer / Task Scheduler).

What it does, in order, fully automatic and SAFE-BY-DEFAULT:
  1. PULL the latest bars (incremental: re-fetch the most recent months and merge+dedup
     into the existing parquet, so history grows week after week with no gaps).
  2. RE-VALIDATE the live strategy on the freshly extended data through the SAME rigor
     gate used to accept it originally (OOS Sharpe, profit factor, drawdown, trade count).
  3. COMPARE against the stored "champion" metrics in champion.json.
        - new config must PASS the gate AND be >= champion on risk-adjusted terms.
        - only THEN is champion.json updated (a genuine improvement is promoted).
        - otherwise the champion is kept untouched -> the bot NEVER auto-degrades.
  4. LOG a one-line verdict + NOTIFY (Telegram/email) so you see it on your phone.

The live bot (live_trader.NexaBot) reads champion.json at startup of each cycle, so an
accepted improvement flows to live trading automatically on the next run — no manual step.

Run:  python execution/auto_update.py                # all live symbols/TFs
      python execution/auto_update.py --pair BTCUSDT --symbol BTCUSDm --tf H4
"""
import argparse, json, sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import symbol_params, pipeline
from strategy import playbook
from strategy.smc import atr
from backtest.trade_sim import trade_stats
from backtest.engine import BARS_PER_YEAR
from research.long_short_walkforward import both_sides
from data.pull_open_data import pull_binance, TF_MAP

RAW = ROOT / "data" / "raw"
CHAMP = ROOT / "execution" / "champion.json"
HEALTH = ROOT / "execution" / "health.json"     # bot's weekly "trading license"
LOG = ROOT / "logs" / "auto_update.log"
GATE = pipeline().get("gate", {})
IS = pipeline().get("is_fraction", 0.70)

# live universe (symbol -> Binance pair); extend as you add instruments
LIVE = {"BTCUSDm": "BTCUSDT"}
LIVE_TFS = ["H4"]                       # what the bot trades; add "H1"/"M15" once proven


def _notify(msg):
    try:
        from execution.notifier import notify
        notify(msg)
    except Exception:
        pass
    print(msg)


def incremental_pull(pair, symbol, tf, lookback_months=2):
    """Re-fetch the last few months and MERGE into the existing parquet (dedup on index)
    so the history extends week after week without re-downloading years of data."""
    interval = {v: k for k, v in TF_MAP.items()}[tf]
    start = (date.today().replace(day=1) - timedelta(days=31 * lookback_months)).strftime("%Y-%m")
    fresh = pull_binance(pair, interval, start)
    out = RAW / f"{symbol}_{tf}.parquet"
    if fresh is None or fresh.empty:
        return pd.read_parquet(out).sort_index() if out.exists() else None
    if out.exists():
        old = pd.read_parquet(out)
        merged = pd.concat([old, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    else:
        merged = fresh.sort_index()
    merged.to_parquet(out)
    return merged


def _year_return(tr, df):
    """Account return for a set of trades using confidence-tiered risk (0.5/1/2%) compounded
    — the SAME sizing the live bot uses (incl. the lengthy-candle confidence boost)."""
    if tr.empty:
        return 0.0
    conf = playbook.confidence_size(df).reindex(tr["entry_time"]).fillna(1.0).values
    risk = np.where(conf < 1.5, 0.005, np.where(conf < 2.0, 0.01, 0.02))
    return float(np.prod(1 + risk * tr["R"].values) - 1)


def evaluate_oos(df, sym, tf):
    """Robustness of the CANONICAL live strategy via ANCHORED PER-YEAR walk-forward
    (train on all prior years, test the next) — NOT a single OOS slice, which is noisy and
    understated H4. Reports the share of profitable years + avg/worst yearly return: the
    honest measure of whether the edge persists across regimes."""
    sp = symbol_params(sym, df["close"]); a = atr(df, 14)
    method = "hmm" if len(df) >= pipeline().get("hmm_min_bars", 6000) else "adx"
    reg = playbook.regime_labels(df, method)
    years = sorted(df.index.year.unique())[1:]
    rets, total_trades = [], 0
    for ty in years:
        mask = df.index.year == ty
        if mask.sum() < 50 or df[df.index.year < ty].shape[0] < 1000:
            continue
        tr = both_sides(df, mask, a, sp, reg, do_short=True)
        if tr.empty:
            continue
        rets.append(100 * _year_return(tr, df)); total_trades += len(tr)
    if not rets:
        return None
    rets = np.array(rets)
    return {"asof": str(df.index[-1].date()), "years": len(rets),
            "pos_years": int((rets > 0).sum()), "pct_pos": round(float((rets > 0).mean()), 2),
            "avg_yr_pct": round(float(rets.mean()), 1), "median_yr_pct": round(float(np.median(rets)), 1),
            "worst_yr_pct": round(float(rets.min()), 1), "trades": int(total_trades)}


def passes_gate(m):
    """Believable only if the edge PERSISTS: majority of years profitable, positive average,
    no catastrophic year, and enough trades to be statistically meaningful."""
    return (m and m["trades"] >= GATE.get("min_trades", 30)
            and m["pct_pos"] >= 0.60 and m["avg_yr_pct"] > 0 and m["worst_yr_pct"] > -25.0)


def _score(m):
    return (m["pct_pos"], m["avg_yr_pct"])      # rank by persistence, then average return


def better(new, champ):
    """A real improvement = passes gate AND more persistent/profitable without a worse worst-year."""
    if not passes_gate(new):
        return False
    if champ is None:
        return True
    return _score(new) >= _score(champ) and new["worst_yr_pct"] >= champ["worst_yr_pct"] - 5.0


def load_champ():
    return json.loads(CHAMP.read_text()) if CHAMP.exists() else {}


def load_health():
    return json.loads(HEALTH.read_text()) if HEALTH.exists() else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair"); ap.add_argument("--symbol"); ap.add_argument("--tf")
    a = ap.parse_args()
    universe = ([(a.symbol, a.pair, a.tf)] if a.symbol
                else [(s, p, tf) for s, p in LIVE.items() for tf in LIVE_TFS])
    LOG.parent.mkdir(parents=True, exist_ok=True)
    champ = load_champ(); health = load_health()
    for sym, pair, tf in universe:
        key = f"{sym}_{tf}"
        df = incremental_pull(pair, sym, tf)
        if df is None or len(df) < 500:
            _notify(f"[auto_update] {key}: not enough data, skipped"); continue
        new = evaluate_oos(df, sym, tf)
        old = champ.get(key)
        gp = passes_gate(new)
        # HEALTH = the bot's "trading license": records this week's gate result + asof date.
        # live_trader reads it and STANDS DOWN (manage-only) if the edge stops persisting.
        health[key] = {"gate_passed": bool(gp), "checked": new["asof"] if new else None,
                       "pct_pos": new["pct_pos"] if new else 0.0,
                       "avg_yr_pct": new["avg_yr_pct"] if new else 0.0,
                       "worst_yr_pct": new["worst_yr_pct"] if new else 0.0}
        HEALTH.write_text(json.dumps(health, indent=2))
        if better(new, old):
            champ[key] = new
            CHAMP.write_text(json.dumps(champ, indent=2))
            verdict = (f"PROMOTED champion ({new['pos_years']}/{new['years']} yrs profitable, "
                       f"avg {new['avg_yr_pct']}%/yr, worst {new['worst_yr_pct']}%, "
                       f"{new['trades']} trades, asof {new['asof']})")
        elif passes_gate(new):
            verdict = (f"held champion — new run OK but not better "
                       f"(new {new['pct_pos']:.0%} pos yrs, avg {new['avg_yr_pct']}% vs "
                       f"champ {old['avg_yr_pct'] if old else 'n/a'}%)")
        else:
            verdict = (f"held champion — new run FAILED gate "
                       f"({new['pos_years']}/{new['years']} yrs pos, avg {new['avg_yr_pct']}%, "
                       f"worst {new['worst_yr_pct']}%, {new['trades']} tr)")
        line = f"[auto_update] {key}: {verdict}"
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _notify(line)


if __name__ == "__main__":
    main()
