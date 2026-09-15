"""Route and link resolution (issue #9, LINK-1..LINK-8).

TDD seam: publishing.links + link validation inside `publishing check`.
All repos live in TemporaryDirectory; never mutates live checkouts.
Stdlib-only.
"""

import json
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
    return root


def load_all(root: Path):
    from publishing.config import load_config
    from publishing.identity import infer_identity
    from publishing.inventory import build_inventory
    from publishing.metadata import collect_metadata_state
    config = load_config(root)
    identity = infer_identity(root)
    inventory = build_inventory(root, config)
    final, errors, _missing = collect_metadata_state(
        root, config, inventory, identity.pages_url)
    assert not errors, errors
    return config, identity, inventory, final


class TestLinkIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/01_intro.md": "# i\n",
            "ru/lesson.md": "# r\n",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_maps_normalized_abs_paths_to_canonical(self):
        from publishing.links import build_link_index
        config, identity, inventory, final = load_all(self.root)
        index = build_link_index(self.root, config, identity,
                                 inventory, final)
        lesson_rel = "en/guide/01_intro.md"
        abs_key = str((self.root / lesson_rel).resolve())
        self.assertIn(abs_key, index.lessons)
        entry = index.lessons[abs_key]
        self.assertEqual(entry.slug, final[lesson_rel])
        self.assertTrue(entry.canonical_url.startswith(identity.pages_url))
        self.assertTrue(entry.canonical_url.endswith("/"))

    def test_canonical_matches_backlink_logic(self):
        from publishing.links import build_link_index
        from publishing.metadata import expected_backlink_url
        config, identity, inventory, final = load_all(self.root)
        index = build_link_index(self.root, config, identity,
                                 inventory, final)
        for abs_key, entry in index.lessons.items():
            self.assertEqual(
                entry.canonical_url,
                expected_backlink_url(identity.pages_url, entry.slug))

    def test_index_deterministic_usable_without_starlight(self):
        from publishing.links import build_link_index
        config, identity, inventory, final = load_all(self.root)
        a = build_link_index(self.root, config, identity, inventory, final)
        b = build_link_index(self.root, config, identity, inventory, final)
        self.assertEqual(a.to_deterministic_dict(),
                         b.to_deterministic_dict())
        # No renderer needed: canonical URLs are absolute https.
        for _k, url in a.to_deterministic_dict().items():
            self.assertTrue(url.startswith("https://"))


