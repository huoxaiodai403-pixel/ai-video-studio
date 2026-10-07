"""HTTP endpoints for local preset metadata and registered reference previews."""
from urllib.parse import parse_qs
import voice_library as library


def get(handler, route):
    if route.path == '/api/voice-library/qwen-status':
        from qwen_tts_batch import readiness
        try:
            handler.reply(readiness(parse_qs(route.query).get('engine', ['qwen3-custom'])[0]))
        except ValueError as error:
            handler.reply({'error': str(error)}, 400)
        return True
    if route.path == '/api/voice-library':
        try:
            handler.reply(library.catalog())
        except (ValueError, OSError) as error:
            handler.reply({'error': str(error)}, 400)
        return True
    if route.path == '/api/voice-library/audio':
        identity = parse_qs(route.query).get('ref', [''])[0]
        try:
            path = library.audio_path(identity)
        except FileNotFoundError as error:
            handler.reply({'error': str(error)}, 404)
        except ValueError as error:
            handler.reply({'error': str(error)}, 400)
        else:
            handler.send_file(path)
        return True
    return False


def post(handler, data, jobs=None):
    if not handler.path.startswith('/api/voice-library/'):
        return False
    if handler.path == '/api/voice-library/from-speech':
        handler.reply({'preset':library.from_speech(data),'message':'已保存为固定角色音色；后续复用这段参考，不会逐句重新设计。'})
    elif handler.path == '/api/voice-library/save':
        handler.reply({'preset': library.save(data), 'message': '音色预设已保存；已有视频任务的音色快照保持不变。'})
    elif handler.path == '/api/voice-library/default':
        if not isinstance(data, dict) or set(data) != {'id'}:
            raise ValueError('请选择要设为默认的音色预设')
        preset = library.set_default(data['id'])
        handler.reply({'preset': preset, 'voice': preset['voice'], 'message': '已设为新任务的默认音色。'})
    else:
        handler.reply({'error': '音色库接口不存在'}, 404)
    return True
