"""Render the local workbench shell before the browser's first paint.

Page scripts and body content are retained as source text. This is deliberately
not an HTML sanitizer or a renderer for generated/user-provided media.
"""
from dataclasses import dataclass
from html import escape, unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
import studio_edition


GROUPS = (
    ('home', '工作台', '/home', ()),
    ('library', '我的作品', '/library', ()),
    ('assets', '资源库', '/assets', (('/gallery', '图库'), ('/audio-library', '音频库'), ('/voices', '音色库'), ('/model-library', '模型库'))),
    ('workflows', '工作流', '/workflows', (('/generation', '生成工坊'), ('/whiteboard', '手绘白板'), ('/investigation', '热点调查长片'), ('/novel', '小说转漫剧'), ('/production', '通用视频制作'))),
    ('tools', '创作工具', '/home#tools', (('/image', '图像创作'), ('/motion', '短镜头'), ('/speech', '配音与声音设计'), ('/music', '音乐与音效生成'), ('/subtitles', '语音转字幕'), ('/enhance', '视频增强与补帧'))),
    ('settings', '设置', '/settings', (('/settings', '在线服务'), ('/models', '本地模型'), ('http://127.0.0.1:8188', 'ComfyUI'), ('/learn', '上手教程'), ('/guide', '使用说明'), ('/director', '运镜词典与方法'), ('/plan', '部署方案'), ('/research', '文章与项目参考'))),
)
_LOCAL_PATHS = {'/', '/runtime-settings', '/docs/view', '/deployment'} | {
    urlsplit(href).path for _, _, href, children in GROUPS
    for href in (href, *(href for href, _ in children)) if href.startswith('/')
}
_ICONS = {
    'home': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="4" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
    'library': '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M9 4 6 9m9-5-3 5m8-5-3 5"/><path d="m10 12 5 3-5 3z"/>',
    'assets': '<path d="M3 7V5a2 2 0 0 1 2-2h4l3 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 8h18m-14 9 3-3 3 3 3-4 2 4"/>',
    'workflows': '<rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="15" width="6" height="6" rx="1.5"/><path d="M9 6h6M6 9v7a2 2 0 0 0 2 2h7m3-9v6"/>',
    'tools': '<path d="m14 6 4-3a2.1 2.1 0 0 1 3 3l-8 10-5-5 6-5Z"/><path d="m14 6 4 4M8 11l5 5-2 3a4 4 0 0 1-3 2H3c2-1 1-4 3-6l2-4Z"/>',
    'settings': '<path d="m10 3-.6 2a7 7 0 0 0-1.6.9l-2-.5-2 3.4 1.4 1.6a7 7 0 0 0 0 1.9l-1.4 1.6 2 3.5 2-.5a7 7 0 0 0 1.6.9l.6 2.2h4l.6-2.2a7 7 0 0 0 1.6-.9l2 .5 2-3.5-1.4-1.6a7 7 0 0 0 0-1.9l1.4-1.6-2-3.4-2 .5a7 7 0 0 0-1.6-.9L14 3h-4Z"/><circle cx="12" cy="11.7" r="3"/>',
}

# Geometry is available even before the external stylesheet has arrived. Full
# visual rules and transitions belong to workbench.css, not this critical block.
_CRITICAL = '''<meta charset="utf-8"><meta name="color-scheme" content="dark">
<style id="workbench-critical">html{background:#10151d;color-scheme:dark;scrollbar-gutter:stable}body{margin:0;background:#10151d;color:#edf3fa}main{margin-left:224px;margin-right:0;box-sizing:border-box;min-width:0}.sidebar,.sidebar *{box-sizing:border-box}.sidebar{position:fixed;inset:0 auto 0 0;width:224px;background:#151c26;border-right:1px solid #2d394b;z-index:30;display:flex;flex-direction:column;font:13px/1.6 system-ui,"Microsoft YaHei",sans-serif}.sidebar a{text-decoration:none;color:#aab3c1}.sidebar .brand{min-height:80px;display:flex;align-items:center;gap:11px;padding:17px 21px}.brand-mark{width:36px;height:36px;flex-shrink:0}.brand strong,.brand small{display:block}.sidebar .nav-create{display:flex;align-items:center;justify-content:center;min-height:42px;margin:0 16px 18px}.sidebar nav{padding:0 12px 18px;min-height:0;overflow-y:auto;flex:1}.sidebar nav a{display:flex;align-items:center;gap:11px;min-height:42px;padding:9px 12px;margin:3px 0}.sidebar .nav-primary-list{display:grid;gap:4px}.sidebar nav .nav-primary{min-height:42px;margin:0}.nav-icon{width:19px;height:19px;flex:0 0 19px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}.nav-context[hidden]{display:none!important}.sidebar-footer{padding:16px 22px 20px;flex-shrink:0}.sidebar-footer small{display:block}.nav-toggle,.nav-shade{display:none}.workbench-skip{position:fixed;left:16px;top:-100px;z-index:100}.workbench-skip:focus{top:12px}@media(max-width:700px){main{margin-left:0;padding-top:78px}.sidebar{top:54px;width:min(280px,85vw);transform:translateX(-100%);visibility:hidden}.nav-toggle{display:block;position:fixed;inset:0 0 auto;min-height:54px;width:100%;margin:0;z-index:40;background:#151c26;color:#edf3fa;border:0}.nav-shade{position:fixed;inset:54px 0 0;z-index:25}body.nav-open .sidebar{transform:none;visibility:visible}body.nav-open .nav-shade{display:block}}</style>'''


