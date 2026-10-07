import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def render(project):
    project=Path(project).resolve()
    from creation_settings import load
    spec=json.loads((project/'storyboard.json').read_text(encoding='utf-8'));out=spec.get('settings',load())['output']
    env=os.environ.copy();env['BOARD_PROJECT']=str(project);env['PYTHONUTF8']='1'
    python=ROOT/'apps/animation/.venv/Scripts/python.exe'
    subprocess.run([str(python),'-m','manim','-qm','--fps',str(out['fps']),'--media_dir',str(project/'board'),
        str(ROOT/'scripts/whiteboard_scene.py'),'NarratedBoard'],env=env,check=True)
    board=next((project/'board/videos/whiteboard_scene').glob('*/NarratedBoard.mp4'))
    spec=json.loads((project/'storyboard.json').read_text(encoding='utf-8'))
    ffmpeg=str(ROOT/'tools/ffmpeg.exe')
    args=[ffmpeg,'-v','error','-y']
    for scene in spec['scenes']:args+=['-i',str(project/'audio'/(scene['id']+'.wav'))]
    chain=''.join(f'[{i}:a]' for i in range(len(spec['scenes'])))+f'concat=n={len(spec["scenes"])}:v=0:a=1[a]'
    subprocess.run(args+['-filter_complex',chain,'-map','[a]',str(project/'narration.wav')],check=True)
    subprocess.run([ffmpeg,'-v','error','-y','-i',str(board),'-i',str(project/'narration.wav'),'-vf',
        f"scale={out['width']}:{out['height']}:force_original_aspect_ratio=decrease,pad={out['width']}:{out['height']}:(ow-iw)/2:(oh-ih)/2,subtitles=subtitles.srt:force_style='FontName=Microsoft YaHei,FontSize={out['subtitle_size']},Outline=2,MarginV=28'",
        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart','video.mp4'],cwd=project,check=True)

if __name__=='__main__':render(sys.argv[1])
