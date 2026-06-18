# execution/ccxt_trader.py
"""
NexaQuant CCXT bot — native crypto-exchange execution (NO MetaTrader / NO Wine).

Runs the SAME validated multi-edge engine (trend + breakout, long+short) against a crypto
exchange via the CCXT library. Pure-Python, so it runs cleanly on a 1GB Linux VM where
MT5+Wine cannot. Paper-trades on the exchange's free TESTNET by default (fake money).

Design mirrors execution/live_trader.NexaBot:
  * each (symbol x edge) is a SLEEVE with its own position, sharing ONE exchange connection
    and ONE account-wide RiskManager (portfolio cap + kill switch span all sleeves)
  * dynamic risk sizing: amount = (balance x risk% x confidence) / stop_distance   (no hardcoding)
  * software-managed exits: scale-out 40% at +1.5R -> breakeven, momentum-ride, hard ATR stop
  * modes: dry-run (local parquet replay, no exchange) | paper (testnet) | live (real funds)

Setup on the VM (native python3, no Wine):
    python3 -m pip install --user ccxt
    export CCXT_API_KEY=...  CCXT_SECRET=...        # free TESTNET keys
    python3 execution/ccxt_trader.py --mode paper --poll 60

Run (offline logic check, no keys/network):  python execution/ccxt_trader.py --mode dry-run
"""
import argparse, os, sys, time, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import cfg
from strategy import playbook, breakout
from strategy.smc import atr, ema
from strategy.risk_manager import RiskManager

EXIT = playbook.EXIT


def decide(df, edge):
    """Latest-bar decision for an edge (trend|breakout). Returns dict like NexaBot.decide."""
    reg = playbook.regime_labels(df, "adx")
    if edge == "breakout":
        n = int(cfg().get("ccxt", {}).get("breakout_len",
                cfg().get("edges", {}).get("breakout", {}).get("length", 20)))
        long_sig = bool(breakout.entries(df, side="long", n=n).iloc[-1])
        short_sig = bool(breakout.entries(df, side="short", n=n).iloc[-1])
    else:
        long_sig = bool(playbook.entries(df, side="long", regime=reg).iloc[-1])
        short_sig = bool(playbook.entries(df, side="short", regime=reg).iloc[-1])
    a = atr(df, 14); bar = df.iloc[-1]; atr_now = float(a.iloc[-1])
    ema20 = ema(df["close"], 20).iloc[-1]
    side = 1 if long_sig else (-1 if short_sig else 0)
    sl = bar["close"] - side * EXIT["stop_mult"] * atr_now if side else None
    conf = float(playbook.confidence_size(df).iloc[-1])
    return {"time": str(df.index[-1]), "price": float(bar["close"]), "atr": atr_now,
            "side": side, "entry_signal": side != 0, "conf": round(conf, 2),
            "stop_loss": float(sl) if sl else None, "ema20": float(ema20)}


