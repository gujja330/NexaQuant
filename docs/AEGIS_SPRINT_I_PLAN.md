# AEGIS · Sprint I · 6-State Action Vocabulary + Persistent Recommendation IDs

**Signed:** 2026-08-06 · execute after Runner 3 Day-30 gate
**Trigger:** Operator scoring 2026-08-06 · Recommendation Continuity 6.5/10 ·
"the biggest remaining leap isn't another factor model · it's making every
recommendation behave like a living investment"

---

## 1 · Three items to build

### I-1 · 6-State Action Vocabulary
Current: STRONG BUY · BUY · HOLD · EXIT (4 states)
Target:  STRONG BUY · BUY · HOLD · HOLD & ADD · HOLD & REDUCE ·
              HOLD & TRAIL STOP · TAKE PROFIT · EXIT (8 states)

Rules for the new HOLD sub-states:
- **HOLD & ADD**: current position profitable · rank rising · sector strong
- **HOLD & REDUCE**: current position at loss · rank falling · sector weak
- **HOLD & TRAIL STOP**: position up > 10% · lock partial gains
- **TAKE PROFIT**: position hit T1 or +15% · lock half · trail remainder

Determined by combining:
- Position store (entry_price · current_price · high_water · low_water)
- Health Score band + delta from prior day
- CIL adjusted confidence
- Rank Δ (rising/falling/stable)

### I-2 · Persistent Recommendation IDs
Format: `{MARKET}-{RUNNER}-{6DIGIT}` (e.g. `IND-R2-000143`)
Rules:
- New position opens → assign next sequential ID
- ID persists for lifetime of the position (never recycled)
- Rotation OUT closes old ID · rotation IN opens new ID
- ID surfaces in XLSX new column · `Rec ID`
- Timeline CLI can lookup by Rec ID or ticker

Storage: `reports/research/rec_id_registry.jsonl` (append-only)

### I-3 · Lifecycle Evolution stream
Every rec's story column shows day-by-day evolution:
```
Day 1  · IND-R2-000143 · TCS · NEW BUY · entry ₹2452
Day 2  · IND-R2-000143 · TCS · ACTIVE · +1.2%
Day 5  · IND-R2-000143 · TCS · HOLD · rank ↓ 1→3
Day 11 · IND-R2-000143 · TCS · HOLD & REDUCE · sector weakness
Day 18 · IND-R2-000143 · TCS · EXIT · rotation to LUPIN · Total Return +8.4%
```

Rendered via new XLSX column `Lifecycle Trail` (compact) + full narrative
via `ticker_timeline.py --rec-id IND-R2-000143`.

---

## 2 · Why deferred (not now)

Sprint I is a NEW STATE MODEL change · not just UI polish. Requires:
- Migration path for existing (idless) positions
- Portfolio ledger schema extension
- Runner 2 SSoT enrichment to emit the sub-states
- Full regression test

Landing this mid-Runner-3 shadow window would confound the 3-runner
comparison at Day-90 gate. Better: wait until after 2026-09-09 gate ·
then execute Sprint I in the same window as Sprint H-3 through H-6.

Estimated total effort: 3-4 days.

---

## 3 · Success criteria

- Every active position has a stable Rec ID that persists across days
- HOLD row can be one of 4 sub-flavors (ADD/REDUCE/TRAIL/plain)
- XLSX shows `Rec ID` column + `Lifecycle Trail` column
- Timeline CLI queryable by Rec ID
- Total Return field on EXIT rows shows realized P&L
- Zero R1 code touches (R1 stays SEALED)

---

## 4 · Operator's ideal output (goal state)

```
Recommendation ID: IND-R2-000143
Ticker: TCS
Sector: IT
────────────────────────────────
Lifecycle
  Day 1  · 2026-07-29 · NEW BUY · ₹2258
  Day 2  · 2026-07-30 · ACTIVE  · +0.5% · confidence 39% → 41%
  Day 5  · 2026-08-01 · HOLD    · rank 1 → 3
  Day 11 · 2026-08-04 · HOLD & REDUCE · sector IT weakness
  Day 18 · 2026-08-11 · EXIT    · rotation to LUPIN · +8.4% realized
────────────────────────────────
Total Return: +8.4%
Max Gain:     +9.2%
Max DD:       -1.1%
```

---

## 5 · Signed for execution 2026-09-15+

CEO (AI): 2026-08-06 · aligned with Runner 3 Day-30 gate outcome.
