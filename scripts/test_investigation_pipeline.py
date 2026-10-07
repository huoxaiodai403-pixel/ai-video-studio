import json
from array import array
import math
import os
import testing_support as tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import investigation_pipeline as pipeline


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.project=Path(self.tmp.name)

    def spec(self,count=3):
        return {'title':'测试', 'scenes':[{'id':f's{i}', 'kind':'diagram','narration':'核对原始出处。',
                'heading':'出处','points':['来源'],'source_ids':[]} for i in range(count)]}

    def prepare(self,spec,duration):
        pipeline.write(self.project/'timeline.json',[{'id':s['id'],'duration':duration} for s in spec['scenes']])
        (self.project/'subtitles.srt').write_text('1\n00:00:00,100 --> 00:00:00,500\n核对出处\n',encoding='utf-8')

    def test_cumulative_frame_rounding_does_not_drift_in_long_film(self):
        spec=self.spec(96);self.prepare(spec,6.337)
        props,_=pipeline.build_props(self.project,spec)
        self.assertEqual(props['durationInFrames'],round(96*6.337*30))
        self.assertEqual(sum(s['durationInFrames'] for s in props['scenes']),props['durationInFrames'])
        for left,right in zip(props['scenes'],props['scenes'][1:]):
            self.assertEqual(left['startFrame']+left['durationInFrames'],right['startFrame'])

    def test_actual_audio_rejects_insufficient_clip(self):
        spec=self.spec(1);spec['scenes'][0].update(kind='video',media_id='m',media_start=4)
        (self.project/'clip.mp4').write_bytes(b'test fixture')
        spec['media']=[{'id':'m','path':'clip.mp4'}];self.prepare(spec,8)
        with patch.object(pipeline,'probe',return_value={'format':{'duration':10}}):
            with self.assertRaisesRegex(ValueError,'不能循环'):
                pipeline.build_props(self.project,spec)

    def test_quote_requires_actual_source_text(self):
        spec=self.spec(1);spec['scenes'][0].update(kind='evidence',text='伪造的原话',source_ids=['source'])
        spec['sources']=[{'id':'source','title':'来源','content':'实际的原文'}];self.prepare(spec,8)
        with self.assertRaisesRegex(ValueError,'逐字'):
            pipeline.build_props(self.project,spec)

    def test_reused_video_is_counted_once(self):
        spec=self.spec(2)
        for s in spec['scenes']:s.update(kind='video',media_id='m',media_start=2)
        (self.project/'clip.mp4').write_bytes(b'test fixture')
        spec['media']=[{'id':'m','path':'clip.mp4'}];self.prepare(spec,8)
        with patch.object(pipeline,'probe',return_value={'format':{'duration':20}}):
            pipeline.build_props(self.project,spec)
        coverage=pipeline.read(self.project/'coverage.json')
        self.assertEqual(coverage['video_seconds'],16)
        self.assertEqual(coverage['unique_video_seconds'],8)
        self.assertEqual(coverage['reused_video_seconds'],8)

    def test_project_escape_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'工程目录'):
            pipeline.contained(self.project,'../outside.wav')

    @unittest.skipUnless(pipeline.FFMPEG.is_file(), 'bundled FFmpeg is required')
    def test_mixed_tts_sample_rates_preserve_duration_before_concat(self):
        (self.project/'audio').mkdir()
        scenes=[]
        for rate in (22050,24000):
            sid=f'rate{rate}';scenes.append({'id':sid})
            samples=array('h',(round(1000*math.sin(2*math.pi*220*i/rate)) for i in range(rate)))
            with wave.open(str(self.project/'audio'/f'{sid}.wav'),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
                wav.writeframes(samples.tobytes())
        output=pipeline.assemble_narration(self.project,scenes)
        with wave.open(str(output)) as wav:
            self.assertEqual((wav.getframerate(),wav.getnchannels(),wav.getsampwidth()),(48000,2,2))
            self.assertAlmostEqual(wav.getnframes()/wav.getframerate(),2.0,delta=1/48000)
        for index in range(2):
            with wave.open(str(self.project/'render-public'/f'narration-{index:03}.wav')) as wav:
                self.assertAlmostEqual(wav.getnframes()/wav.getframerate(),1.0,delta=1/48000)

    def test_text_evidence_retains_explicit_fiction_label(self):
        spec=self.spec(1);spec['scenes'][0].update(kind='evidence',text='教学示例',
            badge='虚构教学案例',source_ids=['source'])
        spec['sources']=[{'id':'source','title':'自拟示例','content':'以下内容是教学示例。'}]
        self.prepare(spec,8)
        props,_=pipeline.build_props(self.project,spec)
        self.assertIn('虚构',props['scenes'][0]['badge'])

    def test_long_title_publish_copy_passes_actual_upstream_checker(self):
        spec=self.spec(1);spec['title']='这是一条超过十六字的资料核验方法演示标题'
        props={'durationInFrames':30,'scenes':[{'startFrame':0}]}
        (self.project/'video.mp4').write_bytes(b'non-media fixture; decode is mocked in this copy-only test')
        actual_run=pipeline.run
        def run_only_copy_checker(command,log,cwd=None):
            if 'check-publish-copy.py' in str(command[1]):
                return actual_run(command,log,cwd)
        info={'format':{'duration':1.0},'streams':[{'codec_type':'video','width':1920,'height':1080,
            'r_frame_rate':'30/1'},{'codec_type':'audio','codec_name':'aac'}]}
        with patch.object(pipeline,'run',side_effect=run_only_copy_checker),patch.object(pipeline,'probe',return_value=info),patch.dict(os.environ,{'PYTHONUTF8':'1'}):
            pipeline.deliver(self.project,spec,props)
        self.assertIn('COPY_OK',(self.project/'publish-copy.check.log').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
