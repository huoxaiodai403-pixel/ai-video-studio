"""Run a local storyboard through audio, alignment, illustration and rendering."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from contextlib import nullcontext
from pathlib import Path
import imageio_ffmpeg
from filelock import FileLock
from prompt_library import ROOT, compile_prompt
from comfy_client import generate, unload
import providers
import online_pipeline
from creation_settings import load


def run(command, log, cwd=None):
    print('Running:', ' '.join(map(str, command)), flush=True)
    with log.open('w', encoding='utf-8') as f:
        subprocess.run(list(map(str, command)), cwd=cwd, stdout=f, stderr=subprocess.STDOUT, check=True)


def render(project, spec):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    settings=spec.get('settings',load());out=settings['output'];width,height,fps=out['width'],out['height'],out['fps']
    segments = project / 'segments'
    segments.mkdir(exist_ok=True)
    listing = []
    for scene in spec['scenes']:
        sid = scene['id']
        audio = project / 'audio' / (sid+'.wav')
        image = project / 'images' / (sid+'.png')
        with wave.open(str(audio)) as f:
            duration = f.getnframes()/f.getframerate()
        output = segments / (sid+'.mp4')
        if spec.get('motion_enabled'):
            video=project/'motion'/(sid+'.mp4')
            reader=imageio_ffmpeg.read_frames(str(video));metadata=next(reader);reader.close()
            rate=duration/metadata['duration']
            vf=f'setpts={rate}*(PTS-STARTPTS),fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},tpad=stop_mode=clone:stop_duration=1'
            inputs=['-i',video,'-i',audio]
        else:
            vf = f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},zoompan=z='min(zoom+0.00015,1.05)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}"
            inputs=['-loop','1','-framerate',str(fps),'-i',image,'-i',audio]
        run([ffmpeg,'-y',*inputs,'-vf',vf,'-t',str(duration),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','48000',output], project / (sid+'.render.log'))
        listing.append(f"file '{output.as_posix()}'")
    (project/'segments.txt').write_text('\n'.join(listing), encoding='utf-8')
    run([ffmpeg,'-y','-f','concat','-safe','0','-i',project/'segments.txt','-c','copy',project/'video.clean.mp4'], project/'concat.log')
    run([ffmpeg,'-y','-i','video.clean.mp4','-vf',f"subtitles=subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize={out['subtitle_size']},Outline=2,MarginV=28'",'-c:v','libx264','-preset','fast','-crf','20','-c:a','copy','-movflags','+faststart','video.mp4'],project/'subtitles.render.log',project)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--stage', choices=['all','tts','align','images','motion','render'], default='all')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    project = args.project.resolve()
    spec = json.loads((project/'storyboard.json').read_text(encoding='utf-8'))
    settings=spec.get('settings',load())
    # Validate frozen inputs even when the stage or per-image cache is reusable.
    from image_references import checked_paths
    for scene in spec['scenes']:
        references=scene.get('image_references',[])
        reference_ids=scene.get('image_reference_ids',spec.get('image_reference_ids'))
        if reference_ids is not None:
            if not isinstance(reference_ids,list) or reference_ids != [row.get('id') for row in references if isinstance(row,dict)]:
                raise ValueError('参考图选择尚未冻结或与快照不一致，请通过工作台重新提交')
        if references:
            if spec.get('backends',{}).get('image','local')!='local' or settings['image'].get('engine','qwen-image-2512')!='flux2-klein-4b':
                raise ValueError('参考图编辑需要本地 FLUX.2 klein 4B，不能忽略参考图继续生成')
            checked_paths(references)
    for scene in spec['scenes']:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',scene['id']):
            raise ValueError('Scene ids must use letters, numbers, underscore or hyphen')
    fingerprint = hashlib.sha256((project/'storyboard.json').read_bytes())
    backends=spec.get('backends',{})
    selected={k:v for k,v in providers.load(public=True).items() if backends.get(k)=='online'}
    fingerprint.update(json.dumps(selected,sort_keys=True).encode())
    source_names = ['pipeline.py','tts_batch.py','align_batch.py','comfy_client.py','prompt_library.py','render_whiteboard.py','whiteboard_scene.py','providers.py','online_pipeline.py','wan_client.py','creation_settings.py']
    source_names += ['flux_klein.py','model_profiles.py','image_references.py','wan_a14b.py']
    if backends.get('tts') in ('windows','edge','volc') or spec.get('render_mode') == 'excalidraw':
        source_names += ['lightweight_speech.py','windows_speech.ps1','volc_speech.py']
    if backends.get('tts')=='volc':
        import volc_speech
        fingerprint.update(json.dumps(volc_speech.load(public=True),sort_keys=True).encode())
    if spec.get('render_mode') == 'excalidraw':
        source_names += ['simon_whiteboard.py', 'simon_bridge.cjs', 'simon_caption_timing.cjs']
    for name in source_names:
        fingerprint.update((ROOT/'scripts'/name).read_bytes())
    if spec.get('render_mode') == 'excalidraw':
        engine = ROOT/'apps/simon-skills/skills/whiteboard-video'
        for name in ['config.json', 'lib/paths.cjs', 'lib/scene-dsl.js', 'lib/render.js', 'lib/render.html', 'lib/captions.cjs']:
            fingerprint.update((engine/name).read_bytes())
    repository_manifest=ROOT/'manifests/repositories.json'
    if repository_manifest.is_file():fingerprint.update(repository_manifest.read_bytes())
    elif (ROOT/'runtime-dependencies.json').is_file():fingerprint.update((ROOT/'runtime-dependencies.json').read_bytes())
    digest = fingerprint.hexdigest()
    state_file = project/'state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if state.get('input_sha256') != digest:
        state = {'input_sha256':digest, 'completed':[]}
    os.environ['PYTHONUTF8']='1'
    os.environ['HF_HOME']=str(ROOT/'cache/huggingface')
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ['PATH']=str(ROOT/'tools')+os.pathsep+str(ffmpeg.parent)+os.pathsep+os.environ['PATH']
    stages = ['tts','align','images','render'] if args.stage=='all' else [args.stage]
    is_board = spec.get('render_mode') in ('whiteboard', 'excalidraw')
    if spec.get('motion_enabled') and args.stage=='all' and not is_board:
        stages.insert(-1,'motion')
    if is_board:
        stages=[stage for stage in stages if stage!='images']
        if 'motion' in stages:
            raise ValueError('白板使用逐笔动画，不支持动态模型阶段。')
    artifacts = {
        'tts': [project/'audio'/(s['id']+'.wav') for s in spec['scenes']],
        'align': [project/'subtitles.srt', project/'timeline.json'],
        'images': [project/'images'/(s['id']+'.png') for s in spec['scenes']],
        'motion': [project/'motion'/(s['id']+'.mp4') for s in spec['scenes']],
        'render': [project/'video.mp4'],
    }
    if spec.get('render_mode') == 'excalidraw':
        artifacts['align'] += [project/'audio'/(s['id']+'.alignment.json') for s in spec['scenes']]
    if backends.get('asr') == 'synthesis':
        artifacts['tts'] += [project/'audio'/(s['id']+'.alignment.json') for s in spec['scenes']]
    cpu_only = not any((stage in ('tts','align') and backends.get('tts' if stage=='tts' else 'asr','local')=='local')
                       or (stage in ('images','motion') and backends.get('image' if stage=='images' else 'video','local')=='local')
                       for stage in stages)
    with (nullcontext() if cpu_only else FileLock(str(ROOT/'manifests/gpu.lock'), timeout=0)) as gpu_lock:
        for stage in stages:
            if stage in state.get('completed',[]) and all(p.is_file() and p.stat().st_size for p in artifacts[stage]) and not args.force:
                print(f'Skipping completed stage: {stage}',flush=True)
                continue
            state['running']=stage
            state_file.write_text(json.dumps(state,indent=2),encoding='utf-8')
            try:
                if stage=='tts' and (backends.get('tts') in ('windows','edge','volc') or (is_board and backends.get('tts')=='online')):
                    import lightweight_speech
                    lightweight_speech.tts_project(project,spec)
                elif stage=='align' and backends.get('asr')=='synthesis':
                    import lightweight_speech
                    lightweight_speech.align_project(project,spec)
                elif stage=='tts' and backends.get('tts')=='online':
                    online_pipeline.tts(project,spec)
                elif stage=='align' and backends.get('asr')=='online':
                    online_pipeline.align(project,spec)
                elif stage in ('tts','align'):
                    try:
                        unload()
                    except Exception as exc:
                        import requests
                        if not isinstance(exc, requests.ConnectionError):
                            raise
                    app = 'index-tts' if stage=='tts' else 'qwen-asr'
                    script = 'tts_batch.py' if stage=='tts' else 'align_batch.py'
                    from runtime_paths import tts_python
                    python=tts_python(spec) if stage=='tts' else ROOT/f'apps/{app}/.venv/Scripts/python.exe'
                    run([python,ROOT/'scripts'/script,project],project/f'{stage}.log')
                elif stage=='images':
                    (project/'images').mkdir(exist_ok=True)
                    image_code=hashlib.sha256()
                    for name in ['comfy_client.py','flux_klein.py','model_profiles.py','image_references.py','prompt_library.py']:
                        image_code.update((ROOT/'scripts'/name).read_bytes())
                    for scene in spec['scenes']:
                        ratio='竖版' if settings['image']['height']>settings['image']['width'] else '横版'
                        prompt = compile_prompt(scene['subject'],scene['style'],scene.get('composition',ratio+'，底部预留字幕空间'),scene.get('palette','统一角色服装与配色'),scene.get('source_case_id'),scene.get('reference_text',''))
                        prompt.update(settings['image']);prompt['models']=settings['models']
                        prompt['reference_images']=scene.get('image_references',[])
                        if prompt['reference_images']:
                            if backends.get('image','local')!='local' or prompt.get('engine','qwen-image-2512')!='flux2-klein-4b':
                                raise ValueError('参考图编辑需要本地 FLUX.2 klein 4B，不能忽略参考图继续生成')
                            checked_paths(prompt['reference_images'])
                        prompt['workflow_sha256']=image_code.hexdigest()
                        if 'seed' in scene:prompt['seed']=scene['seed']
                        if 'steps' in scene:prompt['steps']=scene['steps']
                        prompt['execution_backend']=backends.get('image','local')
                        if backends.get('image')=='online':prompt['online_model']=selected['image']['model']
                        destination = project/'images'/(scene['id']+'.png')
                        prompt_file = destination.with_suffix('.prompt.json')
                        old = json.loads(prompt_file.read_text(encoding='utf-8')) if prompt_file.exists() else None
                        if old==prompt and destination.is_file() and not args.force:
                            continue
                        if backends.get('image')=='online':providers.image(prompt['prompt'],destination,f"{prompt['width']}x{prompt['height']}")
                        else:generate(prompt,destination)
                        prompt_file.write_text(json.dumps(prompt,ensure_ascii=False,indent=2),encoding='utf-8')
                    if backends.get('image')!='online':unload()
                elif stage=='motion':
                    from wan_client import generate as generate_motion
                    (project/'motion').mkdir(exist_ok=True)
                    for scene in spec['scenes']:
                        description=scene.get('motion_prompt','A slow stable camera move. Preserve the subject and illustration style. No cuts, no text.')
                        output=project/'motion'/(scene['id']+'.mp4')
                        first=project/'images'/(scene['id']+'.png')
                        if backends.get('video')=='online':providers.video(description,output,first)
                        else:
                            motion=dict(settings['motion']);motion['steps']=scene.get('motion_steps',motion['steps'])
                            generate_motion(description,output,first,already_locked=True,models=settings['models'],**motion)
                else:
                    if spec.get('render_mode')=='excalidraw':
                        # Narration and alignment have finished. Chromium/FFmpeg do
                        # not need to reserve the model inference lock.
                        if gpu_lock is not None:
                            gpu_lock.release()
                        run([ROOT/'tools/.venv/Scripts/python.exe',ROOT/'scripts/simon_whiteboard.py',project],project/'whiteboard.log')
                    elif spec.get('render_mode')=='whiteboard':
                        run([ROOT/'tools/.venv/Scripts/python.exe',ROOT/'scripts/render_whiteboard.py',project],project/'whiteboard.log')
                    else:
                        render(project,spec)
                state.setdefault('completed',[])
                if stage not in state['completed']:
                    state['completed'].append(stage)
                state.pop('error',None)
            except Exception as exc:
                state['error']=str(exc)
                raise
            finally:
                state['running']=None
                state_file.write_text(json.dumps(state,indent=2),encoding='utf-8')
    print('Completed requested stages.',flush=True)


if __name__=='__main__':
    main()
