"""CPU-only boundaries for the fixed-model ACE-Step BGM worker."""
import json
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import wave

import requests

import testing_support as tempfile
import ace_bgm


class AceBgmTests(unittest.TestCase):
    def test_only_original_or_exact_official_synced_code_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = 'acestep-v15-turbo/configuration_acestep_v15.py'
            target = root / 'models' / name
            source = root / 'app/acestep/models/turbo' / target.name
            target.parent.mkdir(parents=True); source.parent.mkdir(parents=True)
            original = b'old'
            target.write_bytes(original); source.write_bytes(b'official update')
            row = {'name': name, 'bytes': 3,
                   'git_blob_sha1': hashlib.sha1(b'blob 3\0' + original).hexdigest()}
            with patch.object(ace_bgm, 'MODELS', root / 'models'), patch.object(ace_bgm, 'APP', root / 'app'):
                self.assertTrue(ace_bgm._model_file_ok(row))
                target.write_bytes(source.read_bytes())
                self.assertTrue(ace_bgm._model_file_ok(row))
                target.write_bytes(b'bad')
                self.assertFalse(ace_bgm._model_file_ok(row))
                weights = target.with_name('model.safetensors'); weights.write_bytes(b'12')
                self.assertFalse(ace_bgm._model_file_ok({'name': 'acestep-v15-turbo/model.safetensors', 'bytes': 3}))

    def test_readiness_does_not_import_model_runtime(self):
        self.assertNotIn('ace_bgm_runtime', sys.modules)
        result = ace_bgm.readiness()
        self.assertIsInstance(result['checks'], list)
        self.assertNotIn('ace_bgm_runtime', sys.modules)

    def test_prompt_is_data_and_unknown_paths_or_invalid_controls_are_rejected(self):
        text = '__import__("os").system("not executed")'
        self.assertEqual(ace_bgm.validate_request({'prompt': text})['prompt'], text)
        for extra in [{'model': 'elsewhere'}, {'reference_audio': '../file.wav'}, {'seed': True},
                      {'duration_seconds': 29}, {'duration_seconds': float('nan')},
                      {'duration_seconds': 61}, {'bpm': 75.2}, {'thinking': 'false'}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                ace_bgm.validate_request({'prompt': 'Quiet background music', **extra})

    def test_not_ready_never_calls_runtime(self):
        with patch.object(ace_bgm, 'readiness', return_value={'ready': False, 'checks': [
                {'ready': False, 'message': 'missing model'}]}), patch.object(ace_bgm, '_render') as render:
            with self.assertRaisesRegex(RuntimeError, 'missing model'):
                ace_bgm.generate({'prompt': 'quiet music'}, Path('not-created'))
            render.assert_not_called()

    def test_comfy_cleanup_only_releases_an_idle_available_service(self):
        for state in ('idle', 'running', 'pending', 'connection_refused', 'http_error', 'malformed'):
            with self.subTest(state=state), patch('comfy_client.HTTP') as http, \
                    patch('comfy_client.unload') as unload:
                response = MagicMock()
                response.json.return_value = {'queue_running': [], 'queue_pending': []}
                http.get.return_value = response
                if state == 'running':
                    response.json.return_value['queue_running'] = ['active-task']
                if state == 'pending':
                    response.json.return_value['queue_pending'] = ['pending-task']
                if state == 'connection_refused':
                    http.get.side_effect = requests.ConnectionError('not started')
                if state == 'http_error':
                    response.raise_for_status.side_effect = requests.HTTPError('500')
                if state == 'malformed':
                    response.json.return_value = {'error': 'unknown response'}
                if state in ('idle', 'connection_refused'):
                    self.assertEqual(ace_bgm._release_comfy(), state == 'idle')
                else:
                    with self.assertRaises((RuntimeError, requests.HTTPError)):
                        ace_bgm._release_comfy()
                self.assertEqual(unload.call_count, int(state == 'idle'))

    def test_actual_audio_is_saved_with_hash_and_no_partial_success(self):
        for generated_seconds in (30, 28):
            with self.subTest(seconds=generated_seconds), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan = root / 'plan.json'
                plan.write_text(json.dumps({'repo': 'official/test', 'revision': 'pinned'}), encoding='utf-8')
                def render(request, work):
                    out = work / 'generated.wav'
                    with wave.open(str(out), 'wb') as stream:
                        stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(1000)
                        stream.writeframes(b'\x08\0\x08\0' * (1000 * generated_seconds))
                    return out, {'backend': 'pt'}
                with patch.object(ace_bgm, 'PLAN', plan), \
                     patch.object(ace_bgm, 'readiness', return_value={'ready': True}), \
                     patch.object(ace_bgm, '_release_comfy', return_value=False), \
                     patch.object(ace_bgm, '_render', side_effect=render):
                    if generated_seconds == 30:
                        result = ace_bgm.generate({'prompt': 'quiet music', 'duration_seconds': 30}, root, already_locked=True)
                        self.assertEqual(result['status'], 'done')
                        self.assertEqual(result['duration_seconds'], 30)
                        self.assertEqual(len(result['audio_sha256']), 64)
                        self.assertTrue((root / 'bgm.wav').is_file())
                        self.assertEqual(result['listening_qa'], 'not performed')
                    else:
                        with self.assertRaisesRegex(RuntimeError, '时长'):
                            ace_bgm.generate({'prompt': 'quiet music', 'duration_seconds': 30}, root, already_locked=True)
                        self.assertFalse((root / 'bgm.wav').exists())
                        data = json.loads((root / 'bgm.metadata.json').read_text(encoding='utf-8'))
                        self.assertEqual(data['status'], 'error')


if __name__ == '__main__':
    unittest.main()
