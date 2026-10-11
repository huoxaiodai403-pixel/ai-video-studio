"""Create original deterministic demo soundbeds. No models or third-party music.

Only writes new files; these are synthesized textures, not recorded ambience.
python make_soundbeds.py --out NEW_ASSETS_DIRECTORY
"""
import argparse
from array import array
import math
from pathlib import Path
import random
import wave


def samples(kind, seconds=60, rate=16000):
    randomizer = random.Random(810 if kind == 'garden' else 930)
    notes = [261.63, 329.63, 392., 523.25, 440., 392., 329.63, 293.66]
    filtered = 0.0
    for index in range(int(seconds * rate)):
        t = index / rate
        noise = randomizer.uniform(-1, 1)
        filtered = filtered * .987 + noise * .013
        if kind == 'garden':
            chirp = t % 5.7
            bird = (math.sin(2*math.pi*(1650*chirp+1000*chirp*chirp))*math.sin(math.pi*chirp/.18)**2*.13
                    if chirp < .18 else 0)
            value = filtered*.42 + noise*.011 + bird
        else:
            step = 1.8 if kind in ('paper','mechanism') else 3.1
            age = t % step
            note = notes[int(t / step) % len(notes)]
            value = (math.sin(2*math.pi*note*age) + .23*math.sin(2*math.pi*note*2.003*age))*.14*math.exp(-age*2.3)
            value += math.sin(2*math.pi*130.815*t)*.015
            if kind == 'comic': value += filtered*.15 + noise*.003
        fade = min(1, t/.2, (seconds-t)/.4)
        yield int(max(-.8,min(.8,value*fade))*32767)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    for kind in ('paper','garden','comic','story','study','mechanism'):
        destination=args.out/(kind+'.wav')
        with destination.open('xb') as raw, wave.open(raw,'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
            pcm=array('h',samples(kind))
            import sys
            if sys.byteorder!='little': pcm.byteswap()
            audio.writeframes(pcm.tobytes())
        print(destination)


if __name__=='__main__': main()
