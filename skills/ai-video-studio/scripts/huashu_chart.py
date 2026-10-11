"""Compile reviewed Huashu chart code into the studio's offline HTML contract.

No upstream server, eval, XHR, model, author artwork or external font is executed.
The original MIT license travels with the compiled editable source.
"""
from __future__ import annotations

import copy
import json
import math

from creative_video import recipe, source_path, verify_sources

LIBRARIES = ('util', 'paint', 'palettes', 'motion', 'typo', 'chart')


def number(value, label, low, high, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high
            or (integer and int(value) != value)):
        raise ValueError(f'{label} 应在 {low}–{high} 之间' + ('且为整数' if integer else ''))
    return value


def text(value, label, maximum=160, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f'{label} 应为不超过 {maximum} 字的文本')
    return value


def validate_spec(value):
    allowed = {'grammar', 'width', 'height', 'fps', 'duration', 'theme', 'safe', 'data', 'cues', 'audio_path'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('图表 spec 含不支持的字段')
    spec = copy.deepcopy(value)
    if spec.get('grammar', 't3_finance_chart') != 't3_finance_chart':
        raise ValueError('当前适配器仅支持 t3_finance_chart')
    spec['grammar'] = 't3_finance_chart'
    for key, default, low, high in [('width', 1280, 256, 1920), ('height', 720, 256, 1920), ('fps', 25, 1, 30)]:
        spec[key] = int(number(spec.get(key, default), key, low, high, True))
    spec['duration'] = number(spec.get('duration', 6), 'duration', 1, 8)
    w, h = spec['width'], spec['height']
    if w % 2 or h % 2 or w * h > 1920 * 1080:
        raise ValueError('宽高应为偶数且不超过 1920×1080 总像素')
    if spec.get('theme') not in (None, 'light', 'dark', 'paper', 'poster', 'ink', 'navy', 'bauhaus', 'snow', 'wood', 'chalk'):
        raise ValueError('请使用上游命名色板')
    safe = spec.get('safe', {})
    if not isinstance(safe, dict) or set(safe) - {'top', 'bottom'}:
        raise ValueError('图表安全区当前支持 top、bottom 像素值')
    for key, value in safe.items():
        number(value, 'safe.' + key, 0, h * 0.15)
    data = spec.get('data')
    fields = {'title', 'unit', 'source', 'badge', 'chart', 'series', 'decimals', 'prefix', 'suffix'}
    if not isinstance(data, dict) or set(data) - fields:
        raise ValueError('data 需要标题、单位、来源、图表类型与数据序列')
    for key in ('title', 'unit', 'source'):
        text(data.get(key), key, 100, True)
    for key in ('badge', 'prefix', 'suffix'):
        if key in data:
            text(data[key], key, 32)
    data.setdefault('chart', 'bar')
    if data['chart'] not in ('bar', 'line'):
        raise ValueError('当前适配器支持 bar 与 line')
    if 'decimals' in data:
        number(data['decimals'], 'decimals', 0, 4, True)
    series = data.get('series')
    if not isinstance(series, list) or not 2 <= len(series) <= 16:
        raise ValueError('series 应包含 2–16 个数据点')
    for row in series:
        if not isinstance(row, dict) or set(row) != {'label', 'value'}:
            raise ValueError('每个数据点需要 label 与 value')
        text(row['label'], 'label', 24, True)
        number(row['value'], 'value', -1e9, 1e9)
    values = [row['value'] for row in series]
    extent = max(max(values), 0) - min(min(values), 0) if data['chart'] == 'bar' else max(values) - min(values)
    if extent < 0.001:
        raise ValueError('数据范围过小或全零；请改用清晰单位，等值折线可改为柱状图')
    cues = spec.setdefault('cues', [{'at': 0, 'kind': 'title'}, {'at': 0.7, 'kind': data['chart'], 'dur': 1}])
    if not isinstance(cues, list) or not 1 <= len(cues) <= 40:
        raise ValueError('cues 应为 1–40 个时间标记')
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) - {'at', 'kind', 'dur', 'text', 'sub', 'data'}:
            raise ValueError('cue 含不支持的字段')
        if cue.get('kind') not in ('title', data['chart'], 'highlight'):
            raise ValueError('cue.kind 应为 title、当前图表类型或 highlight')
        number(cue.get('at'), 'cue.at', 0, spec['duration'] - 1 / spec['fps'])
        if 'dur' in cue:
            number(cue['dur'], 'cue.dur', 0.05, spec['duration'])
            if cue['at'] + cue['dur'] > spec['duration']:
                raise ValueError('cue 动画尚未完成就结束了镜头，请延长 duration')
        for key in ('text', 'sub'):
            if key in cue:
                text(cue[key], 'cue.' + key, 80)
        if 'data' in cue:
            indices = cue['data']
            if not isinstance(indices, dict) or set(indices) != {'index'}:
                raise ValueError('cue.data 仅接受 index')
            number(indices['index'], 'cue.data.index', 0, len(series) - 1, True)
        if cue['kind'] == 'highlight' and not cue.get('text'):
            raise ValueError('highlight 需要明确的标注 text')
    if not any(cue['kind'] == data['chart'] for cue in cues):
        raise ValueError('缺少数据展示 cue')
    if sum(cue['kind'] == 'highlight' for cue in cues) > 1:
        raise ValueError('一镜保留一个重点标注')
    if 'audio_path' in spec:
        text(spec['audio_path'], 'audio_path', 2000, True)
    return spec


