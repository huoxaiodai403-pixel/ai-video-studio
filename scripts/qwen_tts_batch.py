"""Isolated official Qwen3-TTS CustomVoice worker; no downloads during synthesis."""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import time
import wave

from filelock import FileLock
from creation_settings import load, voice_for, validate_voice, process_voice
from voice_cache import file_sha, fingerprint, read_cached

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT/'apps/qwen-tts'
MODELS = {'qwen3-custom': 'Qwen3-TTS-12Hz-1.7B-CustomVoice',
          'qwen3-design': 'Qwen3-TTS-12Hz-1.7B-VoiceDesign', 'qwen3-clone': 'Qwen3-TTS-12Hz-1.7B-Base'}
SPEAKERS = ('Vivian', 'Serena', 'Uncle_Fu', 'Dylan', 'Eric', 'Ryan', 'Aiden', 'Ono_Anna', 'Sohee')
LANGUAGES = ('Auto', 'Chinese', 'English', 'Japanese', 'Korean', 'German', 'French', 'Russian', 'Portuguese', 'Spanish', 'Italian')


def readiness(engine='qwen3-custom'):
    if engine not in MODELS:
        raise ValueError('未知 Qwen 配音路线')
    model = ROOT/'models'/MODELS[engine]
    checks = []
    for name, path in [('Qwen 独立 Python', APP/'.venv/Scripts/python.exe'),
                       ('Qwen 官方模型', model/'model.safetensors'),
                       ('Qwen 语音解码器', model/'speech_tokenizer/model.safetensors'),
                       ('Qwen 模型配置', model/'config.json')]:
        checks.append({'name': name, 'ready': path.is_file(), 'message': '已安装' if path.is_file() else '尚未安装完成'})
    # A successful environment check writes this only after importing the official package.
    ready_file = APP/'installation.json'
    installed = json.loads(ready_file.read_text(encoding='utf-8')) if ready_file.is_file() else {}
    checks.append({'name': 'Qwen 运行依赖', 'ready': installed.get('import_verified') is True,
                   'message': '已验证导入' if installed.get('import_verified') else '尚未验证运行依赖'})
    return {'ready': all(row['ready'] for row in checks), 'checks': checks,
            'speakers': list(SPEAKERS), 'languages': list(LANGUAGES), 'engine': engine, 'model': 'Qwen/'+MODELS[engine]}


def model_revision(model):
    return {'id': 'Qwen/'+model.name, 'files': [
        [path.relative_to(model).as_posix(), path.stat().st_size, path.stat().st_mtime_ns]
        for path in sorted(model.rglob('*'))
        if path.is_file() and '.cache' not in path.parts and path.suffix in ('.json', '.safetensors', '.txt')]}


def selected_scenes(spec, selected=None):
    scenes = spec.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 96:
        raise ValueError('配音项目需要 1–96 个镜头')
    seen, result = set(), []
    for scene in scenes:
        identity = scene.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', identity) or identity in seen:
            raise ValueError('配音镜头 ID 无效或重复')
        seen.add(identity)
        voice = validate_voice(voice_for(spec, scene))
        engine = voice.get('engine', 'index-tts')
        if engine not in MODELS:
            if selected and identity in selected:
                raise ValueError('指定镜头未使用 Qwen 引擎：' + identity)
            continue
        if selected is not None and identity not in selected:
            continue
        narration = scene.get('narration')
        if not isinstance(narration, str) or not 1 <= len(narration.strip()) <= 4000:
            raise ValueError('Qwen 单段文字需要 1–4000 字')
        if voice.get('qwen_speaker') not in SPEAKERS or voice.get('qwen_language') not in LANGUAGES:
            raise ValueError('请选择 Qwen 官方音色与支持的语言')
        instruct = voice.get('qwen_instruct', '')
        if not isinstance(instruct, str) or len(instruct) > 1000:
            raise ValueError('Qwen 语气指令应不超过 1000 字')
        if engine == 'qwen3-design' and not instruct.strip():
            raise ValueError('声音设计需要描述目标声线与表达方式')
        ref_text = voice.get('qwen_ref_text', '')
        if not isinstance(ref_text, str) or len(ref_text) > 4000:
            raise ValueError('克隆参考音频原文应不超过 4000 字')
        seed = voice.get('qwen_seed', 42)
        if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2147483647:
            raise ValueError('Qwen seed 应为 0–2147483647 的整数')
        result.append((scene, voice))
    if selected and selected - seen:
        raise ValueError('指定的镜头不存在')
    if any(voice['engine'] == 'qwen3-design' for _, voice in result) and len(scenes) != 1:
        raise ValueError('声音设计仅用于单段试听；请先保存为固定克隆音色，再用于多段视频')
    return sorted(result, key=lambda row: row[1]['engine'])


