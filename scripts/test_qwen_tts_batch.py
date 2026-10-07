"""No-model tests for the isolated worker's scene and engine routing."""
import copy
import unittest
from unittest.mock import patch
import creation_settings as settings
import qwen_tts_batch as worker


class QwenRoutingTests(unittest.TestCase):
    def setUp(self):
        self.voice = copy.deepcopy(settings.DEFAULTS['voice'])
        self.voice.update(engine='qwen3-custom', qwen_instruct='冷静清晰。')

    def spec(self):
        return {'settings': {'voice': self.voice}, 'scenes': [
            {'id': 'a', 'narration': '第一句。'}, {'id': 'b', 'narration': '第二句。',
                                           'voice': {'engine': 'index-tts'}}]}

    def test_scene_selection_and_non_qwen_exclusion(self):
        value = self.spec()
        self.assertEqual([scene['id'] for scene, _ in worker.selected_scenes(value)], ['a'])
        for requested in ({'b'}, {'unknown'}):
            with self.assertRaises(ValueError):
                worker.selected_scenes(value, requested)

    def test_clone_and_custom_group_without_losing_voice(self):
        value = self.spec()
        value['scenes'][1]['voice'] = {'engine': 'qwen3-clone', 'qwen_ref_text': '参考原文。'}
        result = worker.selected_scenes(value)
        self.assertEqual({voice['engine'] for _, voice in result}, {'qwen3-custom', 'qwen3-clone'})
        self.assertEqual(result[0][1]['qwen_ref_text'], '参考原文。')

    def test_design_requires_single_audition_not_long_film(self):
        value = self.spec()
        value['settings']['voice']['engine'] = 'qwen3-design'
        with self.assertRaisesRegex(ValueError, '单段试听'):
            worker.selected_scenes(value)
        value['scenes'] = value['scenes'][:1]
        self.assertEqual(worker.selected_scenes(value)[0][1]['engine'], 'qwen3-design')
        value['settings']['voice']['qwen_instruct'] = ''
        with self.assertRaises(ValueError):
            worker.selected_scenes(value)

    def test_filename_boundary_and_duplicate_id(self):
        for identity in ('../../escape', 'a'):
            value = self.spec()
            value['scenes'][1]['id'] = identity
            with self.assertRaises(ValueError):
                worker.selected_scenes(value)

    def test_readiness_reports_selected_model_without_loading_torch(self):
        with self.assertRaises(ValueError):
            worker.readiness('qwen3-nonexistent')
        value = worker.readiness('qwen3-clone')
        self.assertEqual(value['engine'], 'qwen3-clone')
        self.assertTrue(value['model'].endswith('-Base'))


if __name__ == '__main__':
    unittest.main()
