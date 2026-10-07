"""CPU integration regressions for engine dispatch, references and resume caches."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from PIL import Image

import comfy_client
import creation_api
import creation_settings
import flux_klein
import image_references
import model_profiles
import pipeline
import studio_extensions
import testing_support as tempfile


class FluxIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects/studio/flux-test'
        self.project.mkdir(parents=True)
        self.store = self.root / 'assets/image-references'
        self.output = self.project / 'image.png'
        buffer = io.BytesIO()
        Image.new('RGB', (64, 64), '#234567').save(buffer, format='PNG')
        self.png = buffer.getvalue()

    def spec(self, **changes):
        return {'engine': 'flux2-klein-4b', 'prompt': '原创角色，保留图一服装与面部特征',
                'width': 64, 'height': 64, 'steps': 4, 'cfg': 1, 'seed': 42,
                'reference_images': [], **changes}

    def reference(self, name='one.png', raw=None):
        path = self.project / 'references' / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw or self.png)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def response(self, data=None, content=b''):
        response = MagicMock()
        response.ok = True
        response.json.return_value = data
        response.content = content
        return response

    def fake_http(self, record=None):
        http = MagicMock()
        uploaded = []

        def post(url, **kwargs):
            if url.endswith('/upload/image'):
                uploaded.append(kwargs['files']['image'][1].read())
                return self.response({'name': 'upload-' + str(len(uploaded)) + '.png', 'subfolder': 'references'})
            if url.endswith('/prompt'):
                return self.response({'prompt_id': 'cpu-test'})
            self.fail('Unexpected HTTP mutation: ' + url)

        result = record if record is not None else {
            'status': {'status_str': 'success', 'completed': True},
            'outputs': {'10': {'images': [{'filename': 'result.png', 'type': 'output', 'subfolder': ''}]}}}

        def get(url, **kwargs):
            if '/history/' in url:
                return self.response({'cpu-test': result})
            if url.endswith('/view'):
                return self.response(content=self.png)
            self.fail('Unexpected HTTP read: ' + url)

        http.post.side_effect = post
        http.get.side_effect = get
        return http, uploaded

    def invoke_generate(self, spec, http):
        with patch.object(comfy_client, 'HTTP', http), patch('model_profiles.require'), \
                patch.object(image_references, 'ROOT', self.root), \
                patch.object(image_references, 'STORE', self.store):
            return comfy_client.generate(spec, self.output)

    @staticmethod
    def reference_chain(graph, conditioning):
        names = []
        while graph[conditioning[0]]['class_type'] == 'ReferenceLatent':
            inputs = graph[conditioning[0]]['inputs']
            encoder = graph[inputs['latent'][0]]['inputs']
            scaled = graph[encoder['pixels'][0]]['inputs']
            names.append(graph[scaled['image'][0]]['inputs']['image'])
            conditioning = inputs['conditioning']
        return list(reversed(names)), graph[conditioning[0]]['class_type']

    def test_four_ordered_references_reach_both_sampler_conditionings(self):
        names = ['character.png', 'outfit.png', 'location.png', 'lighting.png']
        graph = comfy_client.workflow('组合参考图', engine='flux2-klein-4b',
                                      steps=4, cfg=1, references=names)
        sampling = next(n['inputs'] for n in graph.values() if n['class_type'] == 'SamplerCustomAdvanced')
        guider = graph[sampling['guider'][0]]['inputs']
        self.assertEqual(self.reference_chain(graph, guider['positive']), (names, 'CLIPTextEncode'))
        self.assertEqual(self.reference_chain(graph, guider['negative']), (names, 'ConditioningZeroOut'))
        self.assertEqual(graph[sampling['latent_image'][0]]['class_type'], 'EmptyFlux2LatentImage')
        self.assertEqual(graph[sampling['sigmas'][0]]['class_type'], 'Flux2Scheduler')
        with self.assertRaises(ValueError):
            flux_klein.workflow('too many', references=names + ['fifth.png'])

    def test_legacy_positional_graph_stays_qwen_and_references_never_fall_back(self):
        models = dict(creation_settings.DEFAULTS['models'])
        graph = comfy_client.workflow('legacy', 'negative', 7, 576, 1024, 9, models, 3.5)
        self.assertEqual(graph['1']['class_type'], 'UnetLoaderGGUF')
        self.assertEqual(graph['2']['inputs']['type'], 'qwen_image')
        self.assertEqual(graph['8']['inputs']['steps'], 9)
        for options in [{'engine': 'qwen-image-2512', 'references': ['one.png']},
                        {'engine': 'unknown'}, {'engine': 'flux2-klein-4b', 'steps': 28, 'cfg': 4}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                comfy_client.workflow('must reject', **options)

    def test_real_reference_upload_order_and_result_provenance_survive_dispatch(self):
        first = self.reference()
        second = self.reference('two.png', self.png + b'permitted-trailing-marker')
        http, uploaded = self.fake_http()
        self.invoke_generate(self.spec(reference_images=[second, first]), http)
        self.assertEqual(uploaded, [Path(second['path']).read_bytes(), Path(first['path']).read_bytes()])
        graph = json.loads(self.output.with_suffix('.workflow.json').read_text(encoding='utf-8'))
        sampling = next(n['inputs'] for n in graph.values() if n['class_type'] == 'SamplerCustomAdvanced')
        guider = graph[sampling['guider'][0]]['inputs']
        self.assertEqual(self.reference_chain(graph, guider['positive'])[0],
                         ['references/upload-1.png', 'references/upload-2.png'])
        info = json.loads(self.output.with_suffix('.generation.json').read_text(encoding='utf-8'))
        self.assertEqual(info['reference_sha256'], [second['sha256'], first['sha256']])
        self.assertEqual(info['engine'], 'flux2-klein-4b')
        self.assertFalse(info['negative_prompt_used'])
        self.assertEqual(self.output.read_bytes(), self.png)

    def test_missing_models_or_tampered_reference_stop_before_any_http(self):
        http = MagicMock()
        with patch('model_profiles.require', side_effect=ValueError('missing klein')), \
                patch.object(comfy_client, 'HTTP', http):
            with self.assertRaisesRegex(ValueError, 'missing klein'):
                comfy_client.generate(self.spec(), self.output)
        http.post.assert_not_called()
        row = self.reference()
        Path(row['path']).write_bytes(self.png + b'changed')
        with self.assertRaisesRegex(ValueError, '变更'):
            self.invoke_generate(self.spec(reference_images=[row]), http)
        http.post.assert_not_called()

    def test_completed_comfy_job_without_image_fails_immediately(self):
        http, _ = self.fake_http({'status': {'status_str': 'success', 'completed': True}, 'outputs': {}})
        with patch.object(comfy_client.time, 'monotonic', side_effect=[0, 0, 0, 99999]), \
                patch.object(comfy_client.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, '图|image'):
                self.invoke_generate(self.spec(), http)
            sleep.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_legacy_settings_snapshot_cannot_inherit_new_global_engines(self):
        old = copy.deepcopy(creation_settings.DEFAULTS)
        old['image'].pop('engine')
        old['motion'].pop('engine')
        current = copy.deepcopy(creation_settings.DEFAULTS)
        current['image'].update(engine='flux2-klein-4b', steps=4, cfg=1)
        current['motion']['engine'] = 'wan2.2-a14b'
        with patch.object(creation_settings, 'load', return_value=current), \
                patch.object(creation_settings, 'model_file'), patch.object(model_profiles, 'require'):
            result = creation_api.snapshot({'settings': old, 'scenes': []})
        self.assertEqual(result['settings']['image']['engine'], 'qwen-image-2512')
        self.assertEqual(result['settings']['motion']['engine'], 'wan2.2-5b')
        self.assertEqual((result['settings']['image']['steps'], result['settings']['image']['cfg']), (28, 4))

    def test_explicit_reference_opt_out_clears_old_frozen_rows(self):
        old = self.reference()
        spec = {'settings': {'image': {'engine': 'flux2-klein-4b'}},
                'scenes': [{'id': 'one', 'image_reference_ids': [], 'image_references': [old]}]}
        with patch.object(image_references, 'ROOT', self.root), patch.object(image_references, 'STORE', self.store):
            actual = image_references.freeze_storyboard(spec, self.project)
        self.assertFalse(actual['scenes'][0].get('image_references'),
                         'Explicitly clearing references must not leave a hidden reference active')

    def test_conflicting_scene_steps_reject_before_job_submission(self):
        settings = copy.deepcopy(creation_settings.DEFAULTS)
        settings['image'].update(engine='flux2-klein-4b', steps=4, cfg=1)
        spec = {'settings': settings, 'scenes': [
            {'id': 'one', 'narration': '旁白', 'subject': '画面', 'style': '插画', 'steps': 20}]}
        handler = MagicMock()
        handler.path = '/api/produce'
        jobs = {}
        with patch.object(creation_settings, 'model_file'), patch.object(model_profiles, 'require'), \
                patch.object(studio_extensions, 'ROOT', self.root), \
                patch.object(studio_extensions, 'listening', return_value=False), \
                patch.object(studio_extensions.threading, 'Thread') as thread:
            with self.assertRaisesRegex(ValueError, '4|四'):
                studio_extensions.handle_post(handler, {'storyboard': spec}, jobs)
            thread.assert_not_called()
            self.assertFalse(jobs)
            self.assertEqual(list((self.root / 'projects/studio').iterdir()), [self.project])


class ImageResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects/example'
        self.project.mkdir(parents=True)
        (self.root / 'manifests').mkdir()
        (self.root / 'manifests/repositories.json').write_text('[]', encoding='utf-8')
        (self.root / 'scripts').mkdir()
        for source in (pipeline.ROOT / 'scripts').glob('*.py'):
            shutil.copy2(source, self.root / 'scripts' / source.name)
        self.settings = copy.deepcopy(creation_settings.DEFAULTS)
        self.settings['image'].update(engine='flux2-klein-4b', steps=4, cfg=1)
        self.spec = {'settings': self.settings, 'scenes': [
            {'id': 'scene01', 'narration': '旁白', 'subject': '原创人物', 'style': '电影感'}]}
        (self.project / 'storyboard.json').write_text(json.dumps(self.spec), encoding='utf-8')
        self.calls = []

    def invoke(self):
        def generate(spec, output):
            self.calls.append(copy.deepcopy(spec))
            output.write_bytes(b'CPU-generated-image-' + str(len(self.calls)).encode())

        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline, 'ROOT', self.root))
            stack.enter_context(patch.object(pipeline, 'load', return_value=self.settings))
            stack.enter_context(patch.object(pipeline.providers, 'load', return_value={}))
            stack.enter_context(patch.object(pipeline, 'generate', side_effect=generate))
            stack.enter_context(patch.object(pipeline, 'unload'))
            stack.enter_context(patch.object(image_references, 'ROOT', self.root))
            stack.enter_context(patch.object(image_references, 'STORE', self.root / 'assets/image-references'))
            stack.enter_context(patch.object(pipeline.imageio_ffmpeg, 'get_ffmpeg_exe',
                                            return_value=str(self.root / 'tools/ffmpeg.exe')))
            stack.enter_context(patch.dict(os.environ))
            stack.enter_context(patch.object(sys, 'argv', ['pipeline.py', str(self.project), '--stage', 'images']))
            pipeline.main()

    def test_changed_klein_graph_cannot_reuse_previous_image_cache(self):
        self.invoke()
        self.invoke()
        self.assertEqual(len(self.calls), 1, 'Unchanged completed image should resume without generation')
        source = self.root / 'scripts/flux_klein.py'
        source.write_text(source.read_text(encoding='utf-8') + '\n# sampling contract changed\n', encoding='utf-8')
        self.invoke()
        self.assertEqual(len(self.calls), 2, 'Changing the active graph must invalidate both stage and per-image caches')

    def test_cli_reference_ids_cannot_be_silently_dropped(self):
        self.spec['scenes'][0]['image_reference_ids'] = ['img-' + '0' * 24]
        (self.project / 'storyboard.json').write_text(json.dumps(self.spec), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.calls, [], 'Unresolved reference IDs must be resolved or rejected, never omitted')

    def test_completed_stage_still_checks_frozen_reference_integrity(self):
        reference = self.project / 'references/original.png'
        reference.parent.mkdir()
        reference.write_bytes(b'CPU fixture represents an already validated frozen image')
        sha = hashlib.sha256(reference.read_bytes()).hexdigest()
        ref_id = 'img-' + sha[:24]
        self.spec['scenes'][0].update(image_reference_ids=[ref_id], image_references=[
            {'id': ref_id, 'path': str(reference), 'sha256': sha, 'project_path': 'references/original.png'}])
        (self.project / 'storyboard.json').write_text(json.dumps(self.spec), encoding='utf-8')
        self.invoke()
        self.assertEqual(len(self.calls), 1)
        reference.write_bytes(b'The frozen source has been modified')
        with self.assertRaisesRegex(ValueError, '变更|修改|不一致'):
            self.invoke()
        self.assertEqual(len(self.calls), 1, 'Integrity rejection must precede generation or resume')


if __name__ == '__main__':
    unittest.main()
