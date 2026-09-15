"""Link repair regression coverage (seam: maintenance.links)."""

import tempfile
import unittest
from pathlib import Path

from maintenance.links import LinkFixer
from tests.helpers import make_lab


class TestLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_move_repair_same_dir(self):
        # Stale number, same topic rest: 01_beta.md -> 02_beta.md.
        d = make_lab(self.root, "lab", {
            "01_alpha.md": "see [B](01_beta.md)\n",
            "02_beta.md": "# 2. Beta\n",
        })
        fixer = LinkFixer(self.root)
        fixed, broken = fixer.process_file(d / "01_alpha.md", check_only=False)
        self.assertEqual(broken, [])
        self.assertEqual(fixed, 1)
        self.assertIn("(02_beta.md)", (d / "01_alpha.md").read_text(encoding="utf-8"))

    def test_anchor_repair_after_resequence(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "see [part](02_b.md#9-install)\n",
            "02_b.md": "### 2. Install\n",
        })
        fixer = LinkFixer(self.root)
        fixed, broken = fixer.process_file(d / "01_a.md", check_only=False)
        self.assertEqual(broken, [])
        self.assertEqual(fixed, 1)
        self.assertIn(
            "(02_b.md#2-install)",
            (d / "01_a.md").read_text(encoding="utf-8"),
        )

    def test_external_and_code_spans_skipped(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": (
                "see [ext](https://example.com/x.md)\n"
                "see `[code](missing.md)`\n"
                "```\n[block](missing.md)\n```\n"
            ),
        })
        fixer = LinkFixer(self.root)
        fixed, broken = fixer.process_file(d / "01_a.md", check_only=False)
        self.assertEqual(fixed, 0)
        self.assertEqual(broken, [])

    def test_broken_target_reported(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "see [gone](nope_missing.md)\n",
        })
        fixer = LinkFixer(self.root)
        fixed, broken = fixer.process_file(d / "01_a.md", check_only=True)
        self.assertEqual(fixed, 0)
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0][1], "nope_missing.md")


if __name__ == "__main__":
    unittest.main()
