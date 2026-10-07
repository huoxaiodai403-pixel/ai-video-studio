"""CPU-only boundary regressions; never load a Stable Audio model."""
from array import array
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import wave

import stable_sfx
import testing_support as tempfile


class StableSfxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects/studio/sfx-test'
        self.project.mkdir(parents=True)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(stable_sfx, 'ROOT', self.root))
        self.request = {'prompt': 'soft page turn, no voices', 'duration_seconds': 1, 'seed': 42}

    def audio(self, path, frames=44100, amplitude=1000):
        values = array('h', [amplitude, -amplitude]) * frames
        if sys.byteorder != 'little':
            values.byteswap()
        with wave.open(str(path), 'wb') as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(44100)
            stream.writeframes(values.tobytes())
        return path

    def fake_runtime(self, request, work):
        return self.audio(work / 'source.wav'), {'mocked_model': True}

    def enable_fake_runtime(self, render=None):
        self.stack.enter_context(patch.object(stable_sfx, 'readiness', return_value={'ready': True}))
        self.stack.enter_context(patch.object(stable_sfx, '_verify_artifacts', return_value=[]))
        self.stack.enter_context(patch.object(stable_sfx, '_offline_environment'))
        return self.stack.enter_context(patch.object(stable_sfx, '_render', side_effect=render or self.fake_runtime))

    def test_invalid_requests_fail_before_runtime(self):
        for value in [None, [], {}, {'prompt': ' '}, {'prompt': 'x\0'},
                      {**self.request, 'duration_seconds': 0.99},
                      {**self.request, 'duration_seconds': 15.1},
                      {**self.request, 'duration_seconds': float('nan')},
                      {**self.request, 'duration_seconds': True},
                      {**self.request, 'seed': 1.5}, {**self.request, 'seed': -1},
                      {**self.request, 'seed': float('inf')},
                      {**self.request, 'model_path': 'arbitrary.tflite'},
                      {**self.request, 'init_audio': 'arbitrary.wav'}]:
            with self.subTest(value=value), patch.object(stable_sfx, '_render') as render:
                with self.assertRaises(ValueError):
                    stable_sfx.generate(value, self.project)
                render.assert_not_called()

    def test_outputs_cannot_escape_workspace_projects(self):
        render = self.enable_fake_runtime()
        with self.assertRaises(ValueError):
            stable_sfx.generate(self.request, self.root / 'outside')
        self.assertFalse((self.root / 'outside').exists())
        render.assert_not_called()

    def test_same_size_weight_tampering_is_rejected(self):
        model_root = self.root / 'models'
        model_root.mkdir()
        original = b'registered weight'
        path = model_root / 'weights.tflite'
        path.write_bytes(original)
        info = (('weights.tflite', len(original), hashlib.sha256(original).hexdigest()),)
        with patch.object(stable_sfx, 'MODELS', model_root), patch.object(stable_sfx, 'MODEL_FILES', info):
            self.assertEqual(stable_sfx._verify_artifacts()[0]['bytes'], len(original))
            path.write_bytes(b'X' * len(original))
            with self.assertRaisesRegex(RuntimeError, 'SHA256'):
                stable_sfx._verify_artifacts()

    def test_readiness_does_not_import_inference_libraries(self):
        code = ("import sys; sys.path.insert(0, 'scripts'); import stable_sfx; "
                "s = stable_sfx.readiness(); "
                "assert not any(x in sys.modules for x in ('numpy','torch','ai_edge_litert','sentencepiece')); "
                "assert s['device'] == 'cpu'; print(s['engine'])")
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code],
                                cwd=Path(stable_sfx.__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'stable-audio-3-sfx')

    def test_success_captures_real_audio_metrics_and_hash(self):
        self.enable_fake_runtime()
        result = stable_sfx.generate(self.request, self.project)
        target = self.project / 'sfx.wav'
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['frames'], 44100)
        self.assertEqual(result['duration_seconds'], 1)
        self.assertEqual(result['audio_sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertAlmostEqual(result['rms'], 1000 / 32768)
        self.assertEqual(result['listening_qa'], 'not performed')

    def test_invalid_runtime_output_preserves_previous_delivered_audio(self):
        target = self.project / 'sfx.wav'
        original = b'previous successful audio'
        target.write_bytes(original)
        def wrong_duration(request, work):
            return self.audio(work / 'source.wav', frames=22050), {}
        self.enable_fake_runtime(wrong_duration)
        with self.assertRaisesRegex(RuntimeError, '实际时长'):
            stable_sfx.generate(self.request, self.project)
        self.assertEqual(target.read_bytes(), original)
        metadata = json.loads((self.project / 'sfx.metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['status'], 'error')

    def test_silent_audio_is_not_marked_done(self):
        def silent(request, work):
            return self.audio(work / 'source.wav', amplitude=0), {}
        self.enable_fake_runtime(silent)
        with self.assertRaisesRegex(RuntimeError, '完全静音'):
            stable_sfx.generate(self.request, self.project)
        self.assertFalse((self.project / 'sfx.wav').exists())

    def test_runtime_cannot_publish_an_external_file(self):
        outside = self.audio(self.root / 'unrelated.wav')
        self.enable_fake_runtime(lambda request, work: (outside, {}))
        with self.assertRaisesRegex(RuntimeError, '本任务目录'):
            stable_sfx.generate(self.request, self.project)
        self.assertTrue(outside.is_file())
        self.assertFalse((self.project / 'sfx.wav').exists())

    def test_cpu_lock_prevents_concurrent_model_loads(self):
        from filelock import FileLock, Timeout
        render = self.enable_fake_runtime()
        (self.root / 'manifests').mkdir()
        with FileLock(str(self.root / 'manifests/stable-sfx-cpu.lock'), timeout=0):
            with self.assertRaises(Timeout):
                stable_sfx.generate(self.request, self.project)
        render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
