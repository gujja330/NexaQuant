# execution/live_trader.py
"""
NexaQuant live/paper BOT for MetaTrader 5 — the deployable agent.

It REUSES the exact validated strategy modules (no logic duplication): playbook entries,
regime gate, event/volatility guard, momentum-ride exit + scale-out, and the risk-manager
kill switch. Once a config is validated (run_nexaquant.py GATE-PASS + 30-day paper), you
"throw" this bot at MT5 and it autonomously handles entries, position sizing, stop-loss,
breakeven, trailing, scale-out, and the daily-loss / drawdown kill switch.

MODES (configs/base_config.yaml system.paper_trading, or --mode):
  dry-run : NO broker — replays local data/raw bars and PRINTS the decisions it WOULD
            make (testable offline, right now). Proves the bot logic end-to-end.
  paper   : connect to an MT5 DEMO account and trade live data with fake money.
  live    : real account — requires explicit --live and a validated, paper-passed config.

MT4 NOTE: MT4 has no Python API. Run this brain in --signal-file mode (writes the current
decision to data/raw/signal_<SYMBOL>.json); a thin MQL4 Expert Advisor reads that file and
executes. Same brain, either platform.

Run (offline test):  python execution/live_trader.py --symbol XAUUSDm --tf H1 --mode dry-run
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config_loader import cfg, symbol_params, timeframes
from strategy import playbook
from strategy.smc import atr, ema
from strategy.risk_manager import RiskManager

EXIT = playbook.EXIT


class NexaBot:
    def __init__(self, symbol, tf, mode="dry-run", equity=10000.0, rm=None, mt5_handle=None, edge="trend"):
        self.symbol, self.tf, self.mode = symbol, tf, mode
        self.edge = edge          # "trend" or "breakout" — one SLEEVE of the multi-edge portfolio
        sysc = cfg().get("system", {})
        self.risk_per_trade = sysc.get("risk_per_trade", 0.01)
        # rm/mt5_handle injected => this bot is part of a MultiBot that shares ONE MT5 terminal
        # and ONE account-wide RiskManager (so portfolio risk + kill switch span ALL symbols).
        self._shared = rm is not None
        self.rm = rm if rm is not None else RiskManager(
            equity, risk_per_trade=self.risk_per_trade, max_drawdown=sysc.get("max_drawdown_limit", 0.20))
        self.pos = None          # paper/dry-run open position dict (this sleeve's own position)
        self.mt5 = mt5_handle
        self.sp = {"pip_size": 0.1, "cost": 0.5}
        self.health_file = ROOT / "execution" / "health.json"
        self.license_stale_days = 21    # weekly loop runs every 7d; >21d w/o a check = stale
        # stable per-sleeve MAGIC number so each (symbol,tf,edge) sleeve's orders/positions are
        # tracked independently at the broker and never interfere with another sleeve.
        self.magic = 1_000_000 + (abs(hash(f"{symbol}:{tf}:{edge}")) % 8_000_000)
        self.tag = f"{symbol}/{edge}"

    # ---------------- data ----------------
    def connect(self):
        if self.mode == "dry-run":
            return True
        if self._shared and self.mt5 is not None:
            return True              # parent MultiBot already initialised the terminal + equity
        import os
        import MetaTrader5 as mt5
        self.mt5 = mt5
        sysc = cfg()["system"]["mt5"]
        kw = dict(login=int(os.environ.get("MT5_LOGIN", sysc.get("login") or 0)),
                  password=os.environ.get("MT5_PASSWORD"),
                  server=os.environ.get("MT5_SERVER", sysc.get("server")))
        path = os.environ.get("MT5_PATH")              # auto-launch terminal (Wine/Windows)
        if path:
            kw["path"] = path
        if not mt5.initialize(**kw):
            sys.exit(f"MT5 connect failed: {mt5.last_error()}")
        # sync bot equity to the real account balance so sizing is correct
        acc = mt5.account_info()
        if acc:
            self.rm.equity = self.rm.peak = self.rm.start_equity = float(acc.balance)
            print(f"  connected: balance={acc.balance} {acc.currency}  server={kw['server']}")
        return True

    def get_bars(self, n=400):
        if self.mode == "dry-run":
            df = pd.read_parquet(ROOT / f"data/raw/{self.symbol}_{self.tf}.parquet").sort_index()
            return df
        tf_map = {"M5": self.mt5.TIMEFRAME_M5, "M15": self.mt5.TIMEFRAME_M15,
                  "H1": self.mt5.TIMEFRAME_H1, "H4": self.mt5.TIMEFRAME_H4,
                  "D1": self.mt5.TIMEFRAME_D1}
        r = self.mt5.copy_rates_from_pos(self.symbol, tf_map[self.tf], 0, n)
        df = pd.DataFrame(r); df["time"] = pd.to_datetime(df["time"], unit="s")
        return df.set_index("time").sort_index()

    # ---------------- decision logic (reuses validated strategy) ----------------
    def decide(self, df):
        """Direction-aware decision for the latest CLOSED bar, for THIS sleeve's edge:
          trend    : regime-gated EMA continuation (+ per-symbol TSM/macro gates)
          breakout : Donchian channel break (length from edges.breakout.length)
        Both ride the same ATR-stop + momentum-exit machinery, confidence-scaled size."""
        self.sp = symbol_params(self.symbol, df["close"])
        method = "hmm" if len(df) >= cfg().get("pipeline", {}).get("hmm_min_bars", 6000) else "adx"
        reg = playbook.regime_labels(df, method)
        if self.edge == "breakout":
            from strategy import breakout
            n = int(cfg().get("edges", {}).get("breakout", {}).get("length", 20))
            long_sig = bool(breakout.entries(df, side="long", n=n).iloc[-1])
            short_sig = bool(breakout.entries(df, side="short", n=n).iloc[-1])
        else:
            inst = cfg().get("instruments", {}).get(self.symbol, {})
            tsm = float(inst.get("tsm_confirm", 0.0)); mg = bool(inst.get("macro_gate", False))
            long_sig = bool(playbook.entries(df, side="long", regime=reg, tsm_confirm=tsm, macro_gate=mg).iloc[-1])
            short_sig = bool(playbook.entries(df, side="short", regime=reg, tsm_confirm=tsm, macro_gate=mg).iloc[-1])
        a = atr(df, 14); bar = df.iloc[-1]; atr_now = float(a.iloc[-1])
        ema20 = ema(df["close"], 20).iloc[-1]
        side = 1 if long_sig else (-1 if short_sig else 0)
        sl = bar["close"] - side * EXIT["stop_mult"] * atr_now if side else None
        conf = float(playbook.confidence_size(df).iloc[-1])      # trend-strength conviction
        # momentum_ok per side: long rides while above EMA, short while below
        mom_ok = (bar["close"] > ema20) if (self.pos and self.pos.get("side", 1) == 1) else (bar["close"] < ema20)
        return {"time": str(df.index[-1]), "price": float(bar["close"]), "atr": atr_now,
                "entry_signal": side != 0, "side": side, "conf": round(conf, 2),
                "stop_loss": round(sl, 3) if sl else None,
                "momentum_ok": bool(mom_ok)}

    def size(self, price, sl, conf=1.0):
        """Confidence-scaled, fixed-fractional risk sizing: (risk_$ x conf) / stop_distance."""
        stop_dist = abs(price - sl)
        if stop_dist <= 0:
            return 0.0
        risk_amt = self.rm.equity * self.risk_per_trade * conf
        return round(risk_amt / stop_dist, 4)

    # ---------------- position management ----------------
    def manage(self, df, dec):
        """SL + TRAILING PROFITS (no fixed lock): ride momentum, bank a partial at +R,
        move stop to breakeven, never cap the winner. Returns an action label and may
        ratchet the stop. Order: scale-out -> hard stop -> momentum-fade exit."""
        if self.pos is None:
            return None
        p, price = self.pos, dec["price"]
        sd = p["side"]                                              # +1 long, -1 short
        p["hwm"] = max(p.get("hwm", 0), sd * (price - p["entry"]))  # favourable excursion
        # 1) scale-out once at +partial_at R, then lift stop to breakeven (side-correct)
        if not p["scaled"] and sd * (price - p["entry"]) / p["risk"] >= EXIT["partial_at"]:
            p["scaled"] = True
            p["sl"] = max(p["sl"], p["entry"]) if sd == 1 else min(p["sl"], p["entry"])
            return "scale"
        # 2) hard / breakeven stop hit (long: price<=sl ; short: price>=sl)
        if sd * (price - p["sl"]) <= 0:
            return "exit-stop"
        # 3) momentum-ride trailing exit
        if not dec["momentum_ok"]:
            return "exit-momentum"
        return None

    def _bank(self, dec, units, tag):
        """Close `units` at current price, update risk manager + notify (side-correct)."""
        sd = self.pos["side"]
        pnl = sd * (dec["price"] - self.pos["entry"]) * units - self.sp["cost"] * units
        self.rm.on_close(pnl, self.pos.get("risk_frac", self.risk_per_trade) * units / self.pos["units0"])
        self._broker_close(units, sd)
        return pnl

    def _refresh_equity(self):
        """DYNAMIC compounding/withdrawal-aware sizing: re-read live account equity each
        cycle so lot sizes auto-grow as profits compound and auto-shrink on withdrawal or
        drawdown. Fully dynamic — no hardcoded balance anywhere."""
        if self.mode == "dry-run" or self.mt5 is None:
            return
        acc = self.mt5.account_info()
        if not acc:
            return
        bal = float(acc.balance)
        if self.pos is None:                       # only re-baseline when flat (avoid mid-trade jumps)
            prev = self.rm.equity
            self.rm.equity = bal
            self.rm.peak = max(self.rm.peak, bal)
            if abs(bal - prev) / max(prev, 1e-9) > 0.02:
                self._notify(f"balance changed {prev:.2f} -> {bal:.2f} {acc.currency} "
                             f"(deposit/withdrawal/PnL) — lot sizing rebased")

    def _trading_license(self):
        """The weekly self-learning loop (execution/auto_update.py) writes health.json with
        the latest per-year walk-forward gate result. This is the bot's TRADING LICENSE:
        open NEW trades only while the edge still PERSISTS on fresh data and the check is
        recent. If the gate fails or the check is stale, STAND DOWN to manage-only — never
        keep firing a dead edge. Returns (allowed, reason). Absent file -> allowed (fail-open
        on first deploy, before the first weekly run)."""
        try:
            h = json.loads(self.health_file.read_text()).get(f"{self.symbol}_{self.tf}")
        except Exception:
            return True, "no-license-file(first-run)"
        if not h:
            return True, "no-license-entry(first-run)"
        if not h.get("gate_passed", False):
            return False, (f"edge stopped persisting (pos-years {h.get('pct_pos')}, "
                           f"worst {h.get('worst_yr_pct')}%) — standing down")
        checked = h.get("checked")
        if checked:
            try:
                age = (pd.Timestamp.utcnow().tz_localize(None) - pd.Timestamp(checked)).days
                if age > self.license_stale_days:
                    return False, f"license stale ({age}d since last validation) — standing down"
            except Exception:
                pass
        return True, "ok"

    # ---------------- one cycle ----------------
    def run_once(self, write_signal=False):
        if not self._shared:
            self._refresh_equity()                 # compounding + withdrawal-aware (MultiBot does this once)
        df = self.get_bars()
        dec = self.decide(df)
        # manage existing position first
        if self.pos is not None:
            act = self.manage(df, dec)
            if act == "scale":
                cut = self.pos["units0"] * EXIT["partial_frac"]
                pnl = self._bank(dec, cut, "scale")
                self.pos["units"] -= cut
                msg = (f"SCALE-OUT {self.symbol} {self.tf} @ {dec['price']} banked {EXIT['partial_frac']:.0%}"
                       f" (+{pnl:.2f}), SL->breakeven, riding the rest")
                print(f"  [{dec['time']}] {msg}"); self._notify(msg)
            elif act and act.startswith("exit"):
                pnl = self._bank(dec, self.pos["units"], act)
                msg = f"CLOSE {self.symbol} {self.tf} @ {dec['price']} ({act}) pnl={pnl:.2f} eq={self.rm.equity:.2f}"
                print(f"  [{dec['time']}] {msg}  {self.rm.status()}")
                self._notify(msg); self.pos = None
        # new entry (LONG or SHORT, confidence-scaled size) — gated by the weekly license
        if self.pos is None and dec["entry_signal"]:
            licensed, lic_why = self._trading_license()
            if not licensed:
                print(f"  [{dec['time']}] entry blocked: {lic_why}")
                if write_signal:
                    (ROOT / f"data/raw/signal_{self.symbol}_{self.edge}.json").write_text(
                        json.dumps({**dec, "position": self.pos, "license": lic_why}, default=str))
                return dec
            rf = self._risk_frac(dec.get("conf", 1.0))          # actual conf-scaled risk fraction
            allowed, why = self.rm.can_open(dec["time"], rf)
            if allowed:
                units = self.size(dec["price"], dec["stop_loss"], dec.get("conf", 1.0))
                self.pos = {"entry": dec["price"], "sl": dec["stop_loss"], "side": dec["side"],
                            "hwm": 0.0, "risk": abs(dec["price"] - dec["stop_loss"]),
                            "units": units, "units0": units, "scaled": False, "risk_frac": rf}
                self.rm.on_open(rf)
                self._broker_order(dec, units, dec["side"])
                direction = "BUY" if dec["side"] == 1 else "SELL"
                msg = (f"{direction} {self.tag} {self.tf} @ {dec['price']} SL={dec['stop_loss']} "
                       f"units={units} conf={dec.get('conf',1.0)}x")
                print(f"  [{dec['time']}] {msg}")
                self._notify(msg)
            elif why != "ok":
                print(f"  [{dec['time']}] entry blocked ({self.tag}): {why}")
                if "KILL" in why:
                    self._notify(f"KILL-SWITCH {self.tag}: {why}")
        if write_signal:
            (ROOT / f"data/raw/signal_{self.symbol}_{self.edge}.json").write_text(json.dumps({**dec, "position": self.pos}, default=str))
        return dec

    def _notify(self, msg):
        if self.mode == "dry-run":
            return                       # no alerts during offline replay
        try:
            from execution.notifier import notify
            notify(msg, subject=f"NexaBot {self.mode}")
        except Exception:
            pass

    def _risk_frac(self, conf):
        """Option B risk fraction: base% x confidence, CAPPED at the top configured risk tier.
        Used for BOTH the lot size and the portfolio-risk accounting, so the account-wide 6%
        cap is honest and the live lot matches the validated backtest sizing exactly."""
        tiers = cfg().get("sizing", {}).get("risk_tiers", [[99.0, 0.02]])
        cap = float(max(t[1] for t in tiers))
        return float(min(self.risk_per_trade * float(conf), cap))

    def _calc_lots(self, dec):
        """Broker-accurate lot size from risk: lots = risk_$ / (loss-per-lot at the SL),
        rounded to the symbol's volume step, clamped to [min, max]. Returns (lots, feasible).
        Protects a tiny ($10) account: if even the MINIMUM lot risks more than the budget,
        feasible=False and we SKIP the trade rather than over-risk."""
        info = self.mt5.symbol_info(self.symbol)
        if info is None:
            return 0.0, False
        stop_pts = abs(dec["price"] - dec["stop_loss"]) / info.point
        loss_per_lot = stop_pts * info.trade_tick_value * (info.point / info.trade_tick_size)
        if loss_per_lot <= 0:
            return 0.0, False
        risk_amt = self.rm.equity * self._risk_frac(dec.get("conf", 1.0))
        lots = risk_amt / loss_per_lot
        step = info.volume_step or 0.01
        lots = max(info.volume_min, round(lots / step) * step)
        lots = min(lots, info.volume_max)
        feasible = (info.volume_min * loss_per_lot) <= risk_amt * 1.5   # min lot within ~budget
        return round(lots, 2), feasible

    def _filling_mode(self, info):
        """Pick a fill mode the broker actually supports (varies by broker/account)."""
        fm = getattr(info, "filling_mode", 0)
        if fm & 1:   return self.mt5.ORDER_FILLING_FOK
        if fm & 2:   return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _broker_order(self, dec, units, side):
        if self.mode == "dry-run" or self.mt5 is None:
            return
        info = self.mt5.symbol_info(self.symbol)
        self.mt5.symbol_select(self.symbol, True)
        lots, feasible = self._calc_lots(dec)
        if not feasible:
            msg = (f"SKIP {self.symbol}: min lot risks more than {self.risk_per_trade:.1%} of "
                   f"{self.rm.equity:.2f} {getattr(self.mt5.account_info(),'currency','')} — too small for this symbol.")
            print("  " + msg); self._notify(msg); self.pos = None
            return
        tick = self.mt5.symbol_info_tick(self.symbol)
        price = tick.ask if side == 1 else tick.bid               # live bid/ask, not bar close
        # respect the broker's MINIMUM stop distance (rejected otherwise; varies by broker)
        min_dist = (info.trade_stops_level or 0) * info.point
        sl = dec["stop_loss"]
        if min_dist and abs(price - sl) < min_dist:
            sl = price - side * min_dist
        self.pos["sl"] = round(sl, info.digits)
        otype = self.mt5.ORDER_TYPE_BUY if side == 1 else self.mt5.ORDER_TYPE_SELL
        req = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": lots,
               "type": otype, "price": price, "sl": self.pos["sl"], "deviation": 20,
               "magic": self.magic, "comment": f"nexa-{self.edge}",   # tag this sleeve's orders
               "type_filling": self._filling_mode(info)}
        r = self.mt5.order_send(req)
        if r is None or r.retcode != self.mt5.TRADE_RETCODE_DONE:
            msg = f"ORDER FAILED {self.tag}: {getattr(r,'retcode','?')} {getattr(r,'comment','')}"
            print("  " + msg); self._notify(msg); self.pos = None

    def _broker_close(self, units, side=1):
        if self.mode == "dry-run" or self.mt5 is None:
            return
        info = self.mt5.symbol_info(self.symbol)
        close_type = self.mt5.ORDER_TYPE_SELL if side == 1 else self.mt5.ORDER_TYPE_BUY
        tick = self.mt5.symbol_info_tick(self.symbol)
        price = tick.bid if side == 1 else tick.ask
        req = {"action": self.mt5.TRADE_ACTION_DEAL, "symbol": self.symbol,
               "volume": max(info.volume_min, round(units, 2)), "type": close_type, "price": price,
               "deviation": 20, "magic": self.magic, "comment": f"nexa-{self.edge}-close",
               "type_filling": self._filling_mode(info)}
        self.mt5.order_send(req)

    # ---------------- offline replay (dry-run proof) ----------------
    def replay(self, last=300):
        df = self.get_bars()
        print(f"=== DRY-RUN replay: {self.symbol} {self.tf}, last {last} bars ===")
        sub = df.iloc[-(last + 400):]
        for k in range(400, len(sub)):
            window = sub.iloc[:k + 1]
            dec = self.decide(window)
            if self.pos is not None:
                act = self.manage(window, dec)
                if act == "scale":
                    cut = self.pos["units0"] * EXIT["partial_frac"]
                    self._bank(dec, cut, "scale"); self.pos["units"] -= cut
                    print(f"  {dec['time']}  SCALE-OUT @ {dec['price']:.2f} (bank {EXIT['partial_frac']:.0%}, SL->BE, ride rest)")
                elif act and act.startswith("exit"):
                    pnl = self._bank(dec, self.pos["units"], act)
                    print(f"  {dec['time']}  CLOSE @ {dec['price']:.2f} ({act}) pnl={pnl:.1f} eq={self.rm.equity:.0f}")
                    self.pos = None
            if self.pos is None and dec["entry_signal"]:
                ok, why = self.rm.can_open(dec["time"], self.risk_per_trade)
                if ok:
                    u = self.size(dec["price"], dec["stop_loss"], dec.get("conf", 1.0))
                    self.pos = {"entry": dec["price"], "sl": dec["stop_loss"], "side": dec["side"],
                                "hwm": 0.0, "risk": abs(dec["price"] - dec["stop_loss"]),
                                "units": u, "units0": u, "scaled": False}
                    self.rm.on_open(self.risk_per_trade)
                    d = "BUY " if dec["side"] == 1 else "SELL"
                    print(f"  {dec['time']}  {d} @ {dec['price']:.2f} SL={dec['stop_loss']:.2f} conf={dec.get('conf',1.0)}x")
        print(f"  final equity: {self.rm.equity:.0f}  status: {self.rm.status()}")

    # ---------------- pre-flight check (connects, prints, places NO order) ----------------
    def check(self):
        df = self.get_bars()
        dec = self.decide(df)
        acc = self.mt5.account_info() if self.mt5 else None
        info = self.mt5.symbol_info(self.symbol) if self.mt5 else None
        print(f"\n=== PRE-FLIGHT — {self.symbol} {self.tf} ({self.mode}) ===")
        if acc:
            print(f"  account   : balance={acc.balance} {acc.currency}  leverage=1:{acc.leverage}")
        if info:
            print(f"  symbol    : lot min/step/max={info.volume_min}/{info.volume_step}/{info.volume_max}"
                  f"  min-stop={info.trade_stops_level}pts")
        print(f"  signal    : {'LONG' if dec['side']==1 else 'SHORT' if dec['side']==-1 else 'none'}"
              f"  price={dec['price']}  SL={dec['stop_loss']}  conf={dec.get('conf',1.0)}x")
        if dec["side"] and self.mt5:
            lots, feasible = self._calc_lots(dec)
            rf = self._risk_frac(dec.get("conf", 1.0))
            risk = self.rm.equity * rf
            print(f"  WOULD trade: {lots} lots  (risk ~{risk:.2f} {getattr(acc,'currency','')}, "
                  f"{rf*100:.2f}% of balance @ conf {dec.get('conf',1.0)}x)  feasible={feasible}")
            if not feasible:
                print("  -> account too small for this symbol; use a cent account or a cheaper symbol.")
        else:
            print("  no entry signal on the latest bar (bot would wait).")
        print("  (no order placed — pre-flight only)")


class MultiBot:
    """ONE MT5 terminal/connection driving MANY symbols — the resource-correct design
    (a single Wine+MT5 process for the whole account, not one per pair). All symbols share
    ONE account-wide RiskManager, so the portfolio risk cap, daily-loss and drawdown kill
    switch span every symbol together. Each symbol keeps its own position + strategy gates."""

    def __init__(self, symbols, tf, mode="paper"):
        self.symbols = symbols; self.tf = tf; self.mode = mode
        self.mt5 = None; self.rm = None; self.bots = []
        sysc = cfg().get("system", {})
        self.risk_per_trade = sysc.get("risk_per_trade", 0.005)
        self.max_dd = sysc.get("max_drawdown_limit", 0.20)
        self.edges = list(sysc.get("live_edges", ["trend"]))   # sleeves per symbol (config-driven)

    def _make_bots(self, rm=None, mt5h=None):
        """One NexaBot per (symbol x edge) sleeve — the live multi-edge portfolio."""
        return [NexaBot(s, self.tf, mode=self.mode, rm=rm, mt5_handle=mt5h, edge=e)
                for s in self.symbols for e in self.edges]

    def connect(self):
        if self.mode == "dry-run":
            self.bots = self._make_bots()
            return True
        import os
        import MetaTrader5 as mt5
        self.mt5 = mt5
        sysc = cfg()["system"]["mt5"]
        kw = dict(login=int(os.environ.get("MT5_LOGIN", sysc.get("login") or 0)),
                  password=os.environ.get("MT5_PASSWORD"),
                  server=os.environ.get("MT5_SERVER", sysc.get("server")))
        path = os.environ.get("MT5_PATH")
        if path:
            kw["path"] = path
        if not mt5.initialize(**kw):
            sys.exit(f"MT5 connect failed: {mt5.last_error()}")
        acc = mt5.account_info()
        bal = float(acc.balance) if acc else 10000.0
        self.rm = RiskManager(bal, risk_per_trade=self.risk_per_trade, max_drawdown=self.max_dd)
        # SAFETY: multiple edges on ONE symbol need a HEDGING account (independent positions).
        # On a NETTING account they'd share a single position/SL and fight — so detect the
        # margin mode and, if netting, fall back to ONE edge per symbol (no same-symbol stacking).
        hedging = bool(acc and getattr(acc, "margin_mode", None) == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
        if not hedging and len(self.edges) > 1:
            print(f"  ! NETTING account — multiple edges per symbol would share one position. "
                  f"Falling back to one edge per symbol ('{self.edges[0]}') for safe execution.")
            self.edges = [self.edges[0]]
        if acc:
            print(f"  connected: balance={acc.balance} {acc.currency} server={kw['server']}  "
                  f"symbols={','.join(self.symbols)} edges={','.join(self.edges)} "
                  f"({len(self.symbols)*len(self.edges)} sleeves, {'HEDGING' if hedging else 'NETTING'}, ONE terminal)")
        # every sleeve shares the SAME mt5 handle + account-wide RiskManager
        self.bots = self._make_bots(rm=self.rm, mt5h=mt5)
        return True

    def _refresh_equity(self):
        """Account-wide compounding/withdrawal-aware refresh — done ONCE per cycle (balance is
        shared across symbols; it excludes floating PnL so it's stable during open trades)."""
        if self.mode == "dry-run" or self.mt5 is None:
            return
        acc = self.mt5.account_info()
        if not acc:
            return
        bal = float(acc.balance); prev = self.rm.equity
        self.rm.equity = bal; self.rm.peak = max(self.rm.peak, bal)
        if prev and abs(bal - prev) / max(prev, 1e-9) > 0.02:
            self.bots[0]._notify(f"account balance {prev:.2f} -> {bal:.2f} {acc.currency} "
                                 f"(deposit/withdrawal/PnL) — lot sizing rebased account-wide")

    def run_once(self, write_signal=True):
        self._refresh_equity()                     # once for the whole account
        for bot in self.bots:
            try:
                bot.run_once(write_signal=write_signal)
            except Exception as e:
                print(f"  [{bot.symbol}] cycle error: {e}")

    def check(self):
        for bot in self.bots:
            bot.check()

    def replay(self):
        for bot in self.bots:
            try:
                bot.replay()
            except FileNotFoundError:
                print(f"  [{bot.symbol}] dry-run needs a local data/raw/{bot.symbol}_{bot.tf}.parquet; "
                      f"the cent ('c') symbols only have LIVE data — use --mode paper on the VM, "
                      f"or dry-run an 'm' research symbol (e.g. --symbols BTCUSDm,XAUUSDm).")


def resolve_universe(args):
    """Decide which symbols + TF to trade, CONFIG-FIRST (no hardcoding):
      --symbols X,Y  -> exactly those (CLI override)
      --symbol X     -> single symbol (back-compat / dry-run probes)
      neither given  -> system.live_symbols + system.live_tf from config (the live default).
    Returns (symbols_list, tf)."""
    sysc = cfg().get("system", {})
    tf = args.tf or sysc.get("live_tf", "H4")
    if args.symbols:
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    elif args.symbol:
        syms = [args.symbol]
    else:
        syms = list(sysc.get("live_symbols", ["BTCUSDc", "XAUUSDc"]))
    return syms, tf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="single symbol (override config)")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated override, e.g. BTCUSDc,XAUUSDc — ONE terminal drives them all")
    ap.add_argument("--tf", default=None, help="timeframe (default: system.live_tf from config)")
    ap.add_argument("--mode", choices=["dry-run", "paper", "live"], default="dry-run")
    ap.add_argument("--live", action="store_true", help="confirm REAL-money trading")
    ap.add_argument("--poll", type=int, default=0, help="seconds between cycles (0 = one shot)")
    ap.add_argument("--check", action="store_true", help="pre-flight: print balance + lot it would trade, NO order")
    args = ap.parse_args()
    if args.mode == "live" and not args.live:
        sys.exit("Refusing live mode without explicit --live (and a validated, paper-passed config).")

    syms, tf = resolve_universe(args)
    # one terminal drives many symbols; a single symbol uses the lighter NexaBot path
    bot = MultiBot(syms, tf, mode=args.mode) if len(syms) > 1 else NexaBot(syms[0], tf, mode=args.mode)
    bot.connect()

    if args.check:
        bot.check()
    elif args.mode == "dry-run":
        bot.replay()
    elif args.poll > 0:
        print(f"NexaBot {','.join(syms)} {tf} [{args.mode}] — polling every {args.poll}s")
        while True:
            bot.run_once(write_signal=True)
            time.sleep(args.poll)
    else:
        bot.run_once(write_signal=True)


if __name__ == "__main__":
    main()
