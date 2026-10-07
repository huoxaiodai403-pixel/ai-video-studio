"""Parameter propagation and input-boundary regression checks; no model inference."""
import copy
import json
import testing_support as tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import creation_settings as c
import creation_api as api
import comfy_client
import wan_client
import pipeline

class CreationTests(unittest.TestCase):
    def test_graphs_receive_dimensions_models_and_seed(self):
        models=copy.deepcopy(c.DEFAULTS['models']);models.update(image_unet='qwen-test.gguf',video_unet='wan-test.safetensors')
        g=comfy_client.workflow('test',width=576,height=1024,seed=317,steps=9,models=models,cfg=3.5)
        self.assertEqual((g['6']['inputs']['width'],g['6']['inputs']['height']),(576,1024));self.assertEqual(g['1']['inputs']['unet_name'],'qwen-test.gguf');self.assertEqual(g['8']['inputs']['cfg'],3.5)
        g=wan_client.workflow('test',frames=33,seed=91,width=288,height=512,models=models)
        self.assertEqual(g['6']['inputs']['length'],33);self.assertEqual(g['6']['inputs']['height'],512);self.assertEqual(g['8']['inputs']['seed'],91);self.assertEqual(g['1']['inputs']['unet_name'],'wan-test.safetensors')

    def test_invalid_settings_rejected(self):
        for invalid in [{'motion':{'frames':32}},{'image':{'width':777}},{'output':{'height':641}},{'voice':{'speed':0}},{'models':{'image_unet':'../../secrets.gguf'}},{'story':{'local_url':'https://external.example/v1'}}]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):c.validate(invalid)

    def test_novel_split_preserves_source(self):
        text='林默推开窗。\n晨光照进房间！她看到了信封？末尾没有标点'
        d=api.adapt({'text':text,'count':4,'mode':'split'})
        self.assertEqual(''.join(s['narration'] for s in d['scenes']),text);self.assertLessEqual(len(d['scenes']),4)

    def test_character_voice_and_snapshot(self):
        s=api.snapshot({'settings':{'voice':{'intensity':.35}},'scenes':[{'speaker':'角色'}],'characters':{'角色':{'emotion':'高兴','speed':1.2}}})
        voice=c.voice_for(s,s['scenes'][0]);self.assertEqual(voice['speed'],1.2);self.assertEqual(c.emotion_vector(voice)[0],.35)
        with patch.object(c,'load',return_value={'voice':{'speed':2}}):self.assertEqual(c.voice_for(s,s['scenes'][0])['speed'],1.2)
        with self.assertRaises(ValueError):api.snapshot({'scenes':[{'speaker':'未配置角色'}]})

    def test_save_reload_and_validation_atomicity(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(c,'CONFIG',Path(folder)/'creation.json'):
            c.save({'output':{'width':720,'height':1280},'voice':{'speed':1.15}})
            self.assertEqual(c.load()['output']['height'],1280);before=c.CONFIG.read_bytes()
            with self.assertRaises(ValueError):c.save({'motion':{'frames':2}})
            self.assertEqual(c.CONFIG.read_bytes(),before)

    def test_render_commands_use_visible_parameters(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'audio').mkdir()
            with wave.open(str(p/'audio/one.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*1600)
            spec={'scenes':[{'id':'one'}],'settings':c.merge(c.DEFAULTS,{'output':{'width':360,'height':640,'fps':24,'subtitle_size':18}})}
            calls=[]
            with patch.object(pipeline,'run',side_effect=lambda command,*args:calls.append(list(map(str,command)))):pipeline.render(p,spec)
            self.assertIn('s=360x640:fps=24',calls[0][calls[0].index('-vf')+1]);self.assertIn('FontSize=18',calls[-1][calls[-1].index('-vf')+1])

if __name__=='__main__':unittest.main()
