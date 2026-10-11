"""Compose supplied images/videos using the plan's frozen narration and voices.

No authoring engine is invoked here. Codex, Blender and ComfyUI can all return
real shot assets to the same plan. Copies and hashes make retries independent
of later edits to the original files.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil
import wave

import generation_plans as plans
from prompt_library import ROOT


def assemble_timeline(dest, clips, timeline, output, filename):
    """Align clean video and PCM tracks to the same frame clock; encode AAC once."""
    from generation_automation import _command
    from pipeline import run
    ffmpeg=ROOT/'tools/ffmpeg.exe'
    tracks=dest/'timeline-tracks';tracks.mkdir(exist_ok=True)
    for index,(clip,row) in enumerate(zip(clips,timeline)):
        seconds=str(row['duration'])
        _command([ffmpeg,'-y','-v','error','-i',clip,'-map','0:v:0','-an','-t',seconds,
                  '-c:v','copy',tracks/f'{index:03d}.mp4'],dest,f'track-{index}-video')
        _command([ffmpeg,'-y','-v','error','-i',dest/'audio'/(row['id']+'.wav'),
                  '-af','apad','-t',seconds,'-ar','48000','-ac','1','-c:a','pcm_s16le',
                  tracks/f'{index:03d}.wav'],dest,f'track-{index}-audio')
    for suffix,name,target in [('mp4','concat.txt','video.clean.mp4'),('wav','audio-concat.txt','narration.wav')]:
        (dest/name).write_text(''.join(f"file 'timeline-tracks/{index:03d}.{suffix}'\n" for index in range(len(clips))),encoding='utf-8')
        _command([ffmpeg,'-y','-v','error','-f','concat','-safe','1','-i',dest/name,
                  '-c','copy',dest/target],dest,'assemble-'+suffix)
    run([ffmpeg,'-y','-v','error','-i','video.clean.mp4','-i','narration.wav','-map','0:v:0','-map','1:a:0',
         '-vf',f"subtitles=subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize={output['subtitle_size']},Outline=2,MarginV=28'",
         '-c:v','libx264','-crf','20','-c:a','aac','-movflags','+faststart',filename],dest/'subtitles.render.log',dest)


def freeze(plan, dest, preview=False):
    shots=plan['shots'][:1] if preview else plan['shots']
    if not 1<=len(shots)<=24:
        raise ValueError('请提供 1–24 个镜头，长片请按章节制作')
    inputs=[]
    for shot in shots:
        path=plans._asset(shot.get('asset_path',''))
        if not path:
            raise ValueError('请先给镜头 '+shot['id']+' 选择已制作的图片或视频')
        source=ROOT/path
        if source.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm'):
            raise ValueError('镜头素材应为 PNG/JPEG/WebP 或 MP4/MOV/WebM；请先将 Blender 工程渲染成视频')
        inputs.append((shot['id'],source))
    folder=dest/'supplied';folder.mkdir(exist_ok=True)
    rows=[]
    for identity,source in inputs:
        target=folder/(identity+source.suffix.lower())
        shutil.copy2(source,target)
        rows.append({'id':identity,'path':target.relative_to(dest).as_posix(),
                     'source':str(source),
                     'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    (dest/'supplied-assets.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')


def compose(plan,dest,preview,frozen):
    from generation_automation import frozen_speech,_command
    shots=plan['shots'][:1] if preview else plan['shots']
    rows=json.loads((dest/'supplied-assets.json').read_text(encoding='utf-8'))
    if [r['id'] for r in rows]!=[s['id'] for s in shots]:
        raise ValueError('交回镜头与提交版本不符，请另建任务')
    for row in rows:
        path=plans._plain(dest/row['path'])
        if not path.resolve().is_relative_to((dest/'supplied').resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('交回素材快照校验失败，不能继续覆盖')
    spec=frozen_speech(plan,shots,frozen)
    spec['backends']['asr']='synthesis' if spec['backends']['tts']=='windows' else 'local'
    (dest/'storyboard.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    for stage in ('tts','align'):
        _command([ROOT/'tools/.venv/Scripts/python.exe',ROOT/'scripts/pipeline.py',dest,'--stage',stage],dest,stage)
    output=spec['settings']['output'];width,height,fps=(output[k] for k in ('width','height','fps'))
    ffmpeg=ROOT/'tools/ffmpeg.exe'
    folder=dest/'segments';folder.mkdir(exist_ok=True)
    duration=0;timeline=[];subtitles=[]
    from lightweight_speech import cues,write_srt
    for row,shot in zip(rows,shots):
        source=dest/row['path'];audio=dest/'audio'/(row['id']+'.wav')
        with wave.open(str(audio)) as sound:seconds=sound.getnframes()/sound.getframerate()
        clip_duration=math.ceil(seconds*fps)/fps
        still=source.suffix.lower() in ('.png','.jpg','.jpeg','.webp')
        inputs=['-loop','1','-framerate',str(fps)] if still else []
        # Preserve the complete source frame. Short clips hold their last frame;
        # long clips are trimmed to speech, never sped up without user intent.
        vf=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}'
        if not still:vf+=f',tpad=stop_mode=clone:stop_duration={seconds}'
        _command([ffmpeg,'-y','-v','error',*inputs,'-i',source,'-an','-vf',vf,'-t',str(clip_duration),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',folder/(row['id']+'.mp4')],dest,row['id']+'-compose')
        words=json.loads((dest/'audio'/(row['id']+'.alignment.json')).read_text('utf-8'))
        for cue in cues(words,limit=14 if height>width else 18,text=shot['narration'],seconds=seconds):
            subtitles.append({**cue,'start':duration+cue['start'],'end':duration+min(cue['end'],clip_duration)})
        timeline.append({'id':row['id'],'start':duration,'duration':clip_duration,'audio_duration':seconds,'narration':shot['narration']})
        duration+=clip_duration
    write_srt(dest/'subtitles.srt',subtitles)
    (dest/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),'utf-8')
    filename='sample.mp4' if preview else 'video.mp4'
    assemble_timeline(dest,[folder/(r['id']+'.mp4') for r in rows],timeline,output,filename)
    _command([ffmpeg,'-y','-v','error','-i',dest/filename,'-frames:v','1',dest/'cover.png'],dest,'cover')
    qa={'quality_review':'pending','listening_review':'pending','source':'supplied shot assets','duration':duration,
        'width':width,'height':height,'fps':fps,'timing':'short clips hold their final frame; long clips trim to narration'}
    (dest/'qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')
    return {**qa,'video':filename,'image':'cover.png','subtitle':'subtitles.srt','qa':'qa.json',
            'shot_outputs':[{'id':r['id'],'path':r['path']} for r in rows]}
