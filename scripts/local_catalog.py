"""Read-only local component inventory; file presence is not inference success."""
from pathlib import Path

import creation_settings
import lightweight_speech
import model_profiles
from prompt_library import ROOT


def catalog():
    config = creation_settings.load()
    voices = lightweight_speech.options()['windows']
    result = [{'group': '配音与字幕', 'name': 'Windows 系统语音', 'id': 'windows',
               'ready': voices['available'], 'cpu': True, 'system': True, 'bytes': 0,
               'description': '使用系统已有音色，配音与字幕一起生成。无需额外模型，基础音质适合快速制作。',
               'details': [v['label'] for v in voices['voices']], 'action': '/speech?backend=windows'}]
    for kind, group, action in [('image', '图像生成', '/image'), ('motion', '视频生成', '/motion')]:
        for engine in model_profiles.catalog(kind, config['models']):
            result.append({'group': group, 'id': engine['id'], 'name': engine['name'], 'ready': engine['ready'],
                           'cpu': False, 'bytes': sum(c['bytes'] for c in engine['components']),
                           'description': '本机推理，使用独立模型环境。文件齐全后还需要验证实际生成效果。',
                           'details': [('已找到 · ' if c['exists'] else '缺少 · ')+c['name'] for c in engine['components']],
                           'action': action})
    from qwen_tts_batch import MODELS, readiness
    for engine, name in MODELS.items():
        state = readiness(engine)
        result.append({'group': '配音与字幕', 'id': engine, 'name': name, 'ready': state['ready'], 'cpu': False,
                       'description': '角色声线、声音设计或参考克隆。需要独立安装模型与运行依赖。',
                       'details': [c['name']+' · '+c['message'] for c in state['checks']], 'action': '/speech?engine='+engine})
    for name, key, app, group, action in [('IndexTTS', 'tts_dir', 'index-tts', '配音与字幕', '/speech?backend=local'),
            ('Qwen3-ASR', 'asr_dir', 'qwen-asr', '配音与字幕', '/subtitles'),
            ('Qwen3 ForcedAligner', 'align_dir', 'qwen-asr', '配音与字幕', '/subtitles')]:
        folder = Path(config['models'][key])
        weights = list(folder.glob('*.safetensors')) + list(folder.glob('*.pth'))
        python = ROOT/'apps'/app/'.venv/Scripts/python.exe'
        ready = bool(weights) and python.is_file()
        result.append({'group': group, 'id': key, 'name': name, 'ready': ready, 'cpu': False,
                       'description': '本地语音模型；录音识别与已有音轨对齐需要各自的模型。',
                       'bytes': sum(p.stat().st_size for p in weights),
                       'details': ['模型目录：'+str(folder), '独立环境：'+('已找到' if python.is_file() else '未安装')], 'action': action})
    import music_api
    for engine in music_api.ENGINES:
        state = music_api.readiness(engine)
        result.append({'group': '音乐与音效', 'id': engine, 'name': state['name'], 'ready': state['ready'],
                       'cpu': engine == 'stable-audio-3-sfx', 'description': '生成后作为音频素材复用到作品。',
                       'details': state['details'], 'action': '/music'})
    result.append({'group': '编剧与分镜', 'id': 'local-story', 'name': '本机编剧服务', 'ready': False,
                   'cpu': None, 'status': '已填写模型 · 待试运行' if config['story']['local_model'] else '尚未选择模型',
                   'description': '可连接本机兼容服务。也可以直接让 Codex 写稿并提交分镜，无需安装编剧模型。',
                   'details': ['模型：'+(config['story']['local_model'] or '未配置')], 'action': '/production'})
    return {'models': result, 'note': '只检查系统语音和文件，不下载、不加载模型。文件齐全不代表已验证生成效果。'}