class Sleeve:
    """One (symbol, edge) strategy sleeve with its own position, sharing the parent's exchange + RM."""
    def __init__(self, parent, symbol, edge):
        self.p = parent; self.symbol = symbol; self.edge = edge
        self.tag = f"{symbol}/{edge}"; self.pos = None

    def _risk_frac(self, conf):
        base = float(cfg().get("account", {}).get("risk_per_trade", 0.005))
        cap = float(max(t[1] for t in cfg().get("sizing", {}).get("risk_tiers", [[99, 0.02]])))
        return float(min(base * conf, cap))

    def _amount(self, dec):
        """Dynamic size: contracts/base = risk_$ / stop_distance. Rounded to exchange precision."""
        stop_dist = abs(dec["price"] - dec["stop_loss"])
        if stop_dist <= 0:
            return 0.0
        risk_amt = self.p.rm.equity * self._risk_frac(dec["conf"])
        amt = risk_amt / stop_dist
        try:
            amt = float(self.p.ex.amount_to_precision(self.symbol, amt))
        except Exception:
            amt = round(amt, 6)
        return amt

    def manage(self, dec):
        if self.pos is None:
            return None
        p, price, sd = self.pos, dec["price"], self.pos["side"]
        if not p["scaled"] and sd * (price - p["entry"]) / p["risk"] >= EXIT["partial_at"]:
            p["scaled"] = True
            p["sl"] = max(p["sl"], p["entry"]) if sd == 1 else min(p["sl"], p["entry"])
            return "scale"
        if sd * (price - p["sl"]) <= 0:
            return "exit-stop"
        mom_ok = (price > dec["ema20"]) if sd == 1 else (price < dec["ema20"])
        if not mom_ok:
            return "exit-momentum"
        return None

    def step(self, df):
        dec = decide(df, self.edge)
        # manage existing
        if self.pos is not None:
            act = self.manage(dec)
            if act == "scale":
                cut = self.pos["amount0"] * EXIT["partial_frac"]
                self.p._close(self, cut, self.pos["side"], "scale", dec)
                self.pos["amount"] -= cut
            elif act and act.startswith("exit"):
                self.p._close(self, self.pos["amount"], self.pos["side"], act, dec)
                self.pos = None
        # new entry
        if self.pos is None and dec["entry_signal"]:
            rf = self._risk_frac(dec["conf"])
            ok, why = self.p.rm.can_open(dec["time"], rf)
            if not ok:
                if "KILL" in why:
                    self.p.notify(f"KILL-SWITCH {self.tag}: {why}")
                return dec
            amt = self._amount(dec)
            if amt <= 0:
                return dec
            self.pos = {"entry": dec["price"], "sl": dec["stop_loss"], "side": dec["side"],
                        "risk": abs(dec["price"] - dec["stop_loss"]), "amount": amt,
                        "amount0": amt, "scaled": False, "risk_frac": rf}
            self.p.rm.on_open(rf)
            self.p._open(self, amt, dec["side"], dec)
        return dec


