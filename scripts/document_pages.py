"""Read-only, escaped Markdown reader for the workbench and its AI notes."""
import html
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_VAULT = os.environ.get('AI_VIDEO_VAULT', '').strip()
VAULT = Path(EXTERNAL_VAULT).expanduser().resolve() if EXTERNAL_VAULT else ROOT
NOTES = VAULT/'30_AI' if EXTERNAL_VAULT else ROOT/'docs'
TOOLS = NOTES/'40_Tools'
RECORD = TOOLS/'AI视频工作台部署与维护记录.md'
DOCS = {
    '/plan': ('部署方案', TOOLS/'本地AI视频生产部署方案.md', '方案、选型与实施过程；当前安装状态请结合部署实录阅读。'),
    '/research': ('文章与项目参考', NOTES/'10_Sources/20260927_AI视频文章与开源项目调研.md', '保留文章来源、仓库用途与复刻记录，点击原文可继续阅读本地归档。'),
    '/guide': ('使用说明', TOOLS/'工作台与ComfyUI上手教程.md', '从小说分镜、角色配音到 ComfyUI 和成片增强，按步骤上手。'),
    '/deployment': ('部署实录与维护', RECORD, '后续对话优先读取本页：安装清单、配置位置、验证证据与未完成项。'),
}
if not EXTERNAL_VAULT:
    TOOLS = NOTES
    DOCS = {
        '/plan': ('本地模型准备', NOTES/'local-models.md', '按硬件和任务准备可选模型，不自动下载权重。'),
        '/research': ('上游与参考', NOTES/'references.md', '项目依赖、参考实现与开源许可证。'),
        '/guide': ('使用说明', NOTES/'getting-started.md', '安装工作台，再让 Codex 按制作目标组织素材与工作流。'),
        '/deployment': ('工作台结构', NOTES/'architecture.md', '源码、运行时与个人资源分开管理。'),
    }

def allowed(path):
    return path.resolve().is_relative_to(NOTES.resolve())

def resolve_note(name, source):
    name = name.replace('\\|', '|').split('|')[0]
    stem, _, fragment = name.partition('#')
    for p in (VAULT/stem, source.parent/stem, TOOLS/stem):
        if not p.suffix: p = p.with_suffix('.md')
        if allowed(p) and p.is_file(): return p, fragment
    return None, fragment

def note_url(path):
    for route, (_, p, _) in DOCS.items():
        if path.resolve() == p.resolve(): return route
    return '/docs/view?path='+quote(path.relative_to(VAULT).as_posix())

