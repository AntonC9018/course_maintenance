"""Publishing configuration + lesson inventory (issue #7, CFG-1..CFG-6).

TDD seam: publishing.config / publishing.identity / publishing.inventory
+ `publishing check` read-only validation wired into publish.py.

All repos live in TemporaryDirectory; tests never mutate live checkouts.
Stdlib-only (unittest + subprocess git for inference fixtures).
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


def init_repo_with_origin(root: Path, origin_url, branch="master"):
    """Init a git repo at root with one commit and (optionally) an origin."""
    r = git("init", "-b", branch, cwd=root)
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


VALID_CONFIG = {
    "version": 1,
    "default_language": "en",
    "languages": [
        {"code": "en", "root": "en", "label": "English"},
        {"code": "ru", "root": "ru", "label": "Русский"},
    ],
    "exclude": [
        "en/05_programming_fundamentals/linker_examples/README.md",
    ],
    "route_sections": [
        {"source": "00_introduction", "destination": "common"},
        {"source": "labs/common", "destination": "common/labs"},
    ],
    "site_title": {
        "en": "Programming Fundamentals and Data Structures",
        "ru": "Основы программирования и структуры данных",
    },
    "root_lesson": "en/labs/common/01_computer_architecture.md",
    "peer_repositories": [],
}


def write_config(root: Path, cfg=None):
    cfg = VALID_CONFIG if cfg is None else cfg
    write(root / "course-publishing.json", json.dumps(cfg, ensure_ascii=False, indent=2))
    return root / "course-publishing.json"


def make_valid_tree(root: Path):
    """Minimal file tree satisfying VALID_CONFIG (root lesson + excluded)."""
    write(root / "en/labs/common/01_computer_architecture.md", "# t\n")
    write(root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
    write(root / "en/extra.md", "# e\n")
    write(root / "ru/lesson.md", "# r\n")
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
                out[str(p.resolve())] = (p.stat().st_mtime_ns, p.read_bytes())
            except OSError:
                pass
    # also record dir list to catch new files
    names = set(out.keys())
    return names, out


class TestValidConfigParse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_config_parses(self):
        from publishing.config import load_config
        write_config(self.root)
        make_valid_tree(self.root)
        cfg = load_config(self.root)
        self.assertEqual(cfg.version, 1)
        self.assertEqual(cfg.default_language, "en")
        self.assertEqual([l.code for l in cfg.languages], ["en", "ru"])
        self.assertEqual([l.root for l in cfg.languages], ["en", "ru"])
        self.assertIn("en/05_programming_fundamentals/linker_examples/README.md",
                      cfg.exclude)
        self.assertEqual(len(cfg.route_sections), 2)
        self.assertEqual(cfg.root_lesson,
                         "en/labs/common/01_computer_architecture.md")
        self.assertEqual(list(cfg.peer_repositories), [])
        self.assertIn("en", cfg.site_title)


class TestConfigRejections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_valid_tree(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, cfg):
        from publishing.config import load_config
        write_config(self.root, cfg)
        return load_config(self.root)

    def assertRejects(self, cfg, *needles):
        from publishing.config import ConfigError
        write_config(self.root, cfg)
        with self.assertRaises(ConfigError) as ctx:
            from publishing.config import load_config
            load_config(self.root)
        msg = str(ctx.exception).lower()
        for n in needles:
            self.assertIn(n.lower(), msg, f"expected {n!r} in: {ctx.exception}")

    def cfg_with(self, **over):
        c = json.loads(json.dumps(VALID_CONFIG))
        c.update(over)
        return c

    def test_unknown_top_field(self):
        self.assertRejects(self.cfg_with(extra_field=1), "unknown", "course-publishing.json")

    def test_unknown_language_field(self):
        c = self.cfg_with()
        c["languages"] = [{"code": "en", "root": "en", "label": "E", "bogus": 1},
                          {"code": "ru", "root": "ru", "label": "R"}]
        self.assertRejects(c, "unknown")

    def test_unknown_route_field(self):
        c = self.cfg_with()
        c["route_sections"] = [{"source": "a", "destination": "b", "bogus": 1}]
        self.assertRejects(c, "unknown")

    def test_bad_version(self):
        for v in (0, 2, "1", None):
            with self.subTest(version=v):
                c = self.cfg_with(version=v)
                self.assertRejects(c, "version")

    def test_duplicate_language_codes(self):
        c = self.cfg_with()
        c["languages"] = [{"code": "en", "root": "en", "label": "E"},
                          {"code": "en", "root": "ru", "label": "R"}]
        self.assertRejects(c, "duplicate", "code")

    def test_duplicate_language_roots(self):
        c = self.cfg_with()
        c["languages"] = [{"code": "en", "root": "en", "label": "E"},
                          {"code": "ru", "root": "en", "label": "R"}]
        self.assertRejects(c, "duplicate", "root")

    def test_duplicate_codes_casefold(self):
        c = self.cfg_with()
        c["languages"] = [{"code": "en", "root": "en", "label": "E"},
                          {"code": "EN", "root": "ru", "label": "R"}]
        self.assertRejects(c, "duplicate")

    def test_absolute_paths_rejected(self):
        c = self.cfg_with()
        c["languages"] = [{"code": "en", "root": "/en", "label": "E"},
                          {"code": "ru", "root": "ru", "label": "R"}]
        self.assertRejects(c, "absolute", "en")
        c = self.cfg_with(exclude=["/en/extra.md"])
        self.assertRejects(c, "absolute")
        c = self.cfg_with(root_lesson="/en/labs/common/01_computer_architecture.md")
        self.assertRejects(c, "absolute")

    def test_escaping_paths_rejected(self):
        c = self.cfg_with(exclude=["../outside.md"])
        self.assertRejects(c, "escap")
        c = self.cfg_with(exclude=["en/../../etc/passwd"])
        self.assertRejects(c, "escap")
        c = self.cfg_with(root_lesson="en/../ru/lesson.md")
        # contains .. -> non-canonical / escaping
        self.assertRejects(c, "escap", "root_lesson")

    def test_backslash_rejected(self):
        c = self.cfg_with(exclude=["en\\extra.md"])
        self.assertRejects(c, "slash", "exclude")

    def test_overlapping_route_mappings(self):
        c = self.cfg_with(route_sections=[
            {"source": "labs", "destination": "a"},
            {"source": "labs/common", "destination": "b"},
        ])
        self.assertRejects(c, "overlap", "labs")
        c2 = self.cfg_with(route_sections=[
            {"source": "labs/common", "destination": "a"},
            {"source": "labs/common", "destination": "b"},
        ])
        self.assertRejects(c2, "overlap", "duplicate")

    def test_unknown_root_lesson_missing(self):
        c = self.cfg_with(root_lesson="en/labs/common/99_missing.md")
        self.assertRejects(c, "root_lesson", "unknown")

    def test_unknown_root_lesson_excluded(self):
        c = self.cfg_with(
            exclude=["en/labs/common/01_computer_architecture.md"],
            root_lesson="en/labs/common/01_computer_architecture.md",
        )
        self.assertRejects(c, "root_lesson", "exclud")

    def test_unknown_root_lesson_outside_roots(self):
        write(self.root / "outside.md", "# o\n")
        c = self.cfg_with(root_lesson="outside.md")
        self.assertRejects(c, "root_lesson")

    def test_exclusions_outside_roots(self):
        c = self.cfg_with(exclude=["other/foo.md"])
        self.assertRejects(c, "exclud", "outside", "other/foo.md")
        # prefix trap: en2/ is not under en/
        write(self.root / "en2/foo.md", "# x\n")
        c2 = self.cfg_with(exclude=["en2/foo.md"])
        self.assertRejects(c2, "exclud", "outside")

    def test_site_title_unknown_key(self):
        c = self.cfg_with(site_title={"en": "E", "ru": "R", "de": "D"})
        self.assertRejects(c, "site_title", "de")

    def test_site_title_missing_language(self):
        c = self.cfg_with(site_title={"en": "E"})
        self.assertRejects(c, "site_title", "ru")

    def test_default_language_unknown(self):
        c = self.cfg_with(default_language="de")
        self.assertRejects(c, "default_language", "de")

    def test_peer_absolute_rejected(self):
        c = self.cfg_with(peer_repositories=["/abs/path"])
        self.assertRejects(c, "absolute", "peer")


class TestIdentityInference(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ssh_origin(self):
        from publishing.identity import infer_identity
        init_repo_with_origin(self.root, "git@github.com:AntonC9018/uniCourse_dataStructuresAndAlgorithms.git")
        ident = infer_identity(self.root)
        self.assertEqual(ident.owner, "AntonC9018")
        self.assertEqual(ident.repo, "uniCourse_dataStructuresAndAlgorithms")
        self.assertEqual(ident.github_url, "https://github.com/AntonC9018/uniCourse_dataStructuresAndAlgorithms")
        self.assertIn("AntonC9018.github.io", ident.pages_url)
        self.assertIn("uniCourse_dataStructuresAndAlgorithms", ident.pages_url)
        self.assertEqual(ident.default_branch, "master")

    def test_https_origin_with_and_without_git(self):
        from publishing.identity import infer_identity
        for url in ("https://github.com/Owner/Repo.git",
                    "https://github.com/Owner/Repo",
                    "https://github.com/Owner/Repo/"):
            with self.subTest(url=url):
                d = self.root / "sub"
                d.mkdir(exist_ok=True)
                # fresh repo per subtest
                import tempfile as tf
                with tf.TemporaryDirectory() as td:
                    r = Path(td)
                    init_repo_with_origin(r, url)
                    ident = infer_identity(r)
                    self.assertEqual(ident.owner, "Owner")
                    self.assertEqual(ident.repo, "Repo")
                    self.assertEqual(ident.default_branch, "master")

    def test_missing_origin_is_validation_error(self):
        from publishing.identity import IdentityError, infer_identity
        init_repo_with_origin(self.root, None)
        with self.assertRaises(IdentityError) as ctx:
            infer_identity(self.root)
        msg = str(ctx.exception)
        self.assertIn("origin", msg.lower())
        self.assertIn("CFG-5", msg)
        self.assertIn("git remote add origin", msg)

    def test_renamed_remote_is_missing_origin(self):
        from publishing.identity import IdentityError, infer_identity
        init_repo_with_origin(self.root, "git@github.com:O/R.git")
        git("remote", "rename", "origin", "upstream", cwd=self.root)
        with self.assertRaises(IdentityError) as ctx:
            infer_identity(self.root)
        self.assertIn("origin", str(ctx.exception).lower())

    def test_detached_head_still_infers(self):
        from publishing.identity import infer_identity
        init_repo_with_origin(self.root, "git@github.com:O/R.git")
        git("checkout", "--detach", "HEAD", cwd=self.root)
        ident = infer_identity(self.root)
        self.assertEqual(ident.owner, "O")
        self.assertEqual(ident.repo, "R")
        self.assertEqual(ident.default_branch, "master")

    def test_missing_git_is_validation_error(self):
        from publishing.identity import IdentityError, infer_identity
        # plain dir, no .git
        with self.assertRaises(IdentityError) as ctx:
            infer_identity(self.root)
        self.assertIn("origin", str(ctx.exception).lower())

    def test_non_github_origin_rejected(self):
        from publishing.identity import IdentityError, infer_identity
        init_repo_with_origin(self.root, "https://gitlab.com/O/R.git")
        with self.assertRaises(IdentityError):
            infer_identity(self.root)

    def test_master_default_branch_even_on_main(self):
        from publishing.identity import infer_identity
        init_repo_with_origin(self.root, "git@github.com:O/R.git", branch="main")
        ident = infer_identity(self.root)
        self.assertEqual(ident.default_branch, "master")


class TestInventorySelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _load(self, cfg=None):
        from publishing.config import load_config
        write_config(self.root, VALID_CONFIG if cfg is None else cfg)
        return load_config(self.root)

    def test_selects_md_under_roots_then_exclusions(self):
        from publishing.inventory import build_inventory
        write(self.root / "en/a.md", "# a\n")
        write(self.root / "en/b.txt", "x")
        write(self.root / "en/sub/c.md", "# c\n")
        write(self.root / "ru/d.md", "# d\n")
        write(self.root / "other/e.md", "# e\n")
        write(self.root / "en/excluded.md", "# x\n")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        cfg = json.loads(json.dumps(VALID_CONFIG))
        cfg["exclude"] = ["en/excluded.md",
                          "en/05_programming_fundamentals/linker_examples/README.md"]
        config = self._load(cfg)
        inv = build_inventory(self.root, config)
        rels = sorted(l.repo_rel for l in inv.lessons)
        self.assertIn("en/a.md", rels)
        self.assertIn("en/sub/c.md", rels)
        self.assertIn("ru/d.md", rels)
        self.assertIn("en/labs/common/01_computer_architecture.md", rels)
        self.assertNotIn("en/b.txt", rels)
        self.assertNotIn("other/e.md", rels)
        self.assertNotIn("en/excluded.md", rels)
        self.assertNotIn("en/05_programming_fundamentals/linker_examples/README.md", rels)
        # language assignment
        by_rel = {l.repo_rel: l.language for l in inv.lessons}
        self.assertEqual(by_rel["en/a.md"], "en")
        self.assertEqual(by_rel["ru/d.md"], "ru")

    def test_empty_and_stub_remain_valid(self):
        from publishing.inventory import build_inventory
        write(self.root / "en/empty.md", "")
        write(self.root / "en/stub.md", "# stub\n")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        write(self.root / "ru/lesson.md", "# r\n")
        config = self._load()
        inv = build_inventory(self.root, config)
        rels = {l.repo_rel for l in inv.lessons}
        self.assertIn("en/empty.md", rels)
        self.assertIn("en/stub.md", rels)

    def test_casefold_duplicate_sources_rejected(self):
        from publishing.inventory import InventoryError
        write(self.root / "en/Foo.md", "# a\n")
        write(self.root / "en/foo.md", "# b\n")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        write(self.root / "ru/lesson.md", "# r\n")
        config = self._load()
        with self.assertRaises(InventoryError) as ctx:
            from publishing.inventory import build_inventory
            build_inventory(self.root, config)
        self.assertIn("CFG-6", str(ctx.exception))
        self.assertIn("foo", str(ctx.exception).lower())

    def test_unicode_normalization_duplicates_rejected(self):
        from publishing.inventory import InventoryError
        # NFC vs NFD forms of café
        write(self.root / "en/caf\u00e9.md", "# a\n")  # NFC é
        write(self.root / "en/cafe\u0301.md", "# b\n")  # e + combining acute
        # sanity: distinct byte names on linux
        names = sorted(p.name for p in (self.root / "en").iterdir())
        if len(names) < 2 or names[0] == names[1]:
            self.skipTest("filesystem normalizes unicode names")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        write(self.root / "ru/lesson.md", "# r\n")
        config = self._load()
        with self.assertRaises(InventoryError) as ctx:
            from publishing.inventory import build_inventory
            build_inventory(self.root, config)
        self.assertIn("CFG-6", str(ctx.exception))

    def test_config_path_case_mismatch_rejected(self):
        from publishing.inventory import InventoryError
        from publishing.config import ConfigError
        write(self.root / "en/foo.md", "# a\n")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        write(self.root / "ru/lesson.md", "# r\n")
        cfg = json.loads(json.dumps(VALID_CONFIG))
        cfg["exclude"] = ["en/FOO.md"]
        write_config(self.root, cfg)
        try:
            from publishing.config import load_config
            config = load_config(self.root)
        except ConfigError as e:
            self.assertIn("CFG-6", str(e))
            return
        # if config load allows it, inventory must reject
        from publishing.inventory import build_inventory
        with self.assertRaises((InventoryError, ConfigError)) as ctx:
            build_inventory(self.root, config)
        self.assertIn("CFG-6", str(ctx.exception))

    def test_deterministic_sorted_order(self):
        from publishing.inventory import build_inventory
        write(self.root / "en/z.md", "# z\n")
        write(self.root / "en/a.md", "# a\n")
        write(self.root / "en/labs/common/01_computer_architecture.md", "# r\n")
        write(self.root / "en/05_programming_fundamentals/linker_examples/README.md", "# x\n")
        write(self.root / "ru/lesson.md", "# r\n")
        config = self._load()
        inv = build_inventory(self.root, config)
        rels = [l.repo_rel for l in inv.lessons]
        self.assertEqual(rels, sorted(rels))


class TestPublishingCheckReadOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _valid_repo(self, origin="git@github.com:O/R.git"):
        init_repo_with_origin(self.root, origin)
        # origin commit already has placeholder; add course files
        write_config(self.root)
        make_valid_tree(self.root)
        # Issue #8: publishing check includes META validation, so a valid
        # repo needs generated slugs + backlinks.
        gen = run_publish("metadata", "generate",
                          "--course-repo", str(self.root))
        assert gen.returncode == 0, gen.stdout + gen.stderr
        git("add", "-A", cwd=self.root)
        git("commit", "-m", "course", cwd=self.root)
        return self.root

    def test_check_valid_returns_zero_and_readonly(self):
        self._valid_repo()
        before_names, before_state = snapshot(self.root)
        proc = run_publish("publishing", "check", "--course-repo", str(self.root))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        after_names, after_state = snapshot(self.root)
        self.assertEqual(before_names, after_names, "check must not create files")
        self.assertEqual(before_state, after_state, "check must not modify files")

    def test_check_missing_metadata_fails_with_regen_hint(self):
        # Without `metadata generate`, publishing check must reject missing
        # slugs/backlinks (META-7) and tell the contributor the exact command.
        init_repo_with_origin(self.root, "git@github.com:O/R.git")
        write_config(self.root)
        make_valid_tree(self.root)
        proc = run_publish("publishing", "check",
                           "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("META", combined)
        self.assertIn("metadata generate", combined)
        self.assertIn("--course-repo", combined)

    def test_check_invalid_returns_nonzero_and_readonly(self):
        self._valid_repo()
        # break config: unknown field
        cfg = json.loads((self.root / "course-publishing.json").read_text())
        cfg["bogus"] = 1
        (self.root / "course-publishing.json").write_text(json.dumps(cfg))
        git("add", "-A", cwd=self.root)
        git("commit", "-m", "break", cwd=self.root)
        before_names, before_state = snapshot(self.root)
        proc = run_publish("publishing", "check", "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertIn("cfg", combined)
        self.assertIn("course-publishing.json", combined)
        after_names, after_state = snapshot(self.root)
        self.assertEqual(before_names, after_names)
        self.assertEqual(before_state, after_state)

    def test_check_missing_origin_reports_action(self):
        init_repo_with_origin(self.root, None)
        write_config(self.root)
        make_valid_tree(self.root)
        proc = run_publish("publishing", "check", "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("origin", combined.lower())
        self.assertIn("CFG-5", combined)
        self.assertIn("git remote add origin", combined)

    def test_check_missing_config_is_error(self):
        init_repo_with_origin(self.root, "git@github.com:O/R.git")
        proc = run_publish("publishing", "check", "--course-repo", str(self.root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("course-publishing.json", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
