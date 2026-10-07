import copy
import json
import testing_support as tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import whiteboard_api as api


class WhiteboardTests(unittest.TestCase):
    def setUp(self):
        self.spec = api.example()

    def test_example_has_four_distinct_layouts_and_fixed_mode(self):
        self.assertEqual(self.spec['render_mode'], 'excalidraw')
        self.assertEqual({scene['board_layout'] for scene in self.spec['scenes']}, set(api.LAYOUTS))
        self.assertFalse(self.spec['motion_enabled'])

    def test_discards_executable_and_path_fields(self):
        self.spec.update(javascript='require("fs").unlinkSync("important")', project='../../outside')
        self.spec['scenes'][0]['javascript'] = 'process.exit()'
        result = api.storyboard(self.spec)
        self.assertNotIn('javascript', result)
        self.assertNotIn('project', result)
        self.assertNotIn('javascript', result['scenes'][0])

    def test_rejects_path_ids_and_duplicate_ids(self):
        for bad in ('../escape', self.spec['scenes'][1]['id']):
            with self.subTest(bad=bad):
                self.spec['scenes'][0]['id'] = bad
                with self.assertRaises(ValueError):
                    api.storyboard(self.spec)

    def test_rejects_excess_cards_and_long_narration(self):
        for change in ({'board_cards': ['a']*4}, {'narration': '旁白'*301}, {'narration': '旁白|分隔'}):
            with self.subTest(change=change):
                value = copy.deepcopy(self.spec)
                value['scenes'][0].update(change)
                with self.assertRaises(ValueError):
                    api.storyboard(value)

    def test_explicit_beats_must_cover_narration_in_order(self):
        scene = self.spec['scenes'][0]
        scene.update(narration='先提出问题。再说明主张。', board_beats=['先提出问题。', '再说明主张。'])
        self.assertEqual(api.storyboard(self.spec)['scenes'][0]['board_beats'], scene['board_beats'])
        for beats in (['提出问题', '说明主张'], ['再说明主张。', '先提出问题。']):
            scene['board_beats'] = beats
            with self.assertRaises(ValueError):
                api.storyboard(self.spec)

    def test_preview_does_not_validate_diffusion_or_audio_models(self):
        with patch.object(api.settings, 'load', return_value=copy.deepcopy(api.settings.DEFAULTS)), patch.object(api.settings, 'validate') as validate:
            result = api.snapshot({'storyboard': self.spec})
        validate.assert_not_called()
        self.assertEqual(result['settings']['output']['width'], 1920)
        self.assertEqual(result['settings']['output']['height'], 1080)
        self.assertEqual(result['settings']['output']['fps'], 30)

    def test_online_media_rejected_before_launch(self):
        for kind in ('tts', 'asr'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, '本地'):
                api.snapshot({'storyboard': self.spec, 'backends': {kind: 'online'}})

    def test_llm_invalid_json_reports_error_without_example_fallback(self):
        with patch('local_story.complete', return_value={'choices': [{'message': {'content': 'not json'}}]}) as complete, patch.object(api, 'example') as example:
            with self.assertRaisesRegex(ValueError, '格式'):
                api.draft('讲白板视频', 4)
        example.assert_not_called()
        self.assertEqual(complete.call_count, 2)

    def test_wrong_scene_count_is_repaired_once_with_previous_response_and_error(self):
        initial = json.dumps(self.spec, ensure_ascii=False)
        repaired = copy.deepcopy(self.spec)
        repaired['scenes'] = repaired['scenes'][:3]
        repaired['scenes'][2]['narration'] += self.spec['scenes'][3]['narration']
        responses = [{'choices': [{'message': {'content': content}}]} for content in
                     (initial, json.dumps(repaired, ensure_ascii=False))]
        callback = MagicMock()
        with tempfile.TemporaryDirectory() as folder, patch('local_story.complete', side_effect=responses) as complete:
            result = api.draft('讲白板视频', 3, debug_dir=Path(folder), on_retry=callback)
            self.assertEqual((Path(folder)/'model-response-1.txt').read_text(encoding='utf-8'), initial)
            self.assertIn('4 个镜头', (Path(folder)/'model-validation-1.txt').read_text(encoding='utf-8'))
        self.assertEqual(len(result['scenes']), 3)
        self.assertEqual(result['structure_repair_attempts'], 1)
        self.assertEqual(complete.call_count, 2)
        callback.assert_called_once()
        messages = complete.call_args.args[1]['messages']
        self.assertEqual(messages[-2], {'role': 'assistant', 'content': initial})
        self.assertIn('必须恰好含 3 个镜头', messages[-1]['content'])
        self.assertIn('4 个镜头', messages[-1]['content'])

    def test_llm_response_is_validated_and_normalized(self):
        with patch('local_story.complete', return_value={'choices': [{'message': {'content': json.dumps(self.spec)}}]}) as complete:
            result = api.draft('讲白板视频', 4)
        complete.assert_called_once()
        self.assertEqual(result['source_topic'], '讲白板视频')
        self.assertEqual(result['render_mode'], 'excalidraw')

    def test_job_failure_is_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)
            jobs = {'job': {'status': 'queued'}}
            with patch.object(api, 'draft', side_effect=RuntimeError('GPU busy')):
                api.run_job(jobs, 'job', dest, 'draft', {'topic': '选题', 'count': 4})
            saved = json.loads((dest/'status.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['status'], 'error')
            self.assertEqual(saved['error'], 'GPU busy')

    def test_manifest_sources_are_used_and_encoded(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)
            for name in ('preview.png', '封面-4x3.png', 'storyboard.json', 'scenes/scene01.excalidraw.md'):
                path = dest/name
                path.parent.mkdir(exist_ok=True)
                path.write_text('test', encoding='utf-8')
            (dest/'whiteboard.manifest.json').write_text(json.dumps({
                'preview_frames': ['preview.png'], 'covers': ['封面-4x3.png'],
                'editable_scenes': ['scenes/scene01.excalidraw.md'],
            }), encoding='utf-8')
            result = api.artifacts(dest, 'job', False)
            self.assertEqual(result['sources'], ['/outputs/job/scenes/scene01.excalidraw.md'])
            self.assertIn('%E5%B0%81', result['covers'][0])

    def test_manifest_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)/'project'
            dest.mkdir()
            (dest.parent/'outside.png').write_text('test')
            (dest/'whiteboard.manifest.json').write_text(json.dumps({'preview_frames': ['../outside.png']}))
            with self.assertRaisesRegex(ValueError, '越界'):
                api.artifacts(dest, 'job', False)

    def test_limit_two_active_jobs(self):
        handler = MagicMock(path='/api/whiteboard/draft')
        jobs = {str(i): {'kind': 'whiteboard', 'status': 'running'} for i in range(2)}
        self.assertTrue(api.post(handler, {'topic': '选题', 'count': 4}, jobs))
        self.assertEqual(handler.reply.call_args.args[1], 409)


if __name__ == '__main__':
    unittest.main()
