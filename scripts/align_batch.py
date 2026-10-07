import argparse
import json
import wave
import re
from pathlib import Path
import torch
from qwen_asr import Qwen3ForcedAligner
from voice_cache import file_sha, fingerprint, model_revision

ROOT = Path(__file__).resolve().parents[1]


def stamp(t):
    ms = round(t * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    project = args.project.resolve()
    spec = json.loads((project / 'storyboard.json').read_text(encoding='utf-8'))
    from creation_settings import load
    model_dir=spec.get('settings',load())['models']['align_dir']
    revision=model_revision(model_dir)
    model=None
    subtitles, timeline = [], []
    offset = 0.0
    for scene in spec['scenes']:
        wav = project / 'audio' / (scene['id']+'.wav')
        with wave.open(str(wav)) as f:
            duration = f.getnframes()/f.getframerate()
        alignment_file=project/'audio'/(scene['id']+'.alignment.json')
        cache_file=alignment_file.with_suffix('.cache.json')
        key=fingerprint({'audio':file_sha(wav),'text':scene['narration'],'model':revision,'code':file_sha(Path(__file__))})
        entries=None
        if args.resume and cache_file.is_file() and alignment_file.is_file():
            try:
                cache=json.loads(cache_file.read_text(encoding='utf-8'))
                if cache.get('input_sha256')==key and cache.get('alignment_sha256')==file_sha(alignment_file):
                    entries=json.loads(alignment_file.read_text(encoding='utf-8'))
            except (OSError,ValueError):
                pass
        if entries is None:
            if model is None:
                model=Qwen3ForcedAligner.from_pretrained(model_dir,dtype=torch.bfloat16,device_map='cuda:0',attn_implementation='sdpa')
            aligned=model.align(audio=str(wav),text=scene['narration'],language='Chinese')[0]
            entries=[{'text':item.text,'start':float(item.start_time),'end':float(item.end_time)} for item in aligned]
        if not entries:
            raise RuntimeError(f'No alignment: {scene["id"]}')
        alignment_file.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
        cache_file.write_text(json.dumps({'input_sha256':key,'alignment_sha256':file_sha(alignment_file)}),encoding='utf-8')
        # Prefer punctuation boundaries in the supplied script; timing stays model-derived.
        clean = lambda value: ''.join(c for c in value if c.isalnum()).lower()
        clauses = [s for s in re.split(r'[，。！？；、,.!?;]+', scene['narration']) if s]
        boundaries, position = {}, 0
        for clause in clauses:
            position += len(clean(clause))
            boundaries[position] = clause
        matched = clean(''.join(x['text'] for x in entries)) == clean(scene['narration'])
        group = []
        position = 0
        for i, item in enumerate(entries):
            group.append(item)
            position += len(clean(item['text']))
            length = len(''.join(x['text'] for x in group))
            if (matched and position in boundaries and length >= 5) or length >= 18 or i == len(entries)-1:
                start = max(0, min(group[0]['start'], duration))
                end = max(start, min(group[-1]['end'], duration))
                if end <= start:
                    raise RuntimeError(f'Nonpositive subtitle interval: {scene["id"]}')
                text = ''.join(x['text'] for x in group)
                subtitles.append(f'{len(subtitles)+1}\n{stamp(offset+start)} --> {stamp(offset+end)}\n{text}\n')
                group = []
        timeline.append({'id': scene['id'], 'start': offset, 'duration': duration})
        offset += duration
    (project / 'subtitles.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    (project / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Aligned {len(timeline)} scenes, {offset:.2f} seconds', flush=True)


if __name__ == '__main__':
    main()
