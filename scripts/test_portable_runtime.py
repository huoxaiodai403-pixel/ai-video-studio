"""Share-package boundaries: no private vault, sample library, or local weights."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import testing_support as tempfile

import bootstrap_studio
import creation_api
import creation_settings
import director
import document_pages
import model_profiles
import prompt_library
import runtime_paths
import tts_batch


class PortableRuntimeTests(unittest.TestCase):
    def test_prompt_compilation_without_external_repositories(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(prompt_library, 'ROOT', root), patch.object(prompt_library, 'DATA', root/'missing.json'):
                self.assertEqual(prompt_library.search(''), [])
                self.assertEqual(prompt_library.search('', library='seedance'), [])
                value = prompt_library.compile_prompt('茶杯', '电影摄影', '特写', '暖色')
                self.assertIn('茶杯', value['prompt'])
                self.assertIsNone(value['source_commit'])

    def test_director_keeps_builtin_cameras_without_downloads(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(director, 'ROOT', Path(folder)):
            director.catalog.cache_clear()
            try:
                result = director.catalog()
                self.assertGreater(len(result['cameras']), 10)
                self.assertEqual(result['templates'], [])
                self.assertEqual(result['case_count'], 0)
            finally:
                director.catalog.cache_clear()

    def test_online_storyboard_does_not_require_local_model_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(creation_settings, 'CONFIG', Path(folder)/'creation.json'):
            spec = {'backends': {key: 'online' for key in ('image','tts','asr','video')},
                    'settings': {'voice': {'engine': 'qwen3-custom', 'reference': ''}},
                    'scenes': [{'id': 'one', 'narration': '测试'}]}
            with patch.object(model_profiles, 'require', side_effect=AssertionError('Local model check invoked')):
                snapshot = creation_api.snapshot(spec)
            self.assertEqual(snapshot['settings']['voice']['reference'], '')

    def test_online_numeric_and_path_validation_still_applies(self):
        for change in ({'image': {'width': 777}}, {'models': {'image_unet': '../../secret.gguf'}},
                       {'motion': {'frames': 32}}, {'story': {'local_url': 'https://remote.example'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                creation_settings.validate(change, check_models=False, check_voice=False)

    def test_local_engine_still_requires_its_weights(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(model_profiles, 'MODEL_ROOT', Path(folder)):
            with self.assertRaises(ValueError):
                model_profiles.require('image', 'qwen-image-2512', copy.deepcopy(creation_settings.DEFAULTS['models']))

    def test_first_run_preserves_existing_settings_and_ffmpeg(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bootstrap_studio, 'ROOT', Path(folder)):
            root = Path(folder)
            (root/'tools').mkdir()
            (root/'tools/ffmpeg.exe').write_bytes(b'existing runtime')
            (root/'config').mkdir()
            original = {'voice': {'engine': 'qwen3-custom', 'qwen_speaker': 'Serena'}}
            (root/'config/creation.json').write_text(json.dumps(original), encoding='utf-8')
            bootstrap_studio.initialize()
            self.assertEqual(json.loads((root/'config/creation.json').read_text()), original)
            self.assertEqual((root/'tools/ffmpeg.exe').read_bytes(), b'existing runtime')
            self.assertTrue((root/'projects/studio').is_dir())

    def test_docs_cannot_escape_configured_notes_root(self):
        self.assertFalse(document_pages.allowed(document_pages.NOTES/'..'/'private.json'))

    def test_qwen_only_project_does_not_launch_index_environment(self):
        spec={'settings':creation_settings.merge(creation_settings.DEFAULTS,{'voice':{'engine':'qwen3-custom','reference':''}}),
              'scenes':[{'id':'one','narration':'test'}]}
        self.assertEqual(runtime_paths.tts_python(spec), runtime_paths.ROOT/'tools/.venv/Scripts/python.exe')
        spec['scenes'][0]['voice']={'engine':'index-tts'}
        self.assertEqual(runtime_paths.tts_python(spec), runtime_paths.ROOT/'apps/index-tts/.venv/Scripts/python.exe')

    def test_qwen_batch_skips_index_model_revision_and_import(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)
            spec={'settings':creation_settings.merge(creation_settings.DEFAULTS,{'voice':{'engine':'qwen3-custom','reference':''}}),
                  'scenes':[{'id':'one','narration':'测试'}]}
            (project/'storyboard.json').write_text(json.dumps(spec),encoding='utf-8')
            with patch('sys.argv',['tts_batch.py',str(project)]), patch.object(tts_batch,'model_revision',side_effect=AssertionError('Index model accessed')), patch.object(tts_batch.subprocess,'run') as worker:
                tts_batch.main()
            self.assertIn('qwen-tts',worker.call_args.args[0][0])


if __name__ == '__main__':
    unittest.main()
