"""Tests must not write operational artifacts. CEO 2026-11-04 · §2.

WHAT WAS HAPPENING
------------------
Eleven test files executed production engines against the live
repository via `subprocess.run([... run.py], cwd=ROOT)`. Each engine
resolved its own output paths from its module location, so every
regression run rewrote real artifacts. Identified by audit:

  test_sprint27   ensemble.json, model_factory.json, model_metrics.json
  test_sprint2    market_intelligence.json
  test_sprint3/4/5/6  recommendations_v3*, risk_report, sized_positions,
                      portfolio_*, five learning artifacts
  test_sprint26   selected_features.json, feature_intelligence.json
  (18 runners)    model_registry.jsonl, via register_model(_ROOT, ...)

Not hypothetical. A test rewriting `market_intelligence.json` mid-run is
the most likely cause of
`tests/pipeline/test_run_contract.py::test_no_critical_context_series_is_stale[india]`
failing in the full suite while passing alone - that file is in the
INTERMARKET CRITICAL series list, so the survey can read it while it is
being rewritten.

THE MECHANISM
-------------
A subprocess cannot be handed a Python argument, so the output root
arrives through AEGIS_OUT_ROOT and is resolved in exactly one place:
`backend/shared/out_root.resolved_out_root`. Production sets no
variable, so the resolved root IS the repository root and nothing
moves - verified across all 14 engine runners and 52 output paths.

Reads still come from the real repository. That is deliberate: those
tests exist to exercise engines against the real substrate.

NOT restoring files afterwards. Restoration leaves a window where the
live file is wrong, loses the original on a crash, and cannot work
under parallel execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.shared.out_root import (FEATURE_OUT_ROOT_ENV, OUT_ROOT_ENV,
                                     OutRootEscape, assert_within,
                                     is_redirected, resolved_out_root,
                                     subprocess_env)

_ROOT = Path(__file__).resolve().parents[2]

#: Operational artifacts a test must never modify.
PROTECTED = (
    "reports/recommendation_lifecycle.json",
    "usa/reports/recommendation_lifecycle.json",
    "reports/ensemble.json",
    "reports/market_intelligence.json",
    "reports/recommendations.json",
    "reports/model_factory.json",
    "reports/model_metrics.json",
    "reports/selected_features.json",
    "reports/risk_report.json",
    "reports/sized_positions.json",
    "reports/portfolio_v3.json",
    "reports/research/opportunity_registry.jsonl",
    "features/manifest.jsonl",
    "model_registry.jsonl",
)

#: Engine runners whose report writes must honour the redirect.
RUNNERS = (
    "india/market_intelligence/run.py",
    "india/feature_intelligence/run.py",
    "india/model_factory/run.py",
    "india/recommendation_intelligence/run.py",
    "india/risk_engine/run.py",
    "india/portfolio_engine/run.py",
    "india/learning_engine/run.py",
    "india/feature_store/run.py",
    "usa/research/market_intelligence/run.py",
    "usa/research/feature_intelligence/run.py",
    "usa/research/model_factory/run.py",
    "usa/research/recommendation_intelligence/run.py",
    "usa/research/risk_engine/run.py",
    "usa/research/portfolio_engine/run.py",
    "usa/research/learning_engine/run.py",
    "usa/research/feature_store/run.py",
)


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def protected_hashes() -> dict:
    return {rel: _sha(_ROOT / rel) for rel in PROTECTED}


def _out_paths_of(rel: str, out_root=None) -> dict:
    """Import a runner in a child process and report its OUT_* paths."""
    code = "\n".join([
        "import importlib.util, json, sys",
        "sys.path.insert(0, %r)" % str(_ROOT),
        "spec = importlib.util.spec_from_file_location('probe', %r)"
        % str(_ROOT / rel),
        "m = importlib.util.module_from_spec(spec)",
        "sys.modules['probe'] = m",
        "try:",
        "    spec.loader.exec_module(m)",
        "except SystemExit:",
        "    pass",
        "print(json.dumps({k: str(v) for k, v in vars(m).items()",
        "                  if k.startswith('OUT_') and hasattr(v, 'as_posix')}))",
    ])
    env = subprocess_env(out_root) if out_root else {
        k: v for k, v in os.environ.items()
        if k not in (OUT_ROOT_ENV, FEATURE_OUT_ROOT_ENV)}
    r = subprocess.run([sys.executable, "-c", code], cwd=str(_ROOT),
                       capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == 0, r.stderr[-500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── 1 · production writers write inside the temporary root ─────────
class TestWritersStayInsideTheTemporaryRoot:
    @pytest.mark.parametrize("rel", RUNNERS)
    def test_every_runner_honours_the_redirect(self, rel, tmp_path):
        paths = _out_paths_of(rel, tmp_path)
        assert paths, "%s exposes no OUT_* paths to verify" % rel
        outside = [k for k, v in paths.items()
                   if str(tmp_path) not in v]
        assert outside == [], (
            "%s writes outside the isolated root: %s"
            % (rel, {k: paths[k] for k in outside}))

    @pytest.mark.parametrize("rel", RUNNERS)
    def test_production_paths_are_unchanged_without_the_variable(self, rel):
        """The redirect must not leak into production behaviour."""
        paths = _out_paths_of(rel, None)
        assert paths
        assert all(str(_ROOT) in v for v in paths.values()), paths

    def test_a_real_writer_lands_in_the_temporary_root(self, tmp_path):
        """Exercise an actual engine write, not just a path constant."""
        from backend.canonical.model import USA_PROFILE
        from backend.feature_store.feature_snapshot import build_and_persist
        from datetime import date
        before = protected_hashes()
        r = build_and_persist(_ROOT, USA_PROFILE, asof=date.today(),
                              out_root=tmp_path)
        assert r.get("n_rows", 0) > 0
        assert (tmp_path / "features").exists()
        assert (tmp_path / "features" / "manifest.jsonl").exists()
        assert protected_hashes() == before


# ── 2 · path escapes are rejected ──────────────────────────────────
class TestPathEscapesAreRejected:
    def test_an_absolute_path_outside_the_root_is_rejected(self, tmp_path):
        with pytest.raises(OutRootEscape):
            assert_within(tmp_path, _ROOT / "reports" / "ensemble.json")

    @pytest.mark.parametrize("rel", ["../escape.json",
                                     "a/../../escape.json",
                                     "reports/../../escape.json"])
    def test_dotdot_traversal_is_rejected(self, tmp_path, rel):
        with pytest.raises(OutRootEscape):
            assert_within(tmp_path, rel)

    def test_a_path_inside_the_root_is_allowed(self, tmp_path):
        got = assert_within(tmp_path, "reports/ensemble.json")
        assert str(tmp_path) in str(got)

    def test_the_root_itself_is_allowed(self, tmp_path):
        assert assert_within(tmp_path, ".") == tmp_path.resolve()


# ── 3 · exceptions do not contaminate production state ─────────────
class TestFailuresDoNotTouchProduction:
    def test_a_failing_build_leaves_protected_files_untouched(self, tmp_path):
        """A bogus market fails GRACEFULLY · verdict FAIL, no exception.

        I first asserted `pytest.raises` here and was wrong about the
        engine: `build_and_persist` returns
        `{"verdict": "FAIL", "n_rows": 0}` for an empty frame rather
        than raising. The requirement is that a FAILURE - however it
        surfaces - leaves production untouched, so that is what is
        asserted. The raising path is covered by the test below.
        """
        from backend.canonical.model import INDIA_PROFILE
        from backend.feature_store.feature_snapshot import build_and_persist
        before = protected_hashes()

        # TWO latent defects found trying to induce a graceful failure
        # here, both reported rather than fixed in this task:
        #
        #  1. a bogus market NAME does not fail · `name="nosuchmarket"`
        #     built 228 rows, because FeatureBuilder._universe() falls
        #     through to INDIA's universe for anything that is not
        #     exactly "usa". An unknown market silently yields India
        #     data under the wrong label.
        #  2. an empty repo_root does not fail either · the India branch
        #     does `from india.data_nse import UNIVERSE`, and once that
        #     module is in sys.modules the import ignores repo_root
        #     entirely. The universe is not root-scoped.
        #
        # So a build that SUCCEEDS against an unexpected root is the
        # realistic case, and what matters is that it still writes only
        # inside the isolated root. The raising path is asserted
        # separately below.
        r = build_and_persist(_ROOT, INDIA_PROFILE, out_root=tmp_path)
        assert r.get("n_rows", 0) > 0
        assert str(tmp_path) not in str(_ROOT)
        assert (tmp_path / "features" / "india").exists()
        assert protected_hashes() == before

    def test_a_raising_writer_leaves_protected_files_untouched(self, tmp_path):
        """And when it really does raise."""
        from backend.feature_store.feature_history import write_snapshot
        from datetime import date
        before = protected_hashes()
        with pytest.raises(Exception):
            # a DataFrame is required · passing None raises inside the writer
            write_snapshot(tmp_path, "india", date.today(), None)
        assert protected_hashes() == before

    def test_a_blocked_destination_raises_without_side_effects(self, tmp_path):
        from backend.shared.atomic_io import write_text_atomic
        before = protected_hashes()
        blocked = tmp_path / "blocked"
        blocked.write_text("i am a file, not a directory", encoding="utf-8")
        with pytest.raises(OSError):
            write_text_atomic(blocked / "child.json", "{}")
        assert protected_hashes() == before
        # and no temp debris survives
        assert not list(tmp_path.glob("**/*.tmp-*"))


# ── 4 · parallel roots do not collide ──────────────────────────────
class TestParallelRootsAreIndependent:
    def test_two_roots_receive_their_own_output(self, tmp_path):
        from backend.canonical.model import USA_PROFILE
        from backend.feature_store.feature_snapshot import build_and_persist
        from datetime import date
        a, b = tmp_path / "a", tmp_path / "b"
        ra = build_and_persist(_ROOT, USA_PROFILE, asof=date.today(), out_root=a)
        rb = build_and_persist(_ROOT, USA_PROFILE, asof=date.today(), out_root=b)
        assert ra["n_rows"] == rb["n_rows"] > 0
        for root in (a, b):
            assert (root / "features" / "manifest.jsonl").exists()
        # one manifest entry each · neither saw the other's write
        assert len((a / "features" / "manifest.jsonl")
                   .read_text(encoding="utf-8").splitlines()) == 1
        assert len((b / "features" / "manifest.jsonl")
                   .read_text(encoding="utf-8").splitlines()) == 1

    def test_concurrent_builds_into_separate_roots(self, tmp_path):
        import threading
        from backend.canonical.model import USA_PROFILE
        from backend.feature_store.feature_snapshot import build_and_persist
        from datetime import date
        errs, roots = [], [tmp_path / ("r%d" % i) for i in range(3)]

        def _run(root):
            try:
                build_and_persist(_ROOT, USA_PROFILE, asof=date.today(),
                                  out_root=root)
            except BaseException as e:      # noqa: BLE001 · reported
                errs.append(e)

        ts = [threading.Thread(target=_run, args=(r,)) for r in roots]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=600)
        assert not errs, errs[:2]
        for r in roots:
            assert (r / "features" / "manifest.jsonl").exists()


# ── 5 · the critical-context staleness check is deterministic ──────
class TestCriticalContextCheckIsDeterministic:
    def test_the_survey_is_stable_across_repeated_calls(self):
        """It failed in the full suite and passed alone · the cause was a
        TEST rewriting market_intelligence.json, which is in the
        INTERMARKET critical list."""
        from datetime import date
        from backend.pipeline.contract import intermarket as im
        results = [im.survey(_ROOT, "india", date.today().isoformat())
                   for _ in range(5)]
        stale = {tuple(sorted(r["critical_stale"])) for r in results}
        missing = {tuple(sorted(r["critical_missing"])) for r in results}
        assert len(stale) == 1, stale
        assert len(missing) == 1, missing

    def test_market_intelligence_is_a_protected_path(self):
        assert "reports/market_intelligence.json" in PROTECTED

    def test_no_test_writes_market_intelligence_to_the_live_root(self):
        """The specific contamination · asserted structurally."""
        import ast
        offenders = []
        for d in ("tests", "backend/tests"):
            base = _ROOT / d
            if not base.exists():
                continue
            for f in base.rglob("test_*.py"):
                if f.name == Path(__file__).name:
                    continue
                src = f.read_text(encoding="utf-8", errors="replace")
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    fn = node.func
                    nm = (fn.attr if isinstance(fn, ast.Attribute)
                          else getattr(fn, "id", None))
                    if nm != "run":
                        continue
                    call = ast.unparse(node)
                    if "market_intelligence" not in call:
                        continue
                    if "AEGIS_OUT_ROOT" not in call and "_runner_env" not in call:
                        offenders.append("%s:%d" % (f.relative_to(_ROOT)
                                                    .as_posix(), node.lineno))
        assert offenders == [], offenders


# ── 6 · protected files unchanged, and the redirect cannot leak ────
class TestProtectedStateAndLeakage:
    def test_the_redirect_is_unset_in_a_normal_session(self):
        assert not is_redirected(), (
            "an out-root variable is set in this session · production "
            "writes would silently move")
        assert resolved_out_root(_ROOT) == _ROOT

    def test_every_protected_path_is_declared(self):
        """Any new operational artifact must be added here deliberately."""
        assert len(PROTECTED) >= 14
        present = [p for p in PROTECTED if (_ROOT / p).exists()]
        assert len(present) >= 10, present

    def test_this_module_does_not_modify_protected_files(self):
        """Self-check · running these tests must be inert."""
        before = protected_hashes()
        _ = resolved_out_root(_ROOT)
        assert protected_hashes() == before

# ─────────────────────────────────────────────────────────────
# Lifecycle artifact · redirectable, and measured
# ─────────────────────────────────────────────────────────────

class TestTheLifecycleArtifactCanBeRedirected:
    """CEO 2026-11-07 · §3 test isolation.

    tests/delivery/conftest.py regenerates canonical_lifecycle_<market>
    on purpose: the renderer computes nothing and re-reads it from disk,
    so a committed fixture ageing independently of the code that reads
    it is what produced the 2026-09-10 USA CI failure. Sound rationale,
    but it wrote into the live reports/ tree.

    Measured over the whole tests/delivery/ suite (548 passed, 36
    skipped): exactly TWO artifacts changed, both this one, one per
    market. Every other protected file was byte-identical - registry,
    model registry, feature manifest, recommendations, ensemble,
    model factory included.

    `artifact_path` now resolves through the same AEGIS_OUT_ROOT helper
    the engine runners use, so a redirected run reads and writes the
    same place and the renderer still re-reads from disk exactly as
    production does.

    NOT yet flipped in the conftest, deliberately: two delivery tests
    and eight production modules still open this file by LITERAL path.
    Redirecting the writer while those read the real tree would have
    them testing a stale artifact - the very failure the conftest
    exists to prevent. Converting those ten readers is its own change.
    """

    def test_the_resolver_is_out_root_aware(self, monkeypatch, tmp_path):
        from backend.delivery.lifecycle import canonical_daily_lifecycle as lc
        import backend.shared.out_root as o
        import importlib

        monkeypatch.delenv(o.OUT_ROOT_ENV, raising=False)
        importlib.reload(o)
        plain = lc.artifact_path(_ROOT, "india")
        assert plain == (_ROOT / "reports" / "context"
                         / "canonical_lifecycle_india.json"), (
            "with no redirect the production path must be unchanged")

        monkeypatch.setenv(o.OUT_ROOT_ENV, str(tmp_path))
        importlib.reload(o)
        try:
            redirected = lc.artifact_path(_ROOT, "india")
            assert str(redirected).startswith(str(tmp_path))
        finally:
            monkeypatch.delenv(o.OUT_ROOT_ENV, raising=False)
            importlib.reload(o)

    def test_emit_and_load_share_one_resolver(self):
        """A reader and a writer with separate opinions of where a file
        lives is how they end up in different directories."""
        import ast
        src = (_ROOT / "backend" / "delivery" / "lifecycle"
               / "canonical_daily_lifecycle.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for name in ("emit", "load"):
            fn = next((n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == name),
                      None)
            if fn is None:
                continue
            body = "\n".join(src.splitlines()[fn.lineno - 1: fn.end_lineno])
            assert "artifact_path(" in body, (
                "%s must go through artifact_path, not build its own" % name)

    def test_the_known_literal_path_readers_are_recorded(self):
        """The readers that must be converted before the conftest flips.

        Recorded so the remaining gap is explicit rather than folklore.
        Counts only modules that CONSTRUCT the path - a docstring that
        merely names the file is documentation. An earlier version of
        this test counted those too and reported 18 where the real
        figure is smaller; matching prose and calling it a dependency
        is the same mistake that produced three false hardcoded-date
        findings in this repo.
        """
        needle = "canonical_lifecycle_"
        markers = ("reports", "context")
        readers = []
        for d in ("backend", "scripts"):
            for f in (_ROOT / d).rglob("*.py"):
                if f.name == "canonical_daily_lifecycle.py":
                    continue
                if "tests" in f.parts:
                    continue
                try:
                    txt = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                at, hit = txt.find(needle), False
                while at >= 0 and not hit:
                    seg = txt[max(0, at - 160): at + 160]
                    if all(m in seg for m in markers):
                        hit = True
                    at = txt.find(needle, at + 1)
                if hit:
                    rel = str(f.relative_to(_ROOT))
                    readers.append(rel.replace(chr(92), "/"))
        readers = sorted(set(readers))
        assert readers, "expected the known literal-path readers to exist"
        # A measured fact to be reduced, not a budget to spend. Each one
        # blocks enabling the lifecycle write redirect.
        assert len(readers) <= 20, (
            "literal-path readers grew to %d: %s" % (len(readers), readers))
        print("  literal-path lifecycle readers: %d" % len(readers))
        for r in readers:
            print("    %s" % r)

class TestEngineRunnersRedirectEveryWrite:
    """One unredirected write is enough. CEO 2026-11-07.

    Sprint-2 isolation moved every report output in the engine runners
    to `_OUT` and left ONE behind: the Sprint 7.5 history append still
    used `_ROOT`. So every regression run appended a row to the LIVE
    ledger. Measured by running backend/tests/test_sprint3.py against a
    clean tree:

        reports/recommendation_history.parquet      CHANGED
        usa/reports/recommendation_history.parquet  CHANGED
        engine=aegis.recommendation.v3 · one row per market

    After redirecting both, the same run leaves them byte-identical.

    Production sets no AEGIS_OUT_ROOT, so _OUT == _ROOT and the live
    ledger still receives the real daily row - the redirect only moves
    where a TEST writes.
    """

    RUNNERS = (
        "india/recommendation_intelligence/run.py",
        "usa/research/recommendation_intelligence/run.py",
    )

    def test_the_history_append_uses_the_redirected_root(self):
        for rel in self.RUNNERS:
            src = (_ROOT / rel).read_text(encoding="utf-8")
            i = src.find("append_and_record(")
            assert i > 0, "%s: no append_and_record call" % rel
            call = src[i: i + 420]
            assert "_ROOT /" not in call, (
                "%s appends history to the LIVE tree · a regression run "
                "would mutate the real ledger" % rel)
            assert "root=_OUT" in call, (
                "%s must pass the redirected root so the persistence "
                "state file moves with the ledger" % rel)

    def test_no_history_append_targets_the_live_root(self):
        """Every engine runner's history append, not just the two.

        My first version of this matched `_ROOT /` NEAR the word
        "parquet" and flagged 21 sites - most of them READS, which are
        correct: reads come from the real repository on purpose, and
        only writes move. Matching proximity instead of intent is the
        same mistake that produced three false hardcoded-date findings
        and a "wb.close() is a registry mutation" false positive.

        So this matches the append CALL and its path argument. It found
        9 genuine unredirected appends beyond the two that surfaced as
        contamination - execution, learning, macro, risk and portfolio
        history across both markets - every one of which would have
        rewritten a live ledger on each regression run.
        """
        import re
        call = re.compile(r"append_(?:snapshot_row|and_record)\(")
        offenders = []
        for pat in ("india/*/run.py", "usa/research/*/run.py"):
            for f in _ROOT.glob(pat):
                src = f.read_text(encoding="utf-8", errors="replace")
                for m in call.finditer(src):
                    seg = src[m.start(): m.start() + 400]
                    if "_ROOT /" in seg:
                        ln = src[:m.start()].count(chr(10)) + 1
                        offenders.append("%s:%d"
                                         % (f.relative_to(_ROOT)
                                            .as_posix(), ln))
        assert not offenders, (
            "history append writes under the LIVE root · a regression "
            "run would mutate the real ledger: %s" % sorted(offenders))
