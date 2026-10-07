"""Offline speech recognition with aligned subtitles for an existing audio file."""
import argparse
import dataclasses
import json
from pathlib import Path
import torch
from qwen_asr import Qwen3ASRModel

ROOT = Path(__file__).resolve().parents[1]

def stamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--settings',type=Path)
    args = parser.parse_args()
    output = args.output or args.audio.with_suffix('.transcription.json')
    options = dict(dtype=torch.bfloat16, device_map='cuda:0', attn_implementation='sdpa')
    from creation_settings import load
    models=(json.loads(args.settings.read_text(encoding='utf-8')) if args.settings else load())['models']
    model = Qwen3ASRModel.from_pretrained(models['asr_dir'],
        forced_aligner=models['align_dir'],
        forced_aligner_kwargs=options, max_inference_batch_size=1, max_new_tokens=1024, **options)
    result = model.transcribe(audio=str(args.audio.resolve()), language='Chinese', return_time_stamps=True)[0]
    payload = dataclasses.asdict(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    groups, group = [], []
    for item in result.time_stamps:
        group.append(item)
        if len(''.join(x.text for x in group)) >= 16:
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    output.with_suffix('.srt').write_text('\n'.join(
        f'{i}\n{stamp(g[0].start_time)} --> {stamp(g[-1].end_time)}\n'+''.join(x.text for x in g)+'\n'
        for i,g in enumerate(groups,1)), encoding='utf-8')
    print(result.text, flush=True)
    print(f'Saved {output}', flush=True)

if __name__ == '__main__':
    main()
