"""Heading resequencing regression coverage (seam: maintenance.headings)."""

import tempfile
import unittest
from pathlib import Path

from maintenance.headings import fix_headings_in_text, run_headings
from tests.helpers import write


class TestHeadings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_h1_follows_filename_prefix(self):
        new_text, h1_msgs, _, _ = fix_headings_in_text("# 7. Title\n", 3)
        self.assertEqual(new_text, "# 3. Title\n")
        self.assertEqual(h1_msgs, ["H1 : 7 -> 3"])

    def test_h3_resequenced(self):
        text = "### 5. A\n### 9. B\n### 2. C\n"
        new_text, _, h3_msgs, count = fix_headings_in_text(text, None)
        self.assertEqual(new_text, "### 1. A\n### 2. B\n### 3. C\n")
        self.assertEqual(count, 3)
        self.assertTrue(h3_msgs)

    def test_unnumbered_filename_leaves_h1_alone(self):
        text = "# 7. Title\n### 9. A\n"
        new_text, h1_msgs, _, _ = fix_headings_in_text(text, None)
        self.assertIn("# 7. Title", new_text)
        self.assertEqual(h1_msgs, [])
        # H3 resequencing still applies.
        self.assertIn("### 1. A", new_text)

    def test_run_headings_fixes_file(self):
        p = write(self.root / "03_topic.md", "# 7. Title\n### 9. A\n### 2. B\n")
        changed = run_headings([p], check_only=False, quiet=True)
        self.assertEqual(changed, 1)
        self.assertEqual(
            p.read_text(encoding="utf-8"),
            "# 3. Title\n### 1. A\n### 2. B\n",
        )

    def test_run_headings_check_mode_is_read_only(self):
        p = write(self.root / "03_topic.md", "# 7. Title\n")
        changed = run_headings([p], check_only=True, quiet=True)
        self.assertEqual(changed, 1)
        self.assertEqual(p.read_text(encoding="utf-8"), "# 7. Title\n")


if __name__ == "__main__":
    unittest.main()
