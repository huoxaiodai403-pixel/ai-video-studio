import testing_support as tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from filelock import FileLock
import local_story
import creation_api
from urllib.parse import urlparse


class LocalStoryTests(unittest.TestCase):
    def test_empty_ollama_model_list_reports_not_ready(self):
        handler = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value.json.return_value = {'data': None}
        with patch.object(creation_api.requests, 'Session', return_value=session):
            self.assertTrue(creation_api.get(handler, urlparse('/api/story/status')))
        self.assertFalse(handler.reply.call_args.args[0]['ready'])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        (self.root/'manifests').mkdir()
        (self.root/'apps/Ollama').mkdir(parents=True)
        (self.root/'apps/Ollama/ollama.exe').touch()
        self.addCleanup(self.folder.cleanup)
        self.config = {'local_url': 'http://127.0.0.1:11434/v1', 'local_model': 'qwen3.5:9b'}
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session

    def test_busy_gpu_never_requests_generation(self):
        with patch.object(local_story, 'ROOT', self.root), patch.object(local_story.requests, 'Session', return_value=self.session), FileLock(str(self.root/'manifests/gpu.lock')):
            with self.assertRaisesRegex(RuntimeError, '显卡正在'):
                local_story.complete(self.config, {})
        self.session.post.assert_not_called()

    def test_comfy_queue_is_not_interrupted(self):
        with patch.object(local_story, 'ROOT', self.root), patch.object(local_story.requests, 'Session', return_value=self.session), patch.object(local_story.HTTP, 'get') as get, patch.object(local_story, 'unload') as unload:
            get.return_value.json.return_value = {'queue_running': [[1]], 'queue_pending': []}
            with self.assertRaisesRegex(RuntimeError, '正在生成'):
                local_story.complete(self.config, {})
            unload.assert_not_called()
        self.session.post.assert_not_called()

    def test_release_model_even_if_generation_fails(self):
        with patch.object(local_story, 'ROOT', self.root), patch.object(local_story.requests, 'Session', return_value=self.session), patch.object(local_story.HTTP, 'get') as get, patch.object(local_story, 'unload'):
            get.return_value.json.return_value = {'queue_running': [], 'queue_pending': []}
            self.session.post.side_effect = [local_story.requests.Timeout('test timeout'), MagicMock()]
            with self.assertRaises(local_story.requests.Timeout):
                local_story.complete(self.config, {})
        self.assertEqual(self.session.post.call_args.kwargs['json'], {'model': 'qwen3.5:9b', 'keep_alive': 0})


if __name__ == '__main__':
    unittest.main()
