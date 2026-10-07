"""Veyra 1.4.4 portable export adapter; source files are never overwritten."""
import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from filelock import FileLock
from comfy_client import ROOT,unload
from creation_settings import number

APP=ROOT/'apps/Veyra-1.4.4/Veyra-1.4.4-win64-portable/Veyra.exe'
RUNNING={}

def post(handler,data,jobs):
    if handler.path=='/api/enhance/open':
        if not APP.is_file():raise ValueError('Veyra 尚未安装')
        args=[str(APP)]
        if data.get('input'):
            p=Path(data['input'])
            if not p.is_absolute() or not p.is_file():raise ValueError('请选择已有本地视频')
            args.append(str(p))
        subprocess.Popen(args,cwd=APP.parent)
        handler.reply({'message':'已打开 Veyra 桌面界面。工作台导出可直接在本页提交。'});return True
    if handler.path=='/api/enhance/cancel':
        job=data.get('job_id');proc=RUNNING.get(job)
        if proc and proc.poll() is None:proc.terminate();handler.reply({'message':'已请求取消，等待任务释放显存。'})
        else:handler.reply({'message':'任务已经结束或尚未进入导出进程。'})
        return True
    if handler.path!='/api/enhance':return False
    if not APP.is_file():raise ValueError('Veyra 尚未安装')
    source=Path(data.get('input',''))
    if not source.is_absolute() or not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.mkv','.avi','.webm'):raise ValueError('请选择本机已有的视频完整路径')
    factor=number(data.get('factor',2),1,6,'补帧倍率',True)
    if factor not in (1,2,3,4,6):raise ValueError('请选择 1/2/3/4/6 倍率')
    quality=number(data.get('quality',1),1,4,'RTX Video SR 质量',True)
    bitrate=number(data.get('bitrate',16),1,100,'输出码率',True)
    resolution=data.get('resolution','native')
    if resolution not in ('native','720','1080','2160'):raise ValueError('未知导出分辨率')
    if data.get('codec','h264') not in ('h264','hevc'):raise ValueError('未知编码格式')
    if any(j.get('status') in ('running','queued') for j in jobs.values()):raise ValueError('请等待当前任务结束，再进行视频增强')
    from studio_extensions import listening
    if listening(7860):raise ValueError('请先停止独立配音界面，释放显存')
    job='enhance-'+uuid.uuid4().hex[:10];dest=ROOT/'projects/studio'/job;dest.mkdir(parents=True)
    (dest/'request.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    jobs[job]={'kind':'enhance','status':'queued','source':str(source),'factor':factor}
    args=[str(APP),str(source),'--export-out',str(dest/'veyra.mp4'),'--nr-original','--nr' if data.get('nr') else '--no-nr','--fg-dlss','--fg-multiplier',str(factor),'--bitrate-mbps',str(bitrate)]
    args+=['--video-sr',str(quality)] if data.get('sr',True) else ['--no-sr']
    if data.get('codec')=='hevc':args+=['--hevc']
    def run():
        proc=None
        try:
            with FileLock(str(ROOT/'manifests/gpu.lock'),timeout=0):
                jobs[job]['status']='running';unload()
                env=os.environ.copy();env['VEYRA_LOG_FILE']=str(dest/'veyra.log')
                proc=subprocess.Popen(args,cwd=APP.parent,env=env,creationflags=subprocess.CREATE_NO_WINDOW);RUNNING[job]=proc
                code=proc.wait(timeout=7200)
                if code:raise RuntimeError(f'Veyra 导出未完成（退出码 {code}），日志：{dest / "veyra.log"}')
                raw=dest/'veyra.mp4';output=dest/'video.mp4'
                if resolution=='native':raw.rename(output)
                else:
                    # Final delivery canvas only; the AI enhancement occurs in Veyra above.
                    short=int(resolution);long=short*16//9
                    vf=f"scale=w='if(gte(iw,ih),{long},{short})':h='if(gte(iw,ih),{short},{long})':force_original_aspect_ratio=decrease:force_divisible_by=2,pad=w='if(gte(iw,ih),{long},{short})':h='if(gte(iw,ih),{short},{long})':x=(ow-iw)/2:y=(oh-ih)/2,setsar=1"
                    command=[str(ROOT/'tools/ffmpeg.exe'),'-v','error','-y','-i',str(raw),'-vf',vf,'-c:v','libx264' if data.get('codec','h264')=='h264' else 'libx265','-preset','fast','-crf','18','-c:a','copy','-movflags','+faststart',str(output)]
                    with (dest/'resize.log').open('w',encoding='utf-8') as log:
                        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);RUNNING[job]=proc
                        if proc.wait(timeout=7200):raise RuntimeError('最终尺寸合成失败，Veyra 原始导出已保留')
                jobs[job].update(status='done',video=f'/outputs/{job}/video.mp4')
        except Exception as exc:
            if proc and proc.poll() is None:proc.kill();proc.wait()
            jobs[job].update(status='error',error=str(exc))
        finally:
            RUNNING.pop(job,None);(dest/'status.json').write_text(json.dumps(jobs[job],ensure_ascii=False),encoding='utf-8')
    threading.Thread(target=run,daemon=True).start();handler.reply({'job_id':job},202);return True
