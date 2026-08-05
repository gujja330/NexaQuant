"""Global Economic Calendar Engine · Phase 2A prep (data-only ingest today).

Collects upcoming macro event dates (RBI · Fed · CPI · Payrolls · earnings)
into a queryable calendar. Ships as DATA ONLY today · no confidence
adjustment · that arrives in Phase 2A on 2026-09-09.

Why data-only now: calendar gates itself. We can't consume historical
"what events were upcoming N days ago" unless we've been logging them.
Starting today means Phase 2A has 30+ days of calendar data to use.
"""
