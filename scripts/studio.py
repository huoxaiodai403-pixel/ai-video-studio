import json
import mimetypes
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from filelock import FileLock
from prompt_library import cases, search, compile_prompt, ROOT
from comfy_client import generate, unload
from studio_extensions import handle_get, handle_post, PAGES, listening
import providers
import creation_settings
import document_pages
import web_shell
import studio_edition

JOBS = {}
for status_file in (ROOT/'projects/studio').glob('*/status.json'):
    try:
        saved=json.loads(status_file.read_text(encoding='utf-8'))
        if saved.get('status') in ('running','queued'):
            saved.update(status='error',error='服务重启，任务中断；素材已保留。')
        JOBS[status_file.parent.name]=saved
    except (ValueError,OSError):
        pass
GPU_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        # Never log OAuth codes or state from a loopback callback URL.
        self.log_message('"%s %s %s" %s %s', self.command, urlparse(self.path).path, self.request_version, str(code), str(size))

    def send_file(self, path):
        """Stream media and support seeking without loading a full film in RAM."""
        length = path.stat().st_size
        start, end, status = 0, length - 1, 200
        value = self.headers.get('Range')
        if value:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', value.strip())
            if match and any(match.groups()) and length:
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), end) if right else end
                else:
                    start = max(0, length - int(right))
                valid = 0 <= start <= end < length
            else:
                valid = False
            if not valid:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{length}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        generated_source = (path.resolve().is_relative_to((ROOT/'projects/studio').resolve())
                            and path.suffix.lower() in ('.html', '.js', '.py', '.blend'))
        self.send_header('Content-Type', 'application/octet-stream' if generated_source else 'text/plain; charset=utf-8' if path.suffix=='.md' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        if generated_source:
            self.send_header('Content-Disposition', 'attachment')
            self.send_header('Content-Security-Policy', "sandbox; default-src 'none'")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{length}')
        self.end_headers()
        if self.command == 'HEAD':
            return
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    block = stream.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Browsers close a range request when the user seeks again.

    def send_page(self, source, pathname):
        """Send a complete first-frame UI; media keeps its streaming/Range path."""
        body = web_shell.render_page(source, pathname).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    def do_HEAD(self):
        self.do_GET()

    def reply(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path)
        if studio_edition.reject(self, self.path, self.command):
            return
        query = parse_qs(route.query)
        if document_pages.handle(self, route):
            return
        if handle_get(self,route,JOBS.copy()):
            return
        if route.path == '/api/cases':
            library=query.get('library',['image'])[0]
            if library not in ('image','seedance'):
                return self.reply({'error':'invalid library'},400)
            return self.reply({'total':len(search('',100000,library)), 'cases':search(query.get('q',[''])[0],60,library)})
        if route.path == '/api/jobs':
            return self.reply(JOBS)
        if route.path == '/':
            if not studio_edition.is_friend() and set(query) & {'reference', 'engine'}:
                self.send_response(302)
                self.send_header('Location', '/image?' + route.query)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            path = ROOT / 'scripts/home.html'
        elif route.path in PAGES:
            path=PAGES[route.path]
        elif route.path.startswith('/outputs/'):
            base = (ROOT / 'projects/studio').resolve()
            path = (base / unquote(route.path.removeprefix('/outputs/'))).resolve()
            if not path.is_relative_to(base):
                return self.reply({'error': 'invalid path'}, 400)
        else:
            return self.reply({'error': 'not found'}, 404)
        if not path.is_file():
            return self.reply({'error': 'not found'}, 404)
        if path.suffix == '.html' and path.parent.resolve() == (ROOT/'scripts').resolve():
            self.send_page(path.read_text(encoding='utf-8'), route.path)
        else:
            self.send_file(path)

    def do_POST(self):
        if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.reply({'error': 'origin rejected'}, 403)
        if studio_edition.reject(self, self.path, 'POST'):
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size > (18*1024*1024 if self.path in ('/api/voices','/api/image-references') else 3*1024*1024 if self.path=='/api/generation/render' else 500000):
                return self.reply({'error': 'request too large'}, 413)
            data = json.loads(self.rfile.read(size))
            if studio_edition.reject(self, self.path, 'POST', data):
                return
            if handle_post(self,data,JOBS):
                return
            if self.path == '/api/compile':
                return self.reply(compile_prompt(**data))
            if self.path != '/api/generate':
                return self.reply({'error': 'not found'}, 404)
            if not data.get('prompt', '').strip():
                return self.reply({'error': '请填写提示词'}, 400)
            creation=creation_settings.validate(data.get('settings',{}),check_models=False,check_voice=False)
            data.update(creation['image']);data['models']=creation['models'];data['settings']=creation
            backend=data.get('backend','local')
            if backend not in ('local','online'):
                return self.reply({'error':'未知模型来源'},400)
            if backend=='online':
                configured,_=providers.configured('image')
                data['model']=configured['model']
            else:
                import model_profiles
                model_profiles.require('image',creation['image']['engine'],creation['models'])
            import image_references
            references=data.get('reference_ids',[])
            image_references.validate_ids(references)
            if references and (backend!='local' or creation['image']['engine']!='flux2-klein-4b'):
                raise ValueError('参考图编辑目前需要本地 FLUX.2 klein 4B，不会忽略参考图或上传到在线接口')
            if backend=='local' and listening(7860):
                return self.reply({'error':'请先停止配音界面以释放显存。'},409)
            job = uuid.uuid4().hex[:12]
            dest = ROOT / 'projects/studio' / job
            dest.mkdir(parents=True)
            data['reference_images']=image_references.freeze(references,dest)
            (dest / 'prompt.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            JOBS[job] = {'status': 'queued', 'created': time.time(),'backend':backend}
            def run():
                try:
                    if backend=='online':
                        JOBS[job]['status'] = 'running'
                        providers.image(data['prompt'],dest/'image.png',f"{data['width']}x{data['height']}")
                    else:
                        with GPU_LOCK, FileLock(str(ROOT/'manifests/gpu.lock'), timeout=3600):
                            JOBS[job]['status'] = 'running'
                            generate(data, dest / 'image.png')
                    JOBS[job].update(status='done', image=f'/outputs/{job}/image.png', image_path=str(dest/'image.png'),
                                     image_engine=creation['image']['engine'])
                except Exception as exc:
                    JOBS[job].update(status='error', error=str(exc))
                finally:
                    (dest / 'status.json').write_text(json.dumps(JOBS[job], ensure_ascii=False, indent=2), encoding='utf-8')
            threading.Thread(target=run, daemon=True).start()
            return self.reply({'job_id': job}, 202)
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            return self.reply({'error': str(exc)}, 400)


if __name__ == '__main__':
    print('AI Video Studio: http://127.0.0.1:8189', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8189), Handler).serve_forever()
