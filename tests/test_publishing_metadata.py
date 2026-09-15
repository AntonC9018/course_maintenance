"""Lesson metadata generation + validation (issue #8, META-1..META-8).

TDD seam: publishing.metadata + `metadata generate` + extended
`publishing check`. All repos live in TemporaryDirectory; never mutates
live checkouts. Stdlib-only.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import REPO_ROOT, run_publish, write


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True)


def init_repo_with_origin(root: Path, origin_url="git@github.com:O/R.git"):
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


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def slug_of(path: Path) -> str | None:
    """Extract slug value from frontmatter (simple parse)."""
    text = read_text(path)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    for line in lines[1:end]:
        s = line.strip()
        if s.startswith("slug"):
            _, sep, val = s.partition(":")
            if not sep:
                continue
            v = val.strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"')
                                or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1].strip()
            return v or None
    return None


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


class TestSlugifyComponent(unittest.TestCase):
    def test_strips_ordering_and_kebab(self):
        from publishing.metadata import slugify_component
        self.assertEqual(slugify_component("01_foo_bar"), "foo-bar")
        self.assertEqual(slugify_component("21a_function_execution"),
                         "function-execution")
        self.assertEqual(slugify_component("02_RAII"), "raii")
        self.assertEqual(slugify_component("linker_examples"),
                         "linker-examples")
        self.assertEqual(slugify_component("stub"), "stub")
        self.assertEqual(slugify_component("01_stub"), "stub")

    def test_lowercase(self):
        from publishing.metadata import slugify_component
        self.assertEqual(slugify_component("My_File"), "my-file")


class TestSlugGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _repo(self, files: dict, cfg=None, origin="git@github.com:O/R.git"):
        init_repo_with_origin(self.root, origin)
        write_config(self.root, BASE_CONFIG if cfg is None else cfg)
        for rel, content in files.items():
            write(self.root / rel, content)
        return self.root

    def _generate(self):
        from tests.helpers import run_publish
        return run_publish("metadata", "generate",
                           "--course-repo", str(self.root))

    def test_meta1_route_section_mapping(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/00_introduction/01_foo_bar.md": "# x\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # labs/common -> common/labs
        self.assertEqual(
            slug_of(self.root / "en/labs/common/01_computer_architecture.md"),
            "en/common/labs/computer-architecture")
        # 00_introduction -> common
        self.assertEqual(
            slug_of(self.root / "en/00_introduction/01_foo_bar.md"),
            "en/common/foo-bar")

    def test_meta2_index_election_collapses_only_elected(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/index.md": "# i\n",
            "en/guide/other.md": "# o\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(slug_of(self.root / "en/guide/index.md"),
                         "en/guide")
        self.assertEqual(slug_of(self.root / "en/guide/other.md"),
                         "en/guide/other")

    def test_meta2_precedence_readme_over_doc(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/section/README.md": "# r\n",
            "en/section/doc.md": "# d\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # README elected -> collapses; doc keeps component
        self.assertEqual(slug_of(self.root / "en/section/README.md"),
                         "en/section")
        self.assertEqual(slug_of(self.root / "en/section/doc.md"),
                         "en/section/doc")

    def test_meta2_index_beats_readme(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/section/index.md": "# i\n",
            "en/section/README.md": "# r\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(slug_of(self.root / "en/section/index.md"),
                         "en/section")
        self.assertEqual(slug_of(self.root / "en/section/README.md"),
                         "en/section/readme")

    def test_meta3_05a_special(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/05a_programming_fundamentals/01_foo.md": "# a\n",
            "en/05_programming_fundamentals/01_foo.md": "# b\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        slug_a = slug_of(
            self.root / "en/05a_programming_fundamentals/01_foo.md")
        slug_b = slug_of(
            self.root / "en/05_programming_fundamentals/01_foo.md")
        self.assertIsNotNone(slug_a)
        self.assertIsNotNone(slug_b)
        self.assertIn("advanced-programming-fundamentals", slug_a)
        self.assertNotIn("advanced-programming-fundamentals", slug_b)
        self.assertIn("programming-fundamentals", slug_b)

    def test_meta3_test1_only_exact_lessons(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/labs/cpp/test1.md": "# a\n",
            "ru/labs/cpp/test1.md": "# b\n",
            "en/labs/common/test1.md": "# c\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(
            slug_of(self.root / "en/labs/cpp/test1.md").endswith(
                "assessment-1"))
        self.assertTrue(
            slug_of(self.root / "ru/labs/cpp/test1.md").endswith(
                "assessment-1"))
        # same basename elsewhere stays test1
        self.assertTrue(
            slug_of(self.root / "en/labs/common/test1.md").endswith(
                "test1"))
        self.assertNotIn(
            "assessment-1",
            slug_of(self.root / "en/labs/common/test1.md"))

    def test_meta5_existing_valid_slug_never_changed_after_move(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# root\n",
            "en/extra/01_moved.md":
                "---\ntitle: T\nslug: en/custom/kept\n---\n# t\n",
            "ru/lesson.md": "# r\n",
        })
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            slug_of(self.root / "en/extra/01_moved.md"),
            "en/custom/kept")
        # move file within same language, slug must stay (stable identity)
        src = self.root / "en/extra/01_moved.md"
        dst = self.root / "en/extra/02_renamed.md"
        src.rename(dst)
        proc2 = self._generate()
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertEqual(slug_of(dst), "en/custom/kept")

    def test_meta5_invalid_slug_fails_requiring_correction(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: T\nslug: BAD_Slug HERE\n---\n# t\n",
            "ru/lesson.md": "# r\n",
        })
        before = snapshot(self.root)
        proc = self._generate()
        self.assertNotEqual(proc.returncode, 0)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertIn("explicit", combined)
        self.assertIn("correct", combined)
        # no partial writes
        self.assertEqual(snapshot(self.root), before)

    def test_meta4_duplicate_generated_slugs_abort_no_partial(self):
        # 01_foo-bar.md (hyphen) vs 01_foo_bar.md (underscore) -> same slug
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/dup/01_foo-bar.md": "# a\n",
            "en/dup/01_foo_bar.md": "# b\n",
            "ru/lesson.md": "# r\n",
        })
        before = snapshot(self.root)
        proc = self._generate()
        self.assertNotEqual(proc.returncode, 0)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertIn("duplicate", combined)
        self.assertIn("slug", combined)
        self.assertEqual(snapshot(self.root), before)

    def test_meta4_duplicate_after_norm_casefold(self):
        # Two different files claiming the same slug (identical after NFC +
        # casefold) must abort. Both slugs are individually valid kebab.
        self._repo({
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: A\nslug: en/common/dup\n---\n# a\n",
            "en/dup/01_x.md":
                "---\ntitle: B\nslug: en/common/dup\n---\n# b\n",
            "ru/lesson.md": "# r\n",
        })
        before = snapshot(self.root)
        proc = self._generate()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duplicate",
                      (proc.stdout + proc.stderr).lower())
        self.assertIn("meta-4",
                      (proc.stdout + proc.stderr).lower())
        self.assertEqual(snapshot(self.root), before)


class TestBacklinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _repo(self, files, origin="https://github.com/O/R.git"):
        init_repo_with_origin(self.root, origin)
        write_config(self.root)
        for rel, content in files.items():
            write(self.root / rel, content)
        return self.root

    def _generate(self):
        return run_publish("metadata", "generate",
                           "--course-repo", str(self.root))

    def test_meta6_en_backlink_insert(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        }, origin="https://github.com/Owner/Repo.git")
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_text(
            self.root / "en/labs/common/01_computer_architecture.md")
        self.assertIn("<!-- course-site-backlink:start -->", text)
        self.assertIn("<!-- course-site-backlink:end -->", text)
        self.assertIn("[This lesson on the website]", text)
        self.assertIn(
            "https://Owner.github.io/Repo/en/common/labs/computer-architecture/",
            text)

    def test_meta6_ru_backlink_label_and_url(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/labs/common/01_computer_architecture.md": "# r\n",
            "ru/lesson.md": "# x\n",
        })
        # need ru root lesson? root_lesson is en one; ru file extra
        proc = self._generate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_text(
            self.root / "ru/labs/common/01_computer_architecture.md")
        self.assertIn("Этот урок на сайте", text)
        self.assertIn("/ru/common/labs/computer-architecture/", text)

    def test_meta6_backlink_immediately_after_frontmatter(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        })
        self.assertEqual(self._generate().returncode, 0)
        lines = read_text(
            self.root / "en/labs/common/01_computer_architecture.md"
        ).splitlines()
        # find closing --- (second ---)
        idx = [i for i, l in enumerate(lines) if l.strip() == "---"]
        self.assertGreaterEqual(len(idx), 2)
        self.assertEqual(lines[idx[1] + 1].strip(),
                         "<!-- course-site-backlink:start -->")

    def test_meta6_refresh_stale_and_idempotent(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        })
        self.assertEqual(self._generate().returncode, 0)
        p = self.root / "en/labs/common/01_computer_architecture.md"
        first = read_text(p)
        # second run byte-identical
        proc2 = self._generate()
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertEqual(read_text(p), first)
        # corrupt URL -> stale, regenerate fixes
        bad = first.replace("https://", "https://stale.invalid/")
        if bad == first:
            self.fail("could not corrupt backlink URL")
        p.write_text(bad, encoding="utf-8")
        proc3 = self._generate()
        self.assertEqual(proc3.returncode, 0, proc3.stdout + proc3.stderr)
        self.assertEqual(read_text(p), first)

    def test_meta8_idempotent_byte_identical(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/index.md": "# i\n",
            "ru/lesson.md": "# r\n",
        })
        self.assertEqual(self._generate().returncode, 0)
        before = snapshot(self.root)
        proc = self._generate()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(snapshot(self.root), before)


class TestPublishingCheckMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _repo(self, files, origin="https://github.com/O/R.git"):
        init_repo_with_origin(self.root, origin)
        write_config(self.root)
        for rel, content in files.items():
            write(self.root / rel, content)
        return self.root

    def test_meta7_missing_slug_fails_with_regen_command(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# no fm\n",
            "ru/lesson.md": "# r\n",
        })
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("META", combined)
        self.assertIn("metadata generate", combined)
        self.assertIn("--course-repo", combined)

    def test_meta7_stale_backlink_fails_with_regen_command(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        })
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
        p = self.root / "en/labs/common/01_computer_architecture.md"
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("https://", "https://stale.invalid/"),
                     encoding="utf-8")
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("META", combined)
        self.assertIn("stale", combined.lower())
        self.assertIn("metadata generate", combined)

    def test_meta7_missing_backlink_fails(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md":
                "---\ntitle: T\nslug: en/common/labs/computer-architecture\n---\n# t\n",
            "ru/lesson.md":
                "---\ntitle: R\nslug: ru/lesson\n---\n# r\n",
        })
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("backlink", (proc.stdout + proc.stderr).lower())
        self.assertIn("metadata generate", proc.stdout + proc.stderr)

    def test_meta7_duplicate_backlink_fails(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        })
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        self.assertEqual(gen.returncode, 0)
        p = self.root / "en/labs/common/01_computer_architecture.md"
        t = p.read_text(encoding="utf-8")
        # duplicate block at end
        start = "<!-- course-site-backlink:start -->"
        end = "<!-- course-site-backlink:end -->"
        s = t.index(start)
        e = t.index(end) + len(end)
        block = t[s:e]
        p.write_text(t + "\n" + block + "\n", encoding="utf-8")
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("backlink", (proc.stdout + proc.stderr).lower())

    def test_check_ok_after_generate_and_readonly(self):
        self._repo({
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "ru/lesson.md": "# r\n",
        })
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
        before = snapshot(self.root)
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(snapshot(self.root), before)


class TestNoImplicitMaintenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_meta8_ordinary_maintenance_no_side_effect(self):
        import sys
        init_repo_with_origin(self.root, "git@github.com:O/R.git")
        write_config(self.root)
        write(self.root / "en/labs/common/01_computer_architecture.md",
              "# t\n")
        write(self.root / "ru/lesson.md", "# r\n")
        before = snapshot(self.root)
        cmd = [sys.executable, str(REPO_ROOT / "maintain.py"),
               "--check", str(self.root)]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=str(REPO_ROOT))
        # maintain must not add slugs/backlinks
        self.assertEqual(snapshot(self.root), before)
        # and must not mention metadata generation side effects
        for p in [self.root / "en/labs/common/01_computer_architecture.md"]:
            self.assertNotIn("slug", p.read_text(encoding="utf-8").lower())
            self.assertNotIn("course-site-backlink",
                             p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
