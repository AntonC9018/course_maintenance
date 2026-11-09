"""Visualization tags, their source fences, and content-addressed trace generation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from publishing.visualization_config import (
    VisualizationOptions, contained_path, parse_visualizations,
)
from publishing.visualization_tags import scan_document
from publishing.visualization_traces import (
    VisualizationError, check_tags, ci_outputs, generate, trace_key, validate,
)

SOURCE = 'int a{5};\na = 7;'
TAG = '<!-- <visualization> -->\n\n<!-- </visualization> -->'


def document(source=SOURCE, marker=TAG):
    return f'```cpp\n{source}\n```\n\n<details>\n<summary>Answer</summary>\n\n{marker}\n</details>\n'


class ScanTest(unittest.TestCase):
    def test_paired_markers_with_and_without_template(self):
        for marker, template in [(TAG, None),
                                 ('<!-- <visualization template="memory"> -->\nlink\n'
                                  '<!-- </visualization> -->', 'memory')]:
            with self.subTest(marker=marker):
                text = document(marker=marker)
                result = scan_document(text)
                self.assertEqual(result.errors, [])
                tag = result.tags[0]
                self.assertEqual(tag.template, template)
                self.assertEqual(tag.source.source, SOURCE)
                self.assertEqual(text[tag.start:tag.end], marker)
                self.assertEqual(text[tag.body_start:tag.body_end].strip(),
                                 'link' if template else '')

    def test_answer_code_and_fake_html_in_code_do_not_replace_source(self):
        text = ('```cpp\nint a{5}; // <details>\n```\n<details>\n'
                '```cpp\nint fake{2};\n```\n<details>\n' + TAG + '\n</details>\n</details>')
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.tags[0].source.source, 'int a{5}; // <details>')
        self.assertEqual([f.depth for f in result.fences], [0, 1])

    def test_nearest_top_level_source_and_tilde_fences(self):
        text = ('```cpp\nint old{1};\n```\n'
                '~~~~c++\nint current{2};\n~~~\n~~~~\n<details>\n' + TAG + '\n</details>')
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.tags[0].source.source, 'int current{2};\n~~~')

    def test_multiline_opening_marker(self):
        marker = '<!-- <visualization\n  template="memory"> -->\n<!-- </visualization> -->'
        result = scan_document(document(marker=marker))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.tags[0].template, 'memory')

    def test_details_in_unrelated_multiline_comment_are_ignored(self):
        result = scan_document('<!--\n<details>\n-->\n' + document())
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tags), 1)
        self.assertEqual(result.tags[0].source.depth, 0)

    def test_unclosed_comment_does_not_expose_hidden_details_or_tags(self):
        result = scan_document('<!-- unclosed comment\n' + document())
        self.assertEqual(result.tags, [])
        self.assertIn('unclosed', result.errors[0])

    def test_uncommented_marker_is_reported(self):
        result = scan_document(document(marker='<visualization>'))
        self.assertEqual(result.tags, [])
        self.assertIn('HTML comment', result.errors[0])

    def test_non_cpp_nearest_fence_is_not_silently_skipped(self):
        text = '```cpp\nint a{5};\n```\n```python\na = 7\n```\n<details>\n' + TAG + '\n</details>'
        result = scan_document(text, 'lab.md')
        self.assertEqual(result.tags, [])
        self.assertIn('must be C++', result.errors[0])
        self.assertIn('lab.md:', result.errors[0])

    def test_invalid_markers_report_useful_errors(self):
        close = '\n<!-- </visualization> -->'
        for marker, expected in [
            ('<!-- <visualization type="animation"> -->' + close, 'expected'),
            ('<!-- <visualization template="Bad"> -->' + close, 'expected'),
            ('<!-- <visualization template="a" template="b"> -->' + close, 'expected'),
            ('<!-- <visualization /> -->' + close, 'expected'),
            ('<!-- <visualization> -->', 'closing'),
            ('<!-- </visualization> -->', 'no matching opening'),
            ('<!-- <visualization> -->\n' + TAG, 'closing'),
        ]:
            with self.subTest(marker=marker):
                result = scan_document(document(marker=marker))
                self.assertTrue(result.errors)
                self.assertIn(expected, result.errors[0])
        self.assertIn('inside', scan_document('```cpp\nint a;\n```\n' + TAG).errors[0])
        self.assertIn('no preceding', scan_document('<details>\n' + TAG).errors[0])

    def test_ordinary_comments_in_the_body_are_skipped(self):
        marker = ('<!-- <visualization> -->\n<!-- mentions </details>\n```\n-->\n'
                  '<!-- </visualization> -->')
        result = scan_document(document(marker=marker))
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tags), 1)

    def test_closing_marker_cannot_cross_details(self):
        text = document(marker='<!-- <visualization> -->') + '\n<!-- </visualization> -->\n'
        self.assertTrue(scan_document(text).errors)


class ConfigurationTest(unittest.TestCase):
    def test_no_config_is_noop_and_strict_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(parse_visualizations(None, root))
            base = {'roots': ['en/labs/cpp', 'ru/labs/cpp']}
            options = parse_visualizations(base, root)
            self.assertEqual(options, VisualizationOptions(roots=('en/labs/cpp', 'ru/labs/cpp')))
            for changes in ({'extra': 1}, {'roots': ['en', 'en/labs']}, {'roots': ['en', 'en']},
                            {'traces': '../outside'}, {'shell': 'a b'}, {'shell': 3},
                            {'repository': 'owner/course'}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    parse_visualizations({**base, **changes}, root)

    def test_symlink_and_lexical_escapes(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / 'escape').symlink_to(outside, target_is_directory=True)
            for name in ('../secret', '/tmp/secret', 'a/../secret', 'a\\b', './a', 'C:/a', 'escape/a'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    contained_path(root, name)


class GenerationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for lang in ('en', 'ru'):
            (self.root / lang).mkdir()
            (self.root / lang / 'lab.md').write_text(document())
        (self.root / 'visualizations').mkdir()
        self.options = VisualizationOptions(roots=('en', 'ru'))
        self.config = SimpleNamespace(visualizations=self.options)
        self.traces = self.root / self.options.traces
        self.commands = []
        self.revision = 'tracer-v1'
        self.failure = None

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, argv, **kwargs):
        self.commands.append(argv[2:])
        if argv[2] == 'revision':
            return self.revision
        if argv[2] == 'trace':
            if self.failure:
                raise VisualizationError(self.failure)
            source = Path(argv[argv.index('--source') + 1]).read_text()
            return json.dumps({'source': source})
        raise AssertionError(argv)

    def traced(self):
        return [c for c in self.commands if c[0] == 'trace']

    def stored(self):
        return sorted(path.name for path in self.traces.glob('*.json'))

    def test_languages_share_a_trace_and_a_second_run_traces_nothing(self):
        lessons = {p: p.read_bytes() for p in self.root.rglob('*.md')}
        self.assertEqual(validate(self.root, self.config, command=self.command)[0][-1:], '`')
        self.assertEqual(generate(self.root, self.config, command=self.command), [])
        key = trace_key(SOURCE, None, self.revision)
        self.assertEqual(self.stored(), [key + '.json'])
        self.assertEqual(json.loads((self.traces / f'{key}.json').read_text()),
                         {'source': SOURCE + '\n'})
        self.assertEqual(len(self.traced()), 1)
        self.assertEqual(generate(self.root, self.config, command=self.command), [])
        self.assertEqual(len(self.traced()), 1)
        self.assertEqual(validate(self.root, self.config, command=self.command), [])
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*.md')}, lessons)

    def test_source_template_and_revision_change_the_key(self):
        base = trace_key(SOURCE, None, 'r1')
        self.assertNotEqual(base, trace_key(SOURCE + ' ', None, 'r1'))
        self.assertNotEqual(base, trace_key(SOURCE, 'memory', 'r1'))
        self.assertNotEqual(base, trace_key(SOURCE, None, 'r2'))

    def test_template_override_reaches_the_tracer(self):
        marker = '<!-- <visualization template="memory"> -->\n<!-- </visualization> -->'
        (self.root / 'en' / 'lab.md').write_text(document(marker=marker))
        self.assertEqual(generate(self.root, self.config, command=self.command), [])
        self.assertIn(['--template', 'memory'], [c[-2:] for c in self.traced()])
        self.assertEqual(len(self.stored()), 2)

    def test_full_run_prunes_unused_traces_but_a_selected_run_does_not(self):
        self.traces.mkdir(parents=True)
        (self.traces / 'stale.json').write_text('{}')
        generate(self.root, self.config, [self.root / 'en' / 'lab.md'], command=self.command)
        self.assertIn('stale.json', self.stored())
        generate(self.root, self.config, command=self.command)
        self.assertNotIn('stale.json', self.stored())

    def test_trace_failure_names_the_lesson_line_and_stores_nothing(self):
        self.failure = 'generate.py exited 1: unsupported: pointers'
        errors = generate(self.root, self.config, command=self.command)
        self.assertEqual(len(errors), 1)
        self.assertRegex(errors[0], r'^(en|ru)/lab\.md:9: \[VIS\] cannot trace: .*pointers')
        self.assertEqual(self.stored(), [])

    def test_tag_errors_stop_generation_before_tracing(self):
        (self.root / 'en' / 'lab.md').write_text(document(marker='<!-- <visualization> -->'))
        errors = generate(self.root, self.config, command=self.command)
        self.assertTrue(errors)
        self.assertEqual(self.traced(), [])
        self.assertEqual(check_tags(self.root, self.config), errors)

    def test_check_tags_never_runs_the_tracer(self):
        self.assertEqual(check_tags(self.root, self.config), [])
        self.assertEqual(self.commands, [])

    def test_ci_outputs_change_only_with_the_trace_set(self):
        from unittest import mock
        with mock.patch('publishing.visualization_traces._command', self.command):
            first = ci_outputs(self.root, self.config)
            self.assertEqual(first['visualizations'], 'true')
            self.assertTrue(first['visualizations_shell'].endswith('#visualizations'))
            (self.root / 'en' / 'lab.md').write_text(document() + '\n')
            self.assertEqual(ci_outputs(self.root, self.config), first)
            (self.root / 'en' / 'lab.md').write_text(document(source='int b{1};'))
            self.assertNotEqual(ci_outputs(self.root, self.config)['visualizations_cache_key'],
                                first['visualizations_cache_key'])

    def test_config_absent_is_a_noop(self):
        config = SimpleNamespace(visualizations=None)
        self.assertEqual(generate(self.root, config, command=self.command), [])
        self.assertEqual(validate(self.root, config, command=self.command), [])
        self.assertEqual(ci_outputs(self.root, config), {'visualizations': 'false'})
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
