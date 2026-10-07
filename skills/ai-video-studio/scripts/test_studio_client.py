"""CPU-only checks for local boundaries, payload integrity and delivery downloads."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import studio_client as cli


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://example.com/')
            self.end_headers()
            return
        if self.path.startswith('/outputs/'):
            body = b'delivery-test-content'
            self.send_response(200)
        elif self.path == '/api/jobs':
            body = json.dumps({'whiteboard-1234567890': {'status': 'done', 'video': '/outputs/whiteboard-1234567890/video.mp4'}}).encode()
            self.send_response(200)
        elif self.path.startswith('/api/jianying/status'):
            body = json.dumps({'installed': True, 'bridge_ready': True,
                               'requested_path': self.path}).encode()
            self.send_response(200)
        else:
            body = json.dumps({'job_id': 'investigation-1234567890', 'gaps': [{'severity': 'error'}]}).encode()
            self.send_response(422)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path not in ('/api/jianying/export', '/api/jianying/open'):
            self.send_response(404)
            body = b'{}'
        elif payload.get('project_id') == 'whiteboard-0000000000':
            self.send_response(422)
            body = json.dumps({'error': 'Project has no rendered media',
                               'project_id': payload['project_id'],
                               'warnings': ['Render or import media first']}).encode()
        else:
            self.send_response(200)
            body = json.dumps({'requested_path': self.path, 'payload': payload,
                               'opened': self.path.endswith('/open'),
                               'draft_opened_automatically': False}).encode()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.client = cli.Client('http://127.0.0.1:' + str(cls.server.server_port))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def test_reject_nonlocal_and_credential_urls(self):
        for url in ('https://example.com', 'http://192.168.1.1:8189', 'file:///etc/passwd',
                    'http://user:password@localhost:8189', 'http://localhost:8189/path'):
            with self.subTest(url=url), self.assertRaises(cli.StudioError):
                cli.Client(url)

    def test_local_ipv4_ipv6_and_hostname(self):
        for url in ('http://127.0.0.1:8189/', 'http://[::1]:8189', 'http://localhost:8189'):
            self.assertTrue(cli.local_base(url).startswith('http'))

    def test_redirect_never_followed(self):
        with self.assertRaises(cli.StudioError):
            self.client.json('/redirect')

    def test_error_retains_existing_project_and_gaps(self):
        with self.assertRaises(cli.StudioError) as captured:
            self.client.json('/missing')
        self.assertEqual(captured.exception.detail['job_id'], 'investigation-1234567890')
        self.assertTrue(captured.exception.detail['gaps'])

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'request.json'
            for value in ('{"title":"first","title":"second"}', '{"number":NaN}', '[]'):
                path.write_text(value, encoding='utf-8')
                with self.assertRaises(cli.StudioError):
                    cli.load_payload(path)
            path.write_text('{"title":"方法讲解"}', encoding='utf-8-sig')
            self.assertEqual(cli.load_payload(path)['title'], '方法讲解')

    def test_download_paths_cannot_leave_artifact_endpoints(self):
        for value in ('https://example.com/video.mp4', '//example.com/file',
                      '/outputs/whiteboard-1234567890/%2e%2e/config.json', '/api/providers',
                      '/outputs/whiteboard-1234567890/video.mp4?other=1',
                      '/outputs/whiteboard-1234567890/%5cfile'):
            with self.subTest(value=value), self.assertRaises(cli.StudioError):
                cli.download_path(value)

    def test_download_hash_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.mp4'
            result = cli.save_download(self.client, '/outputs/whiteboard-1234567890/video.mp4', path, 1024)
            self.assertEqual(result['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            original = path.read_bytes()
            with self.assertRaises(cli.StudioError):
                cli.save_download(self.client, '/outputs/whiteboard-1234567890/video.mp4', path, 1024)
            self.assertEqual(path.read_bytes(), original)

    def test_oversized_download_leaves_no_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'result.mp4'
            with self.assertRaises(cli.StudioError):
                cli.save_download(self.client, '/outputs/whiteboard-1234567890/video.mp4', path, 3)
            self.assertFalse(path.exists())

    def test_status_reads_real_job_shape(self):
        self.assertEqual(self.client.job('whiteboard-1234567890')['status'], 'done')
        with self.assertRaises(cli.StudioError):
            self.client.job('whiteboard-0000000000')

    def invoke(self, *arguments):
        with patch.object(cli, 'output') as captured:
            code = cli.main(['--url', self.client.base, *arguments])
        self.assertEqual(code, 0)
        return captured.call_args.args[0]

    def test_jianying_status_checks_global_or_one_project_without_launching(self):
        global_state = self.invoke('jianying', 'status')
        self.assertEqual(global_state['requested_path'], '/api/jianying/status')
        project_state = self.invoke('jianying', 'status', '--project', 'whiteboard-1234567890')
        self.assertEqual(project_state['requested_path'],
                         '/api/jianying/status?project_id=whiteboard-1234567890')
        self.assertTrue(project_state['installed'])
        custom_state = self.invoke('jianying', 'status', '--project', 'My_Imported_Project-1')
        self.assertEqual(custom_state['requested_path'],
                         '/api/jianying/status?project_id=My_Imported_Project-1')

    def test_jianying_export_sends_only_selected_project_and_mode(self):
        for mode in ('auto', 'scenes', 'flattened'):
            with self.subTest(mode=mode):
                result = self.invoke('jianying', 'export', '--project', 'whiteboard-1234567890',
                                     '--mode', mode)
                self.assertEqual(result['requested_path'], '/api/jianying/export')
                self.assertEqual(result['payload'], {'project_id': 'whiteboard-1234567890', 'mode': mode})

    def test_jianying_open_keeps_launch_and_opened_project_distinct(self):
        result = self.invoke('jianying', 'open')
        self.assertEqual(result['requested_path'], '/api/jianying/open')
        self.assertEqual(result['payload'], {})
        self.assertTrue(result['opened'])
        self.assertFalse(result['draft_opened_automatically'])
        result = self.invoke('jianying', 'open', '--project', 'whiteboard-1234567890')
        self.assertEqual(result['payload'], {'project_id': 'whiteboard-1234567890'})

    def test_jianying_rejects_project_path_before_contacting_service(self):
        for action in ('status', 'export', 'open'):
            with self.subTest(action=action), patch.object(cli.Client, 'json') as request:
                with self.assertRaises(cli.StudioError):
                    cli.main(['--url', self.client.base, 'jianying', action, '--project', '../config'])
                request.assert_not_called()

    def test_jianying_export_retains_actionable_server_error(self):
        with self.assertRaises(cli.StudioError) as captured:
            self.invoke('jianying', 'export', '--project', 'whiteboard-0000000000')
        self.assertEqual(captured.exception.detail['project_id'], 'whiteboard-0000000000')
        self.assertEqual(captured.exception.detail['warnings'], ['Render or import media first'])

    def test_jianying_copy_timeout_does_not_slow_other_requests(self):
        cases = [(['jianying', 'export', '--project', 'whiteboard-1234567890'], 600),
                 (['jianying', 'status'], 20),
                 (['--timeout', '45', 'jianying', 'export', '--project', 'whiteboard-1234567890'], 45)]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments), patch.object(cli, 'Client') as client, patch.object(cli, 'output'):
                cli.main(['--url', self.client.base, *arguments])
                client.assert_called_once_with(self.client.base, expected)
        with self.assertRaises(cli.StudioError):
            self.invoke('--timeout', '600', 'jianying', 'open')


if __name__ == '__main__':
    unittest.main()
