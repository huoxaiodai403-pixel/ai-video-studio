"""Constrain the desktop bridge HTTP surface to known projects and operations."""
import io
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import studio_extensions as routes


class JianyingRoutesTests(unittest.TestCase):
    def setUp(self):
        self.bridge = types.SimpleNamespace(
            status=MagicMock(return_value={'installed': False, 'bridge_ready': True}),
            export_project=MagicMock(return_value={'draft_name': 'Known project', 'mode': 'scenes'}),
            open_jianying=MagicMock(return_value={'message': 'started'}),
        )
        self.patch = patch.dict(sys.modules, {'jianying_bridge': self.bridge})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.handler = MagicMock()
        self.handler.headers = {'Content-Type': 'application/json; charset=utf-8'}

    def test_status_rejects_paths_duplicate_and_unknown_query_parameters(self):
        for query in ('project_id=../secret', 'project_id=C%3A%5CWindows', 'project_id=',
                      'project_id=x&project_id=y', 'executable=notepad.exe'):
            with self.subTest(query=query):
                self.assertTrue(routes.handle_get(self.handler, urlparse('/api/jianying/status?' + query)))
                self.assertEqual(self.handler.reply.call_args.args[1], 400)
        self.bridge.status.assert_not_called()

    def test_status_and_export_pass_only_validated_project_and_mode(self):
        routes.handle_get(self.handler, urlparse('/api/jianying/status?project_id=video-sample'))
        self.bridge.status.assert_called_once_with('video-sample')
        self.handler.path = '/api/jianying/export'
        self.assertTrue(routes.handle_post(self.handler, {'project_id': 'video-sample', 'mode': 'scenes'}, {}))
        self.bridge.export_project.assert_called_once_with('video-sample', mode='scenes')

    def test_export_and_open_reject_client_paths_commands_and_wrong_shapes(self):
        for route, body in [
            ('export', {'project_id': 'video-sample', 'path': 'C:/private'}),
            ('export', {'project_id': '../private'}),
            ('export', {'project_id': None}),
            ('export', {'project_id': True}),
            ('export', {'project_id': 'video-sample', 'mode': 'command'}),
            ('export', {'project_id': 'video-sample', 'mode': []}),
            ('export', {}),
            ('open', {'project_id': 'video-sample', 'executable': 'cmd.exe'}),
            ('open', {'project_id': 'video-sample', 'mode': 'scenes'}),
            ('open', {'project_id': None}),
            ('open', []),
        ]:
            with self.subTest(route=route, body=body):
                self.handler.path = '/api/jianying/' + route
                with self.assertRaises(ValueError):
                    routes.handle_post(self.handler, body, {})
        self.bridge.export_project.assert_not_called()
        self.bridge.open_jianying.assert_not_called()

    def test_desktop_operations_require_json_content_type(self):
        self.handler.path = '/api/jianying/open'
        for value in ('', 'text/plain', 'application/x-www-form-urlencoded'):
            self.handler.headers = {'Content-Type': value}
            routes.handle_post(self.handler, {}, {})
            self.assertEqual(self.handler.reply.call_args.args[1], 415)
        self.bridge.open_jianying.assert_not_called()

    def test_open_without_project_only_calls_probed_application(self):
        self.handler.path = '/api/jianying/open'
        routes.handle_post(self.handler, {}, {})
        self.bridge.open_jianying.assert_called_once_with(None)

    def test_status_failure_is_a_json_error(self):
        self.bridge.status.side_effect = ValueError('Project missing')
        routes.handle_get(self.handler, urlparse('/api/jianying/status?project_id=missing'))
        self.handler.reply.assert_called_once_with({'error': 'Project missing'}, 400)

    def test_existing_http_origin_gate_blocks_cross_site_desktop_launch(self):
        from studio import Handler
        handler = Handler.__new__(Handler)
        handler.path = '/api/jianying/open'
        body = json.dumps({}).encode()
        handler.headers = {'Origin': 'https://untrusted.example', 'Content-Type': 'application/json',
                           'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.reply = MagicMock()
        handler.do_POST()
        handler.reply.assert_called_once_with({'error': 'origin rejected'}, 403)
        self.assertEqual(handler.rfile.tell(), 0)
        self.bridge.open_jianying.assert_not_called()


if __name__ == '__main__':
    unittest.main()
