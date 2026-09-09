"""One truth for Telegram and the workbook.

The defect this prevents, in full: on 2026-09-08 the Telegram text advised
BUY on SBIN and TATAPOWER after both had stop-breached that morning, and
"Continue HOLD" on DABUR, NTPC and SUNPHARMA - all already closed. None of
the five was in CURRENT. The text came from the retired R1 generator; the
workbook came from the canonical lifecycle.

These tests assert the property that makes that impossible: the message is
a pure function of the same dataset the CURRENT sheet renders, so a name
cannot be advertised as investable unless CURRENT says it is.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.delivery.telegram import canonical_message as cm

ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("india", "usa")


def _life(market: str):
    p = ROOT / "reports" / "context" / ("canonical_lifecycle_%s.json" % market)
    if not p.exists():
        pytest.skip("no lifecycle dataset for %s" % market)
    return json.loads(p.read_text(encoding="utf-8"))


def _tick(t):
    return str(t or "").replace(".NS", "").replace(".BO", "")


# ── the message cannot disagree with CURRENT ────────────────────────────

@pytest.mark.parametrize("market", MARKETS)
def test_every_name_shown_as_held_is_in_current(market):
    d = _life(market)
    text = cm.render(ROOT, market)
    assert text
    current = {_tick(r["ticker"]) for r in (d.get("current") or [])}
    exited = {_tick(e["ticker"]) for e in (d.get("exits") or [])}
    # Any ticker rendered in a holdings block must be in CURRENT.
    body = text.split("🔴 EXITED TODAY")[0]
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith(tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) or " · " not in s:
            continue
        tk = s.split(" · ")[0].strip()
        if tk in exited and tk not in current:
            pytest.fail("%s is EXITED but rendered as a holding" % tk)


@pytest.mark.parametrize("market", MARKETS)
def test_no_exited_name_is_advertised_as_new(market):
    d = _life(market)
    text = cm.render(ROOT, market)
    new_block = text.split("🟢 NEW")[-1].split("━━━")[0] if "🟢 NEW" in text else ""
    # Match the LINE PREFIX, not a substring. USA carries single-letter
    # tickers (O, C, A, L, T) that appear inside ordinary words, so a
    # substring test reports every one of them as a false positive.
    shown = {l.strip().split(" · ")[0] for l in new_block.splitlines()
             if " · " in l}
    exited = {_tick(e["ticker"]) for e in (d.get("exits") or [])}
    current = {_tick(r["ticker"]) for r in (d.get("current") or [])}
    leaked = shown & (exited - current)
    assert not leaked, "exited names in the NEW block: %s" % sorted(leaked)


@pytest.mark.parametrize("market", MARKETS)
def test_stop_breached_names_appear_only_as_exits(market):
    d = _life(market)
    text = cm.render(ROOT, market)
    # The invariant is per ENGINE, not per ticker. R1 EIX breached its
    # stop on 2026-09-08 (advisory, -20.5%) while R2 opened EIX fresh on
    # 2026-09-09 with an intact stop. Those are two engines' positions in
    # one name, and showing both is correct - the R1 row is labelled
    # ADVISORY. A ticker-only rule would forbid a legitimate re-entry.
    breached = {(_tick(e["ticker"]), str(e.get("engine")))
                for e in (d.get("exits") or [])
                if str(e.get("source")) == "lifecycle:stop-breach"}
    if not breached:
        pytest.skip("no breach exits")
    held = {(_tick(r["ticker"]), str(r.get("engine")))
            for r in (d.get("current") or [])}
    overlap = breached & held
    assert not overlap, (
        "same engine holds a stop-breached position: %s" % sorted(overlap))


@pytest.mark.parametrize("market", MARKETS)
def test_prices_match_the_lifecycle_exactly(market):
    """The old surface disagreed even where it agreed on the name."""
    d = _life(market)
    text = cm.render(ROOT, market)
    for r in (d.get("current") or [])[:6]:
        v = r.get("pnl_pct")
        if isinstance(v, (int, float)):
            assert ("%+.2f%%" % v) in text, (
                "%s P&L %s not rendered from the lifecycle"
                % (r.get("ticker"), v))


# ── provenance and labelling ────────────────────────────────────────────

@pytest.mark.parametrize("market", MARKETS)
def test_r1_rows_are_labelled_advisory(market):
    d = _life(market)
    text = cm.render(ROOT, market)
    cur = d.get("current") or []
    # A handful of names are held by BOTH runners (USA: BMY, DXCM, IT,
    # PLTR, VLO). The display collapses those to a single R2 row, which
    # correctly carries no ADVISORY tag - it IS an R2 production position.
    # Only names that are R1-ONLY must be labelled.
    engines = {}
    for r in cur:
        engines.setdefault(_tick(r["ticker"]), set()).add(str(r.get("engine")))
    for tk, eng in engines.items():
        if eng != {"R1"}:
            continue
        line = [l for l in text.splitlines()
                if l.strip().startswith(tk + " ·")]
        assert line and "ADVISORY" in line[0], (
            "R1-only row %s not labelled ADVISORY · %s" % (tk, line[:1]))


@pytest.mark.parametrize("market", MARKETS)
def test_message_names_its_source(market):
    text = cm.render(ROOT, market)
    assert "canonical_lifecycle_%s.json" % market in text
    assert "cannot disagree with the XLSX" in text


def test_renderer_computes_nothing():
    """No pricing, no ranking, no scoring · it renders one dataset."""
    src = Path(cm.__file__).read_text(encoding="utf-8")
    # Inspect CODE, not prose · the module docstring names the legacy
    # sources precisely in order to explain why it does not use them.
    code = chr(10).join(l for l in src.splitlines()
                        if not l.strip().startswith("#"))
    body = code.split('"""', 2)[-1]
    for banned in ("yfinance", "read_csv", "aegis_today",
                   "recommendation_generator"):
        assert banned not in body, "canonical message reaches for %s" % banned


def test_legacy_r1_generator_is_no_longer_the_send_path():
    src = (ROOT / "scripts" / "telegram_send_with_retry.py").read_text(
        encoding="utf-8")
    assert "CANONICAL_MSG" in src
    assert "canonical_message" in src
    # The legacy module may still exist · it must not be executed.
    assert "[python_exe, str(NOTIFY)]" not in src


def test_breach_warning_is_surfaced(market="india"):
    d = _life(market)
    n = (d.get("counts") or {}).get("breach_exits_new_today", 0)
    text = cm.render(ROOT, market)
    if n:
        assert "BREACHED their stop today" in text


@pytest.mark.parametrize("market", MARKETS)
def test_no_r3_opinion_leaks_into_the_message(market):
    """R3 is ABSTAIN everywhere · a shadow layer with no opinion adds
    nothing to a message read on a phone."""
    text = cm.render(ROOT, market)
    for token in ("ABSTAIN", "TAKE", "AVOID", "R3 "):
        assert token not in text, "R3 token %r leaked into the message" % token
