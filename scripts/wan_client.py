"""Local Wan2.2 5B and A14B workflows, based on ComfyUI's official templates."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from filelock import FileLock
from comfy_client import ROOT,HTTP,URL,unload


def workflow(prompt, image=None, steps=20, frames=49, seed=42, width=512, height=288, models=None, engine='wan2.2-5b'):
    if engine=='wan2.2-a14b':
        from wan_a14b import workflow as a14b_workflow
        return a14b_workflow(prompt,image,steps,frames,seed,width,height,models)
    if engine!='wan2.2-5b':
        raise ValueError('未知 Wan 视频引擎')
    graph={
      '1':{'class_type':'UNETLoader','inputs':{'unet_name':'wan2.2_ti2v_5B_fp16.safetensors','weight_dtype':'default'}},
      '2':{'class_type':'CLIPLoader','inputs':{'clip_name':'umt5_xxl_fp8_e4m3fn_scaled.safetensors','type':'wan','device':'cpu'}},
      '3':{'class_type':'VAELoader','inputs':{'vae_name':'wan2.2_vae.safetensors'}},
      '4':{'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':prompt}},
      '5':{'class_type':'CLIPTextEncode','inputs':{'clip':['2',0],'text':'blurry, distorted anatomy, flicker, subtitles, watermark, static image, low quality'}},
      '6':{'class_type':'Wan22ImageToVideoLatent','inputs':{'vae':['3',0],'width':512,'height':288,'length':frames,'batch_size':1}},
      '7':{'class_type':'ModelSamplingSD3','inputs':{'model':['1',0],'shift':8.0}},
      '8':{'class_type':'KSampler','inputs':{'model':['7',0],'positive':['4',0],'negative':['5',0],'latent_image':['6',0],
            'seed':seed,'steps':steps,'cfg':5.0,'sampler_name':'uni_pc','scheduler':'simple','denoise':1.0}},
      '9':{'class_type':'VAEDecodeTiled','inputs':{'samples':['15',0],'vae':['3',0],'tile_size':256,'overlap':64,'temporal_size':128,'temporal_overlap':16}},
      '15':{'class_type':'SaveLatent','inputs':{'samples':['8',0],'filename_prefix':'AI-Video/Wan/latents/'+uuid.uuid4().hex[:12]}},
      '10':{'class_type':'SaveImage','inputs':{'images':['9',0],'filename_prefix':'AI-Video/Wan/'+uuid.uuid4().hex[:12]}}
    }
    from creation_settings import load
    models=models or load()['models']
    graph['1']['inputs']['unet_name']=models['video_unet']
    graph['2']['inputs']['clip_name']=models['video_clip']
    graph['3']['inputs']['vae_name']=models['video_vae']
    graph['6']['inputs'].update(width=width,height=height)
    if image:
        graph['11']={'class_type':'LoadImage','inputs':{'image':image}}
        graph['6']['inputs']['start_image']=['11',0]
    return graph


def _stage_history(graph, record):
    """Identify expert stages without inventing timings absent from /history."""
    status=record.get('status',{})
    cached=set();executed=set();failed=None
    for event,data in status.get('messages',[]):
        if event=='execution_cached':cached.update(str(n) for n in data.get('nodes',[]))
        if event in ('execution_error','execution_interrupted'):
            executed.update(str(n) for n in data.get('executed',[]));failed=str(data.get('node_id',''))
    completed=status.get('status_str')=='success' and status.get('completed',False)
    rows=[]
    for node_id,label in [('8','high_noise' if '14' in graph else 'single'),('14','low_noise')]:
        if node_id not in graph:continue
        values=graph[node_id]['inputs']
        state=('cached' if node_id in cached else 'failed' if node_id==failed else
               'completed' if completed or node_id in executed else 'unknown')
        rows.append({'stage':label,'node_id':node_id,'status':state,
                     'start_step':values.get('start_at_step',0),
                     'end_step':values.get('end_at_step',values['steps']),
                     'steps':values['steps'],'elapsed_seconds':None})
    return rows


def generate(prompt,output,image=None,steps=20,frames=49,already_locked=False,width=512,height=288,fps=16,seed=42,models=None,engine='wan2.2-5b'):
    if engine not in ('wan2.2-5b','wan2.2-a14b'):raise ValueError('未知 Wan 视频引擎')
    if engine=='wan2.2-a14b':
        from wan_a14b import validate
        from model_profiles import require
        validate(str(image) if image else None,steps,frames,width,height)
        require('motion',engine,models)
    if image and not Path(image).is_file():raise ValueError('首帧图片不存在')
    if isinstance(fps,bool) or not isinstance(fps,(int,float)) or not 0<fps<=120:raise ValueError('视频帧率应在 0–120 之间')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    image_name=None
    with (nullcontext() if already_locked else FileLock(str(ROOT/'manifests/gpu.lock'),timeout=0)):
        started=time.monotonic()
        unload()
        if image:
            image=Path(image)
            with image.open('rb') as f:
                response=HTTP.post(URL+'/upload/image',files={'image':(uuid.uuid4().hex+image.suffix,f)},timeout=60)
            response.raise_for_status();image_name=response.json()['name']
        graph=workflow(prompt,image_name,steps,frames,seed,width,height,models,engine)
        output.with_suffix('.workflow.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
        metadata={'engine':engine,'status':'submitting','width':width,'height':height,'frames':frames,
                  'fps':fps,'steps':steps,'seed':seed,'stage_timing_note':'ComfyUI /history does not report per-node durations.',
                  'stages':_stage_history(graph,{})}
        metadata_path=output.with_suffix('.generation.json')
        def save_metadata():
            metadata['elapsed_seconds']=round(time.monotonic()-started,3)
            metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
        save_metadata()
        response=HTTP.post(URL+'/prompt',json={'prompt':graph,'client_id':uuid.uuid4().hex},timeout=30)
        if not response.ok:
            metadata.update(status='rejected',error=response.text);save_metadata()
            raise RuntimeError(response.text)
        pid=response.json()['prompt_id'];print('ComfyUI task '+pid,flush=True)
        metadata.update(prompt_id=pid,status='running');save_metadata()
        submitted=time.monotonic()
        deadline=time.monotonic()+3600
        while time.monotonic()<deadline:
            response=HTTP.get(URL+'/history/'+pid,timeout=30);response.raise_for_status()
            record=response.json().get(pid)
            if record:
                output.with_suffix('.history.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                metadata.update(stages=_stage_history(graph,record),comfy_elapsed_seconds=round(time.monotonic()-submitted,3))
                latents=record.get('outputs',{}).get('15',{}).get('latents',[])
                if latents and 'latent_sha256' not in metadata:
                    entry=latents[0]
                    base=(ROOT/'apps/ComfyUI/output').resolve()
                    source=(base/entry.get('subfolder','')/entry['filename']).resolve()
                    if entry.get('type')!='output' or not source.is_relative_to(base) or source.suffix!='.latent':
                        raise ValueError('Invalid latent snapshot path')
                    target=output.with_suffix('.latent')
                    shutil.copy2(source,target)
                    metadata.update(latent_path=str(target),latent_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                    temporal_size=graph['9']['inputs']['temporal_size'],
                                    temporal_overlap=graph['9']['inputs']['temporal_overlap'])
                    save_metadata()
                if record.get('status',{}).get('status_str')=='error':
                    metadata.update(status='error',error=record['status']);save_metadata()
                    raise RuntimeError(str(record['status']))
                images=record.get('outputs',{}).get('10',{}).get('images',[])
                if images:
                    if len(images)!=frames:
                        metadata.update(status='error',actual_frames=len(images),error='ComfyUI output frame count differs from request');save_metadata()
                        raise RuntimeError(f'Wan 输出帧数 {len(images)} 与请求 {frames} 不符')
                    # A rerender may have fewer frames than the previous take.
                    # Keep each task's frames isolated so ffmpeg cannot append
                    # stale frames from another scene or a longer old take.
                    target=output.parent/'frames'/(output.stem+'-'+pid)
                    target.mkdir(parents=True,exist_ok=True)
                    base=(ROOT/'apps/ComfyUI/output').resolve()
                    for i,entry in enumerate(images):
                        source=(base/entry['subfolder']/entry['filename']).resolve()
                        if not source.is_relative_to(base):raise ValueError('Invalid output path')
                        shutil.copy2(source,target/f'{i:05}.png')
                    encoding_started=time.monotonic()
                    try:
                        subprocess.run([str(ROOT/'tools/ffmpeg.exe'),'-v','error','-y','-framerate',str(fps),'-i',str(target/'%05d.png'),
                            '-frames:v',str(len(images)),'-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-movflags','+faststart',str(output)],check=True)
                    except subprocess.CalledProcessError as error:
                        metadata.update(status='error',error='FFmpeg 编码失败',ffmpeg_returncode=error.returncode);save_metadata()
                        raise
                    metadata.update(status='done',actual_frames=len(images),duration_seconds=len(images)/fps,
                                    encoding_elapsed_seconds=round(time.monotonic()-encoding_started,3),frames_directory=str(target))
                    save_metadata()
                    unload();return
                if record.get('status',{}).get('completed'):
                    metadata.update(status='error',error='ComfyUI completed without output images');save_metadata()
                    raise RuntimeError('ComfyUI 已结束但未返回视频帧')
            time.sleep(3)
        metadata.update(status='timeout',error='ComfyUI may still be running; inspect queue before retry');save_metadata()
        raise TimeoutError('Wan task still running; inspect ComfyUI before resubmitting.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('prompt');parser.add_argument('output',type=Path)
    parser.add_argument('--image',type=Path);parser.add_argument('--steps',type=int,default=20);parser.add_argument('--frames',type=int,default=49)
    parser.add_argument('--engine',choices=['wan2.2-5b','wan2.2-a14b'])
    parser.add_argument('--width',type=int,default=512);parser.add_argument('--height',type=int,default=288)
    parser.add_argument('--fps',type=float,default=16);parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--settings',type=Path)
    args=parser.parse_args()
    if args.settings:
        c=json.loads(args.settings.read_text(encoding='utf-8'));m=dict(c['motion'])
        if args.engine:m['engine']=args.engine
        generate(args.prompt,args.output,args.image,models=c['models'],**m)
    else:generate(args.prompt,args.output,args.image,args.steps,args.frames,width=args.width,height=args.height,
                  fps=args.fps,seed=args.seed,engine=args.engine or 'wan2.2-5b')
