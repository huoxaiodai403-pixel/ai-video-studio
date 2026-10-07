"""Handoff validation and real draft serialization; never touches installed drafts."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

import jianying_bridge as bridge


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(bridge, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.project = self.root / 'projects/studio/video-test'
        self.project.mkdir(parents=True)
        self.drafts = self.root / 'drafts'
        self.drafts.mkdir()
        self.info = {'installed': True, 'executable': 'JianyingPro.exe', 'draft_root': str(self.drafts),
                     'bridge_ready': True, 'bridge_version': 'pyJianYingDraft 0.3.0'}
        self.probe_patch = patch.object(bridge, '_probe', return_value={'duration': 2.5, 'width': 1280, 'height': 720, 'fps': 30})
        self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)
        self.discover_patch = patch.object(bridge, 'discover', return_value=self.info)
        self.discover_patch.start()
        self.addCleanup(self.discover_patch.stop)
        save(self.project / 'status.json', {'status': 'done'})
        (self.project / 'video.mp4').write_bytes(b'test-video-stub-probe-mocked')
        self.spec = {'title': '测试双角色', 'scenes': [
            {'id': 'scene01', 'speaker': '旁白', 'heading': '第一幕', 'points': ['先看来源']},
            {'id': 'scene02', 'speaker': '提问者', 'heading': '第二幕', 'points': ['再核对时间']}]}
        save(self.project / 'storyboard.json', self.spec)
        self.timeline = [{'id': 'scene01', 'start': 0, 'duration': 1.25, 'audio_start': 0.2},
                         {'id': 'scene02', 'start': 1.25, 'duration': 1.25, 'audio_start': 1.45}]
        save(self.project / 'timeline.json', self.timeline)
        (self.project / 'audio').mkdir()
        for sid in ('scene01', 'scene02'):
            with wave.open(str(self.project / ('audio/' + sid + '.wav')), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b'\0\0' * 8000)
        (self.project / 'subtitles.srt').write_text('1\n00:00:00,200 --> 00:00:01,150\n先看来源\n\n2\n00:00:01,450 --> 00:00:02,450\n再核对时间\n', encoding='utf-8')

    def test_fixed_id_rejects_traversal_absolute_and_malformed(self):
        for value in ('../video-test', 'a/b', 'D:\\x', '/tmp', '', None, 'a' * 121):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.project_path(value)

    def test_containment_rejects_outside_and_links(self):
        outside = self.root / 'outside.wav'
        outside.write_bytes(b'secret')
        for value in ('../../../outside.wav', str(outside), 'file:stream'):
            with self.assertRaises(ValueError):
                bridge.contained(self.project, value)
        link = self.project / 'linked.wav'
        try:
            link.symlink_to(outside)
        except OSError:
            return  # Windows without symlink privileges still checks traversal above.
        with self.assertRaises(ValueError):
            bridge.contained(self.project, 'linked.wav')

    def test_completed_only(self):
        save(self.project / 'status.json', {'status': 'running'})
        with self.assertRaisesRegex(ValueError, '等待'):
            bridge.build_plan('video-test')

    def test_scene_plan_preserves_roles_and_audio_lead(self):
        plan = bridge.build_plan('video-test', 'scenes')
        self.assertEqual(plan['mode'], 'scenes')
        self.assertEqual(plan['duration'], 2.5)
        self.assertEqual([row['audio_start'] for row in plan['scenes']], [0.2, 1.45])
        self.assertEqual([row['speaker'] for row in plan['scenes']], ['旁白', '提问者'])
        self.assertEqual(len(plan['subtitles']), 2)
        self.assertNotIn('video.mp4', plan['sources'])

    def test_auto_fallback_is_explicit_and_no_double_captions(self):
        (self.project / 'timeline.json').unlink()
        plan = bridge.build_plan('video-test')
        self.assertEqual(plan['mode'], 'flattened')
        self.assertEqual(plan['scenes'], [])
        self.assertEqual(plan['subtitles'], [])
        self.assertTrue(any('自动回退' in row for row in plan['warnings']))
        self.assertIn('video.mp4', plan['sources'])
        self.assertIn('subtitles.srt', plan['sources'])
        with self.assertRaises(ValueError):
            bridge.build_plan('video-test', 'scenes')

    def test_audio_cannot_overlap_next_scene(self):
        self.timeline[0]['audio_start'] = 0.8
        save(self.project / 'timeline.json', self.timeline)
        with self.assertRaisesRegex(ValueError, '旁白实长'):
            bridge.build_plan('video-test', 'scenes')

    def test_bad_subtitle_overlap_rejected(self):
        (self.project / 'subtitles.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nA\n\n2\n00:00:01,000 --> 00:00:02,450\nB\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重叠'):
            bridge.build_plan('video-test', 'scenes')

    def test_nan_or_duplicate_timeline_rejected(self):
        self.timeline[0]['start'] = float('nan')
        save(self.project / 'timeline.json', self.timeline)
        with self.assertRaises(ValueError):
            bridge.build_plan('video-test', 'scenes')

    def test_media_registration_cannot_escape_project(self):
        self.spec['media'] = [{'id': 'unsafe', 'path': '../elsewhere.mp4', 'kind': 'video'}]
        self.spec['scenes'][0].update(kind='video', media_id='unsafe')
        save(self.project / 'storyboard.json', self.spec)
        with self.assertRaisesRegex(ValueError, '超出'):
            bridge.build_plan('video-test', 'scenes')

    def test_returned_videos_are_project_confined(self):
        export_dir = self.project / 'jianying/exports'
        export_dir.mkdir(parents=True)
        # Tiny structurally complete MP4 fixture; media probe is mocked in setUp.
        (export_dir / 'review.mp4').write_bytes(b'\0\0\0\x08ftyp\0\0\0\x08moov\0\0\0\x08mdat')
        os.utime(export_dir / 'review.mp4', (time.time() - 10, time.time() - 10))
        (self.project / 'unrelated.mp4').write_bytes(b'other')
        save(self.project / 'jianying/latest.json', {'files': [], 'draft_name': 'test'})
        status = bridge.status('video-test')
        self.assertEqual(status['project']['available_modes'], ['scenes', 'flattened'])
        files = status['last_export']['files']
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0]['url'].endswith('/jianying/exports/review.mp4'))
        self.assertTrue(files[0]['verification']['container_readable'])
        self.assertEqual(files[0]['verification']['visual_review'], 'pending')

    def test_incomplete_exports_are_pending_without_download_urls(self):
        exports = self.project / 'jianying/exports'
        exports.mkdir(parents=True)
        for name, body in [('empty.mp4', b''), ('truncated.mp4', b'\0\0\0\x08ftyp\0\0\x01\x00mdat'),
                           ('streaming.mp4', b'\0\0\0\x08ftyp\0\0\0\0mdat')]:
            path = exports / name
            path.write_bytes(body)
            os.utime(path, (time.time() - 10, time.time() - 10))
        save(self.project / 'jianying/latest.json', {'files': [], 'draft_name': 'test'})
        result = bridge.status('video-test')['last_export']
        self.assertEqual(result['files'], [])
        self.assertEqual(len(result['pending_files']), 3)
        self.assertTrue(all('url' not in row for row in result['pending_files']))

    @unittest.skipUnless(os.name == 'nt', 'Windows writer-share semantics')
    def test_active_writer_is_not_exposed_even_with_complete_mp4_header(self):
        exports = self.project / 'jianying/exports'
        exports.mkdir(parents=True)
        path = exports / 'writing.mp4'
        path.write_bytes(b'\0\0\0\x08ftyp\0\0\0\x08moov\0\0\0\x08mdat')
        os.utime(path, (time.time() - 10, time.time() - 10))
        save(self.project / 'jianying/latest.json', {'files': [], 'draft_name': 'test'})
        with path.open('r+b') as writer:
            result = bridge.status('video-test')['last_export']
            self.assertEqual(result['files'], [])
            self.assertIn('写入', result['pending_files'][0]['reason'])
        self.assertEqual(len(bridge.status('video-test')['last_export']['files']), 1)

    def test_app_custom_draft_root_overrides_appdata_index(self):
        self.discover_patch.stop()
        local = self.root / 'LocalAppData'
        settings = local / 'JianyingPro/User Data/Config/globalSetting'
        settings.parent.mkdir(parents=True)
        default = local / 'JianyingPro/User Data/Projects/com.lveditor.draft'
        default.mkdir(parents=True)
        settings.write_text('[General]\ncurrentCustomDraftPath=' + str(self.drafts).replace('\\', '\\\\') + '\n', encoding='utf-8')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
            found = bridge.discover()
        self.assertEqual(Path(found['draft_root']), self.drafts)
        self.assertEqual(found['draft_root_source'], 'jianying-settings')
        # A configured missing folder must not silently write to the default root.
        settings.write_text('[General]\ncurrentCustomDraftPath=' + str(self.root / 'missing') + '\n', encoding='utf-8')
        with patch.dict(os.environ, {'LOCALAPPDATA': str(local)}):
            self.assertIsNone(bridge.discover()['draft_root'])

    @unittest.skipUnless(importlib.util.find_spec('pyJianYingDraft'), 'Run with the isolated bridge Python for real serialization')
    def test_real_draft_tracks_copied_assets_idempotency_and_preservation(self):
        existing = self.drafts / 'keep-existing'
        existing.mkdir()
        (existing / 'draft_content.json').write_bytes(b'untouched')
        before = {str(p.relative_to(self.project)): bridge.file_sha(p) for p in self.project.rglob('*') if p.is_file()}
        first = bridge._worker_export('video-test', 'scenes')
        location = Path(first['draft_path'])
        content = json.loads((location / 'draft_content.json').read_text(encoding='utf-8'))
        names = {row['name']: row for row in content['tracks']}
        self.assertEqual(len(names['画面']['segments']), 2)
        self.assertEqual(len(names['字幕']['segments']), 2)
        self.assertIn('配音 · 提问者', names)
        self.assertEqual(names['配音 · 旁白']['segments'][0]['target_timerange']['start'], 200000)
        for kind in ('videos', 'audios'):
            for material in content['materials'][kind]:
                path = Path(material['path'])
                self.assertTrue(path.is_file(), str(path))
                self.assertTrue(path.is_relative_to(location))
        second = bridge._worker_export('video-test', 'scenes')
        self.assertTrue(second['reused'])
        self.assertEqual(first['draft_id'], second['draft_id'])
        # Current Jianying can encrypt/replace both JSON files when saving. The
        # handoff must neither parse nor overwrite the user's edited draft.
        (location / 'draft_content.json').write_bytes(b'Jianying-encrypted-user-edit')
        (location / 'draft_meta_info.json').write_bytes(b'Jianying-new-metadata')
        reused_after_edit = bridge._worker_export('video-test', 'scenes')
        self.assertTrue(reused_after_edit['reused'])
        self.assertEqual((location / 'draft_content.json').read_bytes(), b'Jianying-encrypted-user-edit')
        self.assertEqual((location / 'draft_meta_info.json').read_bytes(), b'Jianying-new-metadata')
        self.assertEqual((existing / 'draft_content.json').read_bytes(), b'untouched')
        for relative, digest in before.items():
            self.assertEqual(bridge.file_sha(self.project / relative), digest)
        self.spec['scenes'][0]['heading'] = '改后的标题'
        save(self.project / 'storyboard.json', self.spec)
        third = bridge._worker_export('video-test', 'scenes')
        self.assertNotEqual(first['draft_id'], third['draft_id'])
        self.assertTrue(location.is_dir())


if __name__ == '__main__':
    unittest.main()
