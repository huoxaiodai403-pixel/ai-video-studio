"""CPU-only boundary checks for registered voices and immutable job snapshots."""
import copy
import hashlib
import json
import testing_support as tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import creation_settings as settings
import voice_library as library
import voice_api
import whiteboard_api


class VoiceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.example = self.root / 'apps/index-tts/examples/voice_01.wav'
        self.imported = self.root / 'assets/voices/参考.wav'
        self.outside = self.root / 'outside.wav'
        for path in (self.example, self.imported, self.outside):
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24000)
                audio.writeframes(b'\0\0' * 24)
        self.config = copy.deepcopy(settings.DEFAULTS)
        self.config['voice']['reference'] = str(self.example)
        for patcher in (patch.object(library, 'ROOT', self.root),
                        patch.object(library, 'PRESETS', self.root / 'config/voice-presets.json'),
                        patch.object(settings, 'load', side_effect=lambda: copy.deepcopy(self.config))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def make(self, name='讲解', speed=1.0, **changes):
        voice = {**self.config['voice'], 'reference': str(self.imported), 'speed': speed, **changes}
        return library.save({'name': name, 'tags': ['知识讲解'], 'description': '测试预设', 'voice': voice})

    def board(self):
        return {'title': '测试分镜', 'scenes': [
            {'id': 'scene01', 'narration': '先说明一个观点。', 'board_title': '观点', 'board_cards': ['观点'], 'board_layout': 'opening'},
            {'id': 'scene02', 'narration': '再补充另一个观点。', 'board_title': '补充', 'board_cards': ['补充'], 'board_layout': 'summary'}]}

    def designed_job(self, seconds=3):
        job='speech-1234567890'
        project=self.root/'projects/studio'/job
        (project/'audio').mkdir(parents=True,exist_ok=True)
        voice={**self.config['voice'],'engine':'qwen3-design','qwen_instruct':'成年女性，冷静清晰。',
               'speed':1.1,'pitch_semitones':0.5,'formant_shift':1.04,'duration_factor':0.95}
        transcript='先找到原始出处，再核对上下文。'
        spec={'settings':{'voice':voice},'scenes':[{'id':'preview','narration':transcript}]}
        source=project/'audio/preview.wav'
        with wave.open(str(source),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
            stream.writeframes(b'\x10\x00'*round(24000*seconds))
        metadata={'engine':'qwen3-design','voice':voice,'text':transcript,
                  'audio_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        for file,value in [('status.json',{'kind':'speech','backend':'local','status':'done'}),
                           ('storyboard.json',spec),('audio/preview.json',metadata)]:
            (project/file).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return job,project,source,metadata,spec

    def test_from_speech_freezes_exact_audio_and_resets_repeated_effects(self):
        job,project,source,metadata,spec=self.designed_job()
        before=source.read_bytes()
        with patch.object(settings,'process_voice') as process:
            preset=library.from_speech({'job_id':job,'name':'固定角色','tags':['讲解']})
        process.assert_not_called()
        voice=preset['voice']
        self.assertEqual(voice['engine'],'qwen3-clone')
        self.assertEqual(voice['qwen_ref_text'],spec['scenes'][0]['narration'])
        self.assertEqual(Path(voice['reference']).read_bytes(),before)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual((voice['speed'],voice['pitch_semitones'],voice['formant_shift'],voice['duration_factor']),(1,0,1,1))
        self.assertEqual(voice['qwen_instruct'],'')
        self.assertEqual(voice['prosody_reference'],'')
        again=library.from_speech({'job_id':job,'name':'同源另一个角色'})
        self.assertEqual(again['voice']['reference'],voice['reference'])
        self.assertNotEqual(again['id'],preset['id'])
        self.assertEqual(len(list((self.root/'assets/voices').glob('designed-*.wav'))),1)

    def test_from_speech_rejects_stale_engine_text_voice_and_hash(self):
        job,project,source,metadata,spec=self.designed_job()
        mutations=[{'audio_sha256':'0'*64},{'engine':'qwen3-custom'},{'text':'另一段台词'},
                   {'voice':{**metadata['voice'],'qwen_instruct':'不同描述'}}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                (project/'audio/preview.json').write_text(json.dumps({**metadata,**mutation},ensure_ascii=False),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'生成记录不符'):
                    library.from_speech({'job_id':job,'name':'拒绝'})
                self.assertFalse(list((self.root/'assets/voices').glob('designed-*.wav')))

    def test_from_speech_rejects_unfinished_non_design_and_wrong_scene(self):
        job,project,source,metadata,spec=self.designed_job()
        for status in ({'status':'running','kind':'speech','backend':'local'},
                       {'status':'done','kind':'speech','backend':'online'}):
            (project/'status.json').write_text(json.dumps(status),encoding='utf-8')
            with self.assertRaises(ValueError):
                library.from_speech({'job_id':job,'name':'拒绝'})
        (project/'status.json').write_text(json.dumps({'status':'done','kind':'speech','backend':'local'}),encoding='utf-8')
        for changed in ({**spec,'scenes':[{'id':'wrong','narration':'文字'}]},
                        {**spec,'settings':{'voice':{**metadata['voice'],'engine':'qwen3-custom'}}}):
            (project/'storyboard.json').write_text(json.dumps(changed,ensure_ascii=False),encoding='utf-8')
            with self.assertRaises(ValueError):
                library.from_speech({'job_id':job,'name':'拒绝'})

    def test_from_speech_rejects_short_audio_and_invalid_save_before_copy(self):
        job,project,source,metadata,spec=self.designed_job(seconds=1)
        with self.assertRaisesRegex(ValueError,'2至30秒'):
            library.from_speech({'job_id':job,'name':'过短'})
        job,project,source,metadata,spec=self.designed_job()
        for value in ({'job_id':'../escape','name':'拒绝'},{'job_id':job,'name':''},
                      {'job_id':job,'name':'拒绝','tags':'not-list'},
                      {'job_id':job,'name':'拒绝','path':str(self.outside)}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                library.from_speech(value)
        self.assertFalse(list((self.root/'assets/voices').glob('designed-*.wav')))

    def test_from_speech_detects_conflicting_reference_file(self):
        job,project,source,metadata,spec=self.designed_job()
        destination=self.root/'assets/voices'/('designed-'+metadata['audio_sha256'][:24]+'.wav')
        destination.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'参考文件校验失败'):
            library.from_speech({'job_id':job,'name':'拒绝'})
        self.assertEqual(destination.read_bytes(),b'changed')

    def test_from_speech_rejects_audio_link_outside_project(self):
        job,project,source,metadata,spec=self.designed_job()
        audio=source.parent
        external=self.root/'external_audio'
        self.assertTrue(audio.resolve().is_relative_to(self.root.resolve()))
        self.assertTrue(external.resolve().is_relative_to(self.root.resolve()))
        audio.rename(external)
        import os
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(external),str(audio))
        else:
            audio.symlink_to(external,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'越界'):
            library.from_speech({'job_id':job,'name':'拒绝'})

    def test_registry_exposes_stable_ids_and_no_unregistered_sources(self):
        hidden = self.root / 'assets/voices/sources/raw.wav'
        hidden.parent.mkdir(parents=True)
        hidden.write_bytes(self.imported.read_bytes())
        catalog = library.catalog()
        self.assertEqual({Path(row['path']) for row in catalog['references']}, {self.example, self.imported})
        self.assertEqual(catalog['presets'][0]['id'], 'builtin-voice-01')
        self.assertEqual(catalog['presets'][0]['name'], '示例音色 01')
        self.assertEqual([row['id'] for row in catalog['presets']], [row['id'] for row in library.catalog()['presets']])
        for row in catalog['references']:
            self.assertEqual(library.audio_path(row['id']), Path(row['path']))
            self.assertNotIn(str(self.root), row['preview_url'])

    def test_save_rejects_unregistered_paths_and_unknown_fields(self):
        for reference in (str(self.outside), '../outside.wav', 'https://example.com/audio.wav'):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                library.save({'name': '无效', 'voice': {'reference': reference}})
        with self.assertRaises(ValueError):
            self.make(arbitrary_command='run')
        with self.assertRaises(ValueError):
            library.save({'id': '../escape', 'name': '无效', 'voice': {'reference': str(self.imported)}})
        with self.assertRaises(ValueError):
            library.save({'id': 'unknown-id', 'name': '无效', 'voice': {'reference': str(self.imported)}})
        for invalid in ({'name': '缺音频'}, {'name': '缺音频', 'voice': {'speed': 1}},
                        {'name': '多字段', 'voice': {'reference': str(self.imported)}, 'command': 'run'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                library.save(invalid)
        for identity in ({}, 0, False, []):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                library.save({'id': identity, 'name': '无效', 'voice': {'reference': str(self.imported)}})

    def test_upsert_persists_identity_and_returns_owned_data(self):
        first = self.make()
        changed = library.save({'id': first['id'], 'name': '新名称', 'tags': ['故事', '故事'], 'voice': {**first['voice'], 'speed': 1.15}})
        self.assertEqual(first['id'], changed['id'])
        self.assertEqual(changed['tags'], ['故事'])
        first['voice']['speed'] = 0.5
        self.assertEqual(library.resolve(changed['id'])['voice']['speed'], 1.15)
        saved = json.loads(library.PRESETS.read_text(encoding='utf-8'))
        self.assertEqual(len(saved['presets']), 1)

    def test_snapshot_retains_characters_and_scene_preset_priority(self):
        narrator = self.make('旁白', 1.0)
        character = self.make('人物', 0.9, emotion='高兴', intensity=0.3)
        scene_voice = self.make('镜头', 1.2, emotion='平静', intensity=0.1)
        board = self.board()
        board['scenes'][0]['speaker'] = '小林'
        board['scenes'][1].update(speaker='小林', voice_preset_id=scene_voice['id'])
        spec = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': narrator['id'],
            'voice': {'speed': 1.1}, 'characters': {'小林': character['id']}})
        self.assertEqual(spec['settings']['voice']['speed'], 1.1)
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0])['speed'], 0.9)
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0])['emotion'], '高兴')
        self.assertEqual(settings.voice_for(spec, spec['scenes'][1])['speed'], 1.2)
        self.assertEqual(spec['character_preset_ids'], {'小林': character['id']})
        self.assertEqual(set(spec['characters']['小林']), set(settings.DEFAULTS['voice']))

    def test_editing_presets_and_defaults_cannot_change_existing_snapshot(self):
        preset = self.make(speed=0.9)
        board = self.board()
        board['scenes'][0]['speaker'] = '讲师'
        snapshot = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': preset['id'],
                                           'characters': {'讲师': preset['id']}})
        frozen = copy.deepcopy(snapshot)
        library.save({'id': preset['id'], 'name': '已改预设', 'voice': {**preset['voice'], 'speed': 1.5}})
        self.config['voice']['speed'] = 2
        self.assertEqual(snapshot, frozen)
        self.assertEqual(settings.voice_for(snapshot, snapshot['scenes'][0])['speed'], 0.9)
        self.assertEqual(settings.voice_for(snapshot, snapshot['scenes'][1])['speed'], 0.9)

    def test_unknown_roles_and_arbitrary_voice_paths_do_not_survive(self):
        preset = self.make()
        board = self.board()
        board['scenes'][0]['speaker'] = '不存在'
        with self.assertRaisesRegex(ValueError, '没有音色配置'):
            whiteboard_api.snapshot({'storyboard': board})
        for characters in ({'角色': 'unknown-id'}, {'../角色': preset['id']}, {'__proto__': preset['id']}, {'角色': {'reference': str(self.outside)}}):
            with self.subTest(characters=characters), self.assertRaises(ValueError):
                whiteboard_api.snapshot({'storyboard': self.board(), 'characters': characters})
        with self.assertRaises(ValueError):
            whiteboard_api.snapshot({'storyboard': self.board(), 'voice': {'reference': str(self.outside)}})
        board = self.board()
        board['scenes'][0]['voice'] = {'reference': str(self.outside), 'speed': 2}
        snapshot = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': preset['id']})
        self.assertNotIn('voice', snapshot['scenes'][0])
        self.assertNotIn(str(self.outside), json.dumps(snapshot))

    def test_preview_without_preset_does_not_require_voice_models(self):
        self.config['voice']['reference'] = str(self.outside.parent / 'missing.wav')
        with patch.object(settings, 'validate') as validate:
            snapshot = whiteboard_api.snapshot({'storyboard': self.board()})
        validate.assert_not_called()
        self.assertEqual(snapshot['render_mode'], 'excalidraw')

    def test_builtin_narrator_alias_uses_whole_video_voice(self):
        preset = self.make(speed=1.15)
        board = self.board()
        board['scenes'][0]['speaker'] = '旁白'
        spec = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': preset['id']})
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0])['speed'], 1.15)
        character = self.make('旁白角色覆盖', speed=0.85)
        spec = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': preset['id'],
                                       'characters': {'旁白': character['id']}})
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0])['speed'], 0.85)

    def test_default_calls_existing_saver_with_voice_only(self):
        preset = self.make()
        with patch.object(settings, 'save') as save:
            actual = library.set_default(preset['id'])
        self.assertEqual(actual['id'], preset['id'])
        save.assert_called_once_with({'voice': preset['voice']})

    def test_default_identity_survives_duplicate_voice_and_rename(self):
        chosen = self.make('默认预设')
        same_voice = self.make('同参数另一个名称')
        self.assertNotEqual(chosen['id'], same_voice['id'])
        def apply(data):
            self.config['voice'] = copy.deepcopy(data['voice'])
        with patch.object(settings, 'save', side_effect=apply):
            library.set_default(chosen['id'])
        self.assertEqual(library.catalog()['default_preset_id'], chosen['id'])
        library.save({'id': chosen['id'], 'name': '默认预设改名', 'voice': chosen['voice']})
        self.assertEqual(library.catalog()['default_preset_id'], chosen['id'])
        self.assertEqual(library.resolve(chosen['id'])['name'], '默认预设改名')

    def test_advanced_voice_values_remain_complete_in_all_snapshot_levels(self):
        narrator = self.make('旁白', duration_factor=0.95, pitch_semitones=0.2, formant_shift=1.04)
        role = self.make('角色', duration_factor=1.1, pitch_semitones=-0.5, formant_shift=0.97)
        board = self.board()
        board['scenes'][0]['speaker'] = '角色'
        board['scenes'][1].update(speaker='旁白', voice_preset_id=narrator['id'])
        spec = whiteboard_api.snapshot({'storyboard': board, 'voice_preset_id': narrator['id'], 'characters': {'角色': role['id']}})
        self.assertEqual(spec['settings']['voice'], narrator['voice'])
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0]), role['voice'])
        self.assertEqual(settings.voice_for(spec, spec['scenes'][1]), narrator['voice'])
        library.save({'id': role['id'], 'name': '已修改角色', 'voice': {**role['voice'], 'pitch_semitones': 2}})
        self.assertEqual(settings.voice_for(spec, spec['scenes'][0])['pitch_semitones'], -0.5)

    def test_failed_save_preserves_registry_bytes(self):
        self.make()
        before = library.PRESETS.read_bytes()
        with self.assertRaises(ValueError):
            self.make(pitch_semitones=4)
        self.assertEqual(library.PRESETS.read_bytes(), before)

    def test_audio_endpoint_accepts_only_opaque_registered_ids(self):
        handler = MagicMock()
        self.assertTrue(voice_api.get(handler, urlparse('/api/voice-library/audio?ref=../../outside.wav')))
        handler.send_file.assert_not_called()
        self.assertEqual(handler.reply.call_args.args[1], 400)
        handler.reset_mock()
        ref = library.catalog()['references'][0]
        self.assertTrue(voice_api.get(handler, urlparse(ref['preview_url'])))
        handler.send_file.assert_called_once_with(Path(ref['path']))

    def test_invalid_optional_ids_and_controls_are_rejected_before_preview(self):
        for identity in ({}, 0, False, [], '../escape'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                whiteboard_api.snapshot({'storyboard': self.board(), 'voice_preset_id': identity})
        for voice in ({'speed': 0}, {'speed': float('nan')}, {'intensity': 1}, {'emotion': '未知'}):
            with self.subTest(voice=voice), self.assertRaises(ValueError):
                whiteboard_api.snapshot({'storyboard': self.board(), 'voice': voice})
        with self.assertRaisesRegex(ValueError, '未知字段'):
            whiteboard_api.snapshot({'storyboard': self.board(), 'voicePreset': 'typo'})


if __name__ == '__main__':
    unittest.main()
