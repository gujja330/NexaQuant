# UX030 · Telegram Message Examples

Generated from live AEGIS outputs at run time (`reports/`).

> These are the actual messages the delivery layer would produce today.

---

## 1 · Morning Brief

```
🌅 *Morning Brief*   _2026-07-17 · 18:11 IST_
📊 Regime: 🟡 Neutral
🟢 Buys today: 51   🔴 Exits: 0
```

## 2 · Daily Executive Summary

```
🏢 *NEXAQUANT · AEGIS · Daily*
_2026-07-17 · 18:11 IST_

🟢 *BUY:*  51    🟡 *HOLD:* 0    🔴 *EXIT:* 0

📊 *Market Regime:* 🟡 Neutral
🏆 *Champion:* `top_5_ew`   Sharpe 0.97

💼 *Portfolio*
  positions: 20   cash: 0.0%
  top-5 concentration: 45.8%

🥇 *Top Opportunity*
  `IPCALAB`   ★★★★★   conf 100%

🤖 *AI Summary*
  _Neutral market regime. Deploying capital into fresh opportunities. Cash near minimum; sizing discipline is tight._

👇 Reply /help for commands
```

## 3 · Portfolio Health

```
💼 *Portfolio Health*
_2026-07-17 · 18:11 IST_

📊 *Overall Grade:*   🟡 B
📈 *Health:* ██████░░░░  65/100

🎯 *Positions:*        20
💵 *Cash:*             0.0%
🧩 *Top-5 share:*      45.8%
🌐 *Diversification:* 🟡 B
⚠ *Risk level:*      🟡 Medium

🏆 *Champion:*  `top_5_ew`
   Sharpe 0.97   Max DD -25.24%
📊 *Regime:*   🟡 Neutral
```

## 4 · Champion Update

```
🏆 *CHAMPION STRATEGY UPDATE*

*Current Champion:*  `top_5_ew`
  composite: 95.96
  Sharpe: 0.97   CAGR: 24.8%
  Max DD: -25.24%

*Decision:* initial_champion
_no prior champion recorded; adopting top-ranked strategy_
```

## 5 · New Buys Summary

```
🟢 *NEW BUYS (5)*

  • `IPCALAB`   ★★★★★   conf 100%
  • `KALYANKJIL`   ★★★★★   conf 100%
  • `LODHA`   ★★★★★   conf 100%
  • `GLAND`   ★★★★★   conf 100%
  • `SONACOMS`   ★★★★★   conf 100%
```

## 6 · Weekly Review

```
📅 *Weekly Review*
_2026-07-17 · 18:11 IST_

📊 *Regime:*  🟡 Neutral

🏆 *Leaderboard*
  *1. `top_5_ew          `   score 95.96   Sharpe 0.97
   2. `top_20_ew         `   score 87.25   Sharpe 1.06
   3. `top_20_sw         `   score 86.20   Sharpe 1.06
   4. `top_10_sw         `   score 69.86   Sharpe 0.78
   5. `ew_universe       `   score 69.14   Sharpe 0.80
```

---

## Command Examples

### /help

```
*AEGIS COMMANDS*

/summary            — daily executive summary
/portfolio          — full portfolio breakdown
/buy                — new buy signals
/exits              — exit signals
/health             — portfolio health report
/risk               — risk dashboard
/champion           — current champion strategy
/challengers        — challenger scoreboard
/regime             — market regime snapshot
/performance        — weekly review
/confidence         — confidence calibration status
/why <ticker>       — reasons for the current recommendation
/doctor <ticker>    — strategy doctor diagnosis
/history <ticker>   — historical rec + calibration for ticker
/compare <a> <b>    — head-to-head between two tickers
/sector <name>      — sector snapshot
/help               — this menu
```

### /portfolio

```
💼 *Portfolio*
  type: `Balanced (Top 20 diversified)`   allocator: `hrp`
  positions: 20   cash: 0.0%
  top-5 share: 45.8%

*HOLDINGS (0)*
```

### /risk

```
⚠ *Risk Dashboard*
_2026-07-17 · 18:11 IST_

📊 Regime:            🟡 Neutral
💵 Cash cushion:      0.0%
🧩 Top-5 concentration: 45.8%
🎯 Positions:         20
```

### /champion

```
🏆 *CHAMPION STRATEGY UPDATE*

*Current Champion:*  `top_5_ew`
  composite: 95.96
  Sharpe: 0.97   CAGR: 24.8%
  Max DD: -25.24%

*Decision:* initial_champion
_no prior champion recorded; adopting top-ranked strategy_
```

### /regime

```
📊 *Market Regime*

Current:  🟡 Neutral

*Historical Windows*
  🟢 Risk-On   643 days
  🟡 Neutral   331 days
  🔴 Risk-Off   128 days

*Regime Champions*
  🟢 Risk-On            `top_5_ew`   CAGR 44.8%
  🔴 Risk-Off           `top_20_ew`   CAGR 3.4%
  🟡 Neutral            `top_5_ew`   CAGR 112.5%
```

### /confidence

```
📐 *Confidence Calibration*

  method:       `platt_scaling`
  raw ECE:      0.2868
  calibrated:   0.0021

_Retrain only when new data available; drift-based_
```