class TestResolveTargets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        cfg = json.loads(json.dumps(BASE_CONFIG))
        cfg["exclude"] = ["en/excluded.md"]
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md":
                "# Root\n\nSee [intro](../guide/01_intro.md).\n",
            "en/guide/01_intro.md": "# Intro\n",
            "en/excluded.md": "# Ex\n",
            "en/assets/code.py": "print(1)\n",
            "en/assets/pic.png": b"\x89PNG",
            "en/subdir/note.txt": "hi\n",
            "ru/lesson.md": "# r\n",
        }, cfg=cfg)
        self.config, self.identity, self.inventory, self.final = load_all(
            self.root)
        from publishing.links import build_link_index
        self.index = build_link_index(
            self.root, self.config, self.identity,
            self.inventory, self.final)

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, source_rel, dest, is_image=False):
        from publishing.links import resolve_link
        src = (self.root / source_rel).resolve()
        return resolve_link(src, dest, is_image=is_image, index=self.index)

    def test_published_markdown_to_canonical_trailing_slash(self):
        out = self._resolve("en/labs/common/01_computer_architecture.md",
                            "../../guide/01_intro.md")
        self.assertEqual(out.kind, "canonical")
        self.assertIn("/en/guide/intro/", out.url)
        self.assertTrue(out.url.startswith(self.identity.pages_url))
        self.assertTrue(out.url.endswith("/"))
        self.assertIsNone(out.copy_source)

    def test_excluded_markdown_to_blob_master(self):
        out = self._resolve("en/guide/01_intro.md", "../excluded.md")
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("/blob/master/en/excluded.md", out.url)
        self.assertIn("github.com", out.url)
        self.assertIsNone(out.copy_source)

    def test_ordinary_file_to_blob_master(self):
        out = self._resolve("en/guide/01_intro.md",
                            "../assets/code.py")
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("/blob/master/en/assets/code.py", out.url)

    def test_directory_to_tree_master(self):
        out = self._resolve("en/guide/01_intro.md", "../assets")
        self.assertEqual(out.kind, "github-tree")
        self.assertIn("/tree/master/en/assets", out.url)

    def test_image_syntax_marked_for_copying(self):
        out = self._resolve("en/guide/01_intro.md",
                            "../assets/pic.png", is_image=True)
        self.assertEqual(out.kind, "image")
        self.assertIsNotNone(out.copy_source)
        self.assertTrue(str(out.copy_source).endswith("pic.png"))
        self.assertIsNotNone(out.copy_rel)
        # Rewritten destination points at the copied asset, not GitHub.
        self.assertNotIn("github.com", out.url)
        self.assertIn("pic.png", out.url)

    def test_link_syntax_to_same_image_is_github_not_copy(self):
        out = self._resolve("en/guide/01_intro.md",
                            "../assets/pic.png", is_image=False)
        self.assertEqual(out.kind, "github-blob")
        self.assertIsNone(out.copy_source)

    def test_img_tag_src_marked_for_copying(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_intro.md").resolve()
        text = ('---\ntitle: T\nslug: en/guide/intro\n---\n'
                '<img src="../assets/pic.png" alt="p">\n')
        new_text, copies, errors = rewrite_document(src, text, self.index)
        self.assertEqual(errors, [])
        self.assertEqual(len(copies), 1)
        self.assertTrue(str(copies[0][0]).endswith("pic.png"))
        self.assertNotIn("github.com", new_text)

    def test_only_embedded_images_copied(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_intro.md").resolve()
        text = ('---\ntitle: T\nslug: en/guide/intro\n---\n'
                '![a](../assets/pic.png)\n'
                '[b](../assets/code.py)\n'
                '[c](../excluded.md)\n')
        _new, copies, errors = rewrite_document(src, text, self.index)
        self.assertEqual(errors, [])
        self.assertEqual(len(copies), 1)
        self.assertTrue(str(copies[0][0]).endswith("pic.png"))

    def test_query_and_fragment_preserved_canonical(self):
        out = self._resolve("en/labs/common/01_computer_architecture.md",
                            "../../guide/01_intro.md?x=1&y=2#intro")
        self.assertEqual(out.kind, "canonical")
        self.assertTrue(out.url.endswith("?x=1&y=2#intro"))

    def test_query_frag_preserved_blob_and_tree(self):
        blob = self._resolve("en/guide/01_intro.md",
                             "../assets/code.py?dl=1#L10")
        self.assertTrue(blob.url.endswith("?dl=1#L10"))
        tree = self._resolve("en/guide/01_intro.md",
                             "../assets?x=1#f")
        self.assertTrue(tree.url.endswith("?x=1#f"))

    def test_query_frag_preserved_image(self):
        out = self._resolve("en/guide/01_intro.md",
                            "../assets/pic.png?v=2#frag", is_image=True)
        self.assertTrue(out.url.endswith("?v=2#frag"))
        self.assertIsNotNone(out.copy_source)

    def test_encoded_path_resolves(self):
        write(self.root / "en/guide/my file.md", "# M\n")
        # re-resolve: file exists on disk (not necessarily a lesson)
        out = self._resolve("en/labs/common/01_computer_architecture.md",
                            "../../guide/my%20file.md")
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("my%20file.md", out.url)

    def test_default_branch_always_master(self):
        out = self._resolve("en/guide/01_intro.md", "../excluded.md")
        self.assertIn("/blob/master/", out.url)
        d = self._resolve("en/guide/01_intro.md", "../assets")
        self.assertIn("/tree/master/", d.url)


class TestLinkErrors(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/01_intro.md": "# i\n",
            "en/Actual.md": "# a\n",
            "ru/lesson.md": "# r\n",
        })
        self.config, self.identity, self.inventory, self.final = load_all(
            self.root)
        from publishing.links import build_link_index
        self.index = build_link_index(
            self.root, self.config, self.identity,
            self.inventory, self.final)

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, source_rel, dest, is_image=False):
        from publishing.links import resolve_link
        src = (self.root / source_rel).resolve()
        return resolve_link(src, dest, is_image=is_image, index=self.index)

    def test_missing_target_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_intro.md", "./does-not-exist.md")
        self.assertIn("LINK-7", str(ctx.exception))
        self.assertIn("missing", str(ctx.exception).lower())

    def test_escaping_target_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_intro.md", "../../../etc/passwd")
        msg = str(ctx.exception)
        self.assertIn("LINK-7", msg)
        self.assertIn("escap", msg.lower())

    def test_ambiguous_case_mismatch_rejected_not_guessed(self):
        from publishing.links import LinkError
        # on-disk is Actual.md; link uses wrong case -> ambiguous, no fallback
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_intro.md", "../actual.md")
        msg = str(ctx.exception)
        self.assertIn("LINK-7", msg)
        self.assertIn("ambiguous", msg.lower())

    def test_unsupported_absolute_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_intro.md", "/en/guide/01_intro.md")
        self.assertIn("LINK-7", str(ctx.exception))

    def test_unsupported_scheme_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/01_intro.md", "file:///etc/passwd")
        self.assertIn("LINK-7", str(ctx.exception))

    def test_external_left_alone_by_rewriter(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_intro.md").resolve()
        text = ('---\ntitle: T\nslug: en/guide/intro\n---\n'
                '[e](https://example.com/x) [m](mailto:a@b.c)\n')
        new_text, copies, errors = rewrite_document(src, text, self.index)
        self.assertEqual(errors, [])
        self.assertEqual(copies, [])
        self.assertIn("https://example.com/x", new_text)


class TestAnchorValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "main"
        make_repo(self.root, {
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/01_intro.md":
                "# Hello World\n\n## My Section!\n",
            "en/guide/02_other.md": "# o\n",
            "ru/lesson.md": "# r\n",
        })
        self.config, self.identity, self.inventory, self.final = load_all(
            self.root)
        from publishing.links import build_link_index
        self.index = build_link_index(
            self.root, self.config, self.identity,
            self.inventory, self.final)

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, source_rel, dest, is_image=False):
        from publishing.links import resolve_link
        src = (self.root / source_rel).resolve()
        return resolve_link(src, dest, is_image=is_image, index=self.index)

    def test_valid_heading_fragment_passes(self):
        out = self._resolve("en/guide/02_other.md",
                            "./01_intro.md#hello-world")
        self.assertEqual(out.kind, "canonical")
        self.assertTrue(out.url.endswith("#hello-world"))

    def test_github_slug_rules_applied(self):
        # "## My Section!" -> "my-section" per github_slug
        out = self._resolve("en/guide/02_other.md",
                            "./01_intro.md#my-section")
        self.assertTrue(out.url.endswith("#my-section"))

    def test_invalid_anchor_rejected(self):
        from publishing.links import LinkError
        with self.assertRaises(LinkError) as ctx:
            self._resolve("en/guide/02_other.md",
                          "./01_intro.md#no-such-heading")
        self.assertIn("LINK-8", str(ctx.exception))

    def test_anchor_only_validated_against_source(self):
        from publishing.links import rewrite_document
        src = (self.root / "en/guide/01_intro.md").resolve()
        ok_text = ('---\ntitle: T\nslug: en/guide/intro\n---\n'
                   '[a](#hello-world)\n')
        _n, _c, errors = rewrite_document(src, ok_text, self.index)
        self.assertEqual(errors, [])
        bad_text = ('---\ntitle: T\nslug: en/guide/intro\n---\n'
                    '[a](#missing-heading)\n')
        _n2, _c2, errors2 = rewrite_document(src, bad_text, self.index)
        self.assertEqual(len(errors2), 1)
        self.assertIn("LINK-8", errors2[0])

    def test_uses_maintenance_github_slug(self):
        import publishing.links as pl
        import inspect
        src = inspect.getsource(pl)
        self.assertIn("github_slug", src)
        self.assertNotIn("def github_slug", src)


class TestPeerResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.peer = base / "peer"
        make_repo(self.peer, {
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/peer_lesson.md": "# Peer\n",
            "en/data.txt": "d\n",
            "ru/lesson.md": "# r\n",
        }, origin="https://github.com/Peer/PeerRepo.git")
        self.root = base / "main"
        init_repo_with_origin(self.root, "https://github.com/O/R.git")
        cfg = json.loads(json.dumps(BASE_CONFIG))
        cfg["peer_repositories"] = ["../peer"]
        write_config(self.root, cfg)
        for rel, content in {
            "en/labs/common/01_computer_architecture.md": "# t\n",
            "en/guide/01_intro.md": "# i\n",
            "ru/lesson.md": "# r\n",
        }.items():
            write(self.root / rel, content)
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        assert gen.returncode == 0, gen.stdout + gen.stderr
        from publishing.config import load_config
        from publishing.identity import infer_identity
        from publishing.inventory import build_inventory
        from publishing.metadata import collect_metadata_state
        from publishing.links import build_link_index
        self.config = load_config(self.root)
        self.identity = infer_identity(self.root)
        self.inventory = build_inventory(self.root, self.config)
        final, errors, _m = collect_metadata_state(
            self.root, self.config, self.inventory,
            self.identity.pages_url)
        assert not errors, errors
        self.final = final
        self.index = build_link_index(
            self.root, self.config, self.identity,
            self.inventory, self.final)

    def tearDown(self):
        self.tmp.cleanup()

    def test_peer_lesson_resolves_to_peer_canonical(self):
        from publishing.links import resolve_link
        src = (self.root / "en/guide/01_intro.md").resolve()
        out = resolve_link(src, "../../../peer/en/peer_lesson.md",
                           is_image=False, index=self.index)
        self.assertEqual(out.kind, "canonical")
        self.assertIn("Peer.github.io/PeerRepo", out.url)
        self.assertIn("/en/peer-lesson/", out.url)
        # main identity unchanged
        self.assertNotIn("O.github.io", out.url)

    def test_peer_file_to_peer_blob(self):
        from publishing.links import resolve_link
        src = (self.root / "en/guide/01_intro.md").resolve()
        out = resolve_link(src, "../../../peer/en/data.txt",
                           is_image=False, index=self.index)
        self.assertEqual(out.kind, "github-blob")
        self.assertIn("github.com/Peer/PeerRepo/blob/master/", out.url)

    def test_peer_identity_preserved_without_changing_main(self):
        # peer slug format identical (language-prefixed) but base differs
        peer_key = str((self.peer / "en/peer_lesson.md").resolve())
        self.assertIn(peer_key, self.index.lessons)
        entry = self.index.lessons[peer_key]
        self.assertTrue(entry.slug.startswith("en/"))
        self.assertIn("Peer.github.io", entry.canonical_url)


class TestCheckIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _valid_repo(self):
        init_repo_with_origin(self.root, "https://github.com/O/R.git")
        write_config(self.root)
        write(self.root / "en/labs/common/01_computer_architecture.md",
              "# t\n")
        write(self.root / "en/guide/01_intro.md", "# i\n")
        write(self.root / "ru/lesson.md", "# r\n")
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        assert gen.returncode == 0, gen.stdout + gen.stderr
        return self.root

    def test_check_passes_with_good_links(self):
        self._valid_repo()
        p = self.root / "en/guide/01_intro.md"
        t = p.read_text(encoding="utf-8")
        # add a valid relative link to the published root lesson
        t = t + "\nSee [root](../labs/common/01_computer_architecture.md).\n"
        p.write_text(t, encoding="utf-8")
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_check_fails_on_missing_link_with_path_rule_fix(self):
        self._valid_repo()
        p = self.root / "en/guide/01_intro.md"
        t = p.read_text(encoding="utf-8")
        t = t + "\nSee [bad](./missing-target.md).\n"
        p.write_text(t, encoding="utf-8")
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("en/guide/01_intro.md", combined)
        self.assertIn("LINK", combined)
        self.assertIn("fix", combined.lower())
        self.assertIn("publishing check", combined)

    def test_check_fails_on_bad_anchor(self):
        self._valid_repo()
        target = self.root / "en/labs/common/01_computer_architecture.md"
        tt = target.read_text(encoding="utf-8")
        # ensure a known heading exists in target
        if "## Known" not in tt:
            target.write_text(tt + "\n## Known Heading\n", encoding="utf-8")
        p = self.root / "en/guide/01_intro.md"
        t = p.read_text(encoding="utf-8")
        t = t + ("\nSee [a](../labs/common/01_computer_architecture.md"
                 "#no-such-anchor).\n")
        p.write_text(t, encoding="utf-8")
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("LINK-8", proc.stdout + proc.stderr)

    def test_check_readonly_on_link_error(self):
        import os
        self._valid_repo()
        p = self.root / "en/guide/01_intro.md"
        p.write_text(p.read_text(encoding="utf-8")
                     + "\n[x](./missing.md)\n", encoding="utf-8")

        def snap(root):
            out = {}
            for dp, dns, fns in os.walk(root):
                if ".git" in Path(dp).parts:
                    continue
                dns[:] = [d for d in dns if d != ".git"]
                for fn in fns:
                    q = Path(dp) / fn
                    out[str(q.resolve())] = q.read_bytes()
            return out
        before = snap(self.root)
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(snap(self.root), before)


if __name__ == "__main__":
    unittest.main()
