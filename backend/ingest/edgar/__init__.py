"""SEC EDGAR ingest · insider Form 4 filings + company submission index.

Sprint F · ships 2026-08-05. Uses EDGAR's public JSON API at
https://www.sec.gov/cgi-bin/browse-edgar (rate-limited to 10 req/sec ·
must send User-Agent per SEC policy).

Feed: reports/edgar/insider_recent.json with per-ticker insider net
buying/selling in trailing 30d. High-signal · directly consumed by future
CIL insider_adapter (Phase 2B).
"""
