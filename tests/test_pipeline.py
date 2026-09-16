"""Pipeline integration coverage via temp-dir harness (seam: pipeline/CLI).

Builds throwaway course repos in TemporaryDirectory, drives maintain.py
as a subprocess, and asserts observable behavior + exit codes. Never
touches fixtures or live checkouts.
"""

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_lab, run_maintain, tree_names


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_dirty_then_clean_then_stable(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\n",
            "03_b.md": "# 9. B\n",
        })
        dirty = run_maintain("--check", str(d))
        self.assertEqual(dirty.returncode, 1, dirty.stdout + dirty.stderr)
        # check mode writes nothing
        self.assertEqual(tree_names(d), ["01_a.md", "03_b.md"])

        applied = run_maintain(str(d))
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertEqual(tree_names(d), ["01_a.md", "02_b.md"])
        self.assertIn("# 2. B", (d / "02_b.md").read_text(encoding="utf-8"))

        again = run_maintain("--check", str(d))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_file_arg_never_triggers_renames(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\n",
            "03_b.md": "# 9. B\n",
        })
        target = d / "03_b.md"
        proc = run_maintain(str(target))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Gap untouched, but the file's own headings are fixed.
        self.assertEqual(tree_names(d), ["01_a.md", "03_b.md"])
        self.assertIn("# 3. B", target.read_text(encoding="utf-8"))

    def test_pipeline_order_rename_then_headings_then_links(self):
        # 03_b.md will become 02_b.md; 01_a.md links at the stale name
        # and stale anchor. One run must fix the move and the anchor,
        # which proves the link index sees post-rename/post-heading state.
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\nsee [B](03_b.md#9-install)\n",
            "03_b.md": "# 9. B\n### 9. Install\n",
        })
        # --root points at the temp repo so move lookup searches it
        # (default '.' would index the caller's cwd instead).
        proc = run_maintain(str(d), "--root", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(tree_names(d), ["01_a.md", "02_b.md"])
        body = (d / "01_a.md").read_text(encoding="utf-8")
        self.assertIn("(02_b.md#1-install)", body)
        stable = run_maintain("--check", str(d), "--root", str(self.root))
        self.assertEqual(stable.returncode, 0, stable.stdout + stable.stderr)


if __name__ == "__main__":
    unittest.main()
