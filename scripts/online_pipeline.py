"""Online stages preserve the same local artifact contract as local inference."""
import json
import wave
from pathlib import Path
import providers

def tts(project,spec):
    from creation_settings import voice_for
    folder=project/'audio';folder.mkdir(exist_ok=True)
    for scene in spec['scenes']:
        voice=voice_for(spec,scene)
        providers.tts(scene['narration'],folder/(scene['id']+'.wav'),voice['online_voice'],voice['speed'])

def align(project,spec):
    cues=[];timeline=[];offset=0
    for scene in spec['scenes']:
        wav=project/'audio'/(scene['id']+'.wav')
        with wave.open(str(wav)) as f:duration=f.getnframes()/f.getframerate()
        segments=providers.asr(wav,wav.with_suffix('.transcription.json'))
        for item in segments:
            start=max(0,min(float(item['start']),duration));end=max(start,min(float(item['end']),duration))
            if end>start:
                cues.append(f'{len(cues)+1}\n{providers.stamp(offset+start)} --> {providers.stamp(offset+end)}\n{item["text"].strip()}\n')
        timeline.append({'id':scene['id'],'start':offset,'duration':duration});offset+=duration
    (project/'subtitles.srt').write_text('\n'.join(cues),encoding='utf-8')
    (project/'timeline.json').write_text(json.dumps(timeline,indent=2),encoding='utf-8')
