"""CPU request/dispatch contracts; subprocesses and workers are never started."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse
import wave

import music_api as api
import testing_support as tempfile


class MusicAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(api, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    @staticmethod
    def payload(engine='ace-step-1.5', **changes):
        result = {'engine': engine, 'prompt': 'Quiet paper turning sound' if engine == 'stable-audio-3-sfx'
                  else 'Soft piano instrumental background', 'duration_seconds': 5 if engine == 'stable-audio-3-sfx' else 30,
                  'seed': 42}
        if engine == 'ace-step-1.5':
            result['bpm'] = 72
        return {**result, **changes}

    @staticmethod
    def state(engine, ready=True):
        return {'id': engine, 'name': engine, 'ready': ready, 'details': ['test-local-state']}

    def submit_and_run(self, engine='ace-step-1.5', returncode=0, metadata='done', audio=True):
        handler = MagicMock(path='/api/music')
        jobs = {}
        data = self.payload(engine)
        original = copy.deepcopy(data)
        started = []

        def thread_factory(*, target, daemon):
            self.assertTrue(daemon)
            started.append(target)
            return MagicMock()

        def fake_run(command, **kwargs):
            folder = Path(command[4])
            job_id = folder.name
            self.assertEqual(jobs[job_id]['status'], 'running')
            self.assertEqual(json.loads((folder/'status.json').read_text(encoding='utf-8'))['status'], 'running')
            self.assertNotIn('shell', kwargs)
            self.assertEqual(kwargs['cwd'], self.root)
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertEqual(kwargs['env']['HF_HUB_DISABLE_TELEMETRY'], '1')
            self.assertEqual(kwargs['env']['PYTHONUTF8'], '1')
            self.assertEqual(command[1:3], ['-X', 'utf8'])
            self.assertEqual(command[5], '--request')
            self.assertEqual(Path(command[6]), folder/'request.json')
            stem = api.ENGINES[engine]['output']
            if metadata == 'malformed':
                (folder/(stem+'.metadata.json')).write_text('{unfinished', encoding='utf-8')
            elif metadata != 'missing':
                (folder/(stem+'.metadata.json')).write_text(json.dumps({'status': metadata,
                    'duration_seconds': data['duration_seconds']}), encoding='utf-8')
            if audio:
                with wave.open(str(folder/(stem+'.wav')), 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(44100)
                    output.writeframes(b'\0\0'*44)
            return SimpleNamespace(returncode=returncode)

        with patch.object(api, 'readiness', side_effect=lambda chosen: self.state(chosen)), \
                patch.object(api.threading, 'Thread', side_effect=thread_factory), \
                patch.object(api.subprocess, 'run', side_effect=fake_run) as run:
            self.assertTrue(api.post(handler, data, jobs))
            self.assertEqual(data, original)
            handler.reply.assert_called_once()
            reply, code = handler.reply.call_args.args
            self.assertEqual(code, 202)
            job_id = reply['job_id']
            folder = self.root/'projects/studio'/job_id
            self.assertEqual(jobs[job_id]['status'], 'queued')
            self.assertEqual(json.loads((folder/'status.json').read_text(encoding='utf-8'))['status'], 'queued')
            self.assertEqual(len(started), 1)
            run.assert_not_called()
            started[0]()
            run.assert_called_once()
            command = run.call_args.args[0]
        self.assertEqual(json.loads((folder/'status.json').read_text(encoding='utf-8')), jobs[job_id])
        return jobs[job_id], folder, command

    def test_ace_boundaries_and_worker_request_fields(self):
        for duration, bpm, seed in [(30, 40, 0), (60, 180, 2147483647)]:
            with self.subTest(duration=duration):
                result = api.validate(self.payload(duration_seconds=duration, bpm=bpm, seed=seed))
                self.assertEqual(result['duration_seconds'], duration)
                self.assertEqual(result['bpm'], bpm)
                self.assertEqual(result['seed'], seed)
                self.assertIs(result['thinking'], True)
                self.assertEqual(set(result), {'prompt', 'duration_seconds', 'bpm', 'seed', 'thinking'})

    def test_sfx_boundaries_exclude_music_only_parameters(self):
        for duration, seed in [(1, 0), (15, 2147483647)]:
            result = api.validate(self.payload('stable-audio-3-sfx', duration_seconds=duration, seed=seed))
            self.assertEqual(result['duration_seconds'], duration)
            self.assertEqual(result['seed'], seed)
            self.assertEqual(set(result), {'prompt', 'duration_seconds', 'seed'})

    def test_engine_specific_defaults(self):
        ace = api.validate({'prompt': 'Soft piano background'})
        sfx = api.validate({'engine': 'stable-audio-3-sfx', 'prompt': 'Gentle paper rustling'})
        self.assertEqual((ace['duration_seconds'], ace['bpm'], ace['seed']), (30, 72, 42))
        self.assertEqual((sfx['duration_seconds'], sfx['seed']), (5, 42))

    def test_invalid_request_shape_and_unknown_fields_are_rejected(self):
        for value in [None, [], 'music', 1, True, {'prompt': 'Soft piano', 'unknown': True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                api.validate(value)

    def test_invalid_engine_values_return_validation_errors(self):
        for value in ['online', '', None, False, 1, [], {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                api.validate(self.payload(engine=value))

    def test_prompt_limits_nul_and_types_are_rejected_per_engine(self):
        for engine, limit in [('ace-step-1.5', 2000), ('stable-audio-3-sfx', 1000)]:
            for valid in ['a'*5, 'a'*limit, '  clear sound  ']:
                self.assertEqual(api.validate(self.payload(engine, prompt=valid))['prompt'], valid.strip())
            for value in ['a'*4, 'a'*(limit+1), 'clear\x00sound', '', '   ', None, ['sound']]:
                with self.subTest(engine=engine, value=repr(value)[:40]), self.assertRaises(ValueError):
                    api.validate(self.payload(engine, prompt=value))

    def test_duration_ranges_integer_and_finite_requirements(self):
        for engine, invalid in [('ace-step-1.5', [29, 61, 30.5]), ('stable-audio-3-sfx', [0, 16, 1.5])]:
            for value in invalid+[True, None, [], float('nan'), float('inf')]:
                with self.subTest(engine=engine, value=value), self.assertRaises(ValueError):
                    api.validate(self.payload(engine, duration_seconds=value))

    def test_seed_and_bpm_ranges_and_sfx_bpm_rejection(self):
        for value in [-1, 2147483648, 1.5, True, None, float('nan')]:
            with self.subTest(seed=value), self.assertRaises(ValueError):
                api.validate(self.payload(seed=value))
        for value in [39, 181, 72.5, True, None]:
            with self.subTest(bpm=value), self.assertRaises(ValueError):
                api.validate(self.payload(bpm=value))
        for value in [None, 72]:
            with self.assertRaisesRegex(ValueError, 'BPM'):
                api.validate(self.payload('stable-audio-3-sfx', bpm=value))

    def test_readiness_dispatches_expected_modules_and_reports_details(self):
        for engine, module in [('ace-step-1.5', 'ace_bgm'), ('stable-audio-3-sfx', 'stable_sfx')]:
            fake = SimpleNamespace(readiness=lambda: {'ready': False, 'checks': [
                {'name': 'weights', 'ready': False, 'message': 'missing local file'}]})
            with patch('importlib.import_module', return_value=fake) as importer:
                result = api.readiness(engine)
            importer.assert_called_once_with(module)
            self.assertEqual(result['id'], engine)
            self.assertIs(result['ready'], False)
            self.assertEqual(result['details'], ['weights: missing local file'])

    def test_readiness_import_error_does_not_claim_ready(self):
        with patch('importlib.import_module', side_effect=ImportError('not installed')):
            state = api.readiness('stable-audio-3-sfx')
        self.assertFalse(state['ready'])
        self.assertIn('not installed', state['details'][0])

    def test_get_exposes_both_engines_and_unrelated_routes_do_nothing(self):
        handler = MagicMock(path='/other')
        with patch.object(api, 'readiness', side_effect=self.state) as ready:
            self.assertFalse(api.get(handler, urlparse('/other')))
            self.assertFalse(api.post(handler, {}, {}))
            ready.assert_not_called()
            self.assertTrue(api.get(handler, urlparse('/api/music')))
        self.assertEqual([row['id'] for row in handler.reply.call_args.args[0]['engines']],
                         ['ace-step-1.5', 'stable-audio-3-sfx'])

    def test_unready_engine_cannot_create_job_or_process(self):
        jobs = {}
        with patch.object(api, 'readiness', return_value=self.state('stable-audio-3-sfx', False)), \
                patch.object(api.threading, 'Thread') as thread, patch.object(api.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, '尚未就绪'):
                api.post(MagicMock(path='/api/music'), self.payload('stable-audio-3-sfx'), jobs)
            thread.assert_not_called()
            run.assert_not_called()
        self.assertEqual(jobs, {})
        self.assertFalse((self.root/'projects').exists())

    def test_ace_dispatch_and_done_artifacts(self):
        status, folder, command = self.submit_and_run()
        self.assertEqual(command[0], str(self.root/'apps/ace-step/.venv/Scripts/python.exe'))
        self.assertEqual(command[3], str(self.root/'scripts/ace_bgm.py'))
        request = json.loads((folder/'request.json').read_text(encoding='utf-8'))
        self.assertEqual(set(request), {'prompt', 'duration_seconds', 'bpm', 'seed', 'thinking'})
        self.assertEqual((status['status'], status['kind'], status['engine']), ('done', 'music', 'ace-step-1.5'))
        self.assertEqual(status['audio'], f'/outputs/{folder.name}/bgm.wav')
        self.assertEqual(status['audio_path'], str(folder/'bgm.wav'))
        self.assertEqual(status['metadata'], f'/outputs/{folder.name}/bgm.metadata.json')
        self.assertEqual(status['duration_seconds'], 30)

    def test_sfx_dispatch_uses_own_python_worker_and_metadata(self):
        status, folder, command = self.submit_and_run('stable-audio-3-sfx')
        self.assertEqual(command[0], str(self.root/'apps/stable-audio-3/.venv/Scripts/python.exe'))
        self.assertEqual(command[3], str(self.root/'scripts/stable_sfx.py'))
        self.assertEqual(set(json.loads((folder/'request.json').read_text(encoding='utf-8'))),
                         {'prompt', 'duration_seconds', 'seed'})
        self.assertEqual((status['status'], status['kind'], status['engine']), ('done', 'music', 'stable-audio-3-sfx'))
        self.assertEqual(status['audio'], f'/outputs/{folder.name}/sfx.wav')
        self.assertEqual(status['metadata'], f'/outputs/{folder.name}/sfx.metadata.json')
        self.assertEqual(status['duration_seconds'], 5)

    def test_nonzero_worker_exit_is_persisted_error_without_fallback(self):
        status, folder, _ = self.submit_and_run('stable-audio-3-sfx', returncode=1)
        self.assertEqual(status['status'], 'error')
        self.assertIn('其他引擎不会自动替代', status['error'])
        self.assertNotIn('audio', status)
        self.assertTrue((folder/'request.json').is_file())
        self.assertTrue((folder/'generation.log').is_file())

    def test_audio_file_without_done_metadata_never_becomes_success(self):
        for engine in ['ace-step-1.5', 'stable-audio-3-sfx']:
            for metadata in ['queued', 'running', 'error', None]:
                with self.subTest(engine=engine, metadata=metadata):
                    status, _, _ = self.submit_and_run(engine, metadata=metadata)
                    self.assertEqual(status['status'], 'error')
                    self.assertNotIn('audio', status)

    def test_done_metadata_without_audio_never_becomes_success(self):
        status, _, _ = self.submit_and_run('stable-audio-3-sfx', audio=False)
        self.assertEqual(status['status'], 'error')
        self.assertNotIn('audio', status)

    def test_missing_or_malformed_metadata_is_persisted_error(self):
        for metadata in ['missing', 'malformed']:
            with self.subTest(metadata=metadata):
                status, _, _ = self.submit_and_run(metadata=metadata)
                self.assertEqual(status['status'], 'error')
                self.assertTrue(status['error'])
                self.assertNotIn('audio', status)


if __name__ == '__main__':
    unittest.main()