def render(source, title, description, active):
    text = source.read_text(encoding='utf-8-sig')
    if title==source.stem:
        heading=re.search(r'^# (.+)$',text,re.M)
        if heading:title=heading.group(1).strip()
    provenance=''
    front=re.match(r'\A---\s*\n(.*?)\n---\s*\n',text,re.S)
    if front:
        fields={k:v.strip().strip('"') for k,v in re.findall(r'^(author|url|date|updated):\s*(.+)$',front.group(1),re.M)}
        provenance='<p class="doc-meta">'+html.escape(' · '.join(fields[k] for k in ('author','updated','date') if fields.get(k)))+'</p>'
        if fields.get('url','').startswith(('https://','http://')):
            provenance+='<p><a href="'+html.escape(fields['url'],quote=True)+'">查看原始来源</a></p>'
    text = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.S)
    def wiki(m):
        raw=m.group(1).replace('\\|','|'); label=raw.split('|')[-1].split('/')[-1]
        p, _ = resolve_note(raw, source)
        return '['+label+']('+note_url(p)+')' if p else label+'（库内笔记）'
    text = re.sub(r'\[\[([^\]]+)\]\]', wiki, text)
    md = MarkdownIt('commonmark', {'html':False, 'breaks':False}).enable('table').enable('strikethrough')
    tokens=md.parse(text); toc=[]
    for i, t in enumerate(tokens):
        if t.type=='heading_open':
            label=tokens[i+1].content; ident='section-'+str(len(toc)+1)
            t.attrSet('id',ident);toc.append((t.tag,label,ident))
        for child in t.children or []:
            key='src' if child.type=='image' else 'href' if child.type=='link_open' else None
            if not key:continue
            href=child.attrGet(key) or ''; parsed=urlparse(href)
            if parsed.scheme or href.startswith(('/', '#')):continue
            p=(source.parent/unquote(parsed.path)).resolve()
            if allowed(p) and p.is_file():
                child.attrSet(key,note_url(p) if p.suffix=='.md' else '/docs/asset?path='+quote(p.relative_to(VAULT).as_posix()))
    body=md.renderer.render(tokens,md.options,{})
    # Provenance comes from metadata; retain the first heading for CSS suppression.
    body=re.sub(r'(<h1\b[^>]*>.*?</h1>)',lambda m:m.group(1)+provenance,body,count=1,flags=re.S)
    body=re.sub(r'<a href="(/docs/asset\?path=[^"<>]+\.(?:mp4|webm))">[^<]*</a>',r'<video controls preload="metadata" src="\1"></video><p><a href="\1">打开视频附件</a></p>',body)
    body=re.sub(r'<table>(.*?)</table>',r'<div class="table-scroll"><table>\1</table></div>',body,flags=re.S)
    toc_html=''.join('<a href="#'+ident+'" class="level-'+tag+'">'+html.escape(label)+'</a>' for tag,label,ident in toc if tag in ('h2','h3'))
    nav=''.join('<a href="'+url+'">'+label+'</a>' for url,label in [('/', '插画与提示词'),('/production','视频制作'),('/motion','动态镜头'),('/subtitles','语音转字幕'),('/speech','音色克隆与配音'),('http://127.0.0.1:8188','ComfyUI'),('/settings','在线接口设置'),('/plan','部署方案'),('/research','文章与项目参考'),('/guide','使用说明')])
    tabs=''.join('<a '+('aria-current="page" ' if url==active else '')+'href="'+url+'">'+label+'</a>' for url,(label,_,_) in DOCS.items())
    raw_url='/docs/raw?path='+quote(source.relative_to(VAULT).as_posix())
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · AI 工作台</title><link rel="stylesheet" href="/assets/workbench.css"><link rel="stylesheet" href="/assets/documents.css"><main><nav>{nav}</nav><p id="services" hidden>正在检查服务</p><header><div class="eyebrow">资料中心 / LOCAL KNOWLEDGE</div><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><div class="doc-tabs">{tabs}</div><div class="doc-meta">知识库实时读取 · {html.escape(source.name)} <a href="{raw_url}" download>下载 Markdown</a><button id="print-doc">打印 / 保存 PDF</button></div></header><div class="doc-layout"><aside class="doc-toc"><strong>本页目录</strong>{toc_html}</aside><article class="doc-body">{body}</article></div></main><script src="/assets/document.js"></script><script src="/assets/workbench.js"></script></html>'''

def handle(handler, route):
    if route.path in DOCS:
        title,source,description=DOCS[route.path]
        if not source.is_file():handler.reply({'error':'资料尚未安装，请查看仓库 docs 目录。'},404);return True
        payload=render(source,title,description,route.path).encode('utf-8');mime='text/html; charset=utf-8'
    elif route.path in ('/docs/view','/docs/raw','/docs/asset'):
        name=parse_qs(route.query).get('path',[''])[0]
        source=(VAULT/name).resolve()
        if not allowed(source) or not source.is_file():handler.reply({'error':'资料不存在'},404);return True
        if route.path in ('/docs/view','/docs/raw') and source.suffix!='.md':handler.reply({'error':'仅支持 Markdown'},400);return True
        if route.path=='/docs/view':
            payload=render(source,source.stem,'知识库原文 · 内容与来源保留，正文中的媒体从本地附件读取。','/research').encode('utf-8');mime='text/html; charset=utf-8'
        else:
            if source.suffix.lower() not in ('.md','.png','.jpg','.jpeg','.webp','.gif','.mp4','.webm','.mp3','.wav','.pdf'):
                handler.reply({'error':'不支持的资料类型'},400);return True
            payload=source.read_bytes();mime='text/plain; charset=utf-8' if source.suffix=='.md' else mimetypes.guess_type(source.name)[0] or 'application/octet-stream'
    else:return False
    handler.send_response(200);handler.send_header('Content-Type',mime)
    handler.send_header('Content-Length',str(len(payload)));handler.send_header('X-Content-Type-Options','nosniff')
    handler.end_headers();handler.wfile.write(payload);return True
