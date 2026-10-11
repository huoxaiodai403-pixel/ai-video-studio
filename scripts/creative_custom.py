"""Source-backed custom production, independent of the fixed example worker."""
import copy
import hashlib
import json
import zipfile
from pathlib import Path

from prompt_library import ROOT

STYLES = {
    'huashu-art-motion': '用具体对象、因果关系和一个主要动作解释机制。根据本次内容重新设计场景，稳定色板，避免标题卡代替动画。',
    'vox-director': '纸张拼贴讲解。为本次内容生成完整拼贴静帧；纸张边缘、材质与明确前后景，主体动作和相机运动分别设计。',
    'hand-drawn-video-prompts': '米白纸上的手绘蜡笔画。每个论点使用不同、具体的可视比喻；保持笔触一致，中文文字由后期制作。',
    'stickman-video-director': '简洁火柴人动画。圆头细线身体，保持比例；每镜写清动作起点、接触、反馈和末态，以动作表达情绪。',
    'kid-papercraft': '温暖纸艺动画。折纸与剪纸材质，柔和阴影，角色比例一致；登场、个性祝福与温暖收尾，不能编造姓名年龄。',
    'classical-poem-silk-video': '国风绢本画卷，克制笔触与留白。先理解全诗，再逐句对应名物、空间层次和一个主动作。诗句在后期叠加。',
    'hbg-life-simulation': '人物人生漫画，统一角色外貌服装与画风；根据情绪、地点和动作改变景别，保持事件连续。静图剪辑不可声称角色动画。',
    'director': '根据当前故事确定视角、因果与结尾。保持角色身份和动作连续性，分别设计主体行动和相机运动；不要每镜重新开始动作。',
    'book-sales-video': '围绕用户给出的书籍内容制作书评。整组规划书页、场景与阅读细节的景别；引用必须来自输入，不虚构书封、原文或购买事实。',
}


def method(identity):
    import sync_creative_methods
    row = next((r for r in sync_creative_methods.catalog() if r['id'] == identity), None)
    if not row or identity not in STYLES:
        raise ValueError('请选择可用的视频方法；Simon 请使用白板编辑器')
    return row


def identify(plan):
    explicit = plan.get('method_id', '')
    if explicit:
        method(explicit)
        return explicit
    return next((key for key in STYLES if '['+key+']' in plan.get('brief', '')), '')


def guidance(plan):
    identity = identify(plan)
    return STYLES[identity] if identity else ''


def production(value):
    """Task-only engine/output choices; never mutate global defaults."""
    if not isinstance(value, dict) or set(value)-{'image_engine', 'format'}:
        raise ValueError('制作设置包含未知字段')
    if not value:return {}
    result = {'image_engine': value.get('image_engine', ''), 'format': value.get('format', 'landscape')}
    if result['image_engine'] not in ('', 'qwen-image-2512', 'flux2-klein-4b'):
        raise ValueError('请选择可用图像引擎')
    if result['format'] not in ('landscape', 'portrait', 'square'):
        raise ValueError('请选择横屏、竖屏或方形画幅')
    return result


def configure(plan, frozen):
    result = copy.deepcopy(frozen)
    if not plan.get('production'):
        return result
    options = production(plan['production'])
    sizes = {'landscape': (1280,720), 'portrait': (720,1280), 'square': (960,960)}
    width,height = sizes[options['format']]
    result['settings']['output'].update(width=width,height=height)
    result['settings']['image'].update(width=width//2*2,height=height//2*2)
    if options['image_engine']:
        import model_profiles
        profile = model_profiles.profile('image',options['image_engine'])
        result['settings']['image'].update(engine=options['image_engine'], steps=profile['defaults']['steps'], cfg=profile['defaults']['cfg'])
    if height>width:
        motion=result['settings']['motion']
        motion['width'],motion['height']=min(motion['width'],motion['height']),max(motion['width'],motion['height'])
    return result


def defaults():
    import creation_settings, model_profiles, voice_library
    settings=creation_settings.load()
    voice=settings['voice']
    ready=False
    if voice['engine'].startswith('qwen3-'):
        from qwen_tts_batch import readiness
        ready=readiness(voice['engine'])['ready']
    elif voice['engine']=='index-tts':
        ready=(Path(settings['models']['tts_dir'])/'config.yaml').is_file()
    engines=model_profiles.catalog('image',settings['models'])
    return {'speech_backend':'local' if ready else 'windows',
            'voice_id':voice_library.catalog()['default_preset_id'] or '',
            'image_backend':'local' if any(e['ready'] for e in engines) else 'online',
            'image_engine':settings['image']['engine'],'image_engines':[
                {'id':e['id'],'name':e['name'],'ready':e['ready']} for e in engines]}


def finish(plan, dest, result, frozen=None):
    """One auditable artifact contract for automatic and Codex-assisted work."""
    identity = identify(plan)
    if not identity:
        return result
    source=(frozen or {}).get('method_source') or {'source':method(identity)['source']}
    receipt = {'method_id':identity,'mode':'custom','source':source['source'],
               'plan_id':plan['id'],'plan_revision':plan['revision'],
               'narration':'user plan and selected voice','visuals':'new content from submitted storyboard',
               'quality_review':'pending','listening_review':'pending'}
    receipt['video_sha256']=hashlib.sha256((dest/result['video']).read_bytes()).hexdigest()
    (dest/'method-source.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    allowed={'.mp4','.png','.jpg','.webp','.wav','.srt','.json','.html','.blend'}
    files=[p for p in dest.rglob('*') if p.is_file() and p.suffix in allowed and p.name not in
           {'render-request.json','status.json','failure.json','request-snapshot.json'} and not p.is_symlink()]
    with zipfile.ZipFile(dest/'delivery.zip','w',zipfile.ZIP_DEFLATED) as package:
        for path in files:
            package.write(path,path.relative_to(dest).as_posix())
    return {**result,'bundle':'delivery.zip'}
