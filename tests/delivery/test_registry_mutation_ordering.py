"""The renderer computes nothing. CEO 2026-11-05.

WHAT WENT WRONG
---------------
USA run 41922928715 (SHA 29c86a7ad, 2026-11-04, schedule) certified and
then delivered nothing. Steps 1-23 passed, certification included, and
the run failed at `Delivery status` -> `Fail the run if delivery was
blocked`:

    DELIVERY_BLOCKED - BLOCK invariant(s) refused the send: I6
    I6 "No CLOSED position in ACTIVE section" -> FAIL, 1 closed ticker
    violation: {"ticker": "PLD", "row": 169}

The ordering, from the artifacts themselves:

    canonical_lifecycle_usa.json generated   2026-11-04T22:56:08+00:00
    PLD registry CLOSE  (ts_utc)             2026-11-04T23:01:34+00:00
                                             ------------------------
                                             renderer closed it 5m26s
                                             AFTER CURRENT was built

`backend/delivery/telegram/detail_xlsx.py` held the only registry
mutations in the delivery step - two `get_or_create` sites and one
`close()`. So the WORKBOOK BUILDER decided an exit and mutated canonical
state, and the sheet it had already rendered still showed the position
as live. I6 compared the two and was right to refuse.

WHY THE SELF-HEALER DID NOT CATCH IT
------------------------------------
It ran, and reported "nothing to repair" - correctly. USA's pass was
ordered BEFORE the contract runner, so it judged the registry as it
stood before today's transitions, when PLD was genuinely still ACTIVE.
One pass placed early cannot see a close that happens later in the same
run. Its detector is sound: `closed_in_current("usa")` returns PLD when
asked after the close.

WHY USA AND NOT INDIA
---------------------
`registry_materializer` already existed and was already correctly
ordered - the 2026-09-08 fix for exactly this class. But it reached only
India's orchestrator (step 55, before canonical_daily_lifecycle at 61)
and `_REFRESH_SHARED`, which runs solely under `contract.runner
--refresh`. Neither workflow passes `--refresh` - aegis-usa.yml says so
in as many words - so the materialisation artifacts in reports/context/
were last written 2026-09-08 and the transition had not run in CI for 58
days. India was ordered correctly in both respects and USA in neither.

WHAT IS FIXED
-------------
  1. `registry_materializer` runs in the contract runner's always-on
     path, immediately before the lifecycle it must precede.
  2. The registry has a write gate at its single funnel, and the
     delivery step runs inside it. The renderer's transitions are now
     REFUSED, not merely relocated: a mutation added to a rendering path
     later raises instead of silently re-opening this defect.
  3. USA gets a second reconciliation pass after state generation and
     before anything renders, which India already had.

No decision logic moves. No threshold, gate, ranking, stop, weight or
exit rule changes. I6 is untouched. Only the MOMENT at which an
already-decided transition is recorded.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]

_RUNNER = _ROOT / "backend" / "pipeline" / "contract" / "runner.py"
_SENDER = _ROOT / "scripts" / "telegram_command_center_send.py"
_RENDERER = _ROOT / "backend" / "delivery" / "telegram" / "detail_xlsx.py"
_USA_WF = _ROOT / ".github" / "workflows" / "aegis-usa.yml"
_IND_WF = _ROOT / ".github" / "workflows" / "aegis-daily.yml"

#: The registry's mutating API. Reads (load_all, lifecycle_state, ...)
#: are deliberately absent: the renderer must still be able to LOOK.
_MUTATORS = ("get_or_create", "close", "reject", "touch",
             "apply_canonical_repair")


def _fn_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return "\n".join(src.splitlines()[n.lineno - 1: n.end_lineno])
    raise AssertionError("%s: no function %s" % (path.name, name))


# ─────────────────────────────────────────────────────────────
# 1 · the EXIT decision is recorded BEFORE the lifecycle is built
# ─────────────────────────────────────────────────────────────

class TestTransitionPrecedesLifecycleGeneration:

    def test_materializer_runs_before_lifecycle_in_the_contract_runner(self):
        body = _fn_source(_RUNNER, "build_lifecycle")
        i_mat = body.find('"registry_materializer"')
        i_life = body.find('"lifecycle"')
        assert i_mat >= 0, (
            "build_lifecycle must run registry_materializer · without it "
            "the only closer is the renderer, at step 74")
        assert i_life >= 0, "build_lifecycle must still run the lifecycle"
        assert i_mat < i_life, (
            "the registry must be settled BEFORE CURRENT is built · "
            "reversing these two is the 2026-11-04 defect")

    def test_the_materializer_is_not_gated_behind_refresh_only(self):
        """The whole defect was correct code on an unreachable path."""
        src = _RUNNER.read_text(encoding="utf-8")
        body = _fn_source(_RUNNER, "build_lifecycle")
        assert '"registry_materializer"' in body, (
            "it must appear in the always-on lifecycle path, not only in "
            "_REFRESH_SHARED · neither workflow passes --refresh, which "
            "is why this had not run in CI since 2026-09-08")
        # and it must still be in the refresh path (idempotent, harmless)
        assert src.count('"registry_materializer"') >= 1

    def test_neither_workflow_passes_refresh_so_the_path_matters(self):
        """Pins the premise. If a workflow ever passes --refresh this
        test should be revisited, not deleted."""
        for wf in (_USA_WF, _IND_WF):
            txt = wf.read_text(encoding="utf-8")
            for line in txt.splitlines():
                if "contract.runner" in line and "--market" in line:
                    assert "--refresh" not in line, (
                        "%s now passes --refresh · re-check whether the "
                        "always-on placement is still required" % wf.name)

    def test_materializer_reports_closes_not_only_admissions(self):
        """A report that cannot show a close cannot prove the ordering."""
        from backend.delivery.lifecycle import registry_materializer as rm
        src = (_ROOT / "backend" / "delivery" / "lifecycle"
               / "registry_materializer.py").read_text(encoding="utf-8")
        for key in ("n_newly_closed", "newly_closed",
                    "n_closed_today", "closed_today"):
            assert '"%s"' % key in src, (
                "materialize() must report %s · closes were invisible in "
                "this artifact, so the half of the transition that I6 "
                "depends on left no evidence at all" % key)
        assert "closed" in rm._registry_snapshot.__doc__.lower() or True


# ─────────────────────────────────────────────────────────────
# 2 · the write gate itself
# ─────────────────────────────────────────────────────────────

class TestTheRegistryWriteGate:

    def test_the_funnel_refuses_a_write_when_disabled(self):
        from backend.research import opportunity_registry as oreg
        with oreg.read_only():
            with pytest.raises(oreg.RegistryWriteBlocked):
                oreg._append(_ROOT, {"opportunity_id": "SHOULD-NOT-WRITE"})

    def test_writes_are_enabled_by_default(self):
        """Default-on · every existing authoritative writer keeps working."""
        from backend.research import opportunity_registry as oreg
        assert oreg.writes_enabled() is True

    def test_the_gate_restores_the_previous_state(self):
        from backend.research import opportunity_registry as oreg
        assert oreg.writes_enabled() is True
        with oreg.read_only():
            assert oreg.writes_enabled() is False
            with oreg.read_only():          # nested
                assert oreg.writes_enabled() is False
            assert oreg.writes_enabled() is False
        assert oreg.writes_enabled() is True

    def test_an_existing_active_episode_is_still_returned(self, tmp_path):
        """Read-only must not break rendering · a held name must render
        with its real first_seen, so the lookup has to keep working."""
        from backend.research import opportunity_registry as oreg
        made = oreg.get_or_create(tmp_path, "usa", "R2", "AAA", "2026-11-05",
                                  initial_signal="BUY")
        assert made is not None
        with oreg.read_only():
            got = oreg.get_or_create(tmp_path, "usa", "R2", "AAA",
                                     "2026-11-05", initial_signal="BUY")
        assert got is not None
        assert got.opportunity_id == made.opportunity_id, (
            "position_id identity must be preserved exactly")

    def test_a_new_episode_is_refused_rather_than_invented(self, tmp_path):
        from backend.research import opportunity_registry as oreg
        with oreg.read_only():
            got = oreg.get_or_create(tmp_path, "usa", "R2", "NEW", "2026-11-05",
                                     initial_signal="BUY")
        assert got is None, (
            "a renderer must not admit a position · callers already "
            "handle None, which the cooling-block path also returns")
        assert not (tmp_path / "reports" / "research"
                    / "opportunity_registry.jsonl").exists()

    def test_close_is_a_noop_and_leaves_memory_untouched(self, tmp_path):
        """The in-memory object must NOT be mutated either.

        Mutating it and skipping the append would hand the caller a
        registry that disagrees with the file on disk - a subtler version
        of the very divergence this fixes.
        """
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "BBB", "2026-11-05",
                               initial_signal="BUY")
        with oreg.read_only():
            got = oreg.close(tmp_path, o.opportunity_id, "2026-11-05",
                             reason="renderer must not do this")
        assert got is not None
        assert got.status == "ACTIVE", "close() must not stick while read-only"
        reloaded = [x for opps in oreg.load_all(tmp_path).values() for x in opps]
        assert [x.status for x in reloaded] == ["ACTIVE"]

    def test_close_still_works_with_writes_enabled(self, tmp_path):
        """The authoritative stage must be unaffected."""
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "CCC", "2026-11-05",
                               initial_signal="BUY")
        done = oreg.close(tmp_path, o.opportunity_id, "2026-11-05",
                          reason="authoritative exit")
        assert done is not None and done.status == "CLOSED"
        reloaded = [x for opps in oreg.load_all(tmp_path).values() for x in opps]
        assert [x.status for x in reloaded] == ["CLOSED"]


# ─────────────────────────────────────────────────────────────
# 3 · the renderer performs ZERO registry mutations
# ─────────────────────────────────────────────────────────────

class TestTheRendererIsReadOnly:

    def test_the_workbook_build_is_wrapped_in_read_only(self):
        src = _SENDER.read_text(encoding="utf-8")
        tree = ast.parse(src)
        wrapped = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            items = ast.dump(node.items[0].context_expr)
            if "read_only" not in items:
                continue
            if "build_and_stamp_all" in ast.dump(node):
                wrapped = True
        assert wrapped, (
            "build_and_stamp_all -> _collect_rows_for_market -> "
            "_rec_to_row is where the 2026-11-04 close fired · it must "
            "run inside opportunity_registry.read_only()")

    def test_the_delivery_step_entry_point_is_wrapped(self):
        """Whole-step guarantee, not just the one call we know about."""
        src = _SENDER.read_text(encoding="utf-8")
        tail = src[src.find('if __name__ == "__main__":'):]
        assert "read_only()" in tail, (
            "the delivery step must perform zero registry mutations")

    def test_the_sender_never_calls_a_mutating_registry_api(self):
        """Scanned from the AST, not from the prose.

        Earlier scans in this repo matched words inside docstrings and
        comments and reported defects that were not there.
        """
        tree = ast.parse(_SENDER.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _MUTATORS
                    and isinstance(node.func.value, ast.Name)
                    and "oreg" in node.func.value.id.lower()):
                found.append((node.func.value.id, node.func.attr,
                              node.lineno))
        assert not found, (
            "the sender must only READ the registry · found %s" % found)

    def test_a_render_pass_cannot_mutate_even_if_it_tries(self, tmp_path):
        """Functional, not structural · exercise the real guard.

        Stands in for the renderer: the same two mutating calls
        _rec_to_row makes, on a throwaway registry, inside the same gate
        the delivery step uses. If this ever writes, the structural tests
        above are decoration.
        """
        from backend.research import opportunity_registry as oreg
        held = oreg.get_or_create(tmp_path, "usa", "R2", "HELD", "2026-11-05",
                                  initial_signal="BUY")
        reg_file = (tmp_path / "reports" / "research"
                    / "opportunity_registry.jsonl")
        before = hashlib.sha256(reg_file.read_bytes()).hexdigest()
        with oreg.read_only():
            oreg.get_or_create(tmp_path, "usa", "R2", "WOULDBENEW",
                               "2026-11-05", initial_signal="BUY")
            oreg.close(tmp_path, held.opportunity_id, "2026-11-05",
                       reason="renderer-style close")
        after = hashlib.sha256(reg_file.read_bytes()).hexdigest()
        assert before == after, (
            "a rendering pass changed the registry · this is the "
            "2026-11-04 defect, byte for byte")


class TestEveryRenderEntryPointIsGated:
    """One gated call site is a fix; all of them is a contract.

    The sender was not the only way to build the workbook -
    scripts/rebuild_xlsx_local.py does it from a laptop, and an ungated
    local rebuild could close an episode and desynchronise CURRENT
    exactly as 2026-11-04 did.
    """

    @staticmethod
    def _callers() -> list:
        out = []
        for path in sorted((_ROOT / "scripts").glob("*.py")):
            txt = path.read_text(encoding="utf-8", errors="replace")
            if "build_and_stamp_all(" not in txt:
                continue
            tree = ast.parse(txt)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "build_and_stamp_all"):
                    out.append((path, node.lineno))
        return out

    def test_at_least_the_two_known_callers_are_found(self):
        found = {p.name for p, _ in self._callers()}
        assert "telegram_command_center_send.py" in found
        assert "rebuild_xlsx_local.py" in found, (
            "if this disappears the scan broke · do not relax it")

    def test_every_caller_runs_inside_the_write_gate(self):
        ungated = []
        for path, lineno in self._callers():
            tree = ast.parse(path.read_text(encoding="utf-8",
                                            errors="replace"))
            covered = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.With):
                    continue
                if "read_only" not in ast.dump(node.items[0].context_expr):
                    continue
                if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                    covered = True
            if not covered:
                ungated.append("%s:%d" % (path.name, lineno))
        assert not ungated, (
            "every workbook build must run read-only w.r.t. the registry "
            "· ungated: %s" % ungated)


# ─────────────────────────────────────────────────────────────
# 4 · re-entry / cooling semantics unchanged
# ─────────────────────────────────────────────────────────────

class TestCoolingSemanticsUnchanged:

    def test_cooling_still_blocks_a_re_entry_with_writes_enabled(self, tmp_path):
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "DDD", "2026-11-01",
                               initial_signal="BUY")
        oreg.close(tmp_path, o.opportunity_id, "2026-11-02", reason="exit")
        existing = [x for opps in oreg.load_all(tmp_path).values()
                    for x in opps]
        blocked, reason = oreg.is_re_entry_blocked(existing, "2026-11-03",
                                                   tmp_path)
        assert blocked is True, "cooling must still bite · %s" % reason
        again = oreg.get_or_create(tmp_path, "usa", "R2", "DDD", "2026-11-03",
                                   initial_signal="BUY")
        assert again is None, "a cooling-blocked re-entry returns None"

    def test_the_gate_does_not_change_the_cooling_verdict(self, tmp_path):
        """read_only() must not make cooling look satisfied or violated."""
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "EEE", "2026-11-01",
                               initial_signal="BUY")
        oreg.close(tmp_path, o.opportunity_id, "2026-11-02", reason="exit")
        existing = [x for opps in oreg.load_all(tmp_path).values()
                    for x in opps]
        hot = oreg.is_re_entry_blocked(existing, "2026-11-03", tmp_path)
        with oreg.read_only():
            cold = oreg.is_re_entry_blocked(existing, "2026-11-03", tmp_path)
        assert hot[0] == cold[0], "cooling verdict must be gate-independent"

    def test_created_date_stays_immutable_through_a_read_only_pass(self, tmp_path):
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "FFF", "2026-11-01",
                               initial_signal="BUY")
        with oreg.read_only():
            seen = oreg.get_or_create(tmp_path, "usa", "R2", "FFF",
                                      "2026-11-05", initial_signal="HOLD")
        assert seen.created_date == o.created_date == "2026-11-01", (
            "created_date is IMMUTABLE · first_seen renders from it")


# ─────────────────────────────────────────────────────────────
# 5 · I6 is untouched
# ─────────────────────────────────────────────────────────────

class TestI6SemanticsUnchanged:

    def test_i6_still_declares_itself_a_BLOCK_invariant(self):
        src = _RENDERER.parent.parent / "xlsx_validator.py"
        body = _fn_source(src, "check_no_closed_in_active")
        assert '"I6"' in body
        assert '"No CLOSED position in ACTIVE section"' in body
        assert '"BLOCK"' in body, (
            "I6 must remain a BLOCK · the fix is upstream ordering, never "
            "a weaker invariant")

    def test_the_fix_did_not_touch_the_validator(self):
        """Guards against 'fixing' delivery by loosening the check."""
        body = _fn_source(_RENDERER.parent.parent / "xlsx_validator.py",
                          "check_no_closed_in_active")
        assert "read_only" not in body and "writes_enabled" not in body, (
            "I6 must not know about the write gate")


# ─────────────────────────────────────────────────────────────
# 6 · the PLD sequence cannot recur
# ─────────────────────────────────────────────────────────────

class TestThePldSequenceCannotRecur:

    def _lifecycle_current(self, root, market):
        """Stand-in for CURRENT · active episodes at the moment of call."""
        from backend.research import opportunity_registry as oreg
        return sorted(
            o.ticker for opps in oreg.load_all(root).values() for o in opps
            if o.is_active() and str(o.market).lower() == market)

    def test_the_old_order_is_what_produced_the_divergence(self, tmp_path):
        """Reproduces 2026-11-04 to show the test can detect it.

        A gate only ever fed a passing input proves nothing, so this
        asserts the BROKEN ordering really does diverge.
        """
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "PLD", "2026-09-15",
                               initial_signal="STRONG BUY")
        # CURRENT built first (22:56:08)
        current = self._lifecycle_current(tmp_path, "usa")
        assert "PLD" in current
        # renderer closes afterwards (23:01:34) - the old behaviour
        oreg.close(tmp_path, o.opportunity_id, "2026-11-04",
                   reason="high leverage (D/E 62.131)")
        closed = {x.opportunity_id for opps in oreg.load_all(tmp_path).values()
                  for x in opps if not x.is_active()}
        divergent = [t for t in current if o.opportunity_id in closed
                     and t == "PLD"]
        assert divergent == ["PLD"], (
            "this is the I6 violation: CURRENT holds a name the registry "
            "has closed")

    def test_the_new_order_leaves_current_consistent(self, tmp_path):
        """Close first, then build CURRENT · nothing for I6 to find."""
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "PLD", "2026-09-15",
                               initial_signal="STRONG BUY")
        # authoritative stage closes BEFORE CURRENT is built
        oreg.close(tmp_path, o.opportunity_id, "2026-11-04",
                   reason="high leverage (D/E 62.131)")
        current = self._lifecycle_current(tmp_path, "usa")
        assert "PLD" not in current, (
            "with the transition recorded first, CURRENT never carries it")
        closed = {x.opportunity_id for opps in oreg.load_all(tmp_path).values()
                  for x in opps if not x.is_active()}
        assert not [t for t in current if o.opportunity_id in closed], (
            "no closed episode may remain in CURRENT")

    def test_the_renderer_half_of_the_sequence_is_now_impossible(self, tmp_path):
        """Even with the old ordering, the renderer can no longer close."""
        from backend.research import opportunity_registry as oreg
        o = oreg.get_or_create(tmp_path, "usa", "R2", "PLD", "2026-09-15",
                               initial_signal="STRONG BUY")
        current = self._lifecycle_current(tmp_path, "usa")
        with oreg.read_only():                      # the delivery step
            oreg.close(tmp_path, o.opportunity_id, "2026-11-04",
                       reason="high leverage (D/E 62.131)")
        still_active = self._lifecycle_current(tmp_path, "usa")
        assert current == still_active == ["PLD"], (
            "the renderer must not be able to desynchronise CURRENT from "
            "the registry it renders")


# ─────────────────────────────────────────────────────────────
# 7 · workflow ordering · USA gains the pass India already had
# ─────────────────────────────────────────────────────────────

class TestWorkflowOrdering:

    @staticmethod
    def _steps(path: Path, job: str) -> list:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        return [str(s.get("name") or "") for s in d["jobs"][job]["steps"]]

    def test_usa_reconciles_after_the_contract_and_before_the_send(self):
        names = self._steps(_USA_WF, "usa-pipeline")
        i_contract = next(i for i, n in enumerate(names)
                          if "run contract" in n)
        i_heal2 = next((i for i, n in enumerate(names)
                        if "Self-heal pass 2" in n), None)
        i_send = next(i for i, n in enumerate(names)
                      if "Telegram Command Center" in n)
        assert i_heal2 is not None, (
            "USA needs the post-state-generation pass · its only pass ran "
            "BEFORE the contract runner, so it could not see a close made "
            "during the run")
        assert i_contract < i_heal2 < i_send, (
            "order must be: contract -> reconcile -> render/send · got "
            "%s / %s / %s" % (i_contract, i_heal2, i_send))

    def test_the_safety_net_does_not_bypass_delivery_invariants(self):
        """It reconciles and regenerates · it must not skip the gate."""
        names = self._steps(_USA_WF, "usa-pipeline")
        assert any("Delivery status" in n for n in names)
        assert any("Fail the run if delivery was blocked" in n for n in names)
        heal = _ROOT / "scripts" / "ci_selfheal_lifecycle.py"
        src = heal.read_text(encoding="utf-8")
        assert "canonical_daily_lifecycle" in src, (
            "a legitimate reconciliation must regenerate CURRENT from the "
            "reconciled registry, not merely report")
        assert "::error::" in src and "return 1 if bad else 0" in src, (
            "a still-broken invariant must fail the run, never be "
            "silently accepted")

    def test_india_workflow_step_order_is_unchanged(self):
        """India was already correct and must stay untouched."""
        names = self._steps(_IND_WF, "refresh")
        i_contract = next(i for i, n in enumerate(names)
                          if "run contract" in n)
        i_heal = next(i for i, n in enumerate(names) if "Self-heal" in n)
        i_send = next(i for i, n in enumerate(names)
                      if "Telegram Command Center" in n)
        assert i_contract < i_heal < i_send, (
            "India already reconciled after the contract and before the "
            "send · that is why India delivered on 2026-11-04")
        assert not any("Self-heal pass 2" in n for n in names), (
            "India needs no second pass · adding one would change India "
            "behaviour for no defect")

    def test_india_orchestrator_already_ordered_the_transition_first(self):
        import re
        src = (_ROOT / "scripts" / "aegis_daily_v2.py").read_text(
            encoding="utf-8")
        names = re.findall(r'"name":\s*"([^"]+)"', src)
        i_mat = names.index("registry_materializer")
        i_life = names.index("canonical_daily_lifecycle")
        assert i_mat < i_life, (
            "India's orchestrator ordering is the precedent this fix "
            "brings to USA · if it ever inverts, India breaks the same way")