class CCXTBot:
    def __init__(self, mode="dry-run"):
        c = cfg().get("ccxt", {})
        self.mode = mode
        self.exchange_id = c.get("exchange", "bybit")
        self.testnet = bool(c.get("testnet", True))
        self.market_type = c.get("market_type", "swap")
        self.symbols = list(c.get("symbols", ["BTC/USDT:USDT"]))
        self.edges = list(c.get("edges", ["trend"]))
        self.tf = c.get("timeframe", "4h")
        self.leverage = int(c.get("leverage", 2))
        self.ex = None
        sysc = cfg().get("system", {})
        self.rm = RiskManager(float(cfg().get("account", {}).get("starting_equity", 1000.0)),
                              risk_per_trade=sysc.get("risk_per_trade", 0.005),
                              max_drawdown=sysc.get("max_drawdown_limit", 0.20))
        self.sleeves = [Sleeve(self, s, e) for s in self.symbols for e in self.edges]

    # ---------- exchange ----------
    def connect(self):
        if self.mode == "dry-run":
            print(f"  dry-run: no exchange ({self.exchange_id}); replaying local data")
            return True
        import ccxt
        klass = getattr(ccxt, self.exchange_id)
        self.ex = klass({"apiKey": os.environ.get("CCXT_API_KEY"),
                         "secret": os.environ.get("CCXT_SECRET"),
                         "enableRateLimit": True,
                         "options": {"defaultType": self.market_type}})
        if self.testnet:
            self.ex.set_sandbox_mode(True)
        self.ex.load_markets()
        for s in self.symbols:
            try:
                self.ex.set_leverage(self.leverage, s)
            except Exception:
                pass
        self._refresh_equity()
        print(f"  connected: {self.exchange_id} {'TESTNET' if self.testnet else 'LIVE'} "
              f"balance={self.rm.equity:.2f} USDT  symbols={self.symbols} edges={self.edges} "
              f"({len(self.sleeves)} sleeves)")
        return True

    def _refresh_equity(self):
        if self.mode == "dry-run" or self.ex is None:
            return
        try:
            bal = self.ex.fetch_balance()
            free = bal.get(cfg().get("ccxt", {}).get("quote", "USDT"), {}).get("free")
            if free:
                self.rm.equity = float(free); self.rm.peak = max(self.rm.peak, self.rm.equity)
        except Exception as e:
            print(f"  ! balance refresh failed: {e}")

    def bars(self, symbol, n=400):
        if self.mode == "dry-run":
            local = symbol.split("/")[0] + "USDm"      # BTC/USDT:USDT -> BTCUSDm (local proxy)
            tf = {"4h": "H4", "1h": "H1", "1d": "D1"}.get(self.tf, "H4")
            return pd.read_parquet(ROOT / f"data/raw/{local}_{tf}.parquet").sort_index()
        o = self.ex.fetch_ohlcv(symbol, timeframe=self.tf, limit=n)
        df = pd.DataFrame(o, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df.set_index("time").sort_index()

    # ---------- orders ----------
    def _open(self, sleeve, amount, side, dec):
        msg = (f"{'BUY' if side == 1 else 'SELL'} {sleeve.tag} @ {dec['price']} "
               f"SL={dec['stop_loss']} amt={amount} conf={dec['conf']}x")
        print(f"  [{dec['time']}] {msg}")
        if self.mode == "dry-run" or self.ex is None:
            return
        try:
            self.ex.create_order(sleeve.symbol, "market", "buy" if side == 1 else "sell", amount)
            self.notify(msg)
        except Exception as e:
            print(f"  ! order failed {sleeve.tag}: {e}"); self.notify(f"ORDER FAILED {sleeve.tag}: {e}")
            sleeve.pos = None

    def _close(self, sleeve, amount, side, tag, dec):
        pnl = side * (dec["price"] - sleeve.pos["entry"]) * amount
        self.rm.on_close(pnl, sleeve.pos.get("risk_frac", 0.005) * amount / sleeve.pos["amount0"])
        print(f"  [{dec['time']}] CLOSE {sleeve.tag} ({tag}) amt={amount} pnl={pnl:.2f} eq={self.rm.equity:.2f}")
        if self.mode == "dry-run" or self.ex is None:
            return
        try:
            self.ex.create_order(sleeve.symbol, "market", "sell" if side == 1 else "buy",
                                 amount, params={"reduceOnly": True})
        except Exception as e:
            print(f"  ! close failed {sleeve.tag}: {e}")

    def notify(self, msg):
        if self.mode == "dry-run":
            return
        try:
            from execution.notifier import notify
            notify(msg, subject=f"NexaCCXT {self.mode}")
        except Exception:
            pass

    # ---------- loop ----------
    def run_once(self):
        self._refresh_equity()
        for sl in self.sleeves:
            try:
                sl.step(self.bars(sl.symbol))
            except Exception as e:
                print(f"  [{sl.tag}] cycle error: {e}")

    def replay(self, last=300):
        for sl in self.sleeves:
            df = self.bars(sl.symbol)
            print(f"=== DRY-RUN {sl.tag} {self.tf}, last {last} bars ===")
            sub = df.iloc[-(last + 400):]
            for k in range(400, len(sub)):
                sl.step(sub.iloc[:k + 1])
            print(f"  final eq: {self.rm.equity:.2f}  {self.rm.status()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dry-run", "paper", "live"], default="dry-run")
    ap.add_argument("--live", action="store_true", help="confirm REAL-money trading")
    ap.add_argument("--poll", type=int, default=0)
    args = ap.parse_args()
    if args.mode == "live" and not args.live:
        sys.exit("Refusing live mode without --live (and a paper-passed config).")
    bot = CCXTBot(mode=args.mode)
    bot.connect()
    if args.mode == "dry-run":
        bot.replay()
    elif args.poll > 0:
        print(f"NexaCCXT {bot.exchange_id} {bot.tf} [{args.mode}] — polling every {args.poll}s")
        while True:
            bot.run_once(); time.sleep(args.poll)
    else:
        bot.run_once()


if __name__ == "__main__":
    main()
