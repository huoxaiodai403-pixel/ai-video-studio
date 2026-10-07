"""Measure real FFmpeg output: tone controls must not accidentally change tempo."""
import array
import math
import testing_support as tempfile
import unittest
import wave
from pathlib import Path

import creation_settings as c


class VoiceProcessingTests(unittest.TestCase):
    def test_neutral_formant_shift_keeps_fundamental_and_duration(self):
        for semitones, formant, speed in [(0, 1.04, 1), (-1, 1.04, 1.1)]:
            with self.subTest(semitones=semitones, formant=formant, speed=speed), tempfile.TemporaryDirectory() as folder:
                audio=Path(folder)/'tone.wav';rate=24000;seconds=3
                samples=array.array('h',(int(5000*math.sin(2*math.pi*220*i/rate)) for i in range(rate*seconds)))
                with wave.open(str(audio),'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(samples.tobytes())
                c.process_voice(audio,{'speed':speed,'pitch_semitones':semitones,'formant_shift':formant})
                with wave.open(str(audio)) as result:
                    duration=result.getnframes()/result.getframerate()
                    decoded=array.array('h',result.readframes(result.getnframes()))
                mid=decoded[rate//2:-rate//2]
                rises=sum(a<=0<b for a,b in zip(mid,mid[1:]))
                fundamental=rises/(len(mid)/rate)
                self.assertAlmostEqual(duration,seconds/speed,delta=.03)
                self.assertAlmostEqual(fundamental,220*2**(semitones/12),delta=2)
                self.assertGreater(max(map(abs,mid)),1000)

    def test_new_voice_controls_are_bounded(self):
        for field,value in [('duration_factor',0),('duration_factor',float('nan')),
                            ('pitch_semitones',4),('formant_shift',1.5)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                c.validate_voice({**c.load()['voice'],field:value})


if __name__=='__main__':unittest.main()
