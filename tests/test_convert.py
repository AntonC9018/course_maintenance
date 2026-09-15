"""List-to-header conversion coverage (seam: maintenance.convert)."""

import tempfile
import unittest
from pathlib import Path

from maintenance.convert import convert_lists_to_headers, run_convert
from tests.helpers import write


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_conversion(self):
        self.assertEqual(
            convert_lists_to_headers("1. foo\n2. bar\n"),
            "### 1. foo\n### 2. bar\n",
        )

    def test_fenced_code_untouched(self):
        text = "```\n1. notalist\n```\n1. real\n"
        self.assertEqual(
            convert_lists_to_headers(text),
            "```\n1. notalist\n```\n### 1. real\n",
        )

    def test_run_convert_check_mode_is_read_only(self):
        p = write(self.root / "01_a.md", "1. foo\n")
        changed = run_convert([p], check_only=True, quiet=True)
        self.assertEqual(changed, 1)
        self.assertEqual(p.read_text(encoding="utf-8"), "1. foo\n")


if __name__ == "__main__":
    unittest.main()