def synthesize(project, spec, resume=False, scene_ids=None):
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed
    from qwen_tts import Qwen3TTSModel

    rows = selected_scenes(spec, scene_ids)
    if not rows:
        print('No Qwen scenes selected.', flush=True)
        return
    if not torch.cuda.is_available():
        raise RuntimeError('Qwen 本地配音需要可用的 CUDA 显卡')
    audio_dir = project/'audio'
    audio_dir.mkdir(exist_ok=True)
    model = None
    current_engine = None
    revisions = {}
    clone_prompts = {}
    for scene, voice in rows:
        engine = voice['engine']
        model_dir = ROOT/'models'/MODELS[engine]
        if not (model_dir/'model.safetensors').is_file() or not (model_dir/'speech_tokenizer/model.safetensors').is_file():
            raise ValueError(MODELS[engine] + ' 官方模型尚未完整安装；请先完成下载')
        if engine not in revisions:
            revisions[engine] = model_revision(model_dir)
        reference_hash = file_sha(voice['reference']) if engine == 'qwen3-clone' else None
        audio = audio_dir/(scene['id']+'.wav')
        raw_audio = audio.with_name(audio.stem+'.raw.wav')
        key = fingerprint({'text': scene['narration'], 'voice': voice, 'model': revisions[engine], 'reference_sha256': reference_hash,
                           'code': [file_sha(Path(__file__)), file_sha(ROOT/'scripts/creation_settings.py')]})
        if resume and read_cached(audio.with_suffix('.json'), audio, key) and raw_audio.is_file():
            print('Reused verified Qwen audio: ' + str(audio), flush=True)
            continue
        started = time.monotonic()
        if current_engine != engine:
            if model is not None:
                del model
                clone_prompts.clear()
                import gc
                gc.collect()
                torch.cuda.empty_cache()
            print('Loading official ' + MODELS[engine] + ', bfloat16 + SDPA', flush=True)
            model = Qwen3TTSModel.from_pretrained(str(model_dir), device_map='cuda:0', dtype=torch.bfloat16,
                                                attn_implementation='sdpa', local_files_only=True)
            current_engine = engine
            if engine == 'qwen3-custom':
                supported = {item.lower() for item in model.get_supported_speakers()}
                if any(row_voice['qwen_speaker'].lower() not in supported for _, row_voice in rows if row_voice['engine'] == engine):
                    raise ValueError('当前模型不支持所选音色')
        set_seed(voice['qwen_seed'])
        torch.cuda.reset_peak_memory_stats()
        inference_started = time.monotonic()
        print(f'Qwen synthesis: {scene["id"]} / {engine} / {voice["qwen_speaker"]}', flush=True)
        with torch.inference_mode():
            kwargs = {'text': scene['narration'], 'language': voice['qwen_language'],
                      'non_streaming_mode': True, 'max_new_tokens': max(4096, min(20000, len(scene['narration']) * 12))}
            if engine == 'qwen3-custom':
                waves, rate = model.generate_custom_voice(**kwargs, speaker=voice['qwen_speaker'], instruct=voice['qwen_instruct'])
            elif engine == 'qwen3-design':
                waves, rate = model.generate_voice_design(**kwargs, instruct=voice['qwen_instruct'])
            else:
                prompt_key = fingerprint({'reference': reference_hash, 'text': voice.get('qwen_ref_text', '')})
                if prompt_key not in clone_prompts:
                    clone_prompts[prompt_key] = model.create_voice_clone_prompt(ref_audio=voice['reference'],
                        ref_text=voice.get('qwen_ref_text') or None, x_vector_only_mode=not bool(voice.get('qwen_ref_text', '').strip()))
                waves, rate = model.generate_voice_clone(**kwargs, voice_clone_prompt=clone_prompts[prompt_key])
        generated = np.asarray(waves[0], dtype=np.float32)
        if generated.ndim != 1 or not generated.size or not np.isfinite(generated).all():
            raise RuntimeError('Qwen 返回了空白或无效音频')
        peak = float(np.max(np.abs(generated)))
        if peak < .001:
            raise RuntimeError('Qwen 返回的音频接近静音')
        # Preserve model output as floating point; no unrequested timbre transformation.
        sf.write(str(raw_audio), generated, rate, subtype='FLOAT')
        gain = min(1.0, .98 / peak) if peak else 1.0
        temporary = audio.with_name(audio.stem+'.pending.wav')
        sf.write(str(temporary), generated * gain, rate, subtype='PCM_16')
        os.replace(temporary, audio)
        inference_seconds = time.monotonic() - inference_started
        processing = process_voice(audio, voice)
        with wave.open(str(audio)) as wav:
            duration = wav.getnframes()/wav.getframerate()
        metadata = {'text': scene['narration'], 'speaker': scene.get('speaker', '旁白'), 'engine': engine,
                    'voice': voice, 'model': 'Qwen/'+MODELS[engine], 'input_sha256': key, 'audio_sha256': file_sha(audio),
                    'raw_sha256': file_sha(raw_audio), 'duration_seconds': duration, 'sample_rate': rate,
                    'seconds_elapsed': time.monotonic()-started, 'inference_seconds': inference_seconds,
                    'real_time_factor': inference_seconds/duration, 'seed': voice['qwen_seed'],
                    'native_speaker': voice['qwen_speaker'] if engine == 'qwen3-custom' else None,
                    'instruction': voice['qwen_instruct'] if engine != 'qwen3-clone' else None,
                    'x_vector_only_mode': not bool(voice.get('qwen_ref_text', '').strip()) if engine == 'qwen3-clone' else None,
                    'language': voice['qwen_language'], 'post_processing': processing, 'peak_normalization_gain': gain,
                    'raw_peak': peak, 'peak_cuda_memory_gb': torch.cuda.max_memory_allocated()/1024**3,
                    'dtype': 'bfloat16', 'attention': 'sdpa', 'torch_version': torch.__version__,
                    'voice_reference': voice['reference'] if engine == 'qwen3-clone' else None, 'reference_sha256': reference_hash,
                    'ignored_index_parameters': ['emotion', 'intensity', 'duration_factor', 'prosody_reference', 'prosody_strength']}
        audio.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Completed Qwen: {audio} ({duration:.2f}s audio, {inference_seconds:.2f}s inference)', flush=True)
    if model is not None:
        del model
        torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--scene-ids', help='Comma-separated existing Qwen scene IDs')
    parser.add_argument('--gpu-lock-held', action='store_true', help='Only for a parent pipeline already holding gpu.lock')
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_relative_to((ROOT/'projects').resolve()) or not project.is_dir():
        raise ValueError('配音项目必须位于工作台 projects 目录')
    spec = json.loads((project/'storyboard.json').read_text(encoding='utf-8-sig'))
    selected = set(args.scene_ids.split(',')) if args.scene_ids else None
    selected_scenes(spec, selected)
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HOME=str(ROOT/'cache/huggingface'))
    context = nullcontext() if args.gpu_lock_held else FileLock(str(ROOT/'manifests/gpu.lock'), timeout=0)
    with context:
        synthesize(project, spec, resume=args.resume, scene_ids=selected)


if __name__ == '__main__':
    main()
