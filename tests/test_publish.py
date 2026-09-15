"""Dispatcher coverage (seam: publish.py command surface).

Issue #6 stubbed all four spec operations plus `ci`. Issue #7 implements
`publishing check` (read-only CFG-1..CFG-6 validation), issue #8
implements `metadata generate` plus META validation inside the check,
issue #10 implements `projection build`, and issue #11 implements
`site build`. The registry test proves follow-up tickets can add logic
without returning to a monolith.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, run_publish

PUBLISH_PY = REPO_ROOT / "publish.py"

REQUIRED_OPS: list = [
    # All four spec operations are implemented since #11 (`ci` stays
    # stubbed until #14).
]

# `projection build` is implemented since issue #10 (deterministic
# disposable projection).

# `publishing check` is implemented since issue #7 (read-only validation).
# `metadata generate` is implemented since issue #8 (explicit generation).

# `site build` is implemented since issue #11 (Starlight + dist/).


def load_publish_module():
    spec = importlib.util.spec_from_file_location("publish", PUBLISH_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPublishDispatcher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_required_operations_stubbed_with_clear_error(self):
        for responsibility, operation in REQUIRED_OPS:
            with self.subTest(f"{responsibility} {operation}"):
                proc = run_publish(
                    responsibility, operation,
                    "--course-repo", str(self.root),
                )
                self.assertNotEqual(
                    proc.returncode, 0,
                    f"{responsibility} {operation} must not exit 0 before #7-15",
                )
                combined = proc.stdout + proc.stderr
                self.assertIn("not yet implemented", combined.lower())

    def test_explicit_course_repo_missing_is_usage_error(self):
        missing = self.root / "does-not-exist"
        proc = run_publish(
            "metadata", "generate", "--course-repo", str(missing))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("course repo", (proc.stdout + proc.stderr).lower())

    def test_unknown_operation_is_usage_error(self):
        proc = run_publish("nope", "nothing", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 2)

    def test_no_args_is_usage_error(self):
        proc = run_publish()
        self.assertEqual(proc.returncode, 2)

    def test_registry_accepts_new_handlers_without_monolith_edits(self):
        publish = load_publish_module()
        calls = []

        def ping_handler(course_repo, args):
            calls.append(course_repo)
            return 42

        publish.register("test-seam", "ping", ping_handler, help_text="test")
        try:
            code = publish.dispatch(
                ["test-seam", "ping", "--course-repo", str(self.root)])
            self.assertEqual(code, 42)
            self.assertEqual(calls, [self.root.resolve()])
        finally:
            publish.unregister("test-seam", "ping")

    def test_ci_stub_present(self):
        proc = run_publish("ci", "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(
            "not yet implemented", (proc.stdout + proc.stderr).lower())

    def test_publishing_check_implemented_read_only(self):
        # Implemented in #7: missing config is a validation error (exit 1),
        # not "not yet implemented", and identifies the source path + rule.
        proc = run_publish(
            "publishing", "check", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 1)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("not yet implemented", combined.lower())
        self.assertIn("course-publishing.json", combined)
        self.assertIn("CFG", combined)

    def test_metadata_generate_implemented(self):
        # Implemented in #8: missing config is a validation error (exit 1),
        # not "not yet implemented".
        proc = run_publish(
            "metadata", "generate", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 1)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("not yet implemented", combined.lower())
        self.assertIn("course-publishing.json", combined)

    def test_projection_build_implemented(self):
        # Implemented in #10: missing config is a validation error (exit 1),
        # not "not yet implemented".
        proc = run_publish(
            "projection", "build", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 1)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("not yet implemented", combined.lower())
        self.assertIn("course-publishing.json", combined)

    def test_site_build_implemented(self):
        # Implemented in #11: missing config is a validation error (exit 1),
        # not "not yet implemented".
        proc = run_publish(
            "site", "build", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 1)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("not yet implemented", combined.lower())
        self.assertIn("course-publishing.json", combined)


if __name__ == "__main__":
    unittest.main()
