"""Service setup, explicit end-to-end checks and lightweight narration jobs."""
import json
import threading
import uuid
import html
from urllib.parse import parse_qs
from datetime import datetime, timezone

import lightweight_speech as speech
import providers
import volc_speech
import chatgpt_auth
from prompt_library import ROOT

SAMPLE = '你好，这是配音与字幕同步测试。先核对信息来源，再查看完整上下文。'


def get(handler, route):
    if route.path == '/auth/chatgpt/callback':
        try:
            chatgpt_auth.complete(parse_qs(route.query, keep_blank_values=True))
            message,code='账号授权成功。返回工作台选择模型，即可验证文稿生成。',200
        except (ValueError,RuntimeError,OSError):
            message,code='账号授权未完成。返回工作台查看状态或重新登录。',400
        body=('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
              '<title>ChatGPT 账号授权</title><body style="font:18px/1.8 sans-serif;padding:8vw;background:#101619;color:#eef4f1">'
              '<h1>AI 视频工作台</h1><p>'+html.escape(message)+'</p><a style="color:#b9e4d0" href="/settings?service=story">返回工作台</a></body></html>').encode('utf-8')
        handler.send_response(code)
        handler.send_header('Content-Type','text/html; charset=utf-8')
        handler.send_header('Content-Length',str(len(body)))
        handler.send_header('Cache-Control','no-store')
        handler.send_header('Referrer-Policy','no-referrer')
        handler.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
        handler.end_headers()
        if handler.command!='HEAD':handler.wfile.write(body)
    elif route.path == '/api/chatgpt/status':
        handler.reply(chatgpt_auth.status())
    elif route.path == '/api/local-models':
        from local_catalog import catalog
        handler.reply(catalog())
    elif route.path == '/api/speech/options':
        handler.reply(speech.options())
    elif route.path == '/api/volc-speech':
        handler.reply(volc_speech.load(public=True))
    else:
        return False
    return True


def queue(handler, jobs, kind, backend, operation):
    # Keep each submitted request on the settings that were reviewed at submission.
    provider_snapshot=providers.load()
    volc_snapshot=volc_speech.load()
    identity = ('speech-' if kind == 'speech' else 'service-test-') + uuid.uuid4().hex[:10]
    dest = ROOT/'projects/studio'/identity
    dest.mkdir(parents=True)
    state = {'kind': kind, 'backend': backend, 'status': 'queued', 'phase': '等待执行',
             'created_at': datetime.now(timezone.utc).isoformat()}
    jobs[identity] = state
    def persist():
        speech.write_json(dest/'status.json', state)
    persist()
    def run():
        token=providers.SNAPSHOT.set(provider_snapshot)
        volc_token=volc_speech.SNAPSHOT.set(volc_snapshot)
        try:
            state.update(status='running', phase='正在请求服务并检查实际输出')
            persist()
            result = operation(dest)
            state.update(result, status='done', phase='验证完成，请检查输出效果')
            for key in ('audio', 'subtitle', 'alignment', 'image', 'video'):
                if key in state:
                    path = dest/state[key]
                    if not path.is_file() or not path.stat().st_size:
                        raise ValueError('服务没有生成有效文件：'+key)
                    state[key] = f'/outputs/{identity}/{path.name}'
        except Exception as exc:
            state.update(status='error', phase='未完成', error=str(exc))
        finally:
            persist()
            providers.SNAPSHOT.reset(token)
            volc_speech.SNAPSHOT.reset(volc_token)
    threading.Thread(target=run, daemon=True).start()
    handler.reply({'job_id': identity}, 202)


def post(handler, data, jobs):
    if handler.path.startswith('/api/chatgpt/'):
        if handler.headers.get('Content-Type','').split(';',1)[0].strip().lower()!='application/json':
            handler.reply({'error':'账号操作需要 application/json 请求'},415)
            return True
        action=handler.path.rsplit('/',1)[-1]
        if action=='login':handler.reply(chatgpt_auth.start(handler.server.server_port, data.get('new_account',False)))
        elif action=='cancel':handler.reply(chatgpt_auth.cancel())
        elif action=='logout':handler.reply(chatgpt_auth.logout())
        elif action=='models':handler.reply({'models':chatgpt_auth.models()})
        else:handler.reply({'error':'账号操作不存在'},404)
        return True
    if handler.path == '/api/volc-speech':
        handler.reply({'config': volc_speech.save(data), 'message': '火山配置已保存，尚未验证服务。凭证仅在本机加密保存。'})
        return True
    if handler.path == '/api/speech' and data.get('backend', 'online') != 'local':
        backend = data.get('backend', 'online')
        voice = data.get('settings', {}).get('voice', {})
        speed = data.get('speed', voice.get('speed', 1.0))
        identity = data.get('voice_id', voice.get('online_voice', '') if backend == 'online' else '')
        identity = speech.validate(backend, identity, speed)
        text = data.get('text', '')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
            raise ValueError('请输入 1–4000 字的配音文本。')
        subtitles = data.get('subtitles', backend != 'online')
        if not isinstance(subtitles, bool):
            raise ValueError('字幕开关必须为 true 或 false。')
        if backend == 'online' and subtitles:
            providers.configured('asr')
        def speak(dest):
            metadata = speech.synthesize(text, dest/'audio.wav', backend, identity, speed, subtitles)
            speech.write_json(dest/'request.json', {'text': text, 'voice_id': identity, 'speed': speed, 'backend': backend})
            return {'audio': 'audio.wav', 'voice_engine': backend, 'speech': metadata,
                    **({'subtitle': 'audio.srt', 'alignment': 'audio.alignment.json'} if subtitles else {})}
        queue(handler, jobs, 'speech', backend, speak)
        return True
    if handler.path != '/api/providers/test':
        return False
    kind = data.get('kind')
    if kind not in providers.KINDS:
        raise ValueError('请选择要验证的服务。')
    providers.configured(kind)
    def check(dest):
        if kind == 'image':
            providers.image('A simple blue ceramic cup on a light background, no text.', dest/'image.png')
            return {'image': 'image.png'}
        if kind == 'tts':
            providers.tts(SAMPLE, dest/'audio.wav')
            return {'audio': 'audio.wav', 'duration': speech.duration(dest/'audio.wav')}
        if kind == 'asr':
            speech.synthesize(SAMPLE, dest/'sample.wav', subtitles=False)
            segments = providers.asr(dest/'sample.wav', dest/'transcription.json')
            return {'audio': 'sample.wav', 'subtitle': 'transcription.srt', 'text': ''.join(s['text'] for s in segments)}
        if kind == 'video':
            providers.video('A blue ceramic cup on a wooden table, slow camera movement, no text.', dest/'video.mp4')
            import imageio_ffmpeg
            reader = imageio_ffmpeg.read_frames(str(dest/'video.mp4'))
            try:
                metadata = next(reader)
            finally:
                reader.close()
            if metadata.get('duration', 0) <= 0:
                raise ValueError('服务返回的视频无法读取。')
            return {'video': 'video.mp4'}
        text = providers.story([{'role': 'user', 'content': '用一句简短中文介绍核对信息来源的意义。'}],max_tokens=100)
        if not isinstance(text, str) or not text.strip():
            raise ValueError('模型没有返回文本，请检查模型是否支持对话接口。')
        return {'text': text}
    queue(handler, jobs, 'service-test', kind, check)
    return True
