"""Edition boundaries for the shipped HTTP surface, independent of navigation.

The full working tree defaults to development. Public packages carry EDITION
containing ``friend`` and omit their unsupported implementation files as well.
"""
from urllib.parse import urlsplit

from prompt_library import ROOT

FRIEND_GENERATION_ROUTES = frozenset({'code-animation', 'whiteboard'})
FRIEND_PAGES = frozenset({
    '/', '/home', '/workflows', '/generation', '/whiteboard', '/speech', '/voices',
    '/library', '/gallery', '/audio-library', '/assets', '/settings', '/learn',
    '/guide', '/plan', '/research', '/deployment', '/docs/view', '/docs/raw', '/docs/asset',
    '/auth/chatgpt/callback', '/favicon.ico', '/tutorial-note', '/brief',
})
FRIEND_ASSETS = frozenset('/assets/' + name for name in (
    'home.js', 'workflows.js', 'hub.css', 'library.css', 'library.js',
    'generation.js', 'generation.css', 'image_references.js', 'voices.js',
    'speech_voices.js', 'speech-picker.js', 'whiteboard.js', 'documents.css',
    'document.js', 'creation.js', 'controls.css', 'workbench.css', 'workbench.js',
    'online-services.css', 'online-services.js', 'chatgpt-account.js',
    'brand/studio-mark.svg', 'brand/studio-mark.png', 'brand/studio-mark.ico',
))
FRIEND_GET_APIS = frozenset({
    '/api/runtime', '/api/services', '/api/jobs', '/api/creation', '/api/providers',
    '/api/story/status', '/api/speech/options', '/api/volc-speech', '/api/chatgpt/status',
    '/api/voice-preview', '/api/voice-library', '/api/voice-library/audio',
    '/api/voice-library/qwen-status', '/api/image-references', '/api/image-references/preview',
    '/api/library', '/api/library/item', '/api/library/file', '/api/jianying/status',
    '/api/whiteboard/status', '/api/whiteboard/example', '/api/generation/catalog',
    '/api/generation/plan', '/api/generation/handoff', '/api/generation/example',
})
FRIEND_POST_APIS = frozenset({
    '/api/creation', '/api/providers', '/api/providers/test', '/api/volc-speech',
    '/api/chatgpt/login', '/api/chatgpt/cancel', '/api/chatgpt/logout', '/api/chatgpt/models',
    '/api/speech', '/api/voices', '/api/voice-library/from-speech',
    '/api/voice-library/save', '/api/voice-library/default', '/api/image-references',
    '/api/library/metadata', '/api/jianying/export', '/api/jianying/open',
    '/api/whiteboard/draft', '/api/whiteboard/preview', '/api/whiteboard/render',
    '/api/generation/plan', '/api/generation/draft', '/api/generation/compose',
    '/api/generation/render', '/api/generation/retry',
})


def edition():
    try:
        value = (ROOT / 'EDITION').read_text(encoding='utf-8-sig').strip()
    except FileNotFoundError:
        return 'development'
    if value not in {'development', 'friend'}:
        raise ValueError('EDITION 必须为 development 或 friend')
    return value


def is_friend():
    return edition() == 'friend'


def generation_allowed(route):
    return not is_friend() or route in FRIEND_GENERATION_ROUTES


def allowed(path, method='GET'):
    """Check exact public endpoints before dispatch or file access."""
    if not is_friend():
        return True
    route = urlsplit(path)
    if route.scheme or route.netloc or '\\' in route.path:
        return False
    path = route.path
    if method in {'GET', 'HEAD'}:
        return (path in FRIEND_PAGES or path in FRIEND_ASSETS or path in FRIEND_GET_APIS
                or path.startswith('/outputs/'))
    return method == 'POST' and path in FRIEND_POST_APIS


def reject(handler, path=None, method='GET', data=None):
    """Return True only after an unavailable request has received an error."""
    if not is_friend():
        return False
    request_path = path if path is not None else handler.path
    if not allowed(request_path, method):
        handler.reply({'error': '朋友版未包含此功能，请使用配音、代码动画、白板或作品库。',
                       'edition': 'friend'}, 404)
        return True
    path = urlsplit(request_path).path
    reason = None
    if method == 'POST' and isinstance(data, dict):
        if path == '/api/providers/test' and data.get('kind') not in {'story', 'tts', 'asr'}:
            reason = '朋友版仅支持编剧、配音和配套字幕服务测试。'
        elif path == '/api/creation':
            # Existing voice controls send a complete settings snapshot. Accept
            # unchanged shared fields, but do not expose model management here.
            import creation_settings
            current = creation_settings.load()
            if any(key in data and data[key] != current[key]
                   for key in ('models', 'image', 'motion', 'story')):
                reason = '朋友版可保存声线与输出设置，不提供高级本地模型管理。'
    if reason:
        handler.reply({'error': reason, 'edition': 'friend'}, 403)
        return True
    return False
