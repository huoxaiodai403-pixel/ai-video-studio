"""CPU-only checks for real image decoding and immutable reference snapshots."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from PIL import Image

import image_references as references
import testing_support as tempfile


class ImageReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / 'assets/image-references'
        self.project = self.root / 'projects/studio/reference-test'
        for patcher in (patch.object(references, 'ROOT', self.root),
                        patch.object(references, 'STORE', self.store)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def raster(self, kind='PNG', size=(64, 64), offset=0):
        width, height = size
        pixels = bytes((x * 7 + y * 13 + channel * 47 + offset) % 256
                       for y in range(height) for x in range(width) for channel in range(3))
        image = Image.frombytes('RGB', size, pixels)
        output = io.BytesIO()
        image.save(output, format=kind)
        return output.getvalue()

    def register(self, offset=0):
        return references.register(self.raster(offset=offset), '角色参考.png')

    def handler(self):
        result = MagicMock()
        result.path = '/api/image-references'
        return result

    def job(self, status='done', job_id='0123456789ab'):
        folder = self.root / 'projects/studio' / job_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'status.json').write_text(json.dumps({'status': status}), encoding='utf-8')
        (folder / 'image.png').write_bytes(self.raster())
        return job_id, folder

    def test_actual_image_format_is_decoded_and_canonical_extension_used(self):
        for kind, suffix in [('PNG', '.png'), ('JPEG', '.jpg'), ('WEBP', '.webp')]:
            with self.subTest(kind=kind):
                raw = self.raster(kind)
                row = references.register(raw, 'misleading-name.gif')
                self.assertEqual(Path(row['path']).suffix, suffix)
                self.assertEqual((row['width'], row['height']), (64, 64))
                self.assertEqual(row['bytes'], len(raw))
                self.assertEqual(row['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(Path(row['path']).read_bytes(), raw)

    def test_duplicate_bytes_reuse_identity_without_overwriting_name(self):
        raw = self.raster()
        first = references.register(raw, '原始名称.png')
        second = references.register(raw, '不同名称.jpg')
        self.assertEqual(first, second)
        self.assertEqual(len(references.catalog()), 1)
        self.assertEqual(len(list(self.store.glob('*.png'))), 1)
        self.assertEqual(len(list(self.store.glob('*.json'))), 1)

    def test_fake_truncated_and_unsupported_images_are_rejected(self):
        for raw in [b'not an image' * 30, self.raster()[:110], self.raster('BMP')]:
            with self.subTest(raw_prefix=raw[:12]):
                with self.assertRaises(ValueError):
                    references.register(raw, 'looks-like.png')
        self.assertFalse(self.store.exists())

    def test_corrupt_png_crc_is_a_validation_error(self):
        raw = bytearray(self.raster())
        offset = 8
        while offset < len(raw):
            length = int.from_bytes(raw[offset:offset + 4], 'big')
            if raw[offset + 4:offset + 8] == b'IDAT':
                raw[offset + 8 + length] ^= 1
                break
            offset += length + 12
        else:
            self.fail('PNG fixture has no IDAT chunk')
        with self.assertRaisesRegex(ValueError, '解码'):
            references.register(bytes(raw), '损坏校验.png')
        self.assertFalse(self.store.exists())

    def test_animated_png_is_rejected(self):
        output = io.BytesIO()
        first = Image.new('RGB', (64, 64), 'red')
        first.save(output, format='PNG', save_all=True,
                   append_images=[Image.new('RGB', (64, 64), 'blue')], duration=100, loop=0)
        with self.assertRaisesRegex(ValueError, '单帧'):
            references.register(output.getvalue(), 'animated.png')

    def test_minimum_dimensions_and_pixel_budget_apply_before_registration(self):
        for size in [(63, 64), (64, 63)]:
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, '像素'):
                references.register(self.raster(size=size), 'too-small.png')
        with patch.object(references, 'MAX_PIXELS', 64 * 64):
            references.register(self.raster(size=(64, 64)), 'boundary.png')
            with self.assertRaisesRegex(ValueError, '像素'):
                references.register(self.raster(size=(64, 65)), 'too-many-pixels.png')

    def test_byte_and_name_limits_are_rejected_without_writing(self):
        raw = self.raster()
        with patch.object(references, 'MAX_BYTES', len(raw) - 1):
            with self.assertRaises(ValueError):
                references.register(raw, 'large.png')
        for invalid in ['', ' ', '长' * 201, None, 123]:
            with self.subTest(name=invalid), self.assertRaises(ValueError):
                references.register(raw, invalid)
        for invalid in [b'', b'x' * 99, 'not bytes', bytearray(raw)]:
            with self.subTest(type=type(invalid).__name__), self.assertRaises(ValueError):
                references.register(invalid, 'invalid.png')
        self.assertFalse(self.store.exists())

    def test_four_references_preserve_order_and_reject_duplicates_or_fifth(self):
        rows = [self.register(offset) for offset in range(5)]
        ids = [rows[index]['id'] for index in [3, 1, 2, 0]]
        self.assertEqual([row['id'] for row in references.validate_ids(ids)], ids)
        self.assertEqual([row['id'] for row in references.freeze(ids, self.project)], ids)
        for bad in [ids + [rows[4]['id']], [ids[0], ids[0]], tuple(ids), [None], ['../image.png']]:
            with self.subTest(values=bad), self.assertRaises(ValueError):
                references.validate_ids(bad)

    def test_source_hash_tampering_is_rejected_before_freeze_or_duplicate_registration(self):
        row = self.register()
        Path(row['path']).write_bytes(self.raster(offset=5))
        with self.assertRaisesRegex(ValueError, '修改'):
            references.resolve(row['id'])
        with self.assertRaisesRegex(ValueError, '修改'):
            references.freeze([row['id']], self.project)
        with self.assertRaisesRegex(ValueError, '修改'):
            self.register()
        self.assertFalse(self.project.exists())

    def test_catalog_metadata_cannot_redirect_reference_outside_store(self):
        row = self.register()
        outside = self.root / 'outside.png'
        outside.write_bytes(self.raster())
        info = self.store / (row['id'] + '.json')
        original = json.loads(info.read_text(encoding='utf-8'))
        for name in ['../../outside.png', str(outside)]:
            info.write_text(json.dumps({**original, 'file': name}), encoding='utf-8')
            with self.subTest(file=name), self.assertRaisesRegex(ValueError, '越界'):
                references.resolve(row['id'])

    def test_project_snapshot_remains_original_after_catalog_image_changes(self):
        row = self.register()
        original = Path(row['path']).read_bytes()
        frozen = references.freeze([row['id']], self.project)
        snapshot = Path(frozen[0]['path'])
        self.assertNotEqual(snapshot, Path(row['path']))
        Path(row['path']).write_bytes(self.raster(offset=9))
        self.assertEqual(snapshot.read_bytes(), original)
        self.assertEqual(references.checked_paths(frozen), [snapshot])
        self.assertEqual(frozen[0]['project_path'], 'references/' + row['file'])

    def test_modified_snapshot_is_rejected_and_never_silently_overwritten(self):
        row = self.register()
        frozen = references.freeze([row['id']], self.project)
        target = Path(frozen[0]['path'])
        changed = self.raster(offset=12)
        target.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, '变更'):
            references.checked_paths(frozen)
        with self.assertRaisesRegex(ValueError, '不一致'):
            references.freeze([row['id']], self.project)
        self.assertEqual(target.read_bytes(), changed)

    def test_project_and_snapshot_paths_must_stay_within_allowed_roots(self):
        row = self.register()
        for project in [self.root / 'outside', self.root / 'projects-elsewhere',
                        self.root / 'projects/../escape']:
            with self.subTest(project=project), self.assertRaisesRegex(ValueError, '项目目录'):
                references.freeze([row['id']], project)
        outside = self.root / 'outside.png'
        outside.write_bytes(self.raster())
        for path in [outside, self.root / 'projects-elsewhere/picture.png']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, '越界'):
                references.checked_paths([{**row, 'path': str(path)}])
        with self.assertRaisesRegex(ValueError, '最多'):
            references.checked_paths([row] * 5)
        with self.assertRaisesRegex(ValueError, '格式'):
            references.checked_paths(['not a row'])

    def test_storyboard_global_references_allow_ordered_scene_override_and_empty_opt_out(self):
        first, second = self.register(0), self.register(1)
        spec = {'settings': {'image': {'engine': 'flux2-klein-4b'}},
                'backends': {'image': 'local'}, 'image_reference_ids': [first['id']],
                'scenes': [{'id': 'one'}, {'id': 'two', 'image_reference_ids': [second['id'], first['id']]},
                           {'id': 'three', 'image_reference_ids': []}]}
        frozen = references.freeze_storyboard(spec, self.project)
        self.assertEqual([row['id'] for row in frozen['scenes'][0]['image_references']], [first['id']])
        self.assertEqual([row['id'] for row in frozen['scenes'][1]['image_references']], [second['id'], first['id']])
        self.assertNotIn('image_references', frozen['scenes'][2])
        for engine, backend in [('qwen-image', 'local'), ('flux2-klein-4b', 'online')]:
            bad = copy.deepcopy(spec)
            bad['settings']['image']['engine'] = engine
            bad['backends']['image'] = backend
            with self.subTest(engine=engine, backend=backend), self.assertRaisesRegex(ValueError, 'FLUX'):
                references.freeze_storyboard(bad, self.project)

    def test_upload_api_validates_base64_and_returns_registered_reference(self):
        handler = self.handler()
        raw = self.raster()
        self.assertTrue(references.post(handler, {'name': '上传.png', 'base64': base64.b64encode(raw).decode('ascii')}))
        response = handler.reply.call_args.args[0]
        self.assertEqual(response['reference']['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(response['references']), 1)
        for data in [{'name': 'bad.png', 'base64': '%%%bad'},
                     {'name': 'bad.png', 'base64': None}, {'name': 'missing-data.png'},
                     {'job_id': '0123456789ab', 'base64': ''}]:
            handler.reply.reset_mock()
            with self.subTest(data=data), self.assertRaises(ValueError):
                references.post(handler, data)
            handler.reply.assert_not_called()

    def test_generated_image_registration_requires_done_status(self):
        handler = self.handler()
        for status in ['queued', 'running', 'error', 'cancelled']:
            job_id, _ = self.job(status)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, '尚未完成'):
                references.post(handler, {'job_id': job_id})
        job_id, folder = self.job()
        (folder / 'status.json').unlink()
        with self.assertRaisesRegex(ValueError, '尚未完成'):
            references.post(handler, {'job_id': job_id})
        for job_id in ['../0123456789ab', 'speech-0123456789ab', '0' * 13, None]:
            with self.subTest(job_id=job_id), self.assertRaises(ValueError):
                references.post(handler, {'job_id': job_id})
        handler.reply.assert_not_called()
        self.assertFalse(self.store.exists())

    def test_completed_generated_image_is_copied_and_fake_output_is_rejected(self):
        handler = self.handler()
        job_id, folder = self.job()
        original = (folder / 'image.png').read_bytes()
        references.post(handler, {'job_id': job_id})
        row = handler.reply.call_args.args[0]['reference']
        (folder / 'image.png').write_bytes(self.raster(offset=20))
        self.assertEqual(Path(row['path']).read_bytes(), original)
        (folder / 'image.png').write_bytes(b'fake PNG' * 50)
        with self.assertRaises(ValueError):
            references.post(self.handler(), {'job_id': job_id})

    def test_preview_verifies_hash_and_unknown_routes_are_ignored(self):
        row = self.register()
        handler = self.handler()
        route = urlparse('/api/image-references/preview?id=' + row['id'])
        self.assertTrue(references.get(handler, route))
        handler.send_file.assert_called_once_with(Path(row['path']))
        Path(row['path']).write_bytes(self.raster(offset=30))
        handler.send_file.reset_mock()
        self.assertTrue(references.get(handler, route))
        handler.send_file.assert_not_called()
        self.assertEqual(handler.reply.call_args.args[1], 400)
        handler.path = '/api/unrelated'
        self.assertFalse(references.post(handler, {}))
        self.assertFalse(references.get(handler, urlparse('/api/unrelated')))


if __name__ == '__main__':
    unittest.main()
