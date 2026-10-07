"""CPU-only tests for dual-expert conditioning and existing Wan dispatch."""
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import testing_support as tempfile
import wan_a14b
import wan_client


PARTS = [
    {'role': 'unet_high', 'name': 'wan2.2_i2v_high_noise_14B_Q4_K_M.gguf'},
    {'role': 'unet_low', 'name': 'wan2.2_i2v_low_noise_14B_Q4_K_M.gguf'},
    {'role': 'clip', 'name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors'},
    {'role': 'vae', 'name': 'wan_2.1_vae.safetensors'},
]
LEGACY = {'video_unet': 'original-5B.safetensors', 'video_clip': 'original-t5.safetensors',
          'video_vae': 'original-wan22.safetensors'}


class WanA14BTests(unittest.TestCase):
    def graph(self, **kwargs):
        with patch.object(wan_a14b, 'components', return_value=PARTS):
            return wan_client.workflow('镜头缓慢推进', image='reference.png', engine='wan2.2-a14b',
                                       frames=81, width=832, height=480, **kwargs)

    def test_experts_continue_same_schedule_without_renoising(self):
        graph = self.graph()
        high, low = (graph[node]['inputs'] for node in ('8', '14'))
        self.assertEqual((high['start_at_step'], high['end_at_step'], low['start_at_step'], low['end_at_step']), (0, 10, 10, 20))
        self.assertEqual((high['steps'], low['steps']), (20, 20))
        self.assertEqual((high['add_noise'], low['add_noise']), ('enable', 'disable'))
        self.assertEqual((high['return_with_leftover_noise'], low['return_with_leftover_noise']), ('enable', 'disable'))
        self.assertEqual(low['latent_image'], ['8', 0])
        self.assertEqual(graph['15']['class_type'], 'SaveLatent')
        self.assertEqual(graph['15']['inputs']['samples'], ['14', 0])
        self.assertEqual(graph['9']['inputs']['samples'], ['15', 0])
        # 81 output frames = 21 temporal latents. The 128-frame window covers
        # all latents, avoiding the 12-frame boundary artefact of 16/4 tiles.
        self.assertGreaterEqual(graph['9']['inputs']['temporal_size']//4, (81+3)//4)
        self.assertEqual(high['latent_image'], ['6', 2])
        for sampler in (high, low):
            self.assertEqual((sampler['positive'], sampler['negative']), (['6', 0], ['6', 1]))
            self.assertEqual((sampler['cfg'], sampler['sampler_name'], sampler['scheduler']), (3.5, 'euler', 'simple'))
        self.assertFalse(any('Lora' in node['class_type'] for node in graph.values()))

    def test_image_conditioning_vae_and_models_are_not_inherited_from_5b(self):
        graph = self.graph(models=LEGACY)
        self.assertEqual(graph['3']['inputs']['vae_name'], 'wan_2.1_vae.safetensors')
        self.assertEqual(graph['1']['class_type'], 'UnetLoaderGGUF')
        self.assertEqual(graph['12']['inputs']['unet_name'], PARTS[1]['name'])
        self.assertEqual(graph['6']['class_type'], 'WanImageToVideo')
        self.assertEqual(graph['6']['inputs']['start_image'], ['11', 0])
        self.assertEqual(graph['2']['inputs']['device'], 'cpu')
        self.assertNotIn('clip_vision_output', graph['6']['inputs'])
        self.assertEqual((graph['7']['inputs']['shift'], graph['13']['inputs']['shift']), (5, 5))

    def test_odd_step_counts_do_not_drop_or_duplicate_a_step(self):
        graph = self.graph(steps=21)
        high, low = graph['8']['inputs'], graph['14']['inputs']
        self.assertEqual(list(range(high['start_at_step'], high['end_at_step'])) +
                         list(range(low['start_at_step'], low['end_at_step'])), list(range(21)))

    def test_input_validation_rejects_missing_image_and_bad_latent_shape(self):
        for changed in [{'image': None}, {'image': ''}, {'steps': 1}, {'steps': True},
                        {'frames': 80}, {'frames': 81.0}, {'width': 831}, {'height': 479}]:
            args = {'image': 'a.png', 'steps': 20, 'frames': 81, 'width': 832, 'height': 480, **changed}
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                wan_a14b.validate(**args)

    def test_old_5b_positional_signature_and_text_only_path_remain_available(self):
        graph = wan_client.workflow('原始文字转视频', None, 20, 49, 42, 512, 288, LEGACY)
        self.assertEqual(graph['1']['inputs']['unet_name'], LEGACY['video_unet'])
        self.assertEqual(graph['6']['class_type'], 'Wan22ImageToVideoLatent')
        self.assertEqual(graph['8']['class_type'], 'KSampler')
        self.assertNotIn('11', graph)
        self.assertEqual(graph['3']['inputs']['vae_name'], LEGACY['video_vae'])
        self.assertEqual(graph['7']['inputs']['shift'], 8)

    def test_missing_a14b_models_fail_before_gpu_unload_upload_or_submission(self):
        with patch('model_profiles.require', side_effect=ValueError('missing experts')), \
                patch.object(wan_client, 'HTTP') as http, patch.object(wan_client, 'unload') as unload:
            with self.assertRaisesRegex(ValueError, 'missing experts'):
                wan_client.generate('test', 'not-created.mp4', image='input.png', engine='wan2.2-a14b')
            unload.assert_not_called()
            http.post.assert_not_called()

    def test_unknown_engine_never_falls_back_to_5b(self):
        with self.assertRaises(ValueError):
            wan_client.workflow('test', models=LEGACY, engine='unknown')

    def test_stage_history_reports_error_location_and_no_fabricated_timing(self):
        graph = self.graph()
        record = {'status': {'status_str': 'error', 'messages': [
            ['execution_error', {'node_id': '14', 'executed': ['1', '6', '8']}]]}}
        rows = wan_client._stage_history(graph, record)
        self.assertEqual([row['status'] for row in rows], ['completed', 'failed'])
        self.assertTrue(all(row['elapsed_seconds'] is None for row in rows))
        cached = {'status': {'status_str': 'success', 'completed': True, 'messages': [
            ['execution_cached', {'nodes': ['8']}]]}}
        self.assertEqual([row['status'] for row in wan_client._stage_history(graph, cached)], ['cached', 'completed'])

    def fake_render(self, root, returned=5, ffmpeg_error=False):
        output = root / 'project' / 'clip.mp4'
        source = root / 'apps/ComfyUI/output' / 'WanTest'
        source.mkdir(parents=True)
        entries = []
        for i in range(returned):
            name = f'{i}.png'
            (source / name).write_bytes(b'cpu-only-test-frame')
            entries.append({'subfolder': 'WanTest', 'filename': name})
        record = {'status': {'status_str': 'success', 'completed': True, 'messages': []},
                  'outputs': {'10': {'images': entries}}}
        http = MagicMock()
        http.post.return_value.ok = True
        http.post.return_value.json.return_value = {'prompt_id': 'test-prompt'}
        http.get.return_value.json.return_value = {'test-prompt': record}
        encoder = MagicMock(side_effect=subprocess.CalledProcessError(7, 'ffmpeg') if ffmpeg_error else None)
        with patch.object(wan_client, 'ROOT', root), patch.object(wan_client, 'HTTP', http), \
                patch.object(wan_client, 'unload'), patch.object(wan_client.subprocess, 'run', encoder):
            try:
                wan_client.generate('test', output, frames=5, already_locked=True, models=LEGACY)
            except (RuntimeError, subprocess.CalledProcessError):
                return output, encoder, False
        return output, encoder, True

    def test_output_frames_are_isolated_and_metadata_uses_actual_frame_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / 'project/frames/old-take'
            stale.mkdir(parents=True)
            (stale / '00099.png').write_bytes(b'stale')
            output, encoder, success = self.fake_render(root)
            self.assertTrue(success)
            info = json.loads(output.with_suffix('.generation.json').read_text(encoding='utf-8'))
            self.assertEqual((info['engine'], info['status'], info['actual_frames']), ('wan2.2-5b', 'done', 5))
            self.assertEqual(info['duration_seconds'], 5 / 16)
            self.assertEqual(len(list(Path(info['frames_directory']).glob('*.png'))), 5)
            self.assertNotIn(str(stale), encoder.call_args.args[0])
            self.assertTrue(output.with_suffix('.history.json').is_file())

    def test_incomplete_output_and_ffmpeg_failure_do_not_report_done(self):
        for returned, fail in [(4, False), (5, True)]:
            with self.subTest(returned=returned, ffmpeg_failure=fail), tempfile.TemporaryDirectory() as tmp:
                output, encoder, success = self.fake_render(Path(tmp), returned, fail)
                self.assertFalse(success)
                info = json.loads(output.with_suffix('.generation.json').read_text(encoding='utf-8'))
                self.assertEqual(info['status'], 'error')
                if returned == 4:
                    encoder.assert_not_called()
                else:
                    self.assertEqual(info['ffmpeg_returncode'], 7)


if __name__ == '__main__':
    unittest.main()
