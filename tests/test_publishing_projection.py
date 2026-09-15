"""Deterministic Markdown web projections (issue #10, PROJ-1..PROJ-6).

TDD seam: publishing.projection + `projection build` handler.
All repos live in TemporaryDirectory; never mutates live checkouts.
Stdlib-only. Outputs always below --out (or auto temp outside source).
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_publish, write


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True)


def init_repo_with_origin(root: Path, origin_url="git@github.com:O/R.git"):
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


BASE_CONFIG = {
    "version": 1,
    "default_language": "en",
    "languages": [
        {"code": "en", "root": "en", "label": "English"},
        {"code": "ru", "root": "ru", "label": "Russian"},
    ],
    "exclude": [],
    "route_sections": [
        {"source": "00_introduction", "destination": "common"},
        {"source": "labs/common", "destination": "common/labs"},
    ],
    "site_title": {"en": "EN", "ru": "RU"},
    "root_lesson": "en/labs/common/01_computer_architecture.md",
    "peer_repositories": [],
}


def write_config(root: Path, cfg=None):
    cfg = BASE_CONFIG if cfg is None else cfg
    write(root / "course-publishing.json",
          json.dumps(cfg, ensure_ascii=False, indent=2))
    return root / "course-publishing.json"


def make_repo(root: Path, files: dict, cfg=None,
              origin="https://github.com/O/R.git"):
    init_repo_with_origin(root, origin)
    write_config(root, BASE_CONFIG if cfg is None else cfg)
    for rel, content in files.items():
        p = root / rel
        if isinstance(content, bytes):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        else:
            write(p, content)
    gen = run_publish("metadata", "generate", "--course-repo", str(root))
    assert gen.returncode == 0, gen.stdout + gen.stderr
    check = run_publish("publishing", "check", "--course-repo", str(root))
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


def snapshot_tree(out_dir: Path):
    """Map output-rel-posix -> bytes for all files below out_dir, sorted."""
    result = {}
    for dirpath, _dns, fns in os.walk(out_dir):
        for fn in fns:
            p = Path(dirpath) / fn
            rel = p.relative_to(out_dir).as_posix()
            result[rel] = p.read_bytes()
    return dict(sorted(result.items()))


def run_projection(root: Path, out: Path | None = None, extra=None):
    args = ["projection", "build", "--course-repo", str(root)]
    if out is not None:
        args += ["--out", str(out)]
    if extra:
        args += extra
    return run_publish(*args)


def read_projected(out: Path, slug: str) -> str:
    p = out / "src" / "content" / "docs" / (slug + ".md")
    assert p.is_file(), f"missing projected file for {slug}: {p}"
    return p.read_text(encoding="utf-8")


class TestBacklinkStripping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                "---\ntitle: Arch\n---\n# Arch\n\nBody.\n"),
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        self.out = Path(self.tmp.name) / "out1"

    def tearDown(self):
        self.tmp.cleanup()

    def test_proj1_backlink_removed_from_projection(self):
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertNotIn("course-site-backlink", text)
        self.assertNotIn("This lesson on the website", text)
        # source still has it
        src = (self.root / "en/labs/common/01_computer_architecture.md"
               ).read_text(encoding="utf-8")
        self.assertIn("course-site-backlink:start", src)

    def test_proj1_fenced_backlink_markers_preserved(self):
        # markers inside fenced code are not backlinks; stripping must not
        # remove fenced content, but the real backlink still goes.
        src_path = self.root / "en/labs/common/01_computer_architecture.md"
        orig = src_path.read_text(encoding="utf-8")
        # insert fenced block containing marker-like text after backlink
        marker_demo = ("\n```\n<!-- course-site-backlink:start -->\n"
                       "not a backlink\n```\n")
        # place after body: need to keep backlink valid (immediately after fm)
        # so append fenced demo at end.
        src_path.write_text(orig + marker_demo, encoding="utf-8")
        # re-validate: publishing check should still pass (fenced markers
        # are ignored by metadata validation).
        check = run_publish("publishing", "check",
                            "--course-repo", str(self.root))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        # fenced marker text survives (PROJ-4), real backlink link is gone
        self.assertIn("not a backlink", text)
        self.assertNotIn("This lesson on the website", text)


class TestHeadingShift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def _project_body(self, source_body: str, title="T") -> str:
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                f"---\ntitle: {title}\n---\n{source_body}"),
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        full = read_projected(self.out, "en/common/labs/computer-architecture")
        # split off frontmatter
        lines = full.splitlines()
        self.assertEqual(lines[0].strip(), "---")
        end = next(i for i in range(1, len(lines))
                   if lines[i].strip() == "---")
        return "\n".join(lines[end + 1:])

    def test_proj2_matching_h1_shifted_no_duplicate_h1(self):
        body = self._project_body("# T\n\n## Sub\n", title="T")
        self.assertNotIn("\n# T", "\n" + body)
        self.assertIn("## T", body)
        self.assertIn("### Sub", body)
        # no H1 remains in projected body
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "),
                             f"duplicate H1 left: {line!r}")

    def test_proj2_differing_h1_shifted(self):
        body = self._project_body("# Other\n\nText\n", title="T")
        self.assertIn("## Other", body)
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_proj2_absent_h1_shifts_rest(self):
        body = self._project_body("Intro\n\n## Sec\n\n### Deep\n",
                                  title="T")
        self.assertIn("### Sec", body)
        self.assertIn("#### Deep", body)

    def test_proj2_repeated_h1_all_shifted(self):
        body = self._project_body("# A\n\n# B\n\n## C\n", title="T")
        self.assertIn("## A", body)
        self.assertIn("## B", body)
        self.assertIn("### C", body)
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_proj2_frontmatter_title_kept_as_sole_h1(self):
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                "---\ntitle: Kept Title\n---\n# Other\n"),
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        full = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("title: Kept Title", full)
        # sole H1 is frontmatter title (no '# ' headings in body)
        lines = full.splitlines()
        end = next(i for i in range(1, len(lines))
                   if lines[i].strip() == "---")
        body = "\n".join(lines[end + 1:])
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_proj2_fenced_headings_untouched(self):
        body = self._project_body("# Real\n\n```\n# Not heading\n```\n",
                                  title="T")
        self.assertIn("## Real", body)
        self.assertIn("# Not heading", body)


class TestMathConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def _project(self, source_body: str):
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                f"---\ntitle: T\n---\n{source_body}"),
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        return run_projection(self.root, self.out)

    def test_proj3_inline_converted_deterministically(self):
        proc = self._project("See $`x^2`$ here.\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("$x^2$", text)
        self.assertNotIn("$`x^2`$", text)
        # source unchanged
        src = (self.root / "en/labs/common/01_computer_architecture.md"
               ).read_text(encoding="utf-8")
        self.assertIn("$`x^2`$", src)

    def test_proj3_display_blocks_survive(self):
        proc = self._project("$$\nx^2\n$$\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("$$", text)
        self.assertIn("x^2", text)

    def test_proj3_fenced_math_untouched(self):
        proc = self._project("```\n$`x`$\n$$\ny\n$$\n```\n")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("$`x`$", text)

    def test_proj3_ambiguous_inline_rejected(self):
        proc = self._project("See $`$ here.\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PROJ-3", proc.stdout + proc.stderr)

    def test_proj3_ambiguous_unclosed_display_rejected(self):
        proc = self._project("$$\nunclosed\n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PROJ-3", proc.stdout + proc.stderr)

    def test_proj3_unit_convert_and_reject(self):
        from publishing.projection import (
            convert_math_body, ProjectionError)
        new_lines, errors = convert_math_body(["See $`a+b`$ ok\n"])
        self.assertEqual(errors, [])
        self.assertIn("$a+b$", "".join(new_lines))
        _n2, errors2 = convert_math_body(["Bad $`$ here\n"])
        self.assertTrue(errors2)
        self.assertIn("PROJ-3", errors2[0])
        _n3, errors3 = convert_math_body(["$$\nopen\n"])
        self.assertTrue(errors3)


class TestPreservation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_proj4_fenced_tables_details_cpp_survive(self):
        body = (
            "# Title\n\n"
            "```cpp\nif (a < b && c > d) { return; }\n```\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "<details>\n<summary>S</summary>\n\n"
            "<details>\n<summary>Inner</summary>\nText\n</details>\n\n"
            "</details>\n\n"
            "Use `a < b` spans.\n")
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                f"---\ntitle: T\n---\n{body}"),
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("if (a < b && c > d)", text)
        self.assertIn("| a | b |", text)
        self.assertIn("<details>", text)
        self.assertIn("`a < b`", text)

    def test_proj4_empty_and_outline_survive(self):
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: T\n---\n",
            "en/guide/01_outline.md":
                "---\ntitle: O\n---\n- [ ] todo\n",
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        empty = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertIn("title: T", empty)
        # outline file projected under slug en/guide/outline
        outline = read_projected(self.out, "en/guide/outline")
        self.assertIn("- [ ] todo", outline)


class TestImagesLinksNav(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_proj_links_images_copied_and_rewritten(self):
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": (
                "---\ntitle: T\n---\n# T\n\n"
                "![pic](../../assets/pic.png)\n\n"
                "See [other](../../guide/01_intro.md).\n"),
            "en/guide/01_intro.md": "---\ntitle: I\n---\n# I\n",
            "en/assets/pic.png": b"\x89PNGDATA",
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertNotIn("github.com", text.split("![pic]")[1].split(")")[0]
                         if "![pic]" in text else text)
        self.assertIn("pic.png", text)
        # copied asset exists below out, byte-identical
        found = list(self.out.rglob("pic.png"))
        self.assertTrue(found, "copied image missing below out")
        self.assertEqual(found[0].read_bytes(), b"\x89PNGDATA")
        # published link became canonical
        self.assertIn("https://", text)

    def test_proj5_order_injected_renderer_only(self):
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: A\n---\n# A\n",
            "en/labs/common/02_second.md": "---\ntitle: B\n---\n# B\n",
            "en/labs/common/21a_appendix.md": "---\ntitle: C\n---\n# C\n",
            "en/labs/common/notes.md": "---\ntitle: D\n---\n# D\n",
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })
        before = snapshot(self.root)
        proc = run_projection(self.root, self.out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # renderer-only: sources have no sidebar/order
        for _k, data in before.items():
            self.assertNotIn(b"sidebar", data)
        after_src = snapshot(self.root)
        self.assertEqual(before, after_src)
        t1 = read_projected(self.out, "en/common/labs/computer-architecture")
        t2 = read_projected(self.out, "en/common/labs/second")
        ta = read_projected(self.out, "en/common/labs/appendix")
        tn = read_projected(self.out, "en/common/labs/notes")
        for t in (t1, t2, ta, tn):
            self.assertIn("sidebar", t)
            self.assertIn("order", t)

        def order_of(text):
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("order:"):
                    return int(s.split(":")[1].strip())
            self.fail("no order in frontmatter")

        o1, o2, oa, on = (order_of(t1), order_of(t2),
                          order_of(ta), order_of(tn))
        # numeric siblings in source order, unnumbered last
        self.assertLess(o1, o2)
        self.assertLess(o2, oa)
        self.assertLess(oa, on)
        # nav.json placeholder exists and is sorted/deterministic
        nav_p = self.out / "nav.json"
        self.assertTrue(nav_p.is_file())
        nav = json.loads(nav_p.read_text(encoding="utf-8"))
        slugs = [e["slug"] for e in nav]
        self.assertEqual(slugs, sorted(slugs))
        self.assertTrue(all("order" in e for e in nav))


class TestDeterminismSourceClean(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: T\n---\n# T\n\nSee $`x`$.\n",
            "en/guide/01_intro.md": "---\ntitle: I\n---\n# I\n",
            "ru/lesson.md": "---\ntitle: R\n---\n# R\n",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_proj6_two_builds_byte_identical(self):
        out1 = Path(self.tmp.name) / "out1"
        out2 = Path(self.tmp.name) / "out2"
        p1 = run_projection(self.root, out1)
        self.assertEqual(p1.returncode, 0, p1.stdout + p1.stderr)
        p2 = run_projection(self.root, out2)
        self.assertEqual(p2.returncode, 0, p2.stdout + p2.stderr)
        self.assertEqual(snapshot_tree(out1), snapshot_tree(out2))

    def test_proj6_placeholders_deterministic_no_timestamps(self):
        out1 = Path(self.tmp.name) / "out1"
        proc = run_projection(self.root, out1)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # placeholders exist
        self.assertTrue((out1 / "astro.config.mjs").is_file())
        self.assertTrue((out1 / "nav.json").is_file())
        self.assertTrue((out1 / "mermaid").is_dir())
        self.assertTrue((out1 / "dist").is_dir())
        # no timestamps: rebuild identical, and no date-like year in config?
        # at least check second build identical (covers timestamps)
        out2 = Path(self.tmp.name) / "out2"
        proc2 = run_projection(self.root, out2)
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertEqual(snapshot_tree(out1), snapshot_tree(out2))

    def test_source_byte_identical_and_no_tracked_files(self):
        before = snapshot(self.root)
        status_before = git("status", "--porcelain", cwd=self.root).stdout
        out = Path(self.tmp.name) / "out"
        proc = run_projection(self.root, out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(snapshot(self.root), before)
        # projection introduces no source changes: git status unchanged
        # (setup leaves untracked fixture files; projection must add none).
        status_after = git("status", "--porcelain", cwd=self.root).stdout
        self.assertEqual(status_after, status_before)

    def test_out_inside_source_rejected(self):
        inside = self.root / "proj-out"
        proc = run_projection(self.root, inside)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("outside", (proc.stdout + proc.stderr).lower())
        self.assertFalse(inside.exists())

    def test_auto_temp_outside_source(self):
        status_before = git(
            "status", "--porcelain", cwd=self.root).stdout
        proc = run_projection(self.root, None)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # out must exist and be outside source; source status unchanged
        self.assertEqual(
            git("status", "--porcelain", cwd=self.root).stdout,
            status_before)

    def test_check_mode_readonly(self):
        before = snapshot(self.root)
        proc = run_projection(self.root, Path(self.tmp.name) / "out",
                              extra=["--check"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((Path(self.tmp.name) / "out").exists())


if __name__ == "__main__":
    unittest.main()