@dataclass
class _Tag:
    name: str
    attrs: dict
    start: int
    end: int
    close_start: int | None = None
    close_end: int | None = None
    parents: tuple = ()


class _Source(HTMLParser):
    """Keep offsets so page JS, attributes and text need no serialization."""
    # HTMLParser otherwise treats markup inside RCDATA fields as real elements.
    CDATA_CONTENT_ELEMENTS = ('script', 'style', 'textarea', 'title')
    _VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.tags, self.stack = source, [], []
        self.lines = [0] + [match.end() for match in re.finditer('\n', source)]
        self.feed(source)
        self.close()

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.source_offset()
        item = _Tag(tag, dict(attrs), start, start + len(self.get_starttag_text()), parents=tuple(self.stack))
        self.tags.append(item)
        if tag not in self._VOID:
            self.stack.append(item)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].start == self.source_offset():
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].name == tag:
                item = self.stack[index]
                item.close_start = self.source_offset()
                item.close_end = self.source.find('>', item.close_start) + 1
                del self.stack[index:]
                break


def _attrs(values):
    return ''.join(' ' + key + ('' if value is None else '="' + escape(str(value), quote=True) + '"') for key, value in values.items())


def _local_asset(value, path):
    parsed = urlsplit(value or '')
    return not parsed.scheme and not parsed.netloc and parsed.path == path


def _selected(path):
    if path in ('/', '/home'):
        return 'home'
    for group, _, href, children in GROUPS:
        if href == path or any(child == path for child, _ in children):
            return group
    return 'settings'


