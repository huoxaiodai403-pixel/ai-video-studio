"""Local, resumable investigation film production from a frozen JSON storyboard.

The UI chooses sources, registered media and voices. This runner never executes
submitted code, fetches arbitrary media, loops short footage, or publishes.
"""
import argparse
from array import array
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import wave
import zipfile

from filelock import FileLock
from voice_cache import file_sha, fingerprint

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT/'tools/ffmpeg.exe'
FFPROBE = ROOT/'tools/ffprobe.exe'
NODE = ROOT/'tools/node/node.exe'
RENDERER = ROOT/'apps/investigation-renderer/render.mjs'
FPS = 30


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def run(command, log, cwd=None):
    with Path(log).open('w', encoding='utf-8') as stream:
        result = subprocess.run(list(map(str, command)), cwd=cwd or ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, env=os.environ.copy())
    if result.returncode:
        tail = Path(log).read_text(encoding='utf-8', errors='replace')[-2000:]
        raise RuntimeError(f'{Path(log).name} 执行失败：{tail}')


def probe(path):
    if not FFPROBE.is_file():
        code = ('import av,json,sys; c=av.open(sys.argv[1]); streams=[]; '
                '\nfor s in c.streams:\n'
                ' d={"codec_type":s.type,"codec_name":s.codec_context.name}; '
                '\n if s.type=="video":d.update(width=s.width,height=s.height,r_frame_rate=str(s.average_rate or 30))'
                '\n streams.append(d)'
                '\nprint(json.dumps({"format":{"duration":float(c.duration or 0)/av.time_base},"streams":streams})); c.close()')
        result = subprocess.run([str(ROOT/'tools/.venv/Scripts/python.exe'), '-c', code, str(path)],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    result = subprocess.run([str(FFPROBE), '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def contained(project, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('素材应为已登记的项目相对路径')
    path = (project/relative).resolve()
    if not path.is_relative_to(project.resolve()) or not path.is_file():
        raise ValueError('项目素材缺失或超出工程目录')
    return path


def subtitles(path):
    result = []
    def seconds(stamp):
        h, m, s = stamp.replace(',', '.').split(':')
        return int(h)*3600+int(m)*60+float(s)
    for block in re.split(r'\n\s*\n', Path(path).read_text(encoding='utf-8').strip()):
        lines = block.splitlines()
        if len(lines)<3 or ' --> ' not in lines[1]:
            continue
        start, end = map(seconds, lines[1].split(' --> '))
        first = max(0, round(start*FPS))
        last = max(first+1, round(end*FPS))
        if result and first < result[-1]['end']:
            first = result[-1]['end']
            last = max(first+1, last)
        result.append({'start': first, 'end': last, 'text': ''.join(lines[2:])})
    return result


def build_props(project, spec, preview=False):
    """Use measured speech duration; quantize cumulative time to avoid drift."""
    public = project/'render-public'
    (public/'assets').mkdir(parents=True, exist_ok=True)
    media = {row['id']: row for row in spec.get('media', [])}
    sources = {row['id']: row for row in spec.get('sources', [])}
    durations = {} if preview else {row['id']:row['duration'] for row in read(project/'timeline.json')}
    scenes, coverage, offset, total_frames = [], [], 0.0, 0
    for scene in spec['scenes']:
        duration = max(5.0, len(scene['narration'])/4.6) if preview else durations[scene['id']]
        end_frame = max(total_frames+1, round((offset+duration)*FPS))
        row = {'id':scene['id'], 'startFrame':total_frames,
               'durationInFrames':end_frame-total_frames, 'kind':scene['kind'],
               'heading':scene.get('heading',''), 'badge':scene.get('badge',''),
               'text':scene.get('text',''), 'points':scene.get('points',[]),
               'diagramLayout':scene.get('diagram_layout','flow'),
               'speaker':scene.get('speaker','旁白'), 'mediaStart':0}
        selected = [sources[sid] for sid in scene.get('source_ids',[]) if sid in sources]
        row['sourceLabel'] = ' / '.join(source['title'] for source in selected)[:160]
        row['sourceDate'] = ' / '.join(source.get('published_at','') for source in selected)[:100]
        source_media = media.get(scene.get('media_id'))
        if source_media:
            origin = contained(project, source_media['path'])
            if source_media.get('sha256') and file_sha(origin)!=source_media['sha256']:
                raise ValueError(f'素材 {source_media["id"]} 已变化，请重新导入并提交')
            suffix = origin.suffix.lower()
            destination = public/'assets'/(source_media['id']+suffix)
            if not destination.exists() or file_sha(destination)!=file_sha(origin):
                shutil.copy2(origin, destination)
            row['media'] = 'assets/'+destination.name
            start = float(scene.get('media_start',0))
            row['mediaStart'] = round(start*FPS)
            if scene['kind']=='video':
                actual = float(probe(origin)['format']['duration'])
                if start+row['durationInFrames']/FPS > actual+1/FPS:
                    raise ValueError(f'{scene["id"]} 配音实长 {duration:.2f} 秒，但素材从 {start:.2f} 秒起只剩 {actual-start:.2f} 秒；请补素材或拆段，不能循环填充')
        elif scene['kind'] in ('video','image'):
            raise ValueError(f'{scene["id"]} 尚未绑定 {scene["kind"]} 素材')
        elif scene['kind']=='evidence':
            row['badge'] = row['badge'] or '原文摘录 · 文字整理'
            if not row['text'] or not any(''.join(row['text'].split()) in ''.join(source.get('content','').split()) for source in selected):
                raise ValueError(f'{scene["id"]} 的文字摘录必须能在对应来源正文中逐字找到')
        coverage.append({'scene_id':scene['id'], 'kind':scene['kind'], 'media_id':scene.get('media_id'),
                         'source_ids':scene.get('source_ids',[]), 'start':total_frames/FPS,
                         'duration':row['durationInFrames']/FPS, 'fact_status':scene.get('fact_status')})
        scenes.append(row)
        offset += duration
        total_frames = end_frame
    props = {'title':spec['title'], 'brand':spec.get('brand',{'signature':'','accent':'#10C46F'}),
             'durationInFrames':total_frames, 'width':1920, 'height':1080, 'fps':FPS,
             'scenes':scenes, 'captions':[] if preview else subtitles(project/'subtitles.srt')}
    for caption in props['captions']:
        caption['end'] = min(caption['end'], total_frames)
    write(project/('preview.props.json' if preview else 'render.props.json'), props)
    intervals={}
    for scene,row in zip(spec['scenes'],coverage):
        item=media.get(scene.get('media_id'))
        if item:
            row['media_sha256']=item.get('sha256')
            row['media_start']=float(scene.get('media_start',0))
            row['media_end']=row['media_start']+row['duration']
            if scene['kind']=='video':intervals.setdefault(item.get('sha256',item['id']),[]).append((row['media_start'],row['media_end']))
    unique=0
    for ranges in intervals.values():
        start=end=None
        for left,right in sorted(ranges):
            if end is None:start,end=left,right
            elif left<=end:end=max(end,right)
            else:unique+=end-start;start,end=left,right
        if end is not None:unique+=end-start
    video_seconds=sum(row['duration'] for row in coverage if row['kind']=='video')
    write(project/'coverage.json', {'estimated':preview, 'duration_seconds':total_frames/FPS,
        'video_seconds':video_seconds,'unique_video_seconds':unique,
        'reused_video_seconds':max(0,video_seconds-unique),'scenes':coverage})
    return props, public


def render(project, mode, props, public, output, *extra):
    with FileLock(str(ROOT/'manifests/gpu.lock'),timeout=3600):
        run([NODE, RENDERER, mode, '--props', props, '--public-dir', public, '--output', output,
             '--overwrite','--gl','angle','--concurrency','4',*extra],project/(Path(output).stem+'.render.log'))


def ambient(path):
    """Original unobtrusive synthesized accompaniment, no downloaded music."""
    rate, seconds = 24000, 24
    samples = array('h')
    chords = [(130.8128,164.8138,195.9977),(110,130.8128,164.8138),
              (87.3071,130.8128,174.6141),(97.9989,146.8324,195.9977)]
    for index in range(rate*seconds):
        t=index/rate
        phase=t%6
        envelope=math.sin(math.pi*phase/6)**2
        value=sum(math.sin(2*math.pi*f*t) for f in chords[int(t/6)])/3
        samples.append(round(32767*.06*envelope*value))
    if sys.byteorder!='little':samples.byteswap()
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(samples.tobytes())


def assemble_narration(project, scenes):
    """Resample each source before concat so mixed TTS engines keep real timing."""
    public = project/'render-public'
    public.mkdir(parents=True, exist_ok=True)
    audio_files=[]
    for index, scene in enumerate(scenes):
        source=project/'audio'/(scene['id']+'.wav')
        target=public/f'narration-{index:03}.wav'
        with wave.open(str(source)) as wav:
            original_duration=wav.getnframes()/wav.getframerate()
            tolerance=max(1/48000,1/wav.getframerate())+1e-9
        run([FFMPEG,'-nostdin','-v','error','-y','-i',source,
             '-ar','48000','-ac','2','-c:a','pcm_s16le',target],
            project/f'narration-{index:03}.normalize.log')
        with wave.open(str(target)) as wav:
            normalized_duration=wav.getnframes()/wav.getframerate()
            if (wav.getframerate()!=48000 or wav.getnchannels()!=2 or wav.getsampwidth()!=2
                    or abs(normalized_duration-original_duration)>tolerance):
                raise RuntimeError(f'{scene["id"]} 配音格式转换改变了实际时长')
        audio_files.append(f"file 'render-public/{target.name}'")
    (project/'narration.concat.txt').write_text('\n'.join(audio_files),encoding='utf-8')
    run([FFMPEG,'-nostdin','-v','error','-y','-f','concat','-safe','0','-i','narration.concat.txt',
         '-af','loudnorm=I=-18:TP=-2:LRA=7','-ar','48000','-ac','2','-c:a','pcm_s16le','narration.wav'],
        project/'narration.log',project)
    return project/'narration.wav'


def mix(project, spec, duration):
    assemble_narration(project, spec['scenes'])
    bgm=spec.get('bgm',{'mode':'generated'});mode=bgm.get('mode','generated')
    command=[FFMPEG,'-v','error','-y','-i',project/'picture.mp4','-i',project/'narration.wav']
    if mode!='none':
        if mode=='media':
            item=next((m for m in spec.get('media',[]) if m['id']==bgm.get('media_id') and m['kind']=='audio'),None)
            if not item:raise ValueError('请先登记背景音乐素材')
            background=contained(project,item['path'])
            if item.get('sha256') and file_sha(background)!=item['sha256']:raise ValueError('配乐已在登记后变化，请重新导入')
        else:
            background=project/'ambient-original.wav';ambient(background)
        command+=['-stream_loop','-1','-i',background,'-filter_complex',
            '[1:a]asplit=2[voice][side];[2:a]volume=0.4,aresample=48000[bg];'
            '[bg][side]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=600[duck];'
            '[voice][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89:level=false:latency=true[mix]',
            '-map','0:v:0','-map','[mix]']
    else:command+=['-map','0:v:0','-map','1:a:0']
    command+=['-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',project/'video.mp4']
    run(command,project/'mix.log')


def deliver(project, spec, props):
    duration=props['durationInFrames']/FPS
    chapters={row['id']:row for row in spec.get('chapters',[])}
    chapter_starts={}
    script=[f'# {spec["title"]}', '', '来源与事实状态以配套台账为准。', '']
    for scene, row in zip(spec['scenes'],props['scenes']):
        chapter_starts.setdefault(scene.get('chapter_id'),row['startFrame']/FPS)
        script += [f'## {scene.get("heading",scene["id"])}',
                   f'角色：{scene.get("speaker","旁白")} / 来源：{", ".join(scene.get("source_ids",[]))}',
                   '',scene['narration'],'']
    (project/'script.md').write_text('\n'.join(script),encoding='utf-8')
    write(project/'sources.json',{'review_note':spec.get('review_note','来源是否支持结论需审阅'), 'sources':spec.get('sources',[])})
    with (project/'sources.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=['id','title','url','published_at','status','fetched_at'],extrasaction='ignore')
        writer.writeheader();writer.writerows(spec.get('sources',[]))
    chapter_lines=[]
    for cid, start in chapter_starts.items():
        chapter_lines.append(f'{int(start)//60:02}:{int(start)%60:02} {chapters.get(cid,{}).get("title",cid or "正文")}')
    (project/'chapters.txt').write_text('\n'.join(chapter_lines),encoding='utf-8')
    title=spec['title'][:20]
    note='内容按配套来源台账整理；尚待复核的部分见事实状态。案例示意与原文摘录分别标注。封面为程序排版图。'
    copy=[f'# {spec["title"]} · 八平台发布文案',f'对应：本次成片（{duration:.2f} 秒）。仅备稿，未公开发布。',
          '标题公式（dbs-xhs-title）：本工作台采用问题与方法标题；未调用外部标题 skill。',
          '共用免责段（各平台正文末尾）：',note]
    for platform in ['抖音','快手','B站','视频号','小红书（弱化品牌名）','YouTube','知乎','公众号']:
        copy += ['',f'## {platform}','',f'主推标题：{title}',f'备选标题：{title[:15]}：核对方法', '',
                 '正文：',spec.get('topic',spec['title']), '',
                 '本片从原始来源、具体语境与核对步骤展开。完整叙述、资料出处和不确定之处见视频与台账。',
                 '', '（共用免责段）',note]
        if platform=='B站':copy+=['','本期结构：']+[f'{i+1:02} {chapters.get(cid,{}).get("title",cid or "正文")}' for i,cid in enumerate(chapter_starts)]
        if platform in ('B站','YouTube'):copy+=['','章节：']+chapter_lines
        if platform in ('抖音','快手','B站','视频号','小红书（弱化品牌名）'):
            copy+=['','置顶评论：完整来源已随片附上。你还会核对哪一项？']
        if platform=='公众号':copy+=['','摘要：'+title+'，把出处和结论逐项对照。']
        copy+=['','标签：资料核对 媒介素养 方法解说']
    (project/'publish-copy.md').write_text('\n'.join(copy),encoding='utf-8')
    run([sys.executable, ROOT/'apps/simon-skills/skills/investigation-video/assets/check-publish-copy.py',
         project/'publish-copy.md'],project/'publish-copy.check.log')
    info=probe(project/'video.mp4')
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    audio=next((s for s in info['streams'] if s['codec_type']=='audio'),None)
    if not audio or abs(float(info['format']['duration'])-duration)>.15:
        raise RuntimeError('成片音轨或时长验收未通过')
    run([FFMPEG,'-v','error','-xerror','-i',project/'video.mp4','-f','null','-'],project/'decode-check.log')
    target=float(spec.get('target_minutes',10))*60
    qa={'full_decode_passed':True,'width':video['width'],'height':video['height'],
        'fps':video['r_frame_rate'],'duration_seconds':float(info['format']['duration']),
        'requested_minutes':spec.get('target_minutes'),'actual_ten_minutes':duration>=600,
        'target_reached':duration>=target,'target_difference_seconds':round(duration-target,3),
        'duration_note':('短流程演示片' if spec.get('demo_mode') else '达到目标时长' if duration>=target else '未达到目标时长，需要补充实质内容'),
        'sha256':file_sha(project/'video.mp4'),'audio_codec':audio['codec_name'],
        'subjective_listening':'pending','source_truth':'not machine-certified',
        'cover_type':'programmatic typography','bgm':spec.get('bgm',{'mode':'generated'})}
    write(project/'verification.json',qa)
    files=['video.mp4','subtitles.srt','script.md','sources.json','sources.csv','coverage.json',
           'chapters.txt','publish-copy.md','verification.json','storyboard.json','cover-3x4.png','cover-4x3.png']
    with zipfile.ZipFile(project/'delivery.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        for name in files:
            if (project/name).is_file():bundle.write(project/name,name)
    return qa


def produce(args):
    project=args.project.resolve();spec=read(project/'storyboard.json')
    if not project.is_relative_to((ROOT/'projects/studio').resolve()):raise ValueError('需要工作台工程目录')
    state_path=project/'state.json';key=fingerprint({'storyboard':spec,'code':file_sha(Path(__file__))})
    state=read(state_path) if state_path.exists() else {}
    if state.get('input_sha256')!=key:state={'input_sha256':key,'completed':[]}
    def status(stage,phase,progress):
        state.update(running=stage,phase=phase,progress=progress,updated=time.time());write(state_path,state)
        print(phase,flush=True)
    os.environ.update(PYTHONUTF8='1',HF_HUB_DISABLE_TELEMETRY='1',HF_HOME=str(ROOT/'cache/huggingface'))
    os.environ['PATH']=str(ROOT/'tools')+os.pathsep+str(NODE.parent)+os.pathsep+os.environ['PATH']
    try:
        if not args.preview:
            with FileLock(str(ROOT/'manifests/gpu.lock'),timeout=0):
                from comfy_client import unload
                import requests
                try:unload()
                except requests.ConnectionError:pass
                status('tts','按角色生成旁白，已完成片段可恢复',10)
                from runtime_paths import tts_python
                run([tts_python(spec),ROOT/'scripts/tts_batch.py',project,'--resume'],project/'tts.log')
                status('align','根据实际语音逐句对齐字幕',40)
                run([ROOT/'apps/qwen-asr/.venv/Scripts/python.exe',ROOT/'scripts/align_batch.py',project,'--resume'],project/'align.log')
        status('coverage','检查素材与实际时间轴',50)
        props,public=build_props(project,spec,args.preview)
        props_path=project/('preview.props.json' if args.preview else 'render.props.json')
        frames=[]
        preview_indices={0,len(spec['scenes'])-1}
        seen_chapters=set();seen_kinds=set()
        for i,scene in enumerate(spec['scenes']):
            if scene.get('chapter_id') not in seen_chapters or scene['kind'] not in seen_kinds:preview_indices.add(i)
            seen_chapters.add(scene.get('chapter_id'));seen_kinds.add(scene['kind'])
        for index in sorted(preview_indices):
            row=props['scenes'][index]
            output=project/f'preview-{index+1:02}.png'
            render(project,'still',props_path,public,output,'--frame',str(row['startFrame']+min(45,row['durationInFrames']-1)))
            frames.append(output.name)
        covers=[]
        for ratio in ('3:4','4:3'):
            output=project/('cover-'+ratio.replace(':','x')+'.png')
            render(project,'cover',props_path,public,output,'--ratio',ratio);covers.append(output.name)
        manifest={'preview_frames':frames,'covers':covers,'duration_seconds':props['durationInFrames']/FPS,
                  'estimated_duration':args.preview,'cover_type':'programmatic typography'}
        if not args.preview:
            status('render','Remotion 合成长片画面',60)
            renderer_files=[RENDERER,RENDERER.parent/'contract.mjs',*sorted((RENDERER.parent/'src').glob('*'))]
            picture_key=fingerprint({'props':props,'code':{p.name:file_sha(p) for p in renderer_files if p.is_file()}})
            if state.get('picture_key')!=picture_key or not (project/'picture.mp4').is_file() or state.get('picture_sha256')!=file_sha(project/'picture.mp4'):
                render(project,'video',props_path,public,project/'picture.mp4')
                state.update(picture_key=picture_key,picture_sha256=file_sha(project/'picture.mp4'));write(state_path,state)
            status('mix','归一旁白响度并闪避背景音乐',85)
            mix(project,spec,props['durationInFrames']/FPS)
            status('verify','检查完整解码、字幕、发布稿并打包',95)
            qa=deliver(project,spec,props)
            manifest.update(video='video.mp4',subtitle='subtitles.srt',verification='verification.json',
                script='script.md',sources='sources.csv',publishing='publish-copy.md',bundle='delivery.zip',
                duration_seconds=qa['duration_seconds'])
            manifest.update(target_reached=qa['target_reached'],duration_note=qa['duration_note'],target_difference_seconds=qa['target_difference_seconds'])
        write(project/'investigation.manifest.json',manifest)
        status('done','预览已完成' if args.preview else '成片与发布包已完成，请审片',100)
    except Exception as error:
        state.update(error=str(error),phase='制作中断；已生成音频和项目已保留');write(state_path,state)
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    if not args.project.resolve().is_relative_to((ROOT/'projects/studio').resolve()):raise ValueError('需要工作台工程目录')
    with FileLock(str(args.project.resolve()/'pipeline.lock'),timeout=0):produce(args)


if __name__=='__main__':main()
