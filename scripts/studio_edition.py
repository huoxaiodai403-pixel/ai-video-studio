"""Compatibility entry points for the single workbench.

The legacy marker remains readable for existing installations and browser draft
keys. Capabilities depend on selected backends and installed dependencies, never
on a friend/development product gate.
"""
from prompt_library import ROOT


def edition():
    try:
        value = (ROOT / 'EDITION').read_text(encoding='utf-8-sig').strip()
    except FileNotFoundError:
        value = 'development'
    if value not in {'development', 'friend'}:
        raise ValueError('无法识别旧版工作台标记，请保留原配置并重新安装工作台源码')
    # Keep the established draft namespace; old friend drafts are migrated by
    # the shared shell without replacing an existing development draft.
    return 'development'


def is_friend():
    return False


def generation_allowed(route):
    return True


def require_local():
    # Each worker/API validates its own model files and isolated environment.
    return None


def allowed(path, method='GET'):
    return True


def reject(handler, path=None, method='GET', data=None):
    return False
