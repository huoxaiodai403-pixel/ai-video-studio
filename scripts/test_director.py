import json
import unittest
from unittest.mock import patch
import director
import creation_api

class DirectorTests(unittest.TestCase):
    def test_sources_and_templates(self):
        d=director.catalog()
        self.assertEqual([len(d[k]) for k in ('sources','cameras','recipes','templates')],[4,22,12,25])
        self.assertEqual(len({t['id'] for t in d['templates']}),25)
        for t in d['templates']:
            for k in ('structure','guidance','pitfalls'):self.assertIsInstance(t[k],list)
            self.assertTrue(t['title'])
        self.assertTrue(director.choose('templates','timeline-shot-script')['copyPrompt'])

    def test_camera_preserves_user_constraints(self):
        result=director.camera({'camera':'rack','action':'人物站立不动','start':'前景信封清晰','end':'后景门口清晰','invariants':'蓝色外套'})
        for text in ('前景信封清晰','后景门口清晰','蓝色外套','焦点从前景目标'):self.assertIn(text,result['prompt'])
        with self.assertRaises(ValueError):director.camera({'camera':'bad'})
        with self.assertRaises(ValueError):director.camera({'camera':'rack','subject':'a'*1201})

    def test_image_brief_requires_target_and_references(self):
        with self.assertRaises(ValueError):director.brief({'kind':'recipes','id':'cleanup'})
        result=director.brief({'kind':'recipes','id':'cleanup','subject':'移除左侧游客','keep':'主角与远处塔楼'})
        self.assertIn('主角与远处塔楼',result['prompt'])
        self.assertIn('必须向支持参考图编辑的模型提交原图',result['prompt'])

    def test_method_reaches_model_without_changing_story_schema(self):
        response={'choices':[{'message':{'content':json.dumps({'scenes':[{'narration':'她看到信。','subject':'蓝衣女子看信。','style':'国漫','motion_prompt':'固定'}]})}}]}
        with patch('local_story.complete',return_value=response) as call:
            result=creation_api.adapt({'mode':'local','text':'她看到信。','count':1,'director_method':'retro-found-footage'})
        system=call.call_args.args[1]['messages'][0]['content']
        self.assertIn(director.choose('templates','retro-found-footage')['title'],system)
        self.assertEqual(result['director_method'],'retro-found-footage')
        self.assertEqual(result['scenes'][0]['narration'],'她看到信。')
        with patch('local_story.complete') as call:
            with self.assertRaises(ValueError):creation_api.adapt({'mode':'local','text':'原文','director_method':'bad'})
            call.assert_not_called()

if __name__=='__main__':unittest.main()
