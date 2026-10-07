"""Catalog provenance, output containment, metadata persistence and real legacy cases."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse
import wave

from PIL import Image

import library_api as api
import testing_support as tempfile


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(api, 'ROOT', self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)
        api.HASH_CACHE.clear()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def project(self, name, state, output=None):
        folder = self.root / 'projects/studio' / name
        self.write(folder / 'status.json', state)
        if output:
            target = folder / output
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.suffix == '.png':
                Image.new('RGB', (80, 64), (100, 50, 20)).save(target)
            elif target.suffix == '.wav':
                with wave.open(str(target), 'wb') as stream:
                    stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
                    stream.writeframes(b'\x01\0' * 8000)
            else:
                target.write_bytes(b'known-deliverable')
        return folder

    def reference(self, image):
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        identity = 'img-' + digest[:24]
        store = self.root / 'assets/image-references'
        self.write(store / (identity + '.json'), {'id': identity, 'file': identity + '.png', 'sha256': digest,
                   'name': '参考图', 'created_at': 2, 'width': 80, 'height': 64})
        (store / (identity + '.png')).write_bytes(image.read_bytes())
        return identity

    def test_primary_outputs_only_with_legacy_kind_and_real_geometry(self):
        folder = self.project('a' * 12, {'status': 'done', 'image': '/outputs/unsafe/else.png'}, 'image.png')
        self.write(folder / 'prompt.json', {'prompt': '橙色笔记本插画', 'source_url': 'https://example.org/original'})
        (folder / 'frames').mkdir(); Image.new('RGB', (64, 64)).save(folder / 'frames/0001.png')
        self.write(self.root / 'assets/voices/sources/private.json', {'secret': 'do not expose'})
        (self.root / 'assets/voices/reference.wav').write_bytes(b'not a work product')
        rows = api.catalog()['items']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['workflow'], row['media_type']), ('image', 'image'))
        self.assertEqual((row['width'], row['height']), (80, 64))
        self.assertEqual(row['title'], '橙色笔记本插画')
        self.assertEqual(row['provenance_url'], 'https://example.org/original')
        self.assertEqual(row['source_url'], '/image')
        self.assertEqual(row['download_url'], '/outputs/' + 'a' * 12 + '/image.png')
        self.assertGreater(row['created_at'], 0)
        self.assertNotIn('private', json.dumps(rows))

    def test_done_preview_and_draft_are_not_falsely_completed_films(self):
        self.project('whiteboard-1111111111', {'kind': 'whiteboard', 'status': 'done'}, 'video.mp4')
        preview = self.project('investigation-2222222222', {'kind': 'investigation', 'status': 'done'}, 'cover-4x3.png')
        self.write(preview / 'storyboard.json', {'title': 'Only a preview', 'scenes': []})
        self.write(preview / 'investigation.manifest.json', {'estimated_duration': True, 'duration_seconds': 600})
        draft = self.project('whiteboard-3333333333', {'kind': 'whiteboard', 'status': 'done'})
        self.write(draft / 'storyboard.json', {'title': 'Only a draft', 'scenes': []})
        self.assertEqual(api.catalog()['total'], 1)
        rows = {row['project_id']: row for row in api.catalog(status='all')['items']}
        self.assertEqual(rows[preview.name]['status'], 'preview')
        self.assertIsNone(rows[preview.name]['download_url'])
        self.assertIsNone(rows[preview.name]['duration_seconds'])
        self.assertEqual(rows[draft.name]['status'], 'draft')
        self.assertEqual(rows[draft.name]['source_url'], '/whiteboard?project=' + draft.name)

    def test_live_job_state_overrides_saved_done_without_publishing_missing_paths(self):
        folder = self.project('motion-1111111111', {'kind': 'motion', 'status': 'done'}, 'video.mp4')
        live = {folder.name: {'kind': 'motion', 'status': 'running', 'phase': 'sampling'},
                'story-2222222222': {'kind': 'story', 'status': 'queued'}, '../secret': {'status': 'done'}}
        self.assertEqual(api.catalog(jobs=live)['total'], 0)
        rows = api.catalog(status='all', jobs=live)['items']
        self.assertEqual(len(rows), 2)
        temporary = next(row for row in rows if row['temporary'])
        self.assertIsNone(temporary['absolute_path'])
        self.assertIsNone(temporary['download_url'])
        self.assertEqual(next(row for row in rows if row['project_id'] == folder.name)['phase'], 'sampling')

    def test_assets_include_generated_visuals_deduplicate_registered_reference_and_separate_sfx(self):
        image = self.project('b' * 12, {'status': 'done'}, 'image.png')
        ref_id = self.reference(image / 'image.png')
        self.project('motion-1111111111', {'kind': 'motion', 'status': 'done'}, 'video.mp4')
        self.project('music-1111111111', {'kind': 'music', 'status': 'done', 'engine': 'ace-step-1.5'}, 'bgm.wav')
        self.project('music-2222222222', {'kind': 'music', 'status': 'done', 'engine': 'stable-audio-3-sfx'}, 'sfx.wav')
        self.project('speech-1111111111', {'kind': 'speech', 'status': 'done'}, 'audio/preview.wav')
        assets = api.catalog(view='assets')['items']
        self.assertEqual(len(assets), 5)
        generated = next(row for row in assets if row['workflow'] == 'image')
        self.assertEqual(generated['reference_id'], ref_id)
        self.assertEqual({row['workflow'] for row in assets}, {'image', 'motion', 'music', 'sfx', 'speech'})
        self.assertEqual(api.catalog(view='assets', kind='audio')['total'], 3)
        self.assertEqual(api.catalog(view='assets', kind='sfx')['total'], 1)
        self.assertEqual(api.catalog(view='assets', kind='image-reference')['total'], 1)
        self.assertEqual(next(row for row in api.catalog()['items'] if row['project_id'] == image.name)['id'], generated['id'])

    def test_only_registered_contained_media_and_existing_deliverables_are_exposed(self):
        folder = self.project('investigation-1111111111', {'kind': 'investigation', 'status': 'done'}, 'video.mp4')
        self.write(folder / 'storyboard.json', {'title': 'Teaching', 'scenes': []})
        self.write(folder / 'sources.csv', 'sources')
        (folder / 'assets/media').mkdir(parents=True)
        Image.new('RGB', (80, 64)).save(folder / 'assets/media/registered.png')
        self.write(folder / 'media.json', [
            {'id': 'media-' + 'a' * 20, 'kind': 'image', 'path': 'assets/media/registered.png', 'description': 'Registered'},
            {'id': 'media-' + 'b' * 20, 'kind': 'image', 'path': 'assets/media/../../image.png'},
            {'id': 'media-' + 'c' * 20, 'kind': 'image', 'path': str(self.root / 'private.png')},
            {'id': 'media-' + 'd' * 20, 'kind': 'image', 'path': 'assets/media/missing.png'}])
        assets = api.catalog(view='assets', kind='registered-media')['items']
        self.assertEqual(len(assets), 1)
        self.assertTrue(assets[0]['absolute_path'].endswith('registered.png'))
        deliverables = api.catalog()['items'][0]['deliverables']
        self.assertEqual({row['kind'] for row in deliverables}, {'video', 'storyboard', 'sources'})
        self.assertFalse(any('missing' in row['url'] for row in deliverables))

    def test_metadata_changes_are_stable_atomic_and_never_rename_original_file(self):
        folder = self.project('c' * 12, {'status': 'done'}, 'image.png')
        source = folder / 'image.png'
        before = source.read_bytes()
        identity = api.catalog()['items'][0]['id']
        saved = api.save_metadata({'id': identity, 'title': '新的标题', 'favorite': True, 'tags': ['角色', '角色', '插画']})['item']
        self.assertEqual(saved['id'], identity)
        self.assertEqual(saved['tags'], ['角色', '插画'])
        self.assertEqual(api.catalog(q='新的 角色', favorite='1')['total'], 1)
        self.assertEqual(source.read_bytes(), before)
        metadata = self.root / 'config/library-metadata.json'
        original = metadata.read_bytes()
        with patch.object(api.os, 'replace', side_effect=OSError('simulated interrupted replacement')):
            with self.assertRaises(OSError):
                api.save_metadata({'id': identity, 'title': 'must not commit'})
        self.assertEqual(metadata.read_bytes(), original)
        self.assertEqual(list(metadata.parent.glob('*.tmp')), [])
        self.assertEqual(source.read_bytes(), before)

    def test_whiteboard_sources_and_chinese_documents_require_registered_safe_existing_paths(self):
        job = 'whiteboard-4444444444'
        prefix = '/outputs/' + job + '/'
        folder = self.project(job, {'kind': 'whiteboard', 'status': 'done', 'sources': [
            prefix + 'scenes/scene01.excalidraw.md', prefix + 'sources/scene02.excalidraw',
            prefix + 'sources/missing.excalidraw', prefix + 'sources/scene02.excalidraw',
            prefix + 'qa/private.excalidraw', prefix + 'sources/%2e%2e/qa/private.excalidraw',
            '/outputs/whiteboard-other/sources/scene02.excalidraw',
            'https://example.org' + prefix + 'sources/scene02.excalidraw',
            'https://[invalid-url', prefix + 'sources/scene02.excalidraw?download=1']}, 'video.mp4')
        for name in ('scenes/scene01.excalidraw.md', 'sources/scene02.excalidraw',
                     'sources/not-registered.excalidraw', 'qa/private.excalidraw', '旁白稿.md', '发布.md'):
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('editable or publication source', encoding='utf-8')
        rows = api.catalog()['items'][0]['deliverables']
        sources = [row for row in rows if row['kind'] == 'excalidraw']
        self.assertEqual({row['url'] for row in sources}, {
            prefix + 'scenes/scene01.excalidraw.md', prefix + 'sources/scene02.excalidraw'})
        self.assertEqual(sum(row['kind'] == 'script' for row in rows), 1)
        self.assertEqual(sum(row['kind'] == 'publishing' for row in rows), 1)
        (folder / '发布.md').unlink()
        self.assertFalse(any(row['kind'] == 'publishing' for row in api.catalog()['items'][0]['deliverables']))
        outside = self.root / 'another-project/sources'
        outside.mkdir(parents=True)
        (outside / 'scene02.excalidraw').write_text('must not expose another project', encoding='utf-8')
        resolve = Path.resolve
        def redirected(path, *args, **kwargs):
            return outside if path == folder / 'sources' else resolve(path, *args, **kwargs)
        with patch.object(Path, 'resolve', redirected):
            rows = api.catalog()['items'][0]['deliverables']
        self.assertEqual([row['url'] for row in rows if row['kind'] == 'excalidraw'], [prefix + 'scenes/scene01.excalidraw.md'])

    def test_metadata_rejects_unknown_id_paths_control_characters_and_bad_types(self):
        self.project('d' * 12, {'status': 'done'}, 'image.png')
        identity = api.catalog()['items'][0]['id']
        invalid = [{'id': '../secret', 'favorite': True}, {'id': 'lib-' + '0' * 24, 'title': 'Fake'},
                   {'id': identity, 'path': 'elsewhere'}, {'id': identity, 'title': 'line\nbreak'},
                   {'id': identity, 'favorite': 1}, {'id': identity, 'tags': 'tag'},
                   {'id': identity, 'tags': ['x' * 33]}, {'id': identity}]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                api.save_metadata(request)
        self.assertFalse((self.root / 'config/library-metadata.json').exists())

    def test_persistent_novel_drafts_have_safe_stable_download_and_item_lookup(self):
        folder = self.root / 'projects/drafts'
        self.write(folder / ('e' * 12 + '.json'), {'title': 'Persisted novel', 'scenes': [{'narration': 'test'}]})
        self.write(folder / 'private-settings.json', {'scenes': [], 'secret': 'not registered'})
        self.assertEqual(api.catalog()['total'], 0)
        draft = api.catalog(status='draft')['items'][0]
        handler = MagicMock()
        self.assertTrue(api.get(handler, urlparse('/api/library/item?id=' + draft['id'])))
        self.assertEqual(handler.reply.call_args.args[0]['item']['draft_id'], 'e' * 12)
        handler.reset_mock()
        api.get(handler, urlparse(draft['download_url']))
        handler.send_file.assert_called_once_with(folder / ('e' * 12 + '.json'))
        self.assertEqual(draft['source_url'], '/novel?draft=' + draft['id'])
        for url in ['/api/library/file?path=' + str(folder / 'private-settings.json'),
                    '/api/library/item?id=lib-' + '0' * 24, '/api/library?status=all&status=done']:
            handler.reset_mock(); api.get(handler, urlparse(url))
            self.assertEqual(handler.reply.call_args.args[1], 400)
            handler.send_file.assert_not_called()

    def test_one_malformed_job_is_skipped_but_corrupt_metadata_is_not_overwritten(self):
        folder = self.project('f' * 12, {'status': 'done'}, 'image.png')
        invalid = self.root / 'projects/studio/broken/status.json'
        invalid.parent.mkdir(parents=True); invalid.write_text('{partial', encoding='utf-8')
        self.assertEqual(api.catalog()['total'], 1)
        identity = api.catalog()['items'][0]['id']
        path = self.root / 'config/library-metadata.json'
        path.parent.mkdir(); path.write_text('{broken', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '损坏'):
            api.save_metadata({'id': identity, 'favorite': True})
        self.assertEqual(path.read_text(), '{broken')
        self.assertTrue((folder / 'image.png').is_file())

    def test_symlink_outside_project_never_becomes_a_download(self):
        folder = self.project('a1' * 6, {'status': 'done', 'kind': 'image'})
        outside = self.root / 'unrelated.png'
        Image.new('RGB', (80, 64)).save(outside)
        try:
            (folder / 'image.png').symlink_to(outside)
        except OSError as error:
            self.skipTest('OS does not permit a test symlink: ' + str(error))
        row = api.catalog(status='all')['items'][0]
        self.assertEqual(row['status'], 'error')
        self.assertIsNone(row['absolute_path'])
        self.assertIsNone(row['download_url'])

    def test_resolved_junction_escape_is_rejected_even_with_a_normal_looking_filename(self):
        folder = self.project('a2' * 6, {'status': 'done', 'kind': 'image'}, 'image.png')
        outside = self.root / 'unrelated.png'
        Image.new('RGB', (80, 64)).save(outside)
        resolve = Path.resolve
        def redirected(path, *args, **kwargs):
            return outside if path == folder / 'image.png' else resolve(path, *args, **kwargs)
        # Exercise Windows reparse-point canonicalization without requiring the
        # machine privilege to create a real symlink in a unit-test directory.
        with patch.object(Path, 'resolve', redirected):
            row = api.catalog(status='all')['items'][0]
        self.assertIsNone(row['absolute_path'])
        self.assertIsNone(row['download_url'])
        self.assertEqual(row['status'], 'error')


if __name__ == '__main__':
    unittest.main()
