"""Shared CI entry point (issue #14, CI-1..CI-12 shared side).

TDD seam: publishing.ci stage functions (maintain check, publishing
check, compatibility suite, site build) are individually mockable.
All repos live in TemporaryDirectory; never mutates live checkouts.
Stdlib-only; npm/Playwright/Chromium mocked where offline.

Covers:
- ordering: maintain check -> publishing check -> compat suite ->
  complete site build, fail-fast with actionable stage errors;
- read-only wrt course sources; reliable exit codes (0 ok, 1 dirty/
  build failure, 2 usage);
- cache keys: different lockfile/browser versions give different keys;
- caller-workflow contract fixture + shared workflow (pinned actions,
  lockfile-keyed caches, submodule use, no floating reusable workflow).
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import REPO_ROOT, run_publish, write


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True)


def init_repo_with_origin(root: Path, origin_url="https://github.com/O/R.git"):
    root.mkdir(parents=True, exist_ok=True)
    r = git("init", "-b", "master", cwd=root)
    assert r.returncode == 0, r.stderr
    git("config", "user.email", "t@t.t", cwd=root)
    git("config", "user.name", "t", cwd=root)
    write(root / "placeholder.txt", "x\n")
    git("add", "-A", cwd=root)
    git("commit", "-m", "init", cwd=root)
    if origin_url is not None:
        r = git("remote", "add", "origin", origin_url, cwd=root)
        assert r.returncode == 0, r.stderr
    return root


MIN_CONFIG = {
    "version": 1,
    "default_language": "en",
    "languages": [
        {"code": "en", "root": "en", "label": "English"},
        {"code": "ru", "root": "ru", "label": "Русский"},
    ],
    "exclude": [],
    "route_sections": [
        {"source": "labs/common", "destination": "common/labs"},
    ],
    "site_title": {"en": "EN Title", "ru": "RU Title"},
    "root_lesson": "en/labs/common/01_computer_architecture.md",
    "peer_repositories": [],
}


def write_config(root: Path, cfg=None):
    cfg = MIN_CONFIG if cfg is None else cfg
    write(root / "course-publishing.json",
          json.dumps(cfg, ensure_ascii=False, indent=2))


def make_min_repo(root: Path):
    """Minimal valid course repo (passes maintain + publishing checks)."""
    init_repo_with_origin(root)
    write_config(root)
    write(root / "en/labs/common/01_computer_architecture.md",
          "---\ntitle: Arch\n---\n# Arch\n\nBody.\n")
    write(root / "ru/labs/common/01_computer_architecture.md",
          "---\ntitle: Арх\n---\n# Арх\n")
    from tests.helpers import run_publish as _run
    gen = _run("metadata", "generate", "--course-repo", str(root))
    assert gen.returncode == 0, gen.stdout + gen.stderr
    check = _run("publishing", "check", "--course-repo", str(root))
    assert check.returncode == 0, check.stdout + check.stderr
    return root


def snapshot(root: Path):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in Path(dirpath).parts:
            continue
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                out[str(p.resolve())] = p.read_bytes()
            except OSError:
                pass
    return out


class TestCacheKeys(unittest.TestCase):
    def test_npm_cache_key_changes_with_lockfile(self):
        from publishing.ci import npm_cache_key
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.lock"
            b = Path(td) / "b.lock"
            a.write_text('{"a": 1}\n', encoding="utf-8")
            b.write_text('{"a": 2}\n', encoding="utf-8")
            self.assertNotEqual(npm_cache_key(a), npm_cache_key(b))

    def test_npm_cache_key_stable_same_content(self):
        from publishing.ci import npm_cache_key
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.lock"
            a.write_text('{"a": 1}\n', encoding="utf-8")
            self.assertEqual(npm_cache_key(a), npm_cache_key(a))

    def test_npm_cache_key_includes_node_and_lock_hash(self):
        from publishing.ci import PINNED_NODE, npm_cache_key
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "package-lock.json"
            lock.write_text('{"x": 1}\n', encoding="utf-8")
            key = npm_cache_key(lock)
            self.assertIn(PINNED_NODE, key)
            # hash fragment present (not just the constant prefix).
            self.assertGreater(len(key), len(PINNED_NODE) + 8)

    def test_npm_cache_key_default_uses_committed_lockfile(self):
        from publishing.ci import lockfile_path, npm_cache_key
        self.assertTrue(lockfile_path().is_file())
        key = npm_cache_key()
        self.assertIn("node", key.lower())

    def test_browser_cache_key_changes_with_versions(self):
        from publishing.ci import browser_cache_key
        k1 = browser_cache_key("1.48.2", "130.0.6723.19")
        k2 = browser_cache_key("1.49.0", "130.0.6723.19")
        k3 = browser_cache_key("1.48.2", "131.0.0.0")
        self.assertNotEqual(k1, k2)
        self.assertNotEqual(k1, k3)

    def test_browser_cache_key_defaults_to_pinned(self):
        from publishing.ci import (
            PINNED_BROWSERS,
            PINNED_VERSIONS,
            browser_cache_key,
        )
        key = browser_cache_key()
        self.assertIn(PINNED_VERSIONS["playwright"], key)
        self.assertIn(PINNED_BROWSERS["chromium"], key)


class TestCiOrdering(unittest.TestCase):
    def _patch_all(self, m_maint=0, m_pub=0, m_compat=0, m_site=0):
        calls = []
        p1 = mock.patch("publishing.ci.run_maintain_check",
                        side_effect=lambda repo: (calls.append("maintain"), m_maint)[1])
        p2 = mock.patch("publishing.ci.run_publishing_check_stage",
                        side_effect=lambda repo: (calls.append("publishing"), m_pub)[1])
        p3 = mock.patch("publishing.ci.run_compat_suite",
                        side_effect=lambda: (calls.append("compat"), m_compat)[1])
        p4 = mock.patch("publishing.ci.run_site_build_stage",
                        side_effect=lambda repo, out: (calls.append("site"), m_site)[1])
        return calls, p1, p2, p3, p4

    def test_runs_stages_in_order(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all()
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["maintain", "publishing", "compat", "site"])

    def test_fails_fast_on_maintain(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_maint=1)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["maintain"])

    def test_fails_on_publishing_without_running_later(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_pub=1)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["maintain", "publishing"])

    def test_fails_on_compat_without_site(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_compat=1)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["maintain", "publishing", "compat"])

    def test_fails_on_site(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_site=1)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 1)
        self.assertEqual(calls, ["maintain", "publishing", "compat", "site"])

    def test_usage_error_propagates(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_site=2)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 2)

    def test_actionable_failure_mentions_stage(self):
        from publishing.ci import run_ci
        calls, p1, p2, p3, p4 = self._patch_all(m_pub=1)
        with p1, p2, p3, p4:
            with tempfile.TemporaryDirectory() as td:
                import io
                err = io.StringIO()
                with mock.patch("sys.stderr", err):
                    code = run_ci(Path(td), mock.Mock(out=None))
        self.assertEqual(code, 1)
        self.assertIn("publishing", err.getvalue().lower())


class TestCiExitCodes(unittest.TestCase):
    def test_missing_config_returns_1_not_stub(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            init_repo_with_origin(root)
            proc = run_publish("ci", "--course-repo", str(root))
            self.assertEqual(proc.returncode, 1)
            combined = proc.stdout + proc.stderr
            self.assertNotIn("not yet implemented", combined.lower())
            self.assertIn("course-publishing.json", combined)

    def test_bad_course_repo_is_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist"
            proc = run_publish("ci", "--course-repo", str(missing))
            self.assertEqual(proc.returncode, 2)

    def test_out_inside_repo_is_usage_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            make_min_repo(root)
            inside = root / "dist-out"
            # Early --out validation fails fast (exit 2) without running
            # expensive stages, so subprocess is fast here.
            proc = run_publish("ci", "--course-repo", str(root),
                               "--out", str(inside))
            # --out inside sources is rejected like site build (exit 2).
            self.assertEqual(proc.returncode, 2)
            self.assertIn("outside", (proc.stdout + proc.stderr).lower())


class TestCiReadOnly(unittest.TestCase):
    def test_ci_does_not_modify_sources(self):
        import argparse
        from publishing.ci import run_ci
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            make_min_repo(root)
            out = Path(td) / "ci-out"
            before = snapshot(root)
            status_before = git("status", "--porcelain", cwd=root).stdout
            # In-process so mocks apply (subprocess cannot be mocked and
            # would run the real 57s compat suite + npm build).
            with mock.patch("publishing.ci.run_compat_suite",
                            return_value=0):
                with mock.patch("publishing.site.run_npm_build",
                                return_value=(0, "mock build")):
                    code = run_ci(root, argparse.Namespace(out=str(out)))
            self.assertEqual(code, 0)
            self.assertEqual(snapshot(root), before)
            self.assertEqual(git("status", "--porcelain", cwd=root).stdout,
                             status_before)
            # Site output went outside the repo, never into sources.
            self.assertTrue(out.is_dir())
            self.assertFalse((root / "dist").exists()
                             and (root / "dist" != out))

    def test_ci_failing_maintain_leaves_sources_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            init_repo_with_origin(root)
            write_config(root)
            # Dirty maintenance state: numbering gap 01_, 03_.
            write(root / "en/labs/common/01_computer_architecture.md",
                  "---\ntitle: A\n---\n# A\n")
            write(root / "en/labs/common/03_gap.md",
                  "---\ntitle: B\n---\n# B\n")
            write(root / "ru/labs/common/01_computer_architecture.md",
                  "---\ntitle: R\n---\n# R\n")
            before = snapshot(root)
            # Fails fast at maintain check (before compat/site), so
            # subprocess stays fast without mocks.
            proc = run_publish("ci", "--course-repo", str(root))
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(snapshot(root), before)


class TestCiOrchestrationIntegration(unittest.TestCase):
    def test_full_pipeline_ok_with_mocked_toolchain(self):
        import argparse
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from publishing.ci import run_ci
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            make_min_repo(root)
            out = Path(td) / "site-out"
            # In-process so mocks apply (subprocess would run the real
            # 57s compat suite + npm build).
            with mock.patch("publishing.ci.run_compat_suite",
                            return_value=0) as m_compat:
                with mock.patch("publishing.site.run_npm_build",
                                return_value=(0, "mock build")):
                    buf_out, buf_err = io.StringIO(), io.StringIO()
                    with redirect_stdout(buf_out), redirect_stderr(buf_err):
                        code = run_ci(root,
                                      argparse.Namespace(out=str(out)))
            self.assertEqual(code, 0)
            m_compat.assert_called_once()
            combined = buf_out.getvalue() + buf_err.getvalue()
            for stage in ("maintain", "publishing", "compat", "site"):
                self.assertIn(stage, combined.lower())
            self.assertTrue((out / "dist").is_dir())

    def test_compat_failure_reports_actionable_error(self):
        import argparse
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from publishing.ci import run_ci
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "course"
            make_min_repo(root)
            out = Path(td) / "site-out"
            with mock.patch("publishing.ci.run_compat_suite",
                            return_value=1):
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    code = run_ci(root, argparse.Namespace(out=str(out)))
            self.assertEqual(code, 1)
            combined = (buf_out.getvalue() + buf_err.getvalue()).lower()
            self.assertIn("compat", combined)
            self.assertIn("operation: ci", combined)


class TestCallerContract(unittest.TestCase):
    def test_fixture_workflow_exists_and_invokes_shared_command(self):
        fixture = REPO_ROOT / "docs" / "ci-caller-workflow.yml"
        self.assertTrue(fixture.is_file(),
                        "missing docs/ci-caller-workflow.yml fixture")
        text = fixture.read_text(encoding="utf-8")
        low = text.lower()
        self.assertIn("course_maintenance/publish.py ci --course-repo", text)
        self.assertIn("submodules", low)
        self.assertIn("recursive", low)
        # No floating reusable-workflow revision independent of submodule.
        self.assertNotIn("workflow_call", low)
        # Pinned actions (immutable SHAs with version comments).
        import re
        pins = re.findall(r"uses:\s*\S+@([0-9a-f]{40})", text)
        self.assertGreaterEqual(len(pins), 2,
                                "caller fixture must pin actions to SHAs")
        # Read-only PR permissions by default.
        self.assertIn("contents: read", text)
        # Concurrency + no path filters (CI-5/CI-10 shared contract).
        self.assertIn("concurrency", low)
        self.assertNotIn("paths:", text)

    def test_contract_doc_exists_for_rollout_and_reuse(self):
        doc = REPO_ROOT / "docs" / "ci-caller-contract.md"
        self.assertTrue(doc.is_file(),
                        "missing docs/ci-caller-contract.md")
        text = doc.read_text(encoding="utf-8")
        low = text.lower()
        for token in ("publish.py ci", "submodule", "pinned",
                      "cache", "#15", "c#"):
            self.assertIn(token.lower(), low,
                          f"contract doc must mention {token}")

    def test_shared_workflow_exists_pinned_and_cached(self):
        wf = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(wf.is_file(),
                        "missing .github/workflows/ci.yml")
        text = wf.read_text(encoding="utf-8")
        low = text.lower()
        import re
        pins = re.findall(r"uses:\s*\S+@([0-9a-f]{40})", text)
        self.assertGreaterEqual(len(pins), 2,
                                "shared CI must pin actions to SHAs")
        # Caches keyed by lockfile/browser versions (CI-8).
        self.assertIn("package-lock.json", text)
        self.assertTrue("hashfiles" in low or "hash-files" in low
                        or "cache-dependency-path" in low)
        self.assertIn("playwright", low)
        # Runs the isolated unit suite; no path filters.
        self.assertIn("unittest", text)
        self.assertNotIn("paths:", text)
        # Concurrency + read-only permissions.
        self.assertIn("concurrency", low)
        self.assertIn("contents: read", text)

    def test_usable_from_submodule_paths(self):
        from publishing.ci import lockfile_path, maintenance_root
        root = maintenance_root()
        self.assertTrue((root / "publish.py").is_file())
        self.assertTrue((root / "renderer" / "package-lock.json").is_file())
        self.assertEqual(lockfile_path(), root / "renderer" / "package-lock.json")
        # Renderer pins resolve from the submodule checkout, not cwd.
        with tempfile.TemporaryDirectory() as td:
            old = Path.cwd()
            os.chdir(td)
            try:
                from publishing.ci import lockfile_path as _lf
                self.assertTrue(_lf().is_file())
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
