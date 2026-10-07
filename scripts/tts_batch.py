import argparse
import json
import os
import sys
import time
import hashlib
import shutil
import wave
import subprocess
import gc
from pathlib import Path
from creation_settings import load,voice_for,emotion_vector,process_voice,validate_voice
from voice_cache import file_sha, fingerprint, model_revision, read_cached

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/index-tts'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    project = args.project.resolve()
    spec = json.loads((project / 'storyboard.json').read_text(encoding='utf-8'))
    models=spec.get('settings',load())['models'];model_dir=Path(models['tts_dir'])
    tts = None
    uses_index = any(voice_for(spec, scene).get('engine', 'index-tts') == 'index-tts' for scene in spec['scenes'])
    revision = model_revision(model_dir) if uses_index else None
    audio_dir = project / 'audio'
    audio_dir.mkdir(exist_ok=True)
    for scene in spec['scenes']:
        audio = audio_dir / (scene['id'] + '.wav')
        start = time.monotonic()
        voice=validate_voice(voice_for(spec,scene));reference=voice['reference']
        if voice['engine'].startswith('qwen3-'):continue
        key=fingerprint({'text':scene['narration'],'voice':voice,'emotion':scene.get('emotion'),
            'reference_sha256':file_sha(reference),'model':revision,
            'prosody_sha256':file_sha(voice['prosody_reference']) if voice['prosody_reference'] else None,
            'code':[file_sha(Path(__file__)),file_sha(ROOT/'scripts/creation_settings.py')]})
        if args.resume and read_cached(audio.with_suffix('.json'),audio,key):
            print(f'Reused verified audio: {audio}',flush=True)
            continue
        if tts is None:
            os.chdir(APP)
            sys.path.insert(0, str(APP))
            from indextts.infer_v2_5 import IndexTTS2
            tts = IndexTTS2(cfg_path=str(model_dir/'config.yaml'), model_dir=str(model_dir), use_bf16=True, use_cuda_kernel=False, use_deepspeed=False)
        delivery=({'emo_audio_prompt':voice['prosody_reference'],'emo_alpha':voice['prosody_strength']}
                  if voice['prosody_reference'] else {'emo_vector':scene.get('emotion',emotion_vector(voice))})
        tts.infer(spk_audio_prompt=reference, text=scene['narration'], lang='ZH', output_path=str(audio),
                  **delivery, duration_factor=voice['duration_factor'],
                  use_random=False, verbose=False)
        shutil.copy2(audio,audio.with_name(audio.stem+'.raw.wav'))
        processing=process_voice(audio,voice)
        with wave.open(str(audio)) as wav:
            duration=wav.getnframes()/wav.getframerate()
        (audio.with_suffix('.json')).write_text(json.dumps({'text': scene['narration'],
            'speaker':scene.get('speaker','旁白'),'input_sha256':key,'seconds_elapsed':time.monotonic()-start,
            'duration_seconds':duration,'voice_reference':reference,'voice':voice,
            'reference_sha256':hashlib.sha256(Path(reference).read_bytes()).hexdigest(),
            'prosody_reference_sha256':file_sha(voice['prosody_reference']) if voice['prosody_reference'] else None,
            'audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'post_processing':processing},
            ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Completed: {audio}', flush=True)
    qwen_ids=[scene['id'] for scene in spec['scenes'] if validate_voice(voice_for(spec,scene))['engine'].startswith('qwen3-')]
    if qwen_ids:
        if tts is not None:
            del tts
            gc.collect()
            import torch
            torch.cuda.empty_cache()
        command=[str(ROOT/'apps/qwen-tts/.venv/Scripts/python.exe'),str(ROOT/'scripts/qwen_tts_batch.py'),str(project),
                 '--scene-ids',','.join(qwen_ids),'--gpu-lock-held']
        if args.resume:command.append('--resume')
        subprocess.run(command,check=True,cwd=str(ROOT))


if __name__ == '__main__':
    main()
