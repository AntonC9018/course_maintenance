"""Site links in tag bodies, players in the projection, and site-wide assets."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from publishing.site_assets import head_entries, parse_site_assets
from publishing.visualization_site import (
    broken_site_links, heading_anchors, link_body, player, with_players, with_site_links,
)
from tests.helpers import run_publish, write
from tests.test_publishing_projection import (
    BASE_CONFIG, init_repo_with_origin, read_projected, write_config,
)

TAG = '<!-- <visualization> -->\n<!-- </visualization> -->'
PAGE = 'https://o.github.io/r/en/cpp/labs/variables/'


def lesson(heading='### 4. Assigning one variable to another', marker=TAG):
    return (f'# 2. Variables\n\n{heading}\n```cpp\nint a = 5;\na = 7;\n```\n\n'
            f'<details>\n<summary>Execution trace</summary>\n\n{marker}\n\n</details>\n')


class AnchorTest(unittest.TestCase):
    def test_github_slugger_rules(self):
        for heading, expected in [
            ('### 4. Assigning one variable to another', '4-assigning-one-variable-to-another'),
            ('### 5. Literals, variables and operators are expressions',
             '5-literals-variables-and-operators-are-expressions'),
            ('## `const` and `int&` -- references', 'const-and-int--references'),
            ('## `a--b` --- c', 'a--b--c'),
            ('### 1. Объявление переменной', '1-объявление-переменной'),
            ('### **Bold** [link](x.md) _it_', 'bold-link-it'),
            ('## `vector<int>`', 'vectorint'),
            ('## A &amp; B', 'a--b'),
            ('## `&amp;` and \\*x\\*', 'amp-and-x'),
            ('## ``a ` b``', 'a--b'),
        ]:
            with self.subTest(heading=heading):
                self.assertEqual(heading_anchors(heading + '\n')[0][1], expected)

    def test_duplicates_fences_and_the_page_title(self):
        text = ('# Title\n## A\n```cpp\n# not a heading\n```\n## A\n## A-1\n## A\n')
        self.assertEqual([slug for _, slug in heading_anchors(text)], ['a', 'a-1', 'a-1-1', 'a-2'])
        two = '# One\n# Two\n'
        self.assertEqual([slug for _, slug in heading_anchors(two)], ['one', 'two'])


class LinkTest(unittest.TestCase):
    def test_body_links_to_the_nearest_heading_and_is_idempotent(self):
        linked = with_site_links(lesson(), 'en', PAGE)
        expected = link_body('en', PAGE, '4-assigning-one-variable-to-another')
        self.assertIn('<!-- <visualization> -->' + expected + '<!-- </visualization> -->', linked)
        self.assertEqual(with_site_links(linked, 'en', PAGE), linked)
        stale = linked.replace('#4-assigning', '#3-assigning')
        self.assertEqual(with_site_links(stale, 'en', PAGE), linked)

    def test_localized_label_and_no_heading(self):
        self.assertIn('[▶ Пошаговое выполнение на сайте курса](' + PAGE + ')',
                      with_site_links(lesson(heading=''), 'ru', PAGE))
        self.assertIn('[▶ Step through', link_body('de', PAGE, None))


class BuiltSiteTest(unittest.TestCase):
    def test_links_are_checked_against_built_heading_ids(self):
        from types import SimpleNamespace
        from publishing.visualization_config import VisualizationOptions
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / 'en/lab.md', with_site_links(lesson(), 'en', PAGE))
            config = SimpleNamespace(visualizations=VisualizationOptions(roots=('en',)))
            page = root / 'dist/en/cpp/labs/variables/index.html'
            self.assertIn('missing page', broken_site_links(root, config, 'https://o.github.io/r',
                                                            root / 'dist')[0])
            write(page, '<h3 id="4-assigning-one-variable">')
            self.assertIn('not a heading id', broken_site_links(
                root, config, 'https://o.github.io/r', root / 'dist')[0])
            write(page, '<h3 id="4-assigning-one-variable-to-another">')
            self.assertEqual(broken_site_links(root, config, 'https://o.github.io/r', root / 'dist'), [])


class PlayerTest(unittest.TestCase):
    def test_player_is_one_line_and_cannot_close_its_script(self):
        html = player(json.dumps({'source': ['</script><b>', 'a b'], 'n': 1}, indent=2))
        self.assertNotIn('\n', html)
        self.assertNotIn('</script><b>', html)
        self.assertTrue(html.startswith('<div class="course-visualization">'
                                        '<script type="application/json">'))
        data = html.split('json">', 1)[1].rsplit('</script>', 1)[0]
        self.assertEqual(json.loads(data)['source'][0], '</script><b>')

    def test_with_players_replaces_tags_and_reports_missing_ones(self):
        text = lesson() + lesson(marker=TAG.replace('<visualization>', '<visualization template="x">'))
        projected, missing = with_players(text, lambda tag: None if tag.template else '{"a":1}')
        self.assertEqual(projected.count('course-visualization'), 1)
        self.assertEqual([tag.template for tag in missing], ['x'])
        self.assertIn('template="x"', projected)


class SiteAssetsTest(unittest.TestCase):
    def test_parse_and_head_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / 'p/player.js', '')
            write(root / 'p/player.css', '')
            assets = parse_site_assets({'scripts': ['p/player.js'], 'styles': ['p/player.css']}, root)
            self.assertEqual(head_entries(assets, '/r/'), [
                {'tag': 'link', 'attrs': {'rel': 'stylesheet', 'href': '/r/site-assets/p/player.css'}},
                {'tag': 'script', 'attrs': {'src': '/r/site-assets/p/player.js', 'defer': True}},
            ])
            for raw in ({'scripts': ['p/player.css']}, {'scripts': ['missing.js']},
                        {'scripts': ['../x.js']}, {'fonts': []}, {'scripts': 'p/player.js'}):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    parse_site_assets(raw, root)


FAKE_TRACER = '''import json, sys
if sys.argv[1] == "revision":
    print("fake-1")
else:
    source = open(sys.argv[sys.argv.index("--source") + 1]).read()
    print(json.dumps({"format": 1, "source": source}))
'''


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'course'
        self.out = Path(self.tmp.name) / 'out'
        init_repo_with_origin(self.root, 'https://github.com/O/R.git')
        config = dict(BASE_CONFIG, visualizations={'roots': ['en/labs']},
                      site_assets={'scripts': ['visualizations/player.js']})
        write_config(self.root, config)
        write(self.root / 'visualizations/generate.py', FAKE_TRACER)
        write(self.root / 'visualizations/player.js', '')
        write(self.root / 'en/labs/common/01_computer_architecture.md', lesson())
        write(self.root / 'ru/lesson.md', '# R\n')

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, *args):
        return run_publish(*args, '--course-repo', str(self.root))

    def test_generate_link_trace_check_and_project(self):
        self.assertEqual(self.publish('metadata', 'generate').returncode, 0)
        source = (self.root / 'en/labs/common/01_computer_architecture.md').read_text()
        self.assertIn('[▶ Step through this example on the course site](https://O.github.io/R/'
                      'en/common/labs/computer-architecture/#4-assigning-one-variable-to-another)',
                      source)
        check = self.publish('publishing', 'check')
        self.assertNotEqual(check.returncode, 0)
        self.assertIn('missing trace', check.stderr)
        self.assertEqual(self.publish('visualizations', 'generate').returncode, 0)
        check = self.publish('publishing', 'check')
        self.assertEqual(check.returncode, 0, check.stderr)
        stale = source.replace('#4-assigning', '#9-assigning')
        (self.root / 'en/labs/common/01_computer_architecture.md').write_text(stale)
        check = self.publish('publishing', 'check')
        self.assertIn('[VIS] missing or stale site link', check.stderr)
        (self.root / 'en/labs/common/01_computer_architecture.md').write_text(source)
        build = run_publish('projection', 'build', '--course-repo', str(self.root),
                            '--out', str(self.out))
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        projected = read_projected(self.out, 'en/common/labs/computer-architecture')
        self.assertIn('<div class="course-visualization"><script type="application/json">'
                      '{"format":1,"source":"int a = 5;\\na = 7;\\n"}</script></div>', projected)
        self.assertNotIn('Step through', projected)
        self.assertNotIn('visualization> -->', projected)


if __name__ == '__main__':
    unittest.main()
