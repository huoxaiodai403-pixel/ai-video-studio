"""Regression checks for browser seeking and isolation of regenerated takes."""
import testing_support as tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import studio
import wan_client


class DeliveryTests(unittest.TestCase):
    def test_encoded_filenames_ranges_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root/'projects/studio/take'
            output.mkdir(parents=True)
            payload = bytes(range(256))*16
            (output/'封面.png').write_bytes(payload)
            (root/'secret.txt').write_text('private', encoding='utf-8')
            with patch.object(studio, 'ROOT', root):
                server = ThreadingHTTPServer(('127.0.0.1', 0), studio.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{server.server_port}'
                client = requests.Session()
                client.trust_env = False
                try:
                    url = base+'/outputs/take/封面.png'
                    response = client.get(url, headers={'Range': 'bytes=10-19'}, timeout=5)
                    self.assertEqual(response.status_code, 206)
                    self.assertEqual(response.content, payload[10:20])
                    self.assertEqual(response.headers['Content-Range'], 'bytes 10-19/4096')
                    self.assertEqual(client.get(url, headers={'Range': 'bytes=-20'}, timeout=5).content, payload[-20:])
                    head = client.head(url, timeout=5)
                    self.assertEqual(head.status_code, 200)
                    self.assertEqual(int(head.headers['Content-Length']), len(payload))
                    self.assertEqual(head.content, b'')
                    for value in ['bytes=4096-', 'bytes=20-10', 'bytes=-0', 'bytes=0-1,3-4']:
                        self.assertEqual(client.get(url, headers={'Range': value}, timeout=5).status_code, 416)
                    escaped = client.get(base+'/outputs/%2e%2e%2f%2e%2e%2fsecret.txt', timeout=5)
                    self.assertEqual(escaped.status_code, 400)
                finally:
                    client.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)

    def test_shorter_rerender_cannot_append_previous_take(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'apps/ComfyUI/output'
            source.mkdir(parents=True)
            for i in range(3):
                (source/f'{i}.png').write_bytes(bytes([i]))
            output = root/'project/motion/scene01.mp4'
            images = [{'subfolder': '', 'filename': f'{i}.png'} for i in range(3)]
            calls = []
            for prompt_id, count in [('take-one', 3), ('take-two', 1)]:
                post = Mock(ok=True)
                post.json.return_value = {'prompt_id': prompt_id}
                get = Mock()
                get.json.return_value = {prompt_id: {'outputs': {'10': {'images': images[:count]}}}}
                with patch.object(wan_client, 'ROOT', root), patch.object(wan_client, 'unload'), \
                     patch.object(wan_client.HTTP, 'post', return_value=post), \
                     patch.object(wan_client.HTTP, 'get', return_value=get), \
                     patch.object(wan_client.subprocess, 'run', side_effect=lambda cmd, **kw: calls.append(cmd)):
                    wan_client.generate('test', output, frames=count, already_locked=True)
            folders = [Path(cmd[cmd.index('-i')+1]).parent for cmd in calls]
            self.assertNotEqual(folders[0], folders[1])
            self.assertEqual(len(list(folders[0].glob('*.png'))), 3)
            self.assertEqual(len(list(folders[1].glob('*.png'))), 1)
            self.assertEqual(calls[1][calls[1].index('-frames:v')+1], '1')


if __name__ == '__main__':
    unittest.main()
