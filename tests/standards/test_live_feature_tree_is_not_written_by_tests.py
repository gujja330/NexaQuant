"""The test suite must not write into the live feature tree.

CEO 2026-11-04.

WHAT HAPPENED
-------------
Three tests in backend/tests/test_sprint25.py used the live repository
as the feature-store OUTPUT root:

    test_build_and_persist_writes_parquet_and_manifest
        build_and_persist(_ROOT, USA_PROFILE, asof=date.today())
    test_india_feature_store_runner_emits_valid_json
    test_usa_feature_store_runner_emits_valid_json
        subprocess.run([...], cwd=str(_ROOT))

So every regression run built real snapshots for the current date and
appended to the TRACKED `features/manifest.jsonl`. Measured on
2026-11-04 after four regression runs: 6 India and 12 USA snapshot
files dated that day, and the manifest grown from 300 to 306 lines.

A suite that mutates the production data it exists to validate cannot
be trusted to validate it. The ledger acquires entries no pipeline run
ever made, and a snapshot appears for a date nothing ever scored - and
under the snapshot-authority contract a canonical file left behind by a
test would then OUTRANK the day's real build.

WHAT THIS FILE DOES
-------------------
Two independent guards:

  1. a STATIC check that no test hands a production path to a
     feature-store writer, or to a subprocess that is one; and
  2. a DYNAMIC check that hashes the live `features/` tree, exercises
     the writer, and proves the tree is byte-identical afterwards.

The static guard catches the pattern coming back by edit. The dynamic
one catches a path the static guard cannot see.
"""
from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FEATURES = _ROOT / "features"

#: Callables that write into a feature-store root.
_WRITERS = {"build_and_persist", "write_snapshot", "append_manifest",
            "promote_candidate"}

#: Identifiers that denote the live repository root in the test suites.
_LIVE_ROOT_NAMES = {"_ROOT", "ROOT", "REPO_ROOT", "_LIVE"}


def _tree_digest(root: Path) -> tuple:
    """(file count, digest) over every parquet/jsonl under features/."""
    if not root.exists():
        return 0, "absent"
    h = hashlib.sha256()
    n = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        h.update(p.relative_to(root).as_posix().encode())
        h.update(str(p.stat().st_size).encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())
        n += 1
    return n, h.hexdigest()


class TestNoTestHandsALiveRootToAWriter:
    """Static · AST, so a comment explaining the rule cannot trip it."""

    @staticmethod
    def _test_files() -> list[Path]:
        out: list[Path] = []
        for d in ("tests", "backend/tests"):
            base = _ROOT / d
            if base.exists():
                out.extend(p for p in base.rglob("test_*.py"))
        return out

    def test_no_writer_is_called_with_the_live_repository_root(self):
        offenders: list[str] = []
        for f in self._test_files():
            if f.name == Path(__file__).name:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else getattr(fn, "id", None))
                if name not in _WRITERS:
                    continue
                # Which argument decides where the WRITE lands?
                #
                # `build_and_persist(repo_root, ..., out_root=X)` reads
                # from repo_root and writes to X, so passing the live
                # root as the first argument is correct and necessary -
                # those tests exist to read the real substrate. Only the
                # effective write root matters. Checking the positional
                # root unconditionally flagged exactly those legitimate
                # calls.
                override = next((k.value for k in node.keywords
                                 if k.arg == "out_root"), None)
                write_root = override if override is not None else (
                    node.args[0] if node.args else None)
                if (isinstance(write_root, ast.Name)
                        and write_root.id in _LIVE_ROOT_NAMES):
                    offenders.append(
                        "%s:%d %s writes to %s"
                        % (f.relative_to(_ROOT).as_posix(), node.lineno,
                           name, write_root.id))
        assert offenders == [], (
            "a test passes the live repository root to a feature-store "
            "writer:\n  " + "\n  ".join(offenders))

    def test_no_subprocess_runs_a_feature_store_runner_without_redirection(self):
        """`cwd=_ROOT` is fine only if AEGIS_FEATURE_OUT_ROOT is set."""
        offenders: list[str] = []
        for f in self._test_files():
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
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else getattr(fn, "id", None))
                if name != "run":
                    continue
                call = ast.unparse(node)
                if "feature_store" not in call:
                    continue
                if "AEGIS_FEATURE_OUT_ROOT" not in call:
                    offenders.append("%s:%d" % (f.relative_to(_ROOT).as_posix(),
                                                node.lineno))
        assert offenders == [], (
            "a test runs a feature-store script as a subprocess without "
            "redirecting its output root:\n  " + "\n  ".join(offenders))


class TestTheLiveTreeSurvivesTheWriter:
    """Dynamic · exercise the writer and prove nothing moved."""

    def test_build_and_persist_with_out_root_leaves_features_untouched(self,
                                                                       tmp_path):
        from backend.canonical.model import USA_PROFILE
        from backend.feature_store.feature_snapshot import build_and_persist

        before = _tree_digest(_FEATURES)
        summary = build_and_persist(_ROOT, USA_PROFILE, asof=date.today(),
                                     out_root=tmp_path)
        after = _tree_digest(_FEATURES)
        assert summary.get("n_rows", 0) > 0, "the build produced nothing"
        assert (tmp_path / "features").exists(), "nothing written to tmp_path"
        assert before == after, (
            "the live features/ tree changed: %s files -> %s files"
            % (before[0], after[0]))

    def test_the_env_var_alone_redirects_a_subprocess(self, tmp_path):
        """Proves the mechanism the runner tests rely on."""
        (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
        before = _tree_digest(_FEATURES)
        code = ("import sys; sys.path.insert(0, %r);"
                "from pathlib import Path;"
                "from backend.canonical.model import INDIA_PROFILE;"
                "from backend.feature_store.feature_snapshot import "
                "build_and_persist, resolved_out_root;"
                "print(resolved_out_root(Path(%r)))"
                % (str(_ROOT), str(_ROOT)))
        r = subprocess.run(
            [sys.executable, "-c", code], cwd=str(_ROOT),
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ, AEGIS_FEATURE_OUT_ROOT=str(tmp_path)))
        assert r.returncode == 0, r.stderr[:400]
        assert str(tmp_path) in r.stdout, (
            "resolved_out_root ignored the env var: %r" % r.stdout)
        assert _tree_digest(_FEATURES) == before

    def test_production_without_the_env_var_still_targets_the_repo_root(self):
        """The redirect must not leak into production behaviour."""
        from backend.feature_store.feature_snapshot import resolved_out_root
        assert os.environ.get("AEGIS_FEATURE_OUT_ROOT") is None, (
            "the env var is set in this session · production would "
            "silently write elsewhere")
        assert resolved_out_root(_ROOT) == _ROOT
