"""Visualization source lookup, minimal updates and lightweight CI boundaries."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError
import json
import tempfile
import unittest

from publishing.visualization_assets import (
    VisualizationError, asset_exists, generate, upload_asset, validate,
)
from publishing.visualization_config import (
    VisualizationOptions, contained_path, parse_visualizations,
)
from publishing.visualization_tags import project_visualizations, render_marker, scan_document

URL = 'https://github.com/user-attachments/assets/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
OTHER_URL = 'https://github.com/user-attachments/assets/ffffffff-bbbb-cccc-dddd-eeeeeeeeeeee'
SOURCE = 'int a{5};\na = 7;'


def document(source=SOURCE, marker='<!-- <visualization type="animation"> -->'):
    return f'```cpp\n{source}\n```\n\n<details>\n<summary>Answer</summary>\n\n{marker}\n</details>\n'


class SourceLookupTest(unittest.TestCase):
    def test_generated_link_is_inside_paired_markers(self):
        text = document()
        tag = scan_document(text).tags[0]
        generated = render_marker(tag, URL)
        expected = ('<!-- <visualization type="animation"> -->\n\n'
                    + URL + '\n\n<!-- </visualization> -->')
        self.assertEqual(generated, expected)
        updated = text[:tag.start] + generated + text[tag.embed_end:]
        result = scan_document(updated)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tags), 1)
        self.assertEqual(result.tags[0].src, URL)
        self.assertEqual(updated[result.tags[0].start:result.tags[0].embed_end], expected)
        projected = project_visualizations(updated)
        self.assertIn(f'src="{URL}"></video>', projected)
        self.assertNotIn('visualization>', projected)

    def test_empty_and_static_paired_markers(self):
        empty = '<!-- <visualization type="static" template="memory"> -->\n\n<!-- </visualization> -->'
        result = scan_document(document(marker=empty))
        self.assertEqual(result.errors, [])
        tag = result.tags[0]
        self.assertIsNone(tag.src)
        generated = render_marker(tag, URL)
        self.assertTrue(generated.startswith('<!-- <visualization type="static" template="memory"> -->'))
        self.assertTrue(generated.endswith('<!-- </visualization> -->'))
        self.assertIn('<img alt=""', generated)
        reread = scan_document(document(marker=generated))
        self.assertEqual(reread.errors, [])
        self.assertEqual(reread.tags[0].src, URL)

    def test_paired_marker_body_is_validated_and_closing_cannot_cross_details(self):
        for body in (URL + '\n' + OTHER_URL, 'unmanaged prose',
                     '<!-- <visualization type="animation"> -->\n' + URL):
            marker = '<!-- <visualization type="animation"> -->\n\n' + body + '\n\n<!-- </visualization> -->'
            with self.subTest(body=body):
                self.assertTrue(scan_document(document(marker=marker)).errors)
        self.assertTrue(scan_document(document(marker='<!-- </visualization> -->')).errors)
        crossed = document(marker='<!-- <visualization type="animation"> -->\n\n' + URL)
        crossed += '\n<!-- </visualization> -->'
        self.assertTrue(scan_document(crossed).errors)

    def test_legacy_marker_before_paired_marker_in_same_details(self):
        for suffix in ('>', ' />'):
            legacy = f'<!-- <visualization type="animation" src="{URL}"{suffix} -->\n\n{URL}'
            paired = ('<!-- <visualization type="animation"> -->\n\n'
                      + OTHER_URL + '\n\n<!-- </visualization> -->')
            with self.subTest(suffix=suffix):
                result = scan_document(document(marker=legacy + '\n\n' + paired))
                self.assertEqual(result.errors, [])
                self.assertEqual([tag.src for tag in result.tags], [URL, OTHER_URL])

    def test_github_attachment_paragraph_and_site_player_use_same_asset(self):
        text = document()
        tag = scan_document(text).tags[0]
        managed = render_marker(tag, URL)
        self.assertNotIn('<video', managed)
        self.assertIn('"> -->\n\n' + URL + '\n\n<!-- </visualization> -->', managed)
        text = text[:tag.start] + managed + text[tag.end:]
        projected = project_visualizations(text)
        self.assertIn('<video controls preload="metadata"', projected)
        self.assertIn('src="' + URL + '"></video>', projected)
        self.assertEqual(project_visualizations(projected), projected)
        self.assertEqual(scan_document(text).errors, [])
        self.assertEqual(text[scan_document(text).tags[0].start:
                              scan_document(text).tags[0].embed_end], managed)

    def test_projection_leaves_fenced_markers_and_unmanaged_urls_unchanged(self):
        text = '```html\n' + document() + '\n```\n\n' + URL + '\n'
        self.assertEqual(project_visualizations(text), text)

    def test_legacy_video_embed_is_consumed_when_upgrading(self):
        marker = f'<!-- <visualization type="animation" src="{URL}"> -->'
        text = document(marker=marker + f'\n<video controls src="{URL}"></video>')
        tag = scan_document(text).tags[0]
        updated = text[:tag.start] + render_marker(tag, URL) + text[tag.embed_end:]
        self.assertNotIn('<video', updated)
        self.assertEqual(updated.count(URL), 1)

    def test_answer_code_and_fake_html_in_code_do_not_replace_source(self):
        text = ('```cpp\nint a{5}; // <details>\n```\n<details>\n'
                '```cpp\nint fake{2};\n```\n<details>\n'
                '<!-- <visualization type="animation"> -->\n</details>\n</details>')
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tags), 1)
        self.assertEqual(result.tags[0].source.source, 'int a{5}; // <details>')
        self.assertEqual([f.depth for f in result.fences], [0, 1])

    def test_nearest_top_level_source_and_tilde_fences(self):
        text = ('```cpp\nint old{1};\n```\n'
                '~~~~c++\nint current{2};\n~~~\n~~~~\n'
                '<details>\n<!-- <visualization type="static"> -->\n</details>')
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.tags[0].source.source, 'int current{2};\n~~~')

    def test_multiline_marker_offsets_and_embed(self):
        text = document(marker=f'<!-- <visualization type="animation"\n src="{URL}"> -->')
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        tag = result.tags[0]
        generated = text[:tag.start] + render_marker(tag, URL) + text[tag.end:]
        reread = scan_document(generated)
        self.assertEqual(reread.errors, [])
        tag = reread.tags[0]
        self.assertEqual(generated[tag.start:tag.embed_end], render_marker(tag, URL))
        self.assertEqual(tag.src, URL)

    def test_details_in_unrelated_multiline_comment_are_ignored(self):
        text = ('<!--\n<details>\n-->\n' + document())
        result = scan_document(text)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.tags), 1)
        self.assertEqual(result.tags[0].source.depth, 0)

    def test_unclosed_comment_does_not_expose_hidden_details_or_tags(self):
        result = scan_document('<!-- unclosed comment\n' + document())
        self.assertEqual(result.tags, [])
        self.assertIn('unclosed', result.errors[0])

    def test_uncommented_marker_is_reported(self):
        result = scan_document(document(marker='<visualization type="animation">'))
        self.assertEqual(result.tags, [])
        self.assertIn('HTML comment', result.errors[0])

    def test_non_cpp_nearest_fence_is_not_silently_skipped(self):
        text = ('```cpp\nint a{5};\n```\n```python\na = 7\n```\n'
                '<details>\n<!-- <visualization type="animation"> -->\n</details>')
        result = scan_document(text, 'lab.md')
        self.assertEqual(len(result.tags), 0)
        self.assertIn('must be C++', result.errors[0])
        self.assertIn('lab.md:', result.errors[0])

    def test_invalid_markers_report_useful_errors(self):
        for marker, expected in [
            ('<!-- <visualization> -->', 'type must'),
            ('<!-- <visualization type="movie"> -->', 'type must'),
            ('<!-- <visualization type="animation" type="static"> -->', 'duplicate'),
            ('<!-- <visualization type="animation" hash="bad"> -->', 'unknown'),
            ('<!-- <visualization type="animation" src="https://evil.invalid/a"> -->', 'src must'),
            ('<!-- <visualization type="animation" -->', 'complete'),
        ]:
            with self.subTest(marker=marker):
                result = scan_document(document(marker=marker))
                self.assertTrue(result.errors)
                self.assertIn(expected, result.errors[0])
        self.assertIn('inside', scan_document('```cpp\nint a;\n```\n'
            '<!-- <visualization type="animation"> -->').errors[0])
        self.assertIn('no preceding', scan_document('<details>\n'
            '<!-- <visualization type="animation"> -->').errors[0])


class ConfigurationTest(unittest.TestCase):
    def test_no_config_is_noop_and_strict_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(parse_visualizations(None, root))
            base = {'roots': ['en/labs/cpp', 'ru/labs/cpp'],
                    'repository': 'owner/course', 'issue': 12}
            options = parse_visualizations(base, root)
            self.assertEqual(options.templates, 'visualizations')
            for changes in ({'extra': 1}, {'issue': True}, {'roots': ['en', 'en/labs']},
                            {'manifest': '../outside'}, {'repository': 'broken'},
                            {'roots': ['en', 'en']}):
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
        self.options = VisualizationOptions(roots=('en', 'ru'), repository='owner/course', issue=12)
        self.config = SimpleNamespace(visualizations=self.options)
        self.commands = []
        self.uploads = []
        self.revision = 'renderer-v1'

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, argv, **kwargs):
        self.commands.append(argv)
        operation = argv[2]
        if operation == 'revision':
            return self.revision
        if operation == 'probe':
            return json.dumps({'supported': True})
        if operation == 'render':
            Path(argv[argv.index('--output') + 1]).write_bytes(b'video')
            return ''
        raise AssertionError(argv)

    def upload(self, path, options, body):
        self.uploads.append(path.read_bytes())
        return URL if len(self.uploads) == 1 else OTHER_URL

    def run_generate(self, **overrides):
        kwargs = {'command': self.command, 'uploader': self.upload, 'exists': lambda _: True}
        kwargs.update(overrides)
        return generate(self.root, self.config, **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_translations_dedupe_and_second_run_is_byte_identical(self):
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(len(self.uploads), 1)
        self.assertEqual(sum(command[2] == 'render' for command in self.commands), 1)
        before = self.snapshot()
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(self.uploads), 1)
        self.assertEqual(validate(self.root, self.config), [])
        body = (self.root / 'en/lab.md').read_text()
        self.assertNotIn('<video', body)
        self.assertIn('\n\n' + URL + '\n', body)
        self.assertIn(URL, body)

    def test_upgrading_legacy_embeds_reuses_upload_and_manifest(self):
        self.assertEqual(self.run_generate(), [])
        manifest = (self.root / self.options.manifest).read_bytes()
        for lang in ('en', 'ru'):
            legacy = f'<!-- <visualization type="animation" src="{URL}" /> -->\n\n{URL}'
            (self.root / lang / 'lab.md').write_text(document(marker=legacy))
        self.commands.clear()
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(len(self.uploads), 1)
        self.assertFalse(any(command[2] in {'probe', 'render'} for command in self.commands))
        self.assertEqual((self.root / self.options.manifest).read_bytes(), manifest)
        self.assertEqual(validate(self.root, self.config), [])
        self.assertEqual((self.root / 'en/lab.md').read_bytes(),
                         (self.root / 'ru/lab.md').read_bytes())

    def test_source_and_renderer_changes_regenerate(self):
        self.assertEqual(self.run_generate(), [])
        path = self.root / 'en/lab.md'
        path.write_text(path.read_text().replace('a = 7;', 'a = 8;'))
        self.assertIn('stale', validate(self.root, self.config)[0])
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(len(self.uploads), 2)
        self.revision = 'renderer-v2'
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(len(self.uploads), 4)
        manifest = json.loads((self.root / self.options.manifest).read_text())
        self.assertEqual(len(manifest['assets']), 4)  # old URLs remain recoverable

    def test_inconclusive_availability_never_renders_uploads_or_changes_sources(self):
        self.assertEqual(self.run_generate(), [])
        before = self.snapshot()
        self.commands.clear()
        def offline(_):
            raise VisualizationError('cannot verify asset availability')
        errors = self.run_generate(exists=offline)
        self.assertEqual(len(errors), 2)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.uploads), 1)
        self.assertFalse(any(command[2] in {'probe', 'render'} for command in self.commands))
        self.assertEqual(len(validate(self.root, self.config, remote=True, exists=offline)), 2)

    def test_moved_tag_reuses_asset(self):
        self.assertEqual(self.run_generate(), [])
        path = self.root / 'en/lab.md'
        target = path.with_name('renamed.md')
        path.rename(target)
        self.assertEqual(self.run_generate(), [])
        self.assertEqual(len(self.uploads), 1)

    def test_failed_render_preserves_existing_markup_and_manifest(self):
        self.assertEqual(self.run_generate(), [])
        self.revision = 'renderer-v2'
        before = self.snapshot()
        def fail(argv, **kwargs):
            if argv[2] == 'render':
                raise VisualizationError('render unavailable')
            return self.command(argv, **kwargs)
        errors = self.run_generate(command=fail)
        self.assertEqual(len(errors), 2)
        self.assertIn('existing media retained', errors[0])
        self.assertEqual(self.snapshot(), before)

    def test_failed_upload_preserves_old_markup(self):
        self.assertEqual(self.run_generate(), [])
        self.revision = 'renderer-v2'
        before = self.snapshot()
        def fail(*args):
            raise VisualizationError('upload unavailable')
        self.assertTrue(self.run_generate(uploader=fail))
        self.assertEqual(before, self.snapshot())

    def test_unsupported_source_and_missing_render_output(self):
        def unsupported(argv, **kwargs):
            return '{"supported":false,"reason":"pointer"}' if argv[2] == 'probe' else self.command(argv)
        self.assertIn('unsupported snippet: pointer', self.run_generate(command=unsupported)[0])
        self.assertEqual(self.uploads, [])
        def missing(argv, **kwargs):
            return '' if argv[2] == 'render' else self.command(argv)
        self.assertIn('nonempty asset', self.run_generate(command=missing)[0])

    def test_ci_checks_do_not_spawn_tools_and_dedupe_http(self):
        self.assertEqual(self.run_generate(), [])
        with mock.patch('subprocess.run', side_effect=AssertionError('CI spawned a tool')):
            calls = []
            def exists(url):
                calls.append(url)
                return True
            self.assertEqual(validate(self.root, self.config, remote=True, exists=exists), [])
            self.assertEqual(calls, [URL])
            errors = validate(self.root, self.config, remote=True, exists=lambda _: False)
            self.assertEqual(len(errors), 2)
            self.assertIn('unavailable', errors[0])

    def test_selected_file_does_not_modify_other_language(self):
        before = (self.root / 'ru/lab.md').read_text()
        self.assertEqual(self.run_generate(selected_paths=[self.root / 'en/lab.md']), [])
        self.assertEqual(before, (self.root / 'ru/lab.md').read_text())
        self.assertEqual(len(self.uploads), 1)

    def test_config_absent_has_no_subprocesses_or_network(self):
        config = SimpleNamespace(visualizations=None)
        with mock.patch('subprocess.run', side_effect=AssertionError), mock.patch('urllib.request.urlopen', side_effect=AssertionError):
            self.assertEqual(generate(self.root, config), [])
            self.assertEqual(validate(self.root, config, remote=True), [])


class TransportTest(unittest.TestCase):
    def test_head_not_allowed_uses_one_byte_range(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 206
        error = HTTPError(URL, 405, 'method', None, None)
        with mock.patch('publishing.visualization_assets.urlopen', side_effect=[error, response]) as open_url:
            self.assertTrue(asset_exists(URL))
        second = open_url.call_args_list[1].args[0]
        self.assertEqual(second.get_header('Range'), 'bytes=0-0')

    def test_missing_asset_is_not_accepted(self):
        error = HTTPError(URL, 404, 'missing', None, None)
        with mock.patch('publishing.visualization_assets.urlopen', side_effect=error) as open_url:
            self.assertFalse(asset_exists(URL))
            self.assertEqual(open_url.call_count, 1)

    def test_transient_availability_failure_retries_without_reporting_missing(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        with mock.patch('publishing.visualization_assets.urlopen',
                        side_effect=[OSError('temporary outage'), response]) as request:
            self.assertTrue(asset_exists(URL))
            self.assertEqual(request.call_count, 2)

    def test_unverified_availability_is_an_error_not_missing(self):
        with mock.patch('publishing.visualization_assets.urlopen', side_effect=OSError('offline')):
            with self.assertRaisesRegex(VisualizationError, 'cannot verify'):
                asset_exists(URL)

    def test_upload_uses_body_file_and_retrieves_resulting_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / 'body.md'
            (Path(tmp) / 'asset.mp4').write_bytes(b'video')
            options = VisualizationOptions(repository='owner/course', issue=12)
            responses = ['https://github.com/owner/course/issues/12#issuecomment-42',
                         json.dumps({'body': '<video src="' + URL + '"></video>'})]
            with mock.patch('publishing.visualization_assets._command', side_effect=responses) as command:
                self.assertEqual(upload_asset(Path(tmp) / 'asset.mp4', options, body), URL)
            self.assertIn('--body-file', command.call_args_list[0].args[0])
            self.assertEqual(command.call_args_list[1].args[0][-1], 'repos/owner/course/issues/comments/42')

    def test_comment_fetch_retry_does_not_reupload(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / 'asset.mp4'
            asset.write_bytes(b'video')
            replies = ['https://github.com/o/r/issues/1#issuecomment-42',
                       VisualizationError('temporary fetch failure'), json.dumps({'body': URL})]
            with mock.patch('publishing.visualization_assets._command', side_effect=replies) as command:
                self.assertEqual(upload_asset(asset, VisualizationOptions(repository='o/r', issue=1),
                                              Path(tmp) / 'body.md'), URL)
            self.assertEqual(sum(call.args[0][1:3] == ['issue', 'comment']
                                 for call in command.call_args_list), 1)
            self.assertEqual(command.call_count, 3)

    def test_upload_retries_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'asset.mp4').write_bytes(b'video')
            with mock.patch('publishing.visualization_assets._command', side_effect=VisualizationError('network')) as command:
                with self.assertRaisesRegex(VisualizationError, 'two attempts'):
                    upload_asset(Path(tmp) / 'asset.mp4', VisualizationOptions(repository='o/r', issue=1),
                                 Path(tmp) / 'body.md')
            self.assertEqual(command.call_count, 2)


if __name__ == '__main__':
    unittest.main()
