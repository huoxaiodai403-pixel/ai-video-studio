import base64
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import testing_support as tempfile
import lightweight_speech as speech
import online_services
import providers
import volc_speech as volc
import whiteboard_api
import simon_whiteboard
import wave


class SpeechTimingTests(unittest.TestCase):
    def test_original_punctuation_and_numbers_survive_timing_mapping(self):
        rows = speech.map_boundaries('你好，2026年！', [{'text': '你好', 'start': .1, 'end': .6},
            {'text': '2026', 'start': .8, 'end': 1.4}, {'text': '年', 'start': 1.5, 'end': 1.8}], 2)
        self.assertEqual(''.join(r['text'] for r in rows), '你好，2026年！')
        self.assertEqual(rows[1]['start'], .8)
        self.assertEqual(rows[1]['end'], 1.4)

    def test_missing_words_bad_order_and_nonfinite_times_fail(self):
        for events in ([{'text': '你', 'start': 0, 'end': 1}],
                       [{'text': '你好', 'start': float('nan'), 'end': 1}],
                       [{'text': '你好', 'start': 1, 'end': .5}],
                       [{'text': '你好', 'start': .1, 'end': 12}]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                speech.map_boundaries('你好', events, 2)

    def test_caption_breaks_use_real_word_boundary_times(self):
        rows = [{'text': '一二三四五六七八九十', 'start': .12, 'end': .7},
                {'text': '甲乙丙丁戊己庚辛壬癸', 'start': 2.3, 'end': 4.1}]
        self.assertEqual(speech.cues(rows), rows)

    def test_whiteboard_burned_captions_keep_measured_boundaries_with_lead(self):
        first='一二三四五六七八九十一二三四五六七八'
        second='甲乙丙丁戊己庚辛壬癸'
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder);(project/'audio').mkdir()
            audio=project/'audio/scene01.wav'
            with wave.open(str(audio),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(b'\0\0'*64000)
            speech.write_json(audio.with_suffix('.alignment.json'),[{'text':first,'start':.1,'end':.5},{'text':second,'start':2,'end':3}])
            result=simon_whiteboard._audio_info(project,{'id':'scene01','beats':[first+second]})
            self.assertEqual(result['studioCaptionCues'][1]['start'],2+simon_whiteboard.LEAD)
            self.assertEqual(result['studioCaptionCues'][0]['end'],.5+simon_whiteboard.LEAD)

    def test_windows_snapshot_needs_no_clone_reference_or_asr_model(self):
        with patch.object(speech, 'validate', return_value='system-voice'):
            result = whiteboard_api.snapshot({'storyboard': whiteboard_api.example()}, render=True)
        self.assertEqual(result['backends'], {'tts': 'windows', 'asr': 'synthesis'})
        self.assertEqual(result['settings']['voice']['voice_id'], 'system-voice')

    @unittest.skipUnless(os.name == 'nt', 'Windows system speech')
    def test_actual_windows_audio_and_timestamps_remain_in_same_timebase(self):
        if not speech.windows_voices():
            self.skipTest('No installed Windows voices')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'audio.wav'
            result = speech.synthesize('字幕跟随这次配音。2026年，比例是30%。', path)
            words = json.loads(path.with_suffix('.alignment.json').read_text(encoding='utf-8'))
            self.assertGreater(result['duration'], 1)
            self.assertTrue(all(0 <= w['start'] < w['end'] <= result['duration'] for w in words))
            self.assertEqual(speech.norm(''.join(w['text'] for w in words)), speech.norm('字幕跟随这次配音。2026年，比例是30%。'))
            self.assertIn('2026', path.with_suffix('.srt').read_text(encoding='utf-8'))


class VolcTests(unittest.TestCase):
    def test_audio_and_late_subtitle_events_are_collected(self):
        raw = 'event: audio\ndata: '+json.dumps({'code': 0, 'data': base64.b64encode(b'part1').decode()})
        raw += '\n'+json.dumps({'data': base64.b64encode(b'part2').decode()})
        event = {'sentence': {'words': [{'word': '你好', 'startTime': .1, 'endTime': .7}]}}
        raw += '\ndata: '+json.dumps(event)+'\ndata: '+json.dumps(event)+'\n'+json.dumps({'code': 20000000})
        audio, words = volc.decode_response(raw)
        self.assertEqual(audio, b'part1part2')
        self.assertEqual(words, [{'text': '你好', 'start': .1, 'end': .7}])

    def test_server_failure_and_partial_responses_do_not_succeed(self):
        for raw in ('{"code":45000000}', '{"data":', '{"code":0}', '{"data":"??notbase64"}'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, RuntimeError)):
                volc.decode_response(raw)

    @unittest.skipUnless(os.name == 'nt', 'DPAPI')
    def test_both_auth_types_are_encrypted_redacted_and_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(volc, 'CONFIG', Path(folder)/'volc.json'):
            result = volc.save({'api_key': 'test-secret-not-real'})
            self.assertTrue(result['has_api_key'])
            self.assertNotIn('test-secret-not-real', json.dumps(result))
            self.assertNotIn('test-secret-not-real', volc.CONFIG.read_text())
            volc.save({'api_key': ''})
            self.assertEqual(volc.configured()[1]['X-Api-Key'], 'test-secret-not-real')
            volc.save({'auth_mode': 'legacy', 'app_id': 'test-app', 'access_token': 'test-token-not-real'})
            headers = volc.configured()[1]
            self.assertNotIn('X-Api-Key', headers)
            self.assertEqual(headers['X-Api-Access-Key'], 'test-token-not-real')
            self.assertNotIn('test-token-not-real', json.dumps(volc.load(public=True)))

    def test_protocol_requests_both_timestamp_modes_and_same_audio(self):
        response = Mock(ok=True, text=json.dumps({'data': base64.b64encode(b'test-audio').decode(),
            'sentence': {'words': [{'word': '你好', 'startTime': 0, 'endTime': .4}]}}))
        with tempfile.TemporaryDirectory() as folder, patch.object(volc, 'configured', return_value=({**volc.DEFAULTS}, {'X-Api-Key': 'test'})), patch.object(volc.requests, 'post', return_value=response) as request:
            path = Path(folder)/'out.mp3'
            words = volc.synthesize('你好', path, 'voice-id', 1.2)
            params = request.call_args.kwargs['json']['req_params']
            self.assertTrue(params['audio_params']['enable_subtitle'])
            self.assertTrue(params['audio_params']['enable_timestamp'])
            self.assertEqual(params['audio_params']['speech_rate'], 20)
            self.assertEqual(path.read_bytes(), b'test-audio')
            self.assertEqual(words[0]['text'], '你好')

    def test_403_reports_action_without_echoing_response_or_credentials(self):
        response = Mock(ok=False, status_code=403, text='test-private-secret')
        with patch.object(volc, 'configured', return_value=(volc.DEFAULTS, {})), patch.object(volc.requests, 'post', return_value=response):
            with self.assertRaisesRegex(RuntimeError, '音色授权') as error:
                volc.synthesize('你好', Path('unused'), '', 1)
            self.assertNotIn('test-private-secret', str(error.exception))


class ServiceApiTests(unittest.TestCase):
    def test_online_speech_does_not_require_missing_local_reference(self):
        handler = Mock(path='/api/speech')
        with patch.object(speech, 'validate', return_value='online-voice'), patch.object(online_services, 'queue') as queue:
            self.assertTrue(online_services.post(handler, {'backend': 'online', 'text': '你好',
                                                          'settings': {'voice': {'reference': 'missing.wav'}}}, {}))
            queue.assert_called_once()

    def test_online_subtitles_require_asr_configuration_before_submission(self):
        handler = Mock(path='/api/speech')
        with patch.object(speech, 'validate', return_value='online-voice'), patch.object(providers, 'configured', side_effect=ValueError('请配置识别')), patch.object(online_services, 'queue') as queue:
            with self.assertRaisesRegex(ValueError, '请配置识别'):
                online_services.post(handler, {'backend': 'online', 'text': '你好', 'subtitles': True}, {})
            queue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
