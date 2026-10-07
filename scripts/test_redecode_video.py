"""CPU-only diagnostic contracts; ComfyUI requests are all mocked."""
import hashlib
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from filelock import FileLock, Timeout
import redecode_video as diagnostic
import testing_support as tempfile


class RedecodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'projects/studio/video-test'
        self.project.mkdir(parents=True)
        (self.root / 'manifests').mkdir()
        (self.root / 'apps/ComfyUI/input').mkdir(parents=True)
        (self.root / 'apps/ComfyUI/output').mkdir(parents=True)
        self.patch = patch.object(diagnostic, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        header = {'latent_tensor': {'dtype': 'F32', 'shape': [1, 16, 2, 2, 2], 'data_offsets': [0, 512]},
                  'latent_format_version_0': {'dtype': 'F32', 'shape': [0], 'data_offsets': [512, 512]}}
        content = json.dumps(header).encode()
        latent = struct.pack('<Q', len(content)) + content + b'\0' * 512
        (self.project / 'video.latent').write_bytes(latent)
        self.metadata = {'engine': 'wan2.2-a14b', 'status': 'done', 'width': 16, 'height': 16,
                         'frames': 5, 'fps': 16, 'latent_sha256': hashlib.sha256(latent).hexdigest()}
        self.write_metadata()
        self.graph = {'3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'wan_2.1_vae.safetensors'}}}
        (self.project / 'video.workflow.json').write_text(json.dumps(self.graph), encoding='utf-8')
        (self.project / 'video.mp4').write_bytes(b'original must survive')

    def write_metadata(self):
        (self.project / 'video.generation.json').write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_prepare_uses_only_decode_nodes_and_never_contacts_service(self):
        with patch.object(diagnostic, 'HTTP') as http:
            plan, graph = diagnostic.prepare(self.project, 16, 4)
        http.get.assert_not_called()
        http.post.assert_not_called()
        self.assertEqual({node['class_type'] for node in graph.values()},
                         {'LoadLatent', 'VAELoader', 'VAEDecodeTiled', 'SaveImage'})
        self.assertEqual(graph['3']['inputs']['samples'], ['1', 0])
        self.assertEqual((graph['3']['inputs']['temporal_size'], graph['3']['inputs']['temporal_overlap']), (16, 4))
        self.assertFalse(plan['samples_are_resampled'])
        self.assertEqual(list((self.root / 'apps/ComfyUI/input').iterdir()), [])
        self.assertEqual((self.project / 'video.mp4').read_bytes(), b'original must survive')
        second, _ = diagnostic.prepare(self.project, 128, 16)
        self.assertNotEqual(second['directory'], plan['directory'])

    def test_sha_tampering_is_rejected_before_new_output_or_network(self):
        path = self.project / 'video.latent'
        content = path.read_bytes()
        path.write_bytes(content[:-1] + b'1')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            diagnostic.prepare(self.project)
        self.assertFalse((self.project / 'redecode').exists())

    def test_running_producer_and_shape_mismatch_are_rejected(self):
        self.metadata['status'] = 'running'
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, '尚未结束'):
            diagnostic.load_source(self.project)
        self.metadata.update(status='done', frames=9)
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, '形状'):
            diagnostic.load_source(self.project)

    def test_temporal_boundary_rejects_silent_overlap_adjustment(self):
        for args in [(4, 4), (4097, 4), (15, 4), (16, 12), (16, 3), (True, 4)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                diagnostic.validate_temporal(*args)
        for args in [(8, 4), (16, 4), (128, 16), (4096, 2048)]:
            diagnostic.validate_temporal(*args)

    def test_existing_gpu_lock_prevents_any_network_or_input_copy(self):
        plan, graph = diagnostic.prepare(self.project)
        with FileLock(str(self.root / 'manifests/gpu.lock'), timeout=0), patch.object(diagnostic, 'HTTP') as http:
            with self.assertRaises(Timeout):
                diagnostic.run(plan, graph)
        http.get.assert_not_called()
        http.post.assert_not_called()
        self.assertEqual(list((self.root / 'apps/ComfyUI/input').iterdir()), [])

    def test_nonempty_queue_does_not_submit_or_free_other_jobs(self):
        plan, graph = diagnostic.prepare(self.project)
        with patch.object(diagnostic, 'HTTP') as http:
            http.get.return_value.json.return_value = {'queue_running': [[1, 'other-job']], 'queue_pending': []}
            with self.assertRaisesRegex(RuntimeError, '队列非空'):
                diagnostic.run(plan, graph)
            http.post.assert_not_called()
        self.assertEqual(list((self.root / 'apps/ComfyUI/input').iterdir()), [])

    def test_completed_without_frames_fails_immediately(self):
        plan, graph = diagnostic.prepare(self.project)
        with patch.object(diagnostic, 'HTTP') as http, patch.object(diagnostic.time, 'sleep') as sleep:
            queue = MagicMock()
            queue.json.return_value = {'queue_running': [], 'queue_pending': []}
            history = MagicMock()
            history.json.return_value = {'pid': {'status': {'completed': True, 'status_str': 'success'}, 'outputs': {}}}
            http.get.side_effect = [queue, history]
            http.post.return_value.json.return_value = {'prompt_id': 'pid'}
            with self.assertRaisesRegex(RuntimeError, '实际输出帧数 0'):
                diagnostic.run(plan, graph)
            sleep.assert_not_called()
        self.assertEqual((self.project / 'video.mp4').read_bytes(), b'original must survive')

    def test_output_count_geometry_and_traversal_checked_before_encoding(self):
        plan, _ = diagnostic.prepare(self.project)
        source = plan['source']
        base = self.root / 'apps/ComfyUI/output'
        entries = []
        for index in range(5):
            name = f'{index}.png'
            Image.new('RGB', (16, 16), (index * 30, 0, 0)).save(base / name)
            entries.append({'type': 'output', 'subfolder': '', 'filename': name})
        frames, count = diagnostic.output_frames({'outputs': {'4': {'images': entries}}}, Path(plan['directory']), source)
        self.assertEqual(count, 5)
        self.assertEqual(len(list(frames.glob('*.png'))), 5)
        another, _ = diagnostic.prepare(self.project)
        entries[-1]['filename'] = '../input/escape.png'
        with self.assertRaisesRegex(ValueError, '路径越界'):
            diagnostic.output_frames({'outputs': {'4': {'images': entries}}}, Path(another['directory']), source)


if __name__ == '__main__':
    unittest.main()