def _shell(path, main_id, title, old_links):
    selected = _selected(path)
    canonical = '/home' if path == '/' else path
    groups = tuple((key, label, href, tuple((child, text) for child, text in children
                   if not studio_edition.is_friend() or child.startswith('/') and studio_edition.allowed(urlsplit(child).path)))
                   for key, label, href, children in GROUPS)

    def link(href, label, group, primary=False):
        attributes = dict(old_links.get(href, {}))
        repeated_as_child = primary and any(child == href for item, _, _, children in groups if item == group for child, _ in children)
        attributes.update(href=href, **{'class': 'nav-primary' + (' is-active' if selected == group else '') if primary else 'nav-child', 'data-nav-group': group})
        attributes.pop('aria-current', None)
        if repeated_as_child:
            attributes.pop('id', None)
        if href == canonical and not repeated_as_child:
            attributes['aria-current'] = 'page'
        icon = ('<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + _ICONS[group] + '</svg>') if primary else ''
        external = ''
        if href.startswith('http'):
            attributes.update(target='_blank', rel='noopener noreferrer')
            external = '<span class="external" aria-hidden="true">↗</span>'
        return '<a' + _attrs(attributes) + '>' + icon + '<span>' + escape(label) + '</span>' + external + '</a>'

    primary = ''.join(link(href, label, group, True) for group, label, href, _ in groups)
    contexts = ''.join('<section class="nav-context" data-nav-group="' + group + '" aria-label="' + label + '分类"' + ('' if selected == group else ' hidden') + '>' + ('<div class="nav-context-title">' + label + '</div>' if children else '') + ''.join(link(href, text, group) for href, text in children) + '</section>' for group, label, _, children in groups)
    return ('<a class="workbench-skip" href="#' + escape(main_id, quote=True) + '">跳到主要内容</a>'
            '<button type="button" class="nav-toggle" id="workbench-toggle" aria-label="展开导航" aria-controls="workbench-nav" aria-expanded="false">☰  AI STUDIO · ' + escape(title) + '</button>'
            '<aside class="sidebar" id="workbench-nav" data-shell="server"><a class="brand" href="/home"><img class="brand-mark" src="/assets/brand/studio-mark.svg" width="36" height="36" alt=""><span><strong>AI STUDIO</strong><small>' + ('朋友版' if studio_edition.is_friend() else '完整开发版') + '</small></span></a>'
            '<a class="nav-create" href="/generation">＋ 开始创作</a><nav aria-label="工作台导航"><div class="nav-primary-list">' + primary + '</div><div class="nav-contexts">' + contexts + '</div></nav>'
            '<div class="sidebar-footer"><span class="status-dot"></span><span class="health">正在检查服务</span><small>本地优先 · 支持在线接口</small></div></aside>'
            '<button type="button" class="nav-shade" id="workbench-shade" tabindex="-1" aria-label="关闭导航"></button>')


def render_page(source: str, pathname: str) -> str:
    """Add one first-paint shell to a known local UI page, without page execution."""
    route = urlsplit(pathname)
    path = route.path
    if route.scheme or route.netloc or path not in _LOCAL_PATHS:
        return source
    parsed = _Source(source)
    if any(tag.name == 'aside' and tag.attrs.get('id') == 'workbench-nav' and tag.attrs.get('data-shell') == 'server' for tag in parsed.tags):
        return source
    main = next((tag for tag in parsed.tags if tag.name == 'main'), None)
    if main is None or not any(_local_asset(tag.attrs.get('src'), '/assets/workbench.js') or _local_asset(tag.attrs.get('href'), '/assets/workbench.css') for tag in parsed.tags):
        return source
    first = lambda name: next((tag for tag in parsed.tags if tag.name == name), None)
    html, head, body = first('html'), first('head'), first('body')
    body_start = body.end if body else main.start
    head_start = head.end if head else html.end if html else 0
    head_end = head.close_start if head and head.close_start is not None else body.start if body else main.start
    document_end = html.close_start if html and html.close_start is not None else len(source)
    edits, old_links = [], {}
    shared_css = None
    for tag in parsed.tags:
        if studio_edition.is_friend() and tag.name == 'a' and tag.attrs.get('href', '').startswith('/') and not studio_edition.allowed(urlsplit(tag.attrs['href']).path):
            attributes = {**tag.attrs, 'hidden': None, 'aria-hidden': 'true', 'tabindex': '-1'}
            edits.append((tag.start, tag.end, '<a' + _attrs(attributes) + '>'))
        if tag.name == 'nav' and tag.attrs.get('aria-label') == '工作台导航' and any(parent is main for parent in tag.parents):
            if tag.close_end is not None:
                edits.append((tag.start, tag.close_end, ''))
                for child in parsed.tags:
                    if child.name == 'a' and any(parent is tag for parent in child.parents) and child.attrs.get('href'):
                        old_links.setdefault(child.attrs['href'], child.attrs)
        if tag.name == 'link' and 'stylesheet' in (tag.attrs.get('rel') or '').lower().split() and _local_asset(tag.attrs.get('href'), '/assets/workbench.css'):
            shared_css = source[tag.start:tag.end]
            edits.append((tag.start, tag.end, ''))
        if tag.name == 'meta' and ('charset' in tag.attrs or (tag.attrs.get('name') or '').lower() == 'color-scheme'):
            edits.append((tag.start, tag.end, ''))
        if tag.name in ('head', 'body') and tag.close_start is not None:
            edits.append((tag.close_start, tag.close_end, ''))
    main_id = main.attrs.get('id') or 'workbench-main'
    if not main.attrs.get('id'):
        used_ids = {tag.attrs.get('id') for tag in parsed.tags}
        suffix = 1
        while main_id in used_ids:
            main_id = 'workbench-main-' + str(suffix)
            suffix += 1
    additions = {}
    if not main.attrs.get('id'):
        additions['id'] = main_id
    if 'tabindex' not in main.attrs:
        additions['tabindex'] = '-1'
    if additions:
        attributes = dict(main.attrs)
        attributes.update(additions)
        edits.append((main.start, main.end, '<main' + _attrs(attributes) + '>'))

    def part(start, end):
        result, cursor = [], start
        for left, right, replacement in sorted(edits):
            if left < cursor or right > end:
                continue
            result.extend((source[cursor:left], replacement))
            cursor = right
        result.append(source[cursor:end])
        return ''.join(result)

    heading = first('h1')
    title = unescape(re.sub('<[^>]+>', '', source[heading.end:heading.close_start])).strip() if heading and heading.close_start is not None else '工作台'
    if path in ('/', '/home'):
        title = '工作台'
    head_content = part(head_start, head_end)
    # A doctype preceding an implicit <html> must not end up inside <head>.
    head_content = re.sub(r'<!doctype\b[^>]*>', '', head_content, flags=re.I)
    html_open = '<html' + _attrs({**(html.attrs if html else {'lang': 'zh-CN'}), 'data-studio-edition': studio_edition.edition()}) + '>'
    head_open = source[head.start:head.end] if head else '<head>'
    body_open = source[body.start:body.end] if body else '<body>'
    stylesheet = shared_css or '<link rel="stylesheet" href="/assets/workbench.css">'
    return '<!doctype html>' + html_open + head_open + _CRITICAL + head_content + stylesheet + '</head>' + body_open + _shell(path, main_id, title, old_links) + part(body_start, document_end) + '</body></html>'
