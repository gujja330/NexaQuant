"""A ticker is not an episode. CEO 2026-11-06 · A23 accounting repair.

WHAT WENT WRONG
---------------
India run 41985177006 (2026-11-05, schedule) blocked delivery:

    A19 / A23   PASS / FAIL
    [A23] 3 Registry-CLOSED tickers silently lost (not in Exit History
    body AND not in orphan audit JSONL): BHARATFORG, HCLTECH, HEROMOTOCO
    FINAL: BLOCKED - No XLSX. No Telegram.

No code changed that day. The CALENDAR moved.

A23 holds the WHOLE registry history of accountable CLOSED episodes to
account, with no date cutoff. Its evidence is a 90-day rolling Exit
History plus the orphan audit. An unbounded population measured against
bounded evidence fails the day its oldest cohort ages out:

    asof 2026-11-04 -> window starts 2026-08-06 -> INSIDE  -> PASS
    asof 2026-11-05 -> window starts 2026-08-07 -> OUTSIDE -> FAIL

Those three closed on 2026-08-06 under the `should_rotate` rule removed
on 2026-09-08 (reason "-> GNFC.NS - +Npp alpha"). India's coverage
begins 2026-08-04, so that cohort is the oldest accountable close that
exists - which is why 2026-11-05 was the first day this could fire.

TWO DEFECTS, NOT ONE
--------------------
1. No durable lineage. The orphan sink reads `closed_*_90d` (already
   window-scoped, so an aged-out episode can never enter it) and dedupes
   by TICKER (so a ticker's second episode never gets a record).

2. Ticker-level accounting. A23 reported 3 lost when 5 had aged out:
   INFY and VEDL were masked because both had re-entered, and a
   ticker-level set cannot tell a CLOSED episode from an ACTIVE one
   wearing the same name. The same masking hid USA's PLD: its Exit
   History row was the AUGUST episode
   (USA-R2-PLD-20260811-07cd90, ORPHAN AUTO-CLOSE) while the episode
   closed on 2026-11-04 (USA-R2-PLD-20260915-4969bb) was absent.

Measured authoritative population at asof 2026-11-06: India 11 episodes
outside the window, all rotation closes; USA 0. The earlier "~136" was a
ticker-level, window-naive discovery sweep and was never the count.

WHAT IS NOT CHANGED
-------------------
A23 still fails on a genuinely unaccounted episode. The 90-day retention
window is untouched. Historical close dates and reasons are copied, never
rewritten - an artifact that lies about when something closed is worse
than one that admits it is missing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.delivery.lineage import episode_lineage as EL

_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FakeOpp:
    """Shaped like registry Opportunity, for the parts lineage reads."""
    opportunity_id: str
    ticker: str
    market: str = "india"
    runner: str = "R2"
    status: str = "CLOSED"
    created_date: str = "2026-08-05"
    closed_date: str = "2026-08-06"
    closed_reason: str = "→ GNFC.NS · +59.7pp alpha"

    def is_active(self) -> bool:
        return self.status == "ACTIVE"


def _patch(monkeypatch, episodes, eh_ids=(), root=None):
    monkeypatch.setattr(EL, "accountable_closed_episodes",
                        lambda r, m: [e for e in episodes
                                      if str(e.market).lower() == str(m).lower()
                                      and e.status == "CLOSED"])
    monkeypatch.setattr(EL, "exit_history_episode_ids",
                        lambda r, m: set(eh_ids))


# ─────────────────────────────────────────────────────────────
# the retention window is read, never changed
# ─────────────────────────────────────────────────────────────

class TestTheRetentionWindowIsUntouched:

    def test_window_is_ninety_days(self):
        assert EL.EXIT_HISTORY_WINDOW_DAYS == 90, (
            "widening retention would HIDE the lineage gap rather than "
            "close it · the window is not the defect")

    def test_window_start_is_asof_minus_ninety(self):
        assert EL.window_start("2026-11-05") == date(2026, 8, 7)
        assert EL.window_start("2026-11-04") == date(2026, 8, 6)

    def test_the_boundary_reproduces_the_incident(self):
        """2026-08-06 inside on the 4th, outside on the 5th."""
        closed = date(2026, 8, 6)
        assert EL.window_start("2026-11-04") <= closed
        assert EL.window_start("2026-11-05") > closed


# ─────────────────────────────────────────────────────────────
# the accounting model
# ─────────────────────────────────────────────────────────────

class TestTheAccountingModel:

    def test_in_exit_history_is_REPRESENTED(self, tmp_path, monkeypatch):
        e = FakeOpp("IND-R2-AAA-20260805-aaa", "AAA")
        _patch(monkeypatch, [e], eh_ids=[e.opportunity_id])
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_REPRESENTED] == 1
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 0

    def test_in_lineage_only_is_ACCOUNTED_ADMINISTRATIVE(self, tmp_path,
                                                         monkeypatch):
        e = FakeOpp("IND-R2-BBB-20260805-bbb", "BBB")
        _patch(monkeypatch, [e], eh_ids=[])
        p = EL.audit_path(tmp_path, "india")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"opportunity_id": e.opportunity_id,
                                 "ticker": "BBB"}) + "\n", encoding="utf-8")
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_ACCOUNTED_ADMIN] == 1
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 0

    def test_in_neither_is_UNACCOUNTED(self, tmp_path, monkeypatch):
        e = FakeOpp("IND-R2-CCC-20260805-ccc", "CCC")
        _patch(monkeypatch, [e], eh_ids=[])
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 1

    def test_a_closed_episode_with_no_identity_fails_closed(self, tmp_path,
                                                            monkeypatch):
        """Guessing by ticker is the defect · absence of id is UNACCOUNTED."""
        e = FakeOpp("", "DDD")
        _patch(monkeypatch, [e], eh_ids=["IND-R2-DDD-20260805-ddd"])
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 1
        assert len(st["episodes_without_identity"]) == 1


# ─────────────────────────────────────────────────────────────
# episode identity · the masking cases
# ─────────────────────────────────────────────────────────────

class TestEpisodeIdentityNotTicker:

    def test_a_reentered_ticker_does_not_account_for_its_closed_episode(
            self, tmp_path, monkeypatch):
        """INFY / VEDL on 2026-11-05, and USA's PLD.

        Episode A closed and aged out; episode B is live. A ticker-level
        set sees "INFY" on both sides and calls it accounted.
        """
        closed = FakeOpp("IND-R2-INFY-20260805-ea04e5", "INFY",
                         status="CLOSED", closed_date="2026-08-06")
        active = FakeOpp("IND-R2-INFY-20261013-999999", "INFY",
                         status="ACTIVE", closed_date="")
        # Exit History holds only the LIVE episode's id
        _patch(monkeypatch, [closed, active],
               eh_ids=[active.opportunity_id])
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 1, (
            "an unrelated active episode must not account for a closed one")

    def test_two_historical_closes_of_one_ticker_are_counted_separately(
            self, tmp_path, monkeypatch):
        a = FakeOpp("USA-R2-PLD-20260811-07cd90", "PLD", market="usa",
                    closed_date="2026-08-26")
        b = FakeOpp("USA-R2-PLD-20260915-4969bb", "PLD", market="usa",
                    closed_date="2026-11-04")
        # the sheet carries only the AUGUST episode · the real PLD case
        _patch(monkeypatch, [a, b], eh_ids=[a.opportunity_id])
        st = EL.account(tmp_path, "usa", "2026-11-07")
        assert st["counts"][EL.STATUS_REPRESENTED] == 1
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 1, (
            "the second episode of the same ticker is its own episode")

    def test_matching_is_by_position_id(self, tmp_path, monkeypatch):
        e = FakeOpp("IND-R2-EEE-20260805-eee", "EEE")
        # right ticker, WRONG episode id
        _patch(monkeypatch, [e], eh_ids=["IND-R2-EEE-20260101-other"])
        st = EL.account(tmp_path, "india", "2026-11-06")
        assert st["counts"][EL.STATUS_UNACCOUNTED] == 1


# ─────────────────────────────────────────────────────────────
# reconcile · selection, idempotence, fidelity
# ─────────────────────────────────────────────────────────────

class TestReconcile:

    def test_an_aged_out_episode_is_recorded(self, tmp_path, monkeypatch):
        e = FakeOpp("IND-R2-FFF-20260805-fff", "FFF", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        man = EL.reconcile(tmp_path, "india", "2026-11-06")
        assert man["n_selected"] == 1
        assert man["unaccounted_before"] == 1
        assert man["unaccounted_after"] == 0

    def test_an_in_window_episode_is_NOT_papered_over(self, tmp_path,
                                                      monkeypatch):
        """USA/PLD on 2026-11-04 was exactly this · a real defect.

        Its absence from Exit History must keep failing A23 rather than
        being silently accounted for by lineage.
        """
        e = FakeOpp("USA-R2-PLD-20260915-4969bb", "PLD", market="usa",
                    closed_date="2026-11-04")
        _patch(monkeypatch, [e], eh_ids=[])
        man = EL.reconcile(tmp_path, "usa", "2026-11-07")
        assert man["n_selected"] == 0, (
            "an episode still inside retention belongs in Exit History · "
            "lineage must not excuse it")
        assert man["unaccounted_after"] == 1
        assert any("inside the" in str(x.get("reason", ""))
                   for x in man["excluded"])

    def test_selection_is_data_driven_not_workbook_driven(self, tmp_path,
                                                          monkeypatch):
        """The first version read the rendered sheet and so depended on
        whichever as-of it happened to be built with: a workbook rendered
        at 2026-11-04 still lists the 2026-08-06 cohort, so the
        reconciler saw nothing to do while CI was blocking on exactly
        those episodes."""
        e = FakeOpp("IND-R2-GGG-20260805-ggg", "GGG", closed_date="2026-08-06")
        # the stale sheet still SHOWS it
        _patch(monkeypatch, [e], eh_ids=[e.opportunity_id])
        man = EL.reconcile(tmp_path, "india", "2026-11-06")
        assert man["n_selected"] == 1, (
            "an episode closed before the window cannot be in Exit "
            "History · that is arithmetic, not a property of whichever "
            "workbook is on disk")

    def test_idempotent_second_run_records_nothing(self, tmp_path,
                                                   monkeypatch):
        e = FakeOpp("IND-R2-HHH-20260805-hhh", "HHH", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        first = EL.reconcile(tmp_path, "india", "2026-11-06")
        second = EL.reconcile(tmp_path, "india", "2026-11-06")
        assert first["n_selected"] == 1
        assert second["n_selected"] == 0
        lines = [l for l in EL.audit_path(tmp_path, "india")
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1, "idempotence means no duplicate lineage"

    def test_no_duplicate_lineage_for_the_same_episode(self, tmp_path,
                                                       monkeypatch):
        e = FakeOpp("IND-R2-III-20260805-iii", "III", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        for _ in range(4):
            EL.reconcile(tmp_path, "india", "2026-11-06")
        ids = [json.loads(l)["opportunity_id"] for l in
               EL.audit_path(tmp_path, "india").read_text(encoding="utf-8")
               .splitlines() if l.strip()]
        assert ids.count(e.opportunity_id) == 1

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        e = FakeOpp("IND-R2-JJJ-20260805-jjj", "JJJ", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        man = EL.reconcile(tmp_path, "india", "2026-11-06", dry_run=True)
        assert man["n_selected"] == 1
        assert not EL.audit_path(tmp_path, "india").exists()

    def test_historical_close_date_and_reason_are_not_rewritten(
            self, tmp_path, monkeypatch):
        """Do not alter historical facts merely to make A23 pass."""
        e = FakeOpp("IND-R2-BHARATFORG-20260805-615b4c", "BHARATFORG",
                    created_date="2026-08-05", closed_date="2026-08-06",
                    closed_reason="→ GNFC.NS · +59.7pp alpha")
        _patch(monkeypatch, [e], eh_ids=[])
        EL.reconcile(tmp_path, "india", "2026-11-06")
        rec = json.loads(EL.audit_path(tmp_path, "india")
                         .read_text(encoding="utf-8").splitlines()[0])
        assert rec["closed_date"] == "2026-08-06"
        assert rec["created_date"] == "2026-08-05"
        assert rec["closed_reason"] == "→ GNFC.NS · +59.7pp alpha"
        assert rec["close_type"] == EL.CLOSE_TYPE_ROTATION
        assert rec["accounting_status"] == EL.STATUS_ACCOUNTED_ADMIN
        assert rec["source"] == EL.SOURCE_REGISTRY

    def test_the_record_carries_every_required_lineage_field(self, tmp_path,
                                                             monkeypatch):
        e = FakeOpp("IND-R2-KKK-20260805-kkk", "KKK", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        EL.reconcile(tmp_path, "india", "2026-11-06")
        rec = json.loads(EL.audit_path(tmp_path, "india")
                         .read_text(encoding="utf-8").splitlines()[0])
        for f in ("market", "position_id", "ticker", "opportunity_id",
                  "closed_date", "closed_reason", "close_type",
                  "disposition", "source", "accounting_status"):
            assert f in rec and rec[f] not in (None, ""), f
        assert rec["position_id"] == rec["opportunity_id"], (
            "one identity under both names consumers already use")

    def test_an_episode_without_identity_is_excluded_not_guessed(
            self, tmp_path, monkeypatch):
        e = FakeOpp("", "LLL", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        man = EL.reconcile(tmp_path, "india", "2026-11-06")
        assert man["n_selected"] == 0
        assert any("no episode identity" in str(x.get("reason", ""))
                   for x in man["excluded"])

    def test_manifest_reports_population_and_before_after(self, tmp_path,
                                                          monkeypatch):
        es = [FakeOpp("IND-R2-M%d-20260805-m%d" % (i, i), "M%d" % i,
                      closed_date="2026-08-06") for i in range(3)]
        _patch(monkeypatch, es, eh_ids=[])
        man = EL.reconcile(tmp_path, "india", "2026-11-06")
        sp = man["source_population"]
        assert sp["n_accountable_closed"] == 3
        assert sp["source"] == EL.SOURCE_REGISTRY
        assert man["unaccounted_before"] == 3
        assert man["unaccounted_after"] == 0
        assert man["destination"].endswith(
            "episode_lineage_india.jsonl"), (
            "the manifest must name the CANONICAL sink · writing to "
            "orphan_audit is what let the sender erase it")


# ─────────────────────────────────────────────────────────────
# close-type classification
# ─────────────────────────────────────────────────────────────

class TestCloseTypeClassification:

    @pytest.mark.parametrize("reason", [
        "→ GNFC.NS · +59.7pp alpha",
        "-> GNFC.NS - +7.8pp alpha",
    ])
    def test_rotation_reasons_are_ROTATION(self, reason):
        assert EL.classify_close_type(reason) == EL.CLOSE_TYPE_ROTATION

    @pytest.mark.parametrize("reason", [
        "STOP_LOSS_HIT", "target reached", "",
        "high leverage (D/E 62.131)",
    ])
    def test_everything_else_is_REAL_EXIT(self, reason):
        assert EL.classify_close_type(reason) == EL.CLOSE_TYPE_REAL_EXIT

    def test_a_peer_mention_without_alpha_is_not_a_rotation(self):
        assert EL.classify_close_type(
            "exited, better names exist") == EL.CLOSE_TYPE_REAL_EXIT


# ─────────────────────────────────────────────────────────────
# A23 itself · semantics preserved, new source accepted
# ─────────────────────────────────────────────────────────────

class TestA23SemanticsPreserved:

    @staticmethod
    def _a23_source() -> str:
        return (_ROOT / "backend" / "research"
                / "wave_regression.py").read_text(encoding="utf-8")

    def test_a23_still_fails_on_a_genuinely_unaccounted_episode(self):
        src = self._a23_source()
        assert "_silently_lost" in src
        assert 'rep.add("A23"' in src
        assert '"FAIL"' in src, "A23 must retain a FAIL outcome"

    def test_a23_reasons_by_episode_when_identity_is_available(self):
        src = self._a23_source()
        assert "_closed_eps" in src and "_in_eh_eps" in src
        assert "_in_audit_eps" in src
        assert "_lost_eps = _closed_eps - _in_eh_eps - _in_audit_eps" in src

    def test_a23_falls_back_to_tickers_only_without_a_position_id_column(self):
        """Legacy layouts and synthetic fixtures carry no Position ID.

        There is then no episode identity to reason with, so the original
        comparison stands rather than being guessed at - and the detail
        string names the basis so a reader never has to infer it.
        """
        src = self._a23_source()
        assert "_a23_basis" in src
        assert '"episode" if _eh_pos_col else "ticker"' in src

    def test_a23_records_which_basis_it_used(self):
        src = self._a23_source()
        assert "{_a23_basis}" in src

    def test_a23_does_not_widen_the_retention_window(self):
        src = self._a23_source()
        assert "timedelta(days=90)" not in src.split("A23")[-1][:4000], (
            "A23 must not grow its own window · the fix is lineage")

    def test_an_unidentified_closed_episode_still_fails_a23(self):
        src = self._a23_source()
        assert "_eps_no_identity" in src
        assert "_silently_lost |= _eps_no_identity" in src


# ─────────────────────────────────────────────────────────────
# pipeline wiring · lineage exists before the gate reads it
# ─────────────────────────────────────────────────────────────

class TestPipelineWiring:

    @staticmethod
    def _build_lifecycle_src() -> str:
        import ast
        p = _ROOT / "backend" / "pipeline" / "contract" / "runner.py"
        src = p.read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.FunctionDef) and n.name == "build_lifecycle":
                return "\n".join(src.splitlines()[n.lineno - 1: n.end_lineno])
        raise AssertionError("build_lifecycle not found")

    def test_lineage_runs_in_the_always_on_path(self):
        body = self._build_lifecycle_src()
        assert '"episode_lineage"' in body, (
            "lineage must be recorded on every run, before DELIVERY_READY "
            "evaluates A23 · this is what makes India need no workflow "
            "change")

    def test_lineage_runs_after_the_lifecycle_and_before_the_reconciler(self):
        body = self._build_lifecycle_src()
        i_life = body.find('"lifecycle"')
        i_lin = body.find('"episode_lineage"')
        i_wnc = body.find('"why_not_current"')
        assert -1 < i_life < i_lin < i_wnc

    def test_the_registry_is_settled_before_the_lifecycle(self):
        """The USA/PLD ordering fix must not regress."""
        body = self._build_lifecycle_src()
        assert (body.find('"registry_materializer"')
                < body.find('"lifecycle"'))


# ─────────────────────────────────────────────────────────────
# isolation · no production decision logic touched
# ─────────────────────────────────────────────────────────────

class TestTheLineageSinkIsNotTruncated:
    """The sender erased the lineage it was supposed to read.

    CEO 2026-11-07. India's A23 gate passed in CI (run 42334884268,
    step 20 success) and the run still failed at step 23, the Telegram
    sender. Cause: the sender rewrote
    reports/delivery/orphan_audit_<market>.jsonl with mode "w" from its
    OWN computed set, deleting every record written by anything else.

    Measured: 37 rows -> 26, the 11 durable episode-lineage records
    gone, and the post-build recompute then reported

        A23 FAIL :: 11 Registry-CLOSED episode(s) silently lost
        ATUL, BHARATFORG, DELHIVERY, HCLTECH, HEROMOTOCO ...

    So the India fix verified locally and was erased on the next real
    run. An audit ledger that a renderer may truncate is not an audit
    ledger.
    """

    _SENDER = _ROOT / "scripts" / "telegram_command_center_send.py"

    def test_the_sender_preserves_records_it_did_not_write(self):
        src = self._SENDER.read_text(encoding="utf-8")
        assert "_foreign_rows" in src, (
            "the sender must carry forward orphan-audit records written "
            "by another component instead of truncating them")
        assert "_own_ids" in src, (
            "its own rows are keyed by opportunity_id so they refresh "
            "rather than duplicate")

    def test_every_truncating_write_of_the_sink_preserves_foreign_rows(self):
        """Structural: the defect WAS the bare mode-"w" rewrite."""
        src = self._SENDER.read_text(encoding="utf-8").splitlines()
        offenders = []
        for i, line in enumerate(src):
            if '_orphan_audit_p.open("w"' not in line:
                continue
            window = "\n".join(src[max(0, i - 40):i + 12])
            if "_foreign_rows" not in window:
                offenders.append(i + 1)
        assert not offenders, (
            "orphan_audit rewritten with mode 'w' and no preservation of "
            "foreign records at line(s) %s" % offenders)

    def test_lineage_ids_are_matched_by_episode_on_read_back(self):
        """Keyed by episode · the old sink deduped by TICKER, which is
        why a ticker's second episode never got a record."""
        src = (_ROOT / "backend" / "delivery" / "lineage"
               / "episode_lineage.py").read_text(encoding="utf-8")
        assert "def recorded_episode_ids" in src
        assert 'e.get("opportunity_id")' in src


