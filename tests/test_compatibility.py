"""Compatibility + acceptance suite (issue #12).

Maintained suite replacing the disposable renderer-compatibility spike
(design: nested details, C++ angle brackets, math, Mermaid, tables, images,
nested routes, rewritten links, Pages base). Covers the spec Compatibility
list end-to-end with fixtures + representative real lessons:

- every slug-generation rule + collision class (META-1..5);
- en/ru backlinks (META-6/7);
- links to published/excluded/files/dirs/images/peers/fragments/queries/
  missing (LINK-1..8);
- matching/differing/absent/repeated H1 (PROJ-2);
- inline/display math (PROJ-3);
- both real Mermaid diagrams in the initial corpus (DIAG-1..4);
- nested details/tables/raw C++/fenced/empty/outlines (PROJ-4);
- locale routes, Pages base, root redirect, indexless-group redirects,
  sidebar labels/order/collapse,
  lab pagination, GitHub source links, Pagefind, no fallback routes
  (SITE-2..15);
- repeat projection/build introduces no source changes or newly tracked
  files (PROJ-6);
- built-output inspection for forbidden Mermaid client JS (DIAG-3) +
  missing search/nav assets.

All repos live in TemporaryDirectory; never mutates live checkouts.
Stdlib-only Python; Playwright/Chromium mocked where offline but the real
rendering path (renderer/render-mermaid.mjs) is exercised when available.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import run_publish, write


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


BASE_CONFIG = {
    "version": 1,
    "default_language": "en",
    "languages": [
        {"code": "en", "root": "en", "label": "English"},
        {"code": "ru", "root": "ru", "label": "Русский"},
    ],
    "exclude": ["en/excluded.md"],
    "route_sections": [
        {"source": "00_intro", "destination": "common"},
        {"source": "04_cpp", "destination": "cpp"},
        {"source": "05_programming_fundamentals",
         "destination": "cpp/programming-fundamentals"},
        {"source": "05a_programming_fundamentals",
         "destination": "cpp/advanced-programming-fundamentals"},
        {"source": "08_dsa", "destination": "dsa"},
        {"source": "labs/common", "destination": "common/labs"},
        {"source": "labs/cpp", "destination": "cpp/labs"},
        {"source": "labs/algorithms", "destination": "dsa/labs"},
    ],
    "site_title": {"en": "EN Title", "ru": "RU Title"},
    "root_lesson": "en/labs/common/01_computer_architecture.md",
    "peer_repositories": [],
}


def write_config(root: Path, cfg=None):
    cfg = BASE_CONFIG if cfg is None else cfg
    write(root / "course-publishing.json",
          json.dumps(cfg, ensure_ascii=False, indent=2))
    return root / "course-publishing.json"


REAL_1 = """flowchart LR
A(1) --> B(2)
A --> C(3)
A --> D(4)
B --> C
C --> D
D --> A"""

REAL_2 = """flowchart LR
A(1) --> B(2)
B --> C(3)
C --> D(4)
D --> A
D <--> B"""


def compat_files():
    """Representative passing corpus (all spec kinds, all valid)."""
    return {
        # Root + labs (SITE-9 numeric incl lettered, unnumbered last).
        "en/labs/common/01_computer_architecture.md":
            "---\ntitle: Arch\n---\n# Arch\n\nRoot lab.\n",
        "en/labs/common/02_second.md":
            "---\ntitle: Second\n---\n# Second\n",
        "en/labs/common/21a_appendix.md":
            "---\ntitle: Appendix\n---\n# Appendix\n",
        "en/labs/common/notes.md":
            "---\ntitle: Notes\n---\n# Notes\n",
        "en/labs/cpp/01_first.md":
            "---\ntitle: First\n---\n# First\n",
        "en/labs/cpp/02_second.md":
            "---\ntitle: Cpp Second\n---\n# Cpp Second\n",
        "en/labs/cpp/test1.md":
            "---\ntitle: Assessment 1\n---\n# Assessment 1\n",
        "en/labs/cpp/notes.md":
            "---\ntitle: Zeta\n---\n# Zeta\n",
        "en/labs/algorithms/01_sorting.md":
            "---\ntitle: Sorting\n---\n# Sorting\n",
        # Common index + ordinary + guide unelected + humanize.
        "en/00_intro/index.md":
            "---\ntitle: Common Index Title\n---\n# Common Index Title\n",
        "en/00_intro/01_intro.md":
            "---\ntitle: Intro\n---\n# Intro\n",
        "en/00_intro/02_basics.md":
            "---\ntitle: Basics\n---\n# Basics\n",
        "en/00_intro/guide/index.md":
            "---\ntitle: Guide Index\n---\n# Guide Index\n",
        "en/00_intro/guide/README.md":
            "---\ntitle: Guide Readme\n---\n# Guide Readme\n",
        "en/00_intro/guide/doc.md":
            "---\ntitle: Guide Doc\n---\n# Guide Doc\n",
        "en/00_intro/sub-topic/01_foo.md":
            "---\ntitle: Foo\n---\n# Foo\n",
        "en/05a_programming_fundamentals/index.md":
            "---\ntitle: Advanced Index\n---\n# Advanced Index\n",
        "en/05a_programming_fundamentals/01_deep.md":
            "---\ntitle: Deep\n---\n# Deep\n",
        "en/05_programming_fundamentals/01_basic.md":
            "---\ntitle: Basic\n---\n# Basic\n",
        "en/04_cpp/01_intro.md":
            "---\ntitle: Cpp Intro\n---\n# Cpp Intro\n",
        "en/08_dsa/01_arrays.md":
            "---\ntitle: Arrays\n---\n# Arrays\n",
        "en/guide/stub.md":
            "---\ntitle: Stub Lesson\n---\n# Stub Lesson\n",
        "en/excluded.md":
            "---\ntitle: Excluded\n---\n# Excluded\n",
        # Link hub: published, excluded, file, dir, image, img tag,
        # fragment (own + other), query.
        "en/guide/01_links.md": (
            "---\ntitle: Links\n---\n# Links\n\n"
            "## Hello World\n\n"
            "See [root](../labs/common/01_computer_architecture.md).\n\n"
            "See [excluded](../excluded.md).\n\n"
            "See [code](../assets/code.py).\n\n"
            "See [assets dir](../assets).\n\n"
            "![pic](../assets/pic.png)\n\n"
            '<img src="../assets/pic.png" alt="p">\n\n'
            "See [own frag](#hello-world).\n\n"
            "See [other frag](./02_mermaid.md#graph-lab).\n\n"
            "See [query](../labs/common/01_computer_architecture.md?x=1&y=2).\n\n"
            "See [qfrag](./02_mermaid.md?dl=1#graph-lab).\n"
        ),
        # Both real Mermaid diagrams + a heading for fragment targets.
        "en/guide/02_mermaid.md": (
            "---\ntitle: Graphs Lab\n---\n# Graphs Lab\n\n"
            "## Graph Lab\n\n"
            f"```mermaid\n{REAL_1}\n```\n\n"
            f"```mermaid\n{REAL_2}\n```\n"
        ),
        "en/guide/03_math.md": (
            "---\ntitle: Math\n---\n# Math\n\n"
            "See $`x^2`$ here and $`a+b`$ too.\n\n"
            "$$\nx^2 + y^2\n$$\n"
        ),
        "en/guide/04_rich.md": (
            "---\ntitle: Rich\n---\n# Rich\n\n"
            "```cpp\nif (a < b && c > d) { return; }\n```\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "<details>\n<summary>Outer</summary>\n\n"
            "Outer text with `a < b` span.\n\n"
            "<details>\n<summary>Inner</summary>\n\n"
            "Inner text.\n\n"
            "</details>\n\n"
            "</details>\n\n"
            "```\n# Not a heading\n$`x`$ untouched\n```\n"
        ),
        "en/guide/05_empty.md":
            "---\ntitle: Empty\n---\n# Empty\n",
        "en/guide/06_outline.md":
            "---\ntitle: Outline\n---\n# Outline\n\n- [ ] todo one\n- [ ] todo two\n",
        # H1 variations (PROJ-2: title derives from the H1).
        "en/guide/h1_matching.md":
            "---\ntitle: Same\n---\n# Same\n\nBody.\n",
        "en/guide/h1_differing.md":
            "---\ntitle: Title Kept\n---\n# Other Heading\n\nBody.\n",
        "en/guide/h1_repeated.md":
            "---\ntitle: Multi\n---\n# First\n\n# Second\n\n## Third\n",
        "en/assets/code.py": "print(1)\n",
        "en/assets/pic.png": b"\x89PNGDATA",
        # Russian counterparts (subset; en/dsa has no ru fallback).
        "ru/labs/common/01_computer_architecture.md":
            "---\ntitle: Арх\n---\n# Арх\n",
        "ru/labs/cpp/test1.md":
            "---\ntitle: Оценка 1\n---\n# Оценка 1\n",
        "ru/00_intro/index.md":
            "---\ntitle: Общий Индекс\n---\n# Общий Индекс\n",
        "ru/00_intro/01_intro.md":
            "---\ntitle: Введ\n---\n# Введ\n",
        "ru/guide/02_mermaid.md": (
            "---\ntitle: Графы\n---\n# Графы\n\n"
            f"```mermaid\n{REAL_1}\n```\n\n"
            f"```mermaid\n{REAL_2}\n```\n"
        ),
        "ru/guide/03_math.md": (
            "---\ntitle: Математика\n---\n# Математика\n\n"
            "См $`x^2`$ здесь.\n\n"
            "$$\ny = x^2\n$$\n"
        ),
    }


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


def load_all(root: Path):
    from publishing.config import load_config
    from publishing.identity import infer_identity
    from publishing.inventory import build_inventory
    from publishing.links import build_link_index
    from publishing.metadata import collect_metadata_state
    from publishing.projection import collect_projection_data
    repo = root.resolve()
    config = load_config(repo)
    identity = infer_identity(repo)
    inventory = build_inventory(repo, config)
    final, errors, _m = collect_metadata_state(
        repo, config, inventory, identity.pages_url)
    assert not errors, errors
    index = build_link_index(repo, config, identity, inventory, final)
    files, copies, nav, proj_errors = collect_projection_data(
        repo, config, identity, inventory, final, index)
    assert not proj_errors, proj_errors
    return config, identity, inventory, final, index, files, copies, nav


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
    result = {}
    for dirpath, _dns, fns in os.walk(out_dir):
        for fn in fns:
            p = Path(dirpath) / fn
            rel = p.relative_to(out_dir).as_posix()
            result[rel] = p.read_bytes()
    return dict(sorted(result.items()))


def read_projected(out: Path, slug: str) -> str:
    p = out / "src" / "content" / "docs" / (slug + ".md")
    assert p.is_file(), f"missing projected {slug}: {p}"
    return p.read_text(encoding="utf-8")


class TestSlugRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())

    def tearDown(self):
        self.tmp.cleanup()

    def _slug_of(self, rel):
        from publishing.config import load_config
        from publishing.identity import infer_identity
        from publishing.inventory import build_inventory
        from publishing.metadata import collect_metadata_state
        config = load_config(self.root.resolve())
        identity = infer_identity(self.root.resolve())
        inv = build_inventory(self.root.resolve(), config)
        final, errors, _m = collect_metadata_state(
            self.root.resolve(), config, inv, identity.pages_url)
        assert not errors, errors
        return final[rel]

    def test_ordering_prefix_stripped_kebab(self):
        self.assertEqual(
            self._slug_of("en/00_intro/01_intro.md"), "en/common/intro")

    def test_lettered_position(self):
        # 21a_ -> appendix, distinct from numeric siblings.
        slug = self._slug_of("en/labs/common/21a_appendix.md")
        self.assertEqual(slug, "en/common/labs/appendix")

    def test_05a_special_mapping(self):
        slug = self._slug_of("en/05a_programming_fundamentals/01_deep.md")
        self.assertIn("advanced-programming-fundamentals", slug)
        other = self._slug_of("en/05_programming_fundamentals/01_basic.md")
        self.assertNotIn("advanced-programming-fundamentals", other)
        self.assertIn("programming-fundamentals", other)

    def test_test1_assessment_only_exact(self):
        self.assertTrue(
            self._slug_of("en/labs/cpp/test1.md").endswith("assessment-1"))
        self.assertTrue(
            self._slug_of("ru/labs/cpp/test1.md").endswith("assessment-1"))

    def test_index_election_collapses_only_elected(self):
        self.assertEqual(
            self._slug_of("en/00_intro/index.md"), "en/common")
        self.assertEqual(
            self._slug_of("en/00_intro/guide/index.md"),
            "en/common/guide")
        self.assertEqual(
            self._slug_of("en/00_intro/guide/README.md"),
            "en/common/guide/readme")
        self.assertEqual(
            self._slug_of("en/00_intro/guide/doc.md"),
            "en/common/guide/doc")

    def test_stub_remains(self):
        self.assertTrue(
            self._slug_of("en/guide/stub.md").endswith("/stub"))

    def test_collision_duplicate_generated_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            init_repo_with_origin(root)
            write_config(root)
            write(root / "en/labs/common/01_computer_architecture.md", "# t\n")
            write(root / "en/dup/01_foo-bar.md", "# a\n")
            write(root / "en/dup/01_foo_bar.md", "# b\n")
            write(root / "ru/lesson.md", "# r\n")
            proc = run_publish("metadata", "generate",
                               "--course-repo", str(root))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("duplicate", (proc.stdout + proc.stderr).lower())

    def test_collision_casefold_duplicate_slug_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            init_repo_with_origin(root)
            write_config(root)
            write(root / "en/labs/common/01_computer_architecture.md",
                  "---\ntitle: A\nslug: en/common/dup\n---\n# a\n")
            write(root / "en/dup/01_x.md",
                  "---\ntitle: B\nslug: en/common/dup\n---\n# b\n")
            write(root / "ru/lesson.md", "# r\n")
            proc = run_publish("metadata", "generate",
                               "--course-repo", str(root))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("duplicate", (proc.stdout + proc.stderr).lower())

    def test_invalid_slug_fails_requiring_explicit_correction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            init_repo_with_origin(root)
            write_config(root)
            write(root / "en/labs/common/01_computer_architecture.md",
                  "---\ntitle: T\nslug: BAD_Slug HERE\n---\n# t\n")
            write(root / "ru/lesson.md", "# r\n")
            proc = run_publish("metadata", "generate",
                               "--course-repo", str(root))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("explicit", (proc.stdout + proc.stderr).lower())


class TestBacklinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files(),
                  origin="https://github.com/Owner/Repo.git")

    def tearDown(self):
        self.tmp.cleanup()

    def test_en_backlink(self):
        text = (self.root / "en/labs/common/01_computer_architecture.md"
                ).read_text(encoding="utf-8")
        self.assertIn("<!-- course-site-backlink:start -->", text)
        self.assertIn("[This lesson on the website]", text)
        self.assertIn(
            "https://Owner.github.io/Repo/en/common/labs/computer-architecture/",
            text)
        # Immediately after frontmatter.
        lines = text.splitlines()
        idx = [i for i, line in enumerate(lines) if line.strip() == "---"]
        self.assertGreaterEqual(len(idx), 2)
        self.assertEqual(lines[idx[1] + 1].strip(),
                         "<!-- course-site-backlink:start -->")

    def test_ru_backlink(self):
        text = (self.root / "ru/labs/common/01_computer_architecture.md"
                ).read_text(encoding="utf-8")
        self.assertIn("Этот урок на сайте", text)
        self.assertIn("/ru/common/labs/computer-architecture/", text)


class TestLinksCompat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.config, self.identity, self.inv, self.final, self.index, \
            self.files, self.copies, self.nav = load_all(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, source_rel, dest, is_image=False):
        from publishing.links import resolve_link
        src = (self.root / source_rel).resolve()
        return resolve_link(src, dest, is_image=is_image, index=self.index)

    def test_published_to_canonical(self):
        out = self._resolve("en/guide/01_links.md",
                            "../labs/common/01_computer_architecture.md")
        self.assertEqual(out.kind, "canonical")
        self.assertIn("/en/common/labs/computer-architecture/", out.url)

    def test_excluded_to_blob(self):
        out = self._resolve("en/guide/01_links.md", "../excluded.md")
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("/blob/master/en/excluded.md", out.url)

    def test_file_to_blob(self):
        out = self._resolve("en/guide/01_links.md", "../assets/code.py")
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("/blob/master/en/assets/code.py", out.url)

    def test_dir_to_tree(self):
        out = self._resolve("en/guide/01_links.md", "../assets")
        self.assertEqual(out.kind, "github-tree")
        self.assertIn("/tree/master/en/assets", out.url)

    def test_image_copied_not_github(self):
        out = self._resolve("en/guide/01_links.md", "../assets/pic.png",
                            is_image=True)
        self.assertEqual(out.kind, "image")
        self.assertIsNotNone(out.copy_source)
        self.assertNotIn("github.com", out.url)
        self.assertIn("pic.png", out.url)

    def test_img_tag_rewritten(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_links.md").resolve()
        text = ('---\ntitle: T\nslug: en/guide/links\n---\n'
                '<img src="../assets/pic.png" alt="p">\n')
        new_text, copies, errors = rewrite_document(src, text, self.index)
        self.assertEqual(errors, [])
        self.assertEqual(len(copies), 1)

    def test_fragment_valid(self):
        out = self._resolve("en/guide/01_links.md",
                            "./02_mermaid.md#graph-lab")
        self.assertEqual(out.kind, "canonical")
        self.assertTrue(out.url.endswith("#graph-lab"))

    def test_anchor_only_valid(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_links.md").resolve()
        ok = ('---\ntitle: T\nslug: en/guide/links\n---\n'
              '[a](#hello-world)\n')
        _n, _c, errors = rewrite_document(src, ok, self.index)
        self.assertEqual(errors, [])

    def test_query_preserved(self):
        out = self._resolve(
            "en/guide/01_links.md",
            "../labs/common/01_computer_architecture.md?x=1&y=2")
        self.assertTrue(out.url.endswith("?x=1&y=2"))
        out2 = self._resolve("en/guide/01_links.md",
                             "./02_mermaid.md?dl=1#graph-lab")
        self.assertTrue(out2.url.endswith("?dl=1#graph-lab"))

    def test_missing_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_links.md", "./does-not-exist.md")
        self.assertIn("LINK-7", str(ctx.exception))

    def test_invalid_anchor_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError):
            self._resolve("en/guide/01_links.md",
                          "./02_mermaid.md#no-such-heading")

    def test_peer_lesson_and_file(self):
        # Peer repo alongside main (allowlisted, identity preserved).
        base = Path(self.tmp.name) / "peerbase"
        base.mkdir(parents=True, exist_ok=True)
        peer = base / "peer"
        init_repo_with_origin(peer, "https://github.com/Peer/PeerRepo.git")
        peer_cfg = json.loads(json.dumps(BASE_CONFIG))
        peer_cfg["root_lesson"] = "en/labs/common/01_computer_architecture.md"
        write(peer / "course-publishing.json",
              json.dumps(peer_cfg, ensure_ascii=False, indent=2))
        write(peer / "en/labs/common/01_computer_architecture.md", "# t\n")
        write(peer / "en/peer_lesson.md", "# Peer\n")
        write(peer / "en/data.txt", "d\n")
        write(peer / "ru/lesson.md", "# r\n")
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(peer))
        self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
        main = base / "main"
        init_repo_with_origin(main, "https://github.com/O/R.git")
        cfg = json.loads(json.dumps(BASE_CONFIG))
        cfg["peer_repositories"] = ["../peer"]
        write(main / "course-publishing.json",
              json.dumps(cfg, ensure_ascii=False, indent=2))
        write(main / "en/labs/common/01_computer_architecture.md", "# t\n")
        write(main / "en/guide/01_intro.md", "# i\n")
        write(main / "ru/lesson.md", "# r\n")
        gen2 = run_publish("metadata", "generate",
                           "--course-repo", str(main))
        self.assertEqual(gen2.returncode, 0, gen2.stdout + gen2.stderr)
        from publishing.config import load_config
        from publishing.identity import infer_identity
        from publishing.inventory import build_inventory
        from publishing.links import build_link_index, resolve_link
        from publishing.metadata import collect_metadata_state
        config = load_config(main)
        ident = infer_identity(main)
        inv = build_inventory(main, config)
        final, errors, _m = collect_metadata_state(
            main, config, inv, ident.pages_url)
        self.assertFalse(errors, errors)
        index = build_link_index(main, config, ident, inv, final)
        src = (main / "en/guide/01_intro.md").resolve()
        out = resolve_link(src, "../../../peer/en/peer_lesson.md",
                           is_image=False, index=index)
        self.assertEqual(out.kind, "canonical")
        self.assertIn("Peer.github.io/PeerRepo", out.url)
        out2 = resolve_link(src, "../../../peer/en/data.txt",
                            is_image=False, index=index)
        self.assertEqual(out2.kind, "github-blob")
        self.assertIn("github.com/Peer/PeerRepo/blob/master/", out2.url)

    def test_projected_links_rewritten(self):
        out = Path(self.tmp.name) / "out"
        proc = run_publish("projection", "build",
                           "--course-repo", str(self.root),
                           "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = read_projected(out, "en/guide/links")
        # Published link became canonical https; image points at copied asset.
        self.assertIn("https://", text)
        self.assertIn("pic.png", text)
        found = list(out.rglob("pic.png"))
        self.assertTrue(found)
        self.assertEqual(found[0].read_bytes(), b"\x89PNGDATA")


class TestHeadingsMath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.out = Path(self.tmp.name) / "out"
        proc = run_publish("projection", "build",
                           "--course-repo", str(self.root),
                           "--out", str(self.out))
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def tearDown(self):
        self.tmp.cleanup()

    def _body(self, slug):
        full = read_projected(self.out, slug)
        lines = full.splitlines()
        end = next(i for i in range(1, len(lines))
                   if lines[i].strip() == "---")
        return "\n".join(lines[end + 1:]), full

    def test_matching_h1_stripped_no_duplicate(self):
        body, full = self._body("en/guide/h1-matching")
        self.assertIn("title: Same", full)
        self.assertNotIn("# Same", body)
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_differing_h1_derives_title(self):
        body, full = self._body("en/guide/h1-differing")
        self.assertIn("title: Other Heading", full)
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_absent_h1_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "c"
            init_repo_with_origin(root)
            write_config(root)
            write(root / "en/labs/common/01_computer_architecture.md",
                  "---\ntitle: A\n---\n# A\n")
            write(root / "en/guide/h1_absent.md",
                  "---\ntitle: No H1 Here\n---\nIntro.\n\n## Sec\n")
            write(root / "ru/lesson.md", "# R\n")
            gen = run_publish("metadata", "generate",
                              "--course-repo", str(root))
            self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
            check = run_publish("publishing", "check",
                                "--course-repo", str(root))
            self.assertNotEqual(check.returncode, 0)
            self.assertIn("PROJ-2", check.stdout + check.stderr)

    def test_repeated_h1_shifted_under_covering_title(self):
        body, full = self._body("en/guide/h1-repeated")
        self.assertIn("title: Multi", full)
        self.assertIn("## First", body)
        self.assertIn("## Second", body)
        self.assertIn("### Third", body)
        for line in body.splitlines():
            self.assertFalse(line.startswith("# "))

    def test_inline_math_converted_source_untouched(self):
        body, _f = self._body("en/guide/math")
        self.assertIn("$x^2$", body)
        self.assertNotIn("$`x^2`$", body)
        src = (self.root / "en/guide/03_math.md").read_text(encoding="utf-8")
        self.assertIn("$`x^2`$", src)

    def test_display_math_survives(self):
        body, _f = self._body("en/guide/math")
        self.assertIn("$$", body)
        self.assertIn("x^2 + y^2", body)

    def test_ru_math(self):
        body, _f = self._body("ru/guide/math")
        self.assertIn("$x^2$", body)
        self.assertIn("$$", body)


class TestMermaidCompat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_real_diagrams_build_as_static_svg(self):
        proc = run_publish("projection", "build",
                           "--course-repo", str(self.root),
                           "--out", str(self.out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for slug in ("en/guide/mermaid", "ru/guide/mermaid"):
            text = read_projected(self.out, slug)
            self.assertNotIn("```mermaid", text)
            self.assertEqual(text.count("<svg"), 2,
                             f"expected 2 static SVGs in {slug}")
            self.assertIn('class="mermaid-static"', text)
        # Disposable SVG files exist (never committed).
        svgs = sorted(self.out.rglob("*.svg"))
        self.assertGreaterEqual(len(svgs), 4)  # 2 en + 2 ru
        for p in svgs:
            self.assertIn("<svg", p.read_text(encoding="utf-8"))
        # No Mermaid client JS shipped.
        from publishing.mermaid import check_no_mermaid_client_js
        self.assertEqual(check_no_mermaid_client_js(self.out), [])

    def test_invalid_mermaid_fails_with_path_and_diagnostic(self):
        bad = dict(compat_files())
        bad["en/guide/02_mermaid.md"] = (
            "---\ntitle: Graphs Lab\n---\n# Graphs Lab\n\n"
            "## Graph Lab\n\n"
            "```mermaid\nnot-a-diagram @@@\n```\n")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "bad"
            init_repo_with_origin(root)
            write_config(root)
            for rel, content in bad.items():
                p = root / rel
                if isinstance(content, bytes):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(content)
                else:
                    write(p, content)
            # Metadata + check pass (mermaid not validated there).
            gen = run_publish("metadata", "generate",
                              "--course-repo", str(root))
            self.assertEqual(gen.returncode, 0, gen.stdout + gen.stderr)
            check = run_publish("publishing", "check",
                                "--course-repo", str(root))
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            out = Path(td) / "out"
            proc = run_publish("projection", "build",
                               "--course-repo", str(root),
                               "--out", str(out))
            self.assertNotEqual(proc.returncode, 0)
            combined = proc.stdout + proc.stderr
            self.assertIn("en/guide/02_mermaid.md", combined)
            self.assertIn("DIAG-2", combined)

    def test_svg_deterministic_repeatable(self):
        out1 = Path(self.tmp.name) / "out1"
        out2 = Path(self.tmp.name) / "out2"
        p1 = run_publish("projection", "build",
                         "--course-repo", str(self.root),
                         "--out", str(out1))
        self.assertEqual(p1.returncode, 0, p1.stdout + p1.stderr)
        p2 = run_publish("projection", "build",
                         "--course-repo", str(self.root),
                         "--out", str(out2))
        self.assertEqual(p2.returncode, 0, p2.stdout + p2.stderr)
        self.assertEqual(snapshot_tree(out1), snapshot_tree(out2))
        # Normalized: random ids would otherwise differ; direct unit check.
        from publishing.mermaid import normalize_svg
        a = '<svg><g id="mermaid-a1b2c3">x</g></svg>'
        b = '<svg><g id="mermaid-z9y8x7">x</g></svg>'
        self.assertEqual(normalize_svg(a), normalize_svg(b))


class TestPreservationCompat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.out = Path(self.tmp.name) / "out"
        proc = run_publish("projection", "build",
                           "--course-repo", str(self.root),
                           "--out", str(self.out))
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_details_tables_cpp_fenced(self):
        text = read_projected(self.out, "en/guide/rich")
        self.assertIn("<details>", text)
        self.assertIn("<summary>Outer</summary>", text)
        self.assertIn("<summary>Inner</summary>", text)
        self.assertIn("| a | b |", text)
        self.assertIn("if (a < b && c > d)", text)
        self.assertIn("`a < b`", text)
        self.assertIn("# Not a heading", text)
        self.assertIn("$`x`$", text)  # fenced math untouched

    def test_empty_and_outline(self):
        empty = read_projected(self.out, "en/guide/empty")
        self.assertIn("title: Empty", empty)
        outline = read_projected(self.out, "en/guide/outline")
        self.assertIn("- [ ] todo one", outline)

    def test_backlink_stripped_source_kept(self):
        text = read_projected(self.out, "en/common/labs/computer-architecture")
        self.assertNotIn("course-site-backlink", text)
        src = (self.root / "en/labs/common/01_computer_architecture.md"
               ).read_text(encoding="utf-8")
        self.assertIn("course-site-backlink:start", src)


class TestRoutesNavCompat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.config, self.identity, self.inv, self.final, self.index, \
            self.files, self.copies, self.nav = load_all(self.root)
        from publishing.navigation import (build_lab_sequences,
                                            build_sidebars,
                                            build_starlight_sidebar,
                                            get_group_redirects,
                                            get_redirects)
        from publishing.site import (astro_base, astro_site,
                                     generate_astro_config)
        self.per_locale = build_sidebars(self.nav, self.config)
        self.lab_seqs = build_lab_sequences(self.nav)
        self.starlight_sidebar = build_starlight_sidebar(
            self.per_locale, self.config)
        # Same merge as run_site_build: SITE-3/4 roots + SITE-15 groups.
        self.redirects = get_redirects(self.config, self.final)
        self.redirects.update(get_group_redirects(self.nav, self.config))
        self.astro_text = generate_astro_config(
            self.config, self.identity, self.starlight_sidebar,
            self.redirects)
        self.base = astro_base(self.identity)
        self.site = astro_site(self.identity)

    def tearDown(self):
        self.tmp.cleanup()

    def test_locale_prefixed_routes_and_base(self):
        for e in self.nav:
            self.assertTrue(e["slug"].startswith("en/") or
                            e["slug"].startswith("ru/"))
        self.assertEqual(self.base, "/R/")
        self.assertEqual(self.site, "https://O.github.io")
        self.assertIn('base: "/R/"', self.astro_text)
        self.assertIn("trailingSlash: 'always'", self.astro_text)

    def test_root_and_locale_redirects(self):
        self.assertEqual(
            self.redirects["/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            self.redirects["/en/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            self.redirects["/ru/"], "/ru/common/labs/computer-architecture/")
        self.assertIn("/R/en/common/labs/computer-architecture/",
                      self.astro_text)

    def test_no_locale_root_starter_pages(self):
        self.assertNotIn("src/content/docs/en.md", self.files)
        self.assertNotIn("src/content/docs/ru.md", self.files)

    def test_indexless_group_redirects_no_listing_pages(self):
        # SITE-15: representative indexless groups redirect to the
        # first descendant lesson in sidebar order; groups with an
        # index serve it (no redirect); no listing content generated.
        self.assertEqual(
            self.redirects["/en/cpp/"], "/en/cpp/intro/")
        self.assertEqual(
            self.redirects["/en/cpp/labs/"], "/en/cpp/labs/first/")
        self.assertEqual(
            self.redirects["/en/common/labs/"],
            "/en/common/labs/computer-architecture/")
        self.assertEqual(
            self.redirects["/ru/cpp/"], "/ru/cpp/labs/assessment-1/")
        self.assertEqual(
            self.redirects["/ru/cpp/labs/"],
            "/ru/cpp/labs/assessment-1/")
        for key in ("/en/common/", "/ru/common/"):
            self.assertNotIn(key, self.redirects)
        # Root/locale roots are SITE-3/4 entries in the same merged map
        # (absence from the SITE-15 helper itself is covered by unit
        # tests); they still point at the root lesson unchanged.
        self.assertEqual(
            self.redirects["/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            self.redirects["/en/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            self.redirects["/ru/"], "/ru/common/labs/computer-architecture/")
        # Redirect targets include the project base in Astro config
        # (same mechanism as the /en/ root redirect, so Astro emits
        # dist redirect pages for them).
        self.assertIn('"/en/cpp/": "/R/en/cpp/intro/"', self.astro_text)
        self.assertIn('"/ru/cpp/labs/": "/R/ru/cpp/labs/assessment-1/"',
                      self.astro_text)
        # Only redirect pages: no content file at any group route.
        for key in self.redirects:
            if key in ("/", "/en/", "/ru/"):
                continue
            rest = key.strip("/")
            self.assertNotIn(f"src/content/docs/{rest}.md", self.files)
            self.assertNotIn(f"src/content/docs/{rest}/index.md",
                             self.files)

    def test_no_fallback_routes(self):
        slugs = {e["slug"] for e in self.nav}
        self.assertIn("en/dsa/arrays", slugs)
        self.assertNotIn("ru/dsa/arrays", slugs)
        self.assertNotIn("src/content/docs/ru/dsa/arrays.md", self.files)

    def test_sidebar_labels_order_collapse(self):
        en_labels = [g["label"] for g in self.per_locale["en"]]
        self.assertEqual(en_labels[:3], [
            "Common Index Title", "C++", "Data Structures and Algorithms"])
        # Index group uses title as label, Overview link first.
        common = next(g for g in self.per_locale["en"]
                      if g["label"] == "Common Index Title")
        self.assertEqual(common["items"][0]["label"], "Overview")
        # Humanized group.
        def find(items, label):
            for n in items:
                if n.get("label") == label and "items" in n:
                    return n
                if "items" in n:
                    r = find(n["items"], label)
                    if r is not None:
                        return r
            return None
        self.assertIsNotNone(find(self.per_locale["en"], "Sub topic"))
        # Numeric incl lettered, unnumbered last.
        labs = find([common], "Labs")
        self.assertIsNotNone(labs)
        self.assertEqual([x["slug"] for x in labs["items"]], [
            "en/common/labs/computer-architecture",
            "en/common/labs/second",
            "en/common/labs/appendix",
            "en/common/labs/notes",
        ])
        # All collapsed, non-clickable groups.
        def walk(items):
            for n in items:
                if "items" in n:
                    self.assertTrue(n["collapsed"])
                    self.assertNotIn("slug", n)
                    walk(n["items"])
        for lang in ("en", "ru"):
            walk(self.per_locale[lang])

    def test_lab_pagination_crosses_groups_assessment_last(self):
        from publishing.navigation import lab_pagination
        pag = lab_pagination(self.nav)
        self.assertEqual(pag["en/common/labs/notes"]["next"],
                         "en/cpp/labs/first")
        cpp = [s for s in self.lab_seqs["en"] if "/cpp/labs/" in s]
        self.assertEqual(cpp[-1], "en/cpp/labs/assessment-1")
        self.assertNotIn("en/common/intro", pag)

    def test_lab_number_display_site16(self):
        # Numbered lab prefixed, unnumbered lab and non-lab plain (SITE-16).
        def find(items, label):
            for n in items:
                if n.get("label") == label and "items" in n:
                    return n
                if "items" in n:
                    r = find(n["items"], label)
                    if r is not None:
                        return r
            return None

        common = next(g for g in self.per_locale["en"]
                      if g["label"] == "Common Index Title")
        labs = find([common], "Labs")
        self.assertIsNotNone(labs)
        by_slug = {x["slug"]: x["label"] for x in labs["items"]}
        self.assertEqual(by_slug["en/common/labs/computer-architecture"],
                         "1. Arch")
        self.assertEqual(by_slug["en/common/labs/appendix"],
                         "21a. Appendix")
        self.assertEqual(by_slug["en/common/labs/notes"], "Notes")

        def find_link(items, rest):
            for n in items:
                if n.get("slug") == rest:
                    return n
                if "items" in n:
                    r = find_link(n["items"], rest)
                    if r is not None:
                        return r
            return None

        # Starlight conversion: explicit lab labels, non-labs omitted.
        lab = find_link(self.starlight_sidebar,
                        "common/labs/computer-architecture")
        self.assertIsNotNone(lab)
        self.assertEqual(lab.get("label"), "1. Arch")
        nonlab = find_link(self.starlight_sidebar, "common/intro")
        self.assertIsNotNone(nonlab)
        self.assertNotIn("label", nonlab)
        self.assertIn("1. Arch", self.astro_text)
        # Matching prev/next pagination labels.
        from publishing.site import augment_projection_files
        aug = augment_projection_files(
            self.files, self.nav, self.identity, self.root)
        notes = aug["src/content/docs/en/common/labs/notes.md"]
        self.assertIn("21a. Appendix", notes)
        self.assertIn("1. First", notes)

    def test_github_source_links_and_i18n(self):
        from publishing.navigation import (VIEW_ON_GITHUB_LABELS,
                                            github_blob_url)
        url = github_blob_url(self.identity, "en/labs/common/notes.md")
        self.assertEqual(
            url, "https://github.com/O/R/blob/master/en/labs/common/notes.md")
        self.assertNotIn("/edit/", url)
        self.assertEqual(VIEW_ON_GITHUB_LABELS["en"], "View on GitHub")
        self.assertTrue(VIEW_ON_GITHUB_LABELS["ru"])
        # Per-page editUrl injected by site augmentation.
        from publishing.site import augment_projection_files
        aug = augment_projection_files(
            self.files, self.nav, self.identity, self.root)
        lab = aug["src/content/docs/en/common/labs/notes.md"]
        self.assertIn("editUrl:", lab)
        self.assertIn("/blob/master/en/labs/common/notes.md", lab)

    def test_pagefind_and_no_placeholders(self):
        self.assertIn("pagefind: true", self.astro_text)
        self.assertIn("remarkMath", self.astro_text)
        self.assertIn("rehypeKatex", self.astro_text)
        low = self.astro_text.lower()
        self.assertNotIn("/views/", low)
        self.assertNotIn("/presentations/", low)
        # Sidebar slugs all published.
        slugs = {e["slug"] for e in self.nav}
        def walk(items):
            for n in items:
                if "slug" in n:
                    self.assertTrue(f"en/{n['slug']}" in slugs or
                                    f"ru/{n['slug']}" in slugs)
                if "items" in n:
                    walk(n["items"])
        walk(self.starlight_sidebar)


class TestRepeatBuildClean(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_projection_identical_no_source_changes(self):
        before = snapshot(self.root)
        status_before = git("status", "--porcelain", cwd=self.root).stdout
        out1 = Path(self.tmp.name) / "out1"
        out2 = Path(self.tmp.name) / "out2"
        p1 = run_publish("projection", "build",
                         "--course-repo", str(self.root),
                         "--out", str(out1))
        self.assertEqual(p1.returncode, 0, p1.stdout + p1.stderr)
        p2 = run_publish("projection", "build",
                         "--course-repo", str(self.root),
                         "--out", str(out2))
        self.assertEqual(p2.returncode, 0, p2.stdout + p2.stderr)
        self.assertEqual(snapshot_tree(out1), snapshot_tree(out2))
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(git("status", "--porcelain", cwd=self.root).stdout,
                         status_before)

    def test_second_site_build_identical_no_tracked_files(self):
        import argparse
        from unittest import mock as _mock
        from publishing.site import run_site_build
        before = snapshot(self.root)
        status_before = git("status", "--porcelain", cwd=self.root).stdout
        out1 = Path(self.tmp.name) / "site1"
        out2 = Path(self.tmp.name) / "site2"
        for out in (out1, out2):
            args = argparse.Namespace(out=str(out), check=False)
            with _mock.patch("publishing.site.run_npm_build",
                             return_value=(0, "mock build")):
                code = run_site_build(self.root, args)
            self.assertEqual(code, 0)
        # Compare ignoring dist/.gitkeep timestamps? dist is placeholder
        # .gitkeep in mocked builds; compare all else + lesson/SVG bytes.
        t1 = snapshot_tree(out1)
        t2 = snapshot_tree(out2)
        # dist/.gitkeep may differ by existence after real-build cleanup;
        # both mocked have identical placeholders, so direct equality holds.
        self.assertEqual(t1, t2)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(git("status", "--porcelain", cwd=self.root).stdout,
                         status_before)


class TestBuiltOutputInspection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, compat_files())
        self.out = Path(self.tmp.name) / "site-out"
        import argparse
        from publishing.site import run_site_build
        args = argparse.Namespace(out=str(self.out), check=False)
        with mock.patch("publishing.site.run_npm_build",
                        return_value=(0, "mock build")):
            code = run_site_build(self.root, args)
        assert code == 0

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_forbidden_mermaid_client_code(self):
        from publishing.mermaid import check_no_mermaid_client_js
        self.assertEqual(check_no_mermaid_client_js(self.out), [])
        # Spot-check generated docs contain static SVG, no fences/bundles.
        text = read_projected(self.out, "en/guide/mermaid")
        self.assertIn("<svg", text)
        self.assertNotIn("```mermaid", text)
        self.assertNotIn("mermaid.min.js", text)
        self.assertNotIn("mermaid.initialize", text)

    def test_search_nav_assets_present(self):
        cfg = (self.out / "astro.config.mjs").read_text(encoding="utf-8")
        self.assertIn("pagefind: true", cfg)
        self.assertIn("pagination", cfg)
        for rel in ("nav.json", "site-nav.json", "astro.config.mjs",
                    "package.json", "src/content.config.ts",
                    "src/content/i18n/en.json", "src/content/i18n/ru.json",
                    "public/.nojekyll"):
            self.assertTrue((self.out / rel).is_file(), f"missing {rel}")
        nav = json.loads((self.out / "site-nav.json").read_text(
            encoding="utf-8"))
        self.assertIn("en", nav["sidebar"])
        self.assertIn("ru", nav["sidebar"])
        self.assertIn("redirects", nav)
        self.assertIn("base", nav)
        self.assertEqual(nav["base"], "/R/")
        # SITE-15 group redirects ship in the built project; only as
        # redirects (no listing content at those routes).
        self.assertEqual(nav["redirects"]["/en/cpp/"], "/en/cpp/intro/")
        self.assertEqual(nav["redirects"]["/ru/cpp/"],
                         "/ru/cpp/labs/assessment-1/")
        # Static SVGs served via public/.
        pub_svgs = sorted((self.out / "public" / "mermaid").glob("*.svg"))
        self.assertGreaterEqual(len(pub_svgs), 4)
        for p in pub_svgs:
            self.assertIn("<svg", p.read_text(encoding="utf-8"))
        # Pagefind indexed routes are existing published routes only.
        slugs = {e["slug"] for e in
                 json.loads((self.out / "nav.json").read_text(
                     encoding="utf-8"))}
        self.assertIn("en/common/labs/computer-architecture", slugs)
        self.assertNotIn("ru/dsa/arrays", slugs)


if __name__ == "__main__":
    unittest.main()
