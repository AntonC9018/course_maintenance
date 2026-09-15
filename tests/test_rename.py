"""Rename ordering regression coverage (seam: maintenance.rename).

Covers the acceptance criterion: rename ordering and lettered lab
appendices (16, 16a, 17 -> 16, 17, 18). All repos live in temp dirs.
"""

import tempfile
import unittest
from pathlib import Path

from maintenance.rename import (
    discover_rename_dirs,
    plan_renames,
    run_rename_on_dirs,
)
from tests.helpers import make_lab, tree_names


def filler_files(first: int, last: int) -> dict:
    return {
        f"{n:02d}_topic{n}.md": f"# {n}. Topic{n}\n"
        for n in range(first, last + 1)
    }


class TestRenameOrdering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gap_closing(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\n",
            "02_b.md": "# 2. B\n",
            "04_c.md": "# 4. C\n",
        })
        ops, errors = plan_renames(d)
        self.assertEqual(errors, [])
        self.assertEqual(
            [(s.name, t.name) for s, t in ops],
            [("04_c.md", "03_c.md")],
        )
        renamed, errors = run_rename_on_dirs([d], check_only=False, quiet=True)
        self.assertEqual(renamed, 1)
        self.assertEqual(errors, [])
        self.assertEqual(tree_names(d), ["01_a.md", "02_b.md", "03_c.md"])

    def test_lettered_appendix_takes_next_number(self):
        # Issue #6 acceptance example: 16, 16a, 17 -> 16, 17, 18.
        # Fillers 01..15 keep the sequence 01-based so the appendix
        # files sit at positions 16/17/18.
        files = filler_files(1, 15)
        files.update({
            "16_foo.md": "# 16. Foo\n",
            "16a_bar.md": "# 16. Bar\n",
            "17_baz.md": "# 17. Baz\n",
        })
        d = make_lab(self.root, "lab", files)
        ops, errors = plan_renames(d)
        self.assertEqual(errors, [])
        self.assertEqual(
            [(s.name, t.name) for s, t in ops],
            [("16a_bar.md", "17_bar.md"), ("17_baz.md", "18_baz.md")],
        )
        renamed, errors = run_rename_on_dirs([d], check_only=False, quiet=True)
        self.assertEqual(errors, [])
        self.assertEqual(renamed, 2)
        names = tree_names(d)
        self.assertIn("16_foo.md", names)
        self.assertIn("17_bar.md", names)
        self.assertIn("18_baz.md", names)
        self.assertNotIn("16a_bar.md", names)
        # Untouched prefix of the sequence keeps its names.
        for n in range(1, 16):
            self.assertIn(f"{n:02d}_topic{n}.md", names)

    def test_duplicate_numbers_abort_directory(self):
        d = make_lab(self.root, "lab", {
            "01_alpha.md": "# 1. Alpha\n",
            "01_beta.md": "# 1. Beta\n",
        })
        ops, errors = plan_renames(d)
        self.assertEqual(ops, [])
        self.assertTrue(errors, "expected duplicate-numbering errors")
        renamed, errors = run_rename_on_dirs([d], check_only=False, quiet=True)
        self.assertEqual(renamed, 0)
        self.assertTrue(errors)
        # Nothing moved.
        self.assertEqual(tree_names(d), ["01_alpha.md", "01_beta.md"])

    def test_non_markdown_assets_ignored(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\n",
            "03_b.md": "# 3. B\n",
        })
        assets = d / "images"
        assets.mkdir()
        (assets / "01_fig.png").write_bytes(b"\x89PNG")
        (assets / "02_fig.png").write_bytes(b"\x89PNG")
        # Asset dirs hold no *.md so they are never rename candidates.
        found = discover_rename_dirs([self.root])
        self.assertIn(d.resolve(), [p.resolve() for p in found])
        self.assertNotIn(assets.resolve(), [p.resolve() for p in found])
        run_rename_on_dirs([d], check_only=False, quiet=True)
        self.assertEqual(
            sorted(p.name for p in assets.iterdir()),
            ["01_fig.png", "02_fig.png"],
        )

    def test_check_mode_reports_without_writing(self):
        d = make_lab(self.root, "lab", {
            "01_a.md": "# 1. A\n",
            "03_b.md": "# 3. B\n",
        })
        renamed, errors = run_rename_on_dirs([d], check_only=True, quiet=True)
        self.assertEqual(errors, [])
        self.assertEqual(renamed, 1)
        self.assertEqual(tree_names(d), ["01_a.md", "03_b.md"])


if __name__ == "__main__":
    unittest.main()