def compile_chart(root, value):
    spec = validate_spec(value)
    item = recipe('huashu-art-motion')
    check = verify_sources(root, item)
    if check['status'] != 'verified':
        raise ValueError('花叔资料未安装或有变动，请运行 install_creative_skills.py --skill huashu-art-motion')
    base = check['directory']
    files = [f'scripts/engine/lib/{name}.js' for name in LIBRARIES] + ['scripts/engine/clips/t3_finance_chart.js']
    scripts = '\n'.join(source_path(base, path).read_text(encoding='utf-8') for path in files)
    # The Windows studio uses available system fonts; no network font fetches.
    for name in ('PuHui-Medium', 'PuHui-Bold', 'PuHui-Heavy', 'PuHui-Black', 'RobotoCondensed'):
        scripts = scripts.replace(name, 'Microsoft YaHei')
    audio = spec.pop('audio_path', None)
    literal = json.dumps(spec, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    boot = r'''
const spec = __SPEC__;
const cv = document.getElementById('c'), c = cv.getContext('2d');
const W = spec.width, H = spec.height, FPS = spec.fps;
cv.width = W; cv.height = H; U.setStage(W, H);
const G = CLIPS.t3_finance_chart;
const safe = {top:0,bottom:0,left:0,right:0,...spec.safe};
const cues = spec.cues.map((q,i)=>({...q,i})).sort((a,b)=>a.at-b.at||a.i-b.i);
const ctx = {spec, data:spec.data, theme:spec.theme||{},
  pal:G.legacyTheme(spec.theme)?null:PAL.resolve(spec.theme),
  W,H,FPS,u:Math.min(W,H)/1080,portrait:H>W,alpha:false,dur:spec.duration,safe,
  box:{x:0,y:safe.top,w:W,h:H-safe.top-safe.bottom},cues,
  of:(...kinds)=>cues.filter(q=>kinds.includes(q.kind)),
  lt:(t,at)=>t-at+1/FPS, p:(t,at,d)=>U.clamp((t-at+1/FPS)/d)};
let ready;
window.renderFrame = async t => {
  if (!ready) ready = document.fonts.ready.then(()=>G.init(ctx));
  await ready;
  c.setTransform(1,0,0,1,0,0); c.clearRect(0,0,W,H); c.save();
  G.draw(c,t,ctx); c.restore();
};
'''.replace('__SPEC__', literal)
    license_text = source_path(base, 'LICENSE').read_text(encoding='utf-8')
    html = ('<!doctype html><meta charset="utf-8">\n<!-- Huashu source: ' + item['ref']
            + '\n' + license_text + '\nWindows studio adapter: offline renderFrame; system font substitution. -->'
            + '<style>body{margin:0}canvas{display:block}</style><canvas id="c"></canvas>'
            + '<script>window.CLIPS={};\n' + (scripts + boot).replace('</script', '<\\/script') + '</script>')
    payload = {key: spec[key] for key in ('width', 'height', 'fps', 'duration')}
    payload['html'] = html
    if audio:
        payload['audio_path'] = audio
    return payload
