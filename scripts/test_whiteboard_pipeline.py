"""Whiteboard resume and GPU scheduling regressions; no model or renderer runs."""
import copy
import json
import os
import shutil
import sys
import testing_support as tempfile
import unittest
import wave
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from filelock import FileLock, Timeout

import creation_settings
import pipeline
import wan_client


class WhiteboardPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root/'projects/example'
        self.project.mkdir(parents=True)
        (self.root/'manifests').mkdir()
        (self.root/'manifests/repositories.json').write_text('[]', encoding='utf-8')
        self.lock_path = self.root/'manifests/gpu.lock'

        # Keep the real fingerprinting behavior while isolating all writes and
        # locks. These source copies are never imported or executed.
        (self.root/'scripts').mkdir()
        for source in (pipeline.ROOT/'scripts').iterdir():
            if source.is_file() and source.suffix in ('.py', '.cjs', '.ps1'):
                shutil.copy2(source, self.root/'scripts'/source.name)
        relative = Path('apps/simon-skills/skills/whiteboard-video')
        (self.root/relative).mkdir(parents=True)
        shutil.copy2(pipeline.ROOT/relative/'config.json', self.root/relative/'config.json')
        shutil.copytree(pipeline.ROOT/relative/'lib', self.root/relative/'lib')

        self.spec = {
            'render_mode': 'excalidraw',
            'motion_enabled': True,  # An old motion toggle must not run Wan.
            'backends': {'tts': 'local', 'asr': 'local'},
            'settings': copy.deepcopy(creation_settings.DEFAULTS),
            'scenes': [{'id': 'scene01', 'narration': '测试一。'},
                       {'id': 'scene02', 'narration': '测试二。'}],
        }
        (self.project/'storyboard.json').write_text(
            json.dumps(self.spec, ensure_ascii=False), encoding='utf-8')
        self.calls = []
        self.on_render = None

    def fake_stage(self, command, log, cwd=None):
        script = Path(command[1]).name
        self.calls.append(script)
        audio = self.project/'audio'
        audio.mkdir(exist_ok=True)
        if script == 'tts_batch.py':
            for scene in self.spec['scenes']:
                with wave.open(str(audio/(scene['id']+'.wav')), 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(16000)
                    output.writeframes(b'\0\0'*8000)
        elif script == 'align_batch.py':
            (self.project/'subtitles.srt').write_text(
                '1\n00:00:00,000 --> 00:00:00,400\n测试\n', encoding='utf-8')
            (self.project/'timeline.json').write_text('[]', encoding='utf-8')
            for scene in self.spec['scenes']:
                (audio/(scene['id']+'.alignment.json')).write_text(
                    json.dumps([{'text': scene['narration'], 'start': 0.0, 'end': 0.4}]),
                    encoding='utf-8')
        elif script == 'simon_whiteboard.py':
            if self.on_render:
                self.on_render()
            (self.project/'video.mp4').write_bytes(b'rendered-test-artifact')
        else:
            self.fail('Unexpected subprocess: '+script)

    def invoke(self, stage='all'):
        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, 'ROOT', self.root))
            stack.enter_context(patch.object(pipeline, 'load', return_value=self.spec['settings']))
            stack.enter_context(patch.object(pipeline.providers, 'load', return_value={}))
            stack.enter_context(patch.object(pipeline, 'run', side_effect=self.fake_stage))
            stack.enter_context(patch.object(pipeline, 'unload'))
            stack.enter_context(patch.object(pipeline.imageio_ffmpeg, 'get_ffmpeg_exe',
                                              return_value=str(self.root/'tools/ffmpeg.exe')))
            for target, name in ((pipeline, 'generate'), (pipeline, 'render'),
                                 (pipeline.providers, 'image'), (pipeline.providers, 'video'),
                                 (wan_client, 'generate')):
                stack.enter_context(patch.object(target, name,
                    side_effect=AssertionError('Whiteboard invoked diffusion or illustrated rendering')))
            stack.enter_context(patch.dict(os.environ))
            stack.enter_context(patch.object(sys, 'argv',
                ['pipeline.py', str(self.project), '--stage', stage]))
            pipeline.main()

    def test_missing_scene_alignment_repeats_alignment_instead_of_skipping(self):
        self.invoke('align')
        self.calls.clear()
        self.invoke('align')
        self.assertEqual(self.calls, [], 'A complete alignment should resume without work')

        missing = self.project/'audio/scene02.alignment.json'
        missing.unlink()
        self.assertTrue((self.project/'subtitles.srt').is_file())
        self.assertTrue((self.project/'timeline.json').is_file())
        self.invoke('align')
        self.assertEqual(self.calls, ['align_batch.py'])
        self.assertTrue(missing.is_file(), 'Missing real timestamps must be regenerated')

    def test_render_only_runs_while_another_job_holds_gpu_lock(self):
        with FileLock(str(self.lock_path), timeout=0) as holder:
            with self.assertRaises(Timeout):
                with FileLock(str(self.lock_path), timeout=0):
                    pass
            self.on_render = lambda: self.assertTrue(holder.is_locked)
            self.invoke('render')
        self.assertEqual(self.calls, ['simon_whiteboard.py'])
        self.assertTrue((self.project/'video.mp4').is_file())

    def test_full_whiteboard_pipeline_never_runs_image_or_motion_stages(self):
        def renderer_can_release_gpu():
            with FileLock(str(self.lock_path), timeout=0):
                pass
        self.on_render = renderer_can_release_gpu
        self.invoke()
        self.assertEqual(self.calls, ['tts_batch.py', 'align_batch.py', 'simon_whiteboard.py'])
        state = json.loads((self.project/'state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['completed'], ['tts', 'align', 'render'])
        self.assertIsNone(state['running'])
        self.assertNotIn('error', state)

    def test_cpu_speech_and_synthesis_captions_do_not_reserve_gpu(self):
        import lightweight_speech
        self.spec['backends'] = {'tts': 'windows', 'asr': 'synthesis'}
        (self.project/'storyboard.json').write_text(json.dumps(self.spec), encoding='utf-8')
        with FileLock(str(self.lock_path), timeout=0), \
             patch.object(lightweight_speech, 'tts_project', side_effect=lambda *args: (self.fake_stage(['python','tts_batch.py'],None), self.fake_stage(['python','align_batch.py'],None))), \
             patch.object(lightweight_speech, 'align_project') as align:
            self.invoke()
        align.assert_called_once()
        self.assertTrue((self.project/'video.mp4').is_file())


if __name__ == '__main__':
    unittest.main()
