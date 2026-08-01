# AEGIS Telegram Format v3.1 · Locked Standard

**Signed into force**: 2026-07-31 (locked per operator directive)
**Scope**: Every daily Telegram message · India + USA · Command Center + Research + Intraday (when it ships)
**Governance**: Any change to this format requires operator sign-off · this doc is the reference

---

## Golden Rule

> **Runner 1 and Runner 2 must feel like two Formula 1 cars on the same timing screen. Users must be able to compare them line-by-line without mentally translating different layouts.**

Only the strategy logic differs. Presentation, terminology, ordering, and metrics are IDENTICAL across both runners.

---

## 1 · Runner Naming (PERMANENT · never rename)

| Identity | Emoji | Tagline |
|---|---|---|
| **Runner 1** | 🛡 | Baseline / Validation Strategy |
| **Runner 2** | 🚀 | Adaptive Strategy |

Do NOT replace these names with role-descriptors ("Validation Engine", "Legacy Engine", "Candidate Engine", "Experimental Engine"). Roles change; **names never**.

**Rationale**: after 60/90-day evaluation, Runner 2 may become canonical (or Runner 1 may keep the crown). Renaming based on status would confuse users and break historical reports. Status changes · identity does not.

---

## 2 · Terminology Lock (use these exact words · nothing else)

| Field | Exact label |
|---|---|
| Ranking | `Rank #N` |
| Confidence | `Conf X% Cal` OR `Conf X% Raw` (never `Conf X%` alone) |
| Current price | `Now Rs1,974` / `Now $369` |
| Entry price | `Entry Rs1,930` / `Entry $365` |
| Max positive excursion | `Max Gain +X.XX%` |
| Max negative excursion | `Max DD -X.XX%` |
| Entry range | `Buy Zone Rs1,955–Rs1,995` |
| Stop-loss | `Stop Rs1,845` |
| First target | `T1 Rs2,180` |
| Second target | `T2 Rs2,350` |
| Holding period | `Day X / Y · N Days Left` (never `2 months` alone) |
| Score | `Model Score 77` (separate line · never mixed with `77/100`) |

**Rule**: if you see any label deviate from this list, it's a bug.

---

## 3 · Section Structure (fixed order · both markets)

Every section starts with a separator line: `━━━━━━━━━━━━━━━━━━━━━━`

```
1.  Header               🏢 AEGIS DAILY · market flag + date
2.  CEO Action           🎯 CEO ACTION TODAY  (whitespace-heavy)
3.  Runner Experiment    🧪 RUNNER EXPERIMENT (canonical + Day X / min 60 / target 90)
4.  Runner Comparison    🥊 RUNNER COMPARISON (Leader + Delta · not TIE+Edge)
5.  Rotation Signals     🔄 N EXITS · 1 REPLACEMENT
6.  New Buy Ideas · R2   🚀 R2 · NEW BUY IDEAS (rich cards)
7.  Exits                🔴 EXITS IF YOU HOLD (always renders · "0 today" line)
8.  Runner 1 Active      🛡 R1 · ACTIVE PICKS (same layout as R2)
9.  What Changed         🔄 WHAT CHANGED SINCE YESTERDAY (compact one-line-per-change)
10. Portfolio Pulse      💼 PORTFOLIO PULSE (top opp + top risk)
11. Footer               timestamp + advisory disclaimer
```

Removed (nice-to-have · never critical): AI Performance Scorecard · Since Inception Performance · Attribution top drivers · Research Platform tail.

---

## 4 · Runner Card · IDENTICAL layout for both runners

Every recommendation MUST contain the same fields in the same order:

```
{emoji} {TICKER} ({Company Name})

    Rank #{N}

    Conf {X}% Cal            ← always with Cal or Raw suffix

    Now {currency}{price}

    Day {X} / {Y}            ← lifecycle position

    {Y-X} Days Left          ← remaining horizon

    {ACTION}                 ← STRONG BUY · BUY · HOLD · EXIT

    Size {X}%                ← portfolio allocation

    📥 Buy Zone
    {currency}{low}–{currency}{high}

    🛡 Stop
    {currency}{stop}

    🎯 T1
    {currency}{t1}

    🎯🎯 T2
    {currency}{t2}

    📈 Since Recommendation
    Entry {currency}{entry}
    Now   {currency}{now}
    {return_pct}%

    🔺 Max Gain
    {+X.XX}%

    🔻 Max DD
    {-X.XX}%

    Reason
    Momentum · Trend · Quality · Relative Strength
```

**Non-negotiable**: if Runner 2 has a field, Runner 1 shows the same field (or explicit "n/a" placeholder — never blank / missing).

---

## 5 · Reason Vocabulary (fixed · these 4 categories only)

Reasons ONLY come from this list:
- `Momentum`
- `Trend`
- `Quality`
- `Relative Strength`

Do NOT use marketing prose like "Low-risk Pharma holding", "above 200 DMA", "sector leader". Those are style · not signal.