class TestTheCanonicalLedgerIsStructurallyProtected:
    """Preserving the sender's write was not enough. CEO 2026-11-07.

    Durable lineage first lived in orphan_audit_<market>.jsonl, which
    the sender rewrites with mode "w". Teaching the sender to carry
    foreign rows forward fixed THAT writer and left the canonical
    ledger reachable by the next one. A sender may CONSUME accounting
    history; it must never be able to destroy history a blocking
    invariant depends on.

    So the canonical record lives in episode_lineage_<market>.jsonl,
    which no renderer, sender or workbook builder writes, and A23 reads
    both it and the sender's derived view.

    Measured: with the sender's orphan_audit wiped to 0 rows,
    A23=PASS and gate=ALLOW. Before the split that same wipe produced
    A23 FAIL on 11 episodes.
    """

    def test_the_canonical_and_derived_sinks_are_different_files(self):
        assert (EL.canonical_path(_ROOT, "india")
                != EL.derived_audit_path(_ROOT, "india"))
        assert "episode_lineage_" in EL.canonical_path(_ROOT, "india").name
        assert "orphan_audit_" in EL.derived_audit_path(_ROOT, "india").name

    def test_lineage_is_written_only_to_the_canonical_sink(self, tmp_path,
                                                            monkeypatch):
        e = FakeOpp("IND-R2-ZZZ-20260805-zzz", "ZZZ", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        EL.reconcile(tmp_path, "india", "2026-11-06")
        assert EL.canonical_path(tmp_path, "india").exists()
        assert not EL.derived_audit_path(tmp_path, "india").exists(), (
            "the durable record must never be written into the file the "
            "sender rewrites")

    def test_accounting_reads_both_sinks(self, tmp_path, monkeypatch):
        """The derived view still holds legitimate retired/admin closes."""
        a = FakeOpp("IND-R2-AAA-20260805-a", "AAA")
        b = FakeOpp("IND-R2-BBB-20260805-b", "BBB")
        _patch(monkeypatch, [a, b], eh_ids=[])
        d = EL.derived_audit_path(tmp_path, "india")
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(json.dumps({"opportunity_id": a.opportunity_id,
                                 "ticker": "AAA"}), encoding="utf-8")
        c = EL.canonical_path(tmp_path, "india")
        c.write_text(json.dumps({"kind": EL.KIND,
                                 "opportunity_id": b.opportunity_id,
                                 "ticker": "BBB"}), encoding="utf-8")
        ids = EL.recorded_episode_ids(tmp_path, "india")
        assert a.opportunity_id in ids and b.opportunity_id in ids

    def test_destroying_the_derived_view_does_not_lose_lineage(self, tmp_path,
                                                                monkeypatch):
        """The five-day defect, now structurally impossible."""
        e = FakeOpp("IND-R2-YYY-20260805-y", "YYY", closed_date="2026-08-06")
        _patch(monkeypatch, [e], eh_ids=[])
        EL.reconcile(tmp_path, "india", "2026-11-06")
        assert e.opportunity_id in EL.recorded_episode_ids(tmp_path, "india")
        # the sender's mode-"w" rewrite, in full
        EL.derived_audit_path(tmp_path, "india").write_text(
            "", encoding="utf-8")
        assert e.opportunity_id in EL.recorded_episode_ids(tmp_path, "india"), (
            "a consumer wiping its own derived view must not erase "
            "accounting history a BLOCKING invariant depends on")

    def test_no_other_production_module_writes_the_canonical_sink(self):
        """Enforced, not promised.

        episode_lineage.py is the sole writer by construction. A module
        may REFERENCE the canonical filename; it may not write it.
        """
        writes = ('open(', 'write_text', '.unlink(', 'shutil.move',
                  'shutil.copy')
        offenders = []
        for d in ("scripts", "backend"):
            for f in (_ROOT / d).rglob("*.py"):
                if f.name == "episode_lineage.py":
                    continue
                try:
                    txt = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                at = txt.find("episode_lineage_")
                while at >= 0:
                    seg = txt[max(0, at - 220): at + 220]
                    if any(w in seg for w in writes):
                        offenders.append(str(f.relative_to(_ROOT)))
                        break
                    at = txt.find("episode_lineage_", at + 1)
        assert not offenders, (
            "only backend/delivery/lineage/episode_lineage.py may write "
            "the canonical ledger · found %s" % sorted(set(offenders)))


class TestNoProductionDecisionLogicTouched:

    def test_lineage_never_writes_the_registry(self):
        """Scanned from the AST, not from the text.

        The first version of this matched the substring ".close(" and
        flagged `wb.close()` - closing a workbook - as a registry
        mutation. Matching prose instead of structure is the same
        mistake that produced earlier false findings in this repo, so
        this resolves real call targets.
        """
        import ast
        src = (_ROOT / "backend" / "delivery" / "lineage"
               / "episode_lineage.py").read_text(encoding="utf-8")
        mutators = {"get_or_create", "close", "reject", "touch",
                    "apply_canonical_repair"}
        found = []
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in mutators:
                continue
            recv = node.func.value
            name = (recv.id if isinstance(recv, ast.Name)
                    else getattr(recv, "attr", ""))
            # `wb.close()` is a workbook handle; `_oreg.close()` is not.
            if "oreg" in str(name).lower() or "registry" in str(name).lower():
                found.append((name, node.func.attr, node.lineno))
        assert not found, (
            "lineage is an accounting record · it must not mutate the "
            "registry it describes · found %s" % found)

    def test_lineage_writes_only_the_audit_sink(self):
        src = (_ROOT / "backend" / "delivery" / "lineage"
               / "episode_lineage.py").read_text(encoding="utf-8")
        # the only write path is audit_path(...).open("a")
        assert src.count('.open("a"') == 1
        assert "orphan_audit_" in src

    def test_lineage_delegates_exclusions_rather_than_redefining_them(self):
        """A second definition of 'accountable close' is the bug class
        this repair exists to remove."""
        src = (_ROOT / "backend" / "delivery" / "lineage"
               / "episode_lineage.py").read_text(encoding="utf-8")
        assert "retired_runners" in src
        assert "_is_administrative_exit" in src

    def test_no_threshold_or_sizing_vocabulary_appears(self):
        src = (_ROOT / "backend" / "delivery" / "lineage"
               / "episode_lineage.py").read_text(encoding="utf-8")
        for word in ("stop_loss", "position_size", "threshold",
                     "weight", "universe"):
            assert word not in src, (
                "lineage is an accounting repair · %s has no business "
                "here" % word)
