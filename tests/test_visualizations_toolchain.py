import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class VisualizationToolchainTest(unittest.TestCase):
    def test_manim_is_pinned_exactly(self):
        lines = [
            line.strip()
            for line in (ROOT / "visualizations" / "requirements.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        manim = [line for line in lines if line.lower().startswith("manim==")]
        self.assertEqual(manim, ["manim==0.22.0"])

    def test_system_packages_cover_latex_and_media(self):
        packages = {
            line.strip()
            for line in (ROOT / "visualizations" / "system-packages.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for package in ("texlive-latex-base", "texlive-latex-extra", "dvisvgm", "ffmpeg"):
            self.assertIn(package, packages)

    def test_core_does_not_import_manim(self):
        sources = [ROOT / "maintain.py", ROOT / "publish.py"]
        sources.extend(sorted((ROOT / "maintenance").glob("*.py")))
        sources.extend(sorted((ROOT / "publishing").glob("*.py")))
        pattern = re.compile(r"^\s*(?:from|import)\s+manim\b", re.MULTILINE)
        for source in sources:
            self.assertIsNone(
                pattern.search(source.read_text(encoding="utf-8")),
                f"{source.relative_to(ROOT)} must stay independent of Manim",
            )


if __name__ == "__main__":
    unittest.main()