---

## 6 · Comparison Section (fix TIE+Edge contradiction)

**Wrong**:
```
Leader: TIE   ·   Edge +0.79%
```
(A tie can't have an edge.)

**Correct**:
```
🥊 RUNNER COMPARISON

Day 1 / Minimum 60 / Target 90

Leader
UNDECIDED

Performance Delta (Runner 2 vs Runner 1)
+0.79pp

Canonical
UNDECIDED
```

When leader is `UNDECIDED` (day < 60), delta line still shows the raw number for information but no "leader" claim is made.

When leader is a real runner (day ≥ 60 AND edge > threshold), format becomes:
```
Leader
RUNNER_2

Edge over Runner 1
+2.10pp
```

---

## 7 · Rotation Section (rewording)

**Wrong**:
```
5 rotations · 1 destinations
```

**Correct**:
```
🔄 5 EXITS · 1 REPLACEMENT

Sell weaker positions · buy stronger ones (expected alpha gain)

Cap: 6% per ticker (Portfolio Engine)

🟢 TCS (TCS) — best +58.1% α
    Sources: BIOCON (+58.1%), FORTIS (+55.7%), ...
    ⚠️ 5 sources rotate to same target · cap consolidated at 6%
```

---

## 8 · Runner Experiment Block (once only · near top)

Dedicated section right after CEO Action:

```
━━━━━━━━━━━━━━━━━━━━━━
🧪 RUNNER EXPERIMENT
━━━━━━━━━━━━━━━━━━━━━━

Day                    {X} / 90
Minimum Decision       60 Days
Target Decision        90 Days
Canonical              UNDECIDED
━━━━━━━━━━━━━━━━━━━━━━
```

Appears ONCE per message. Never duplicated per-rotation or per-block.

---

## 9 · Design Rules

- Every section begins with `━━━━━━━━━━━━━━━━━━━━━━`
- Every recommendation uses identical spacing
- Maximum 3 information lines before action items in any card
- Whitespace is intentional · never crammed
- Avoid long wrapped sentences
- Optimize for phone reading (mobile Telegram is the primary surface)
- Numeric alignment via monospace only when it renders on ALL clients (backtick blocks are OK; complex tables are NOT)
- Emoji only where it adds meaning (never decorative fluff)

---

## 10 · Data Integrity Rules

Every value shown MUST be populated (not zero-as-default). If a value is genuinely zero:
- `Max Gain +0.00%` and `Max DD -0.00%` are acceptable ONLY on Day 1 when position was opened same day at entry price
- Any other zero must be replaced by `—` OR fetched fresh before send

Before every live send:
1. Dry-run the message
2. Check EVERY field has a real value
3. If any core field is `0.00%` on a non-Day-1 position → fix upstream, don't send
4. Only after operator explicit approval → send

Zero-tolerance for stale dates: `📅 Day N` must match today's `date.today() - experiment_start` calculation. If it says Day 1 on Day 2, canonical block is stale · regenerate before sending.

---

## 11 · When operator sees a violation

Any deviation from this document is a bug. Fix path:
1. Identify which rule violated
2. Fix code in `backend/delivery/telegram/command_center.py`
3. Dry-run
4. Get operator approval
5. Send

Never send a violating message just to "get something out". Empty section > wrong section.

---

## 12 · Known operator gotchas (learned the hard way)

- **Silent position vanishing** is unacceptable. If LUPIN was recommended yesterday and isn't today, the message MUST include an explicit exit event for LUPIN with reason. Never let a position vanish.
- **Rotation instability** ("11 stocks → TCS today, 11 stocks → LUPIN yesterday") is a bug in the portfolio state machine · this format doc DOES NOT paper over it · the underlying engine must fix (Ticket R006).
- **Mixed holding horizons** in the same runner (17d + 90d) is a bug · Runner 2 must have ONE horizon at a time · this format doc surfaces the contradiction · engine must resolve.
- **Runner 1 must show its full state**: BUY / HOLD / REDUCE / SELL · not just the actionable subset. Same for Runner 2.

---

## 13 · Reference implementation

Renderer: `backend/delivery/telegram/command_center.py`

Section functions (must all follow the layout above):
- `_header()`
- `_ceo_call()` → renamed from CEO CALL to CEO ACTION TODAY
- `_runner_experiment_block()` → NEW · dedicated
- `_runner_comparison_block()` → renamed from `_r1_vs_r2_headline`
- `_rotation_calls()`
- `_actionable_entries()` → prefix with 🚀 R2
- `_actionable_exits()`
- `_runner1_orphans()` → prefix with 🛡 R1 · identical card layout to R2
- `_daily_change_summary()`
- `_risk_pulse()`
- `_integrity_footer()`

Sender: `scripts/telegram_command_center_send.py` · single message per market · Article X: verify EVERY value populates before send.

---

**Locked 2026-07-31 · edit only with operator sign-off · violations = bugs**
