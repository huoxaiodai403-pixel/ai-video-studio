import base64
import hashlib
import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlparse,parse_qs

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import testing_support as tempfile
import chatgpt_auth as auth
import providers
from studio import Handler


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config=patch.object(auth,'CONFIG',Path(self.temp.name)/'account.json')
        self.config.start();self.addCleanup(self.config.stop)
        auth.cancel()
        self.tokens={'access_token':'fixture-access','refresh_token':'fixture-refresh','id_token':'fixture-id',
                     'expires_in':3600,'scope':auth.SCOPE}

    def pending(self):
        params=parse_qs(urlparse(auth.start(12345)['authorization_url']).query)
        return params,{'state':params['state'],'code':['fixture-code'],'client_id':['oaiapp_fixture']}

    def finish(self,query):
        with patch.object(auth,'token_request',return_value=self.tokens),patch.object(auth,'verify_identity',return_value={'sub':'fixture-sub','email':'test@example.invalid'}):
            return auth.complete(query)

    def test_pkce_loopback_registration_redaction_and_one_time_callback(self):
        params,query=self.pending()
        self.assertEqual(params['client_id'],['dynamic_agent_client'])
        self.assertEqual(params['redirect_uri'],['http://127.0.0.1:12345/auth/chatgpt/callback'])
        digest=base64.urlsafe_b64encode(hashlib.sha256(auth.PENDING['verifier'].encode()).digest()).decode().rstrip('=')
        self.assertEqual(params['code_challenge'],[digest])
        self.assertTrue(self.finish(query)['connected'])
        self.assertNotIn('fixture-access',auth.CONFIG.read_text())
        self.assertNotIn('token',json.dumps(auth.status()))
        with self.assertRaises(ValueError):self.finish(query)
        repeat=parse_qs(urlparse(auth.start(45678)['authorization_url']).query)
        self.assertEqual(repeat['client_id'],['oaiapp_fixture'])
        self.assertEqual(repeat['ext_agent_host_id'],params['ext_agent_host_id'])
        self.assertNotIn('agent_name_hint',repeat)

    def test_state_client_replay_and_late_cancel_are_rejected(self):
        _,q=self.pending()
        with self.assertRaises(ValueError):self.finish({**q,'state':['wrong']})
        with self.assertRaises(ValueError):self.finish({**q,'code':['one','two']})
        self.finish(q)
        _,q=self.pending()
        with self.assertRaises(ValueError):self.finish({**q,'client_id':['oaiapp_other']})
        def interrupted(data):
            self.assertTrue(auth.status()['pending'])
            with self.assertRaisesRegex(ValueError,'重复'):auth.complete(q)
            auth.cancel()
            return self.tokens
        with patch.object(auth,'token_request',side_effect=interrupted),patch.object(auth,'verify_identity',return_value={'sub':'fixture-sub'}),self.assertRaises(ValueError):auth.complete(q)
        self.assertEqual(auth.load()['email'],'test@example.invalid')

    def test_scope_and_subject_validated_before_replacing_account(self):
        _,q=self.pending();self.finish(q)
        _,q=self.pending()
        with patch.object(auth,'token_request',return_value=self.tokens),patch.object(auth,'verify_identity',return_value={'sub':'wrong'}),self.assertRaises(ValueError):auth.complete(q)
        self.assertEqual(auth.load()['subject'],'fixture-sub')
        _,q=self.pending();self.tokens['scope']='openid email'
        with self.assertRaises(ValueError):self.finish(q)
        self.assertTrue(auth.status()['connected'])

    def test_signed_oidc_identity_checks_nonce_audience_and_signature(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims={'iss':'https://auth.openai.com','sub':'test','aud':'oaiapp_test','nonce':'nonce','exp':time.time()+300}
        signed=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture'})
        with patch('jwt.PyJWKClient') as source:
            source.return_value.get_signing_key_from_jwt.return_value.key=key.public_key()
            self.assertEqual(auth.verify_identity(signed,'oaiapp_test','nonce')['sub'],'test')
            for client,nonce in [('oaiapp_wrong','nonce'),('oaiapp_test','wrong')]:
                with self.assertRaises(ValueError):auth.verify_identity(signed,client,nonce)
            source.return_value.get_signing_key_from_jwt.return_value.key=rsa.generate_private_key(public_exponent=65537,key_size=2048).public_key()
            with self.assertRaises(ValueError):auth.verify_identity(signed,'oaiapp_test','nonce')

    def test_refresh_rotates_tokens_and_logout_clears_even_bad_metadata(self):
        _,q=self.pending();self.finish(q)
        new={**self.tokens,'access_token':'rotated-access','refresh_token':'rotated-refresh'}
        with patch.object(auth,'token_request',return_value=new) as request:
            self.assertEqual(auth.access(force=True),'rotated-access')
            self.assertEqual(request.call_args.args[0]['refresh_token'],'fixture-refresh')
        self.assertEqual(auth.load()['refresh_token'],'rotated-refresh')
        with patch.object(auth.requests,'get') as get:
            get.return_value.json.side_effect=ValueError('bad JSON')
            self.assertIn('未确认',auth.logout()['message'])
        self.assertFalse(auth.status()['connected'])
        self.assertNotIn('token',json.dumps(auth.load()))

    def test_responses_requires_completion_and_uses_official_contract(self):
        response=Mock()
        delta=b'data: '+json.dumps({'type':'response.output_text.delta','delta':'test'}).encode()
        with patch.object(auth,'models',return_value=[{'id':'allowed'}]),patch.object(auth,'request',return_value=response) as request:
            for final in [None,'response.failed','response.incomplete']:
                response.iter_lines.return_value=[delta]+([b'data: '+json.dumps({'type':final}).encode()] if final else [])
                with self.assertRaises(RuntimeError):auth.generate('allowed',[{'role':'user','content':'test'}])
            response.iter_lines.return_value=[delta,b'data: {"type":"response.completed"}']
            self.assertEqual(auth.generate('allowed',[]),'test')
            self.assertEqual(request.call_args.args,('POST','/responses'))
            self.assertEqual(request.call_args.kwargs['json']['store'],False)
            self.assertEqual(request.call_args.kwargs['json']['stream'],True)
            with self.assertRaises(ValueError):auth.generate('unknown',[])

    def test_account_tokens_never_flow_to_provider_url_and_callback_log_is_redacted(self):
        with patch.object(providers,'load',return_value={'story':{'auth_mode':'chatgpt','model':'allowed','base_url':'https://untrusted.invalid'}}),patch.object(auth,'status',return_value={'connected':True}),patch.object(auth,'generate',return_value='story') as generate,patch.object(providers.requests,'request') as request:
            self.assertEqual(providers.story([]),'story')
            request.assert_not_called();generate.assert_called_once_with('allowed',[])
            with self.assertRaises(ValueError):providers.request('story','POST','/chat/completions')
        handler=Mock(command='GET',path='/auth/chatgpt/callback?code=secret&state=secret',request_version='HTTP/1.1')
        Handler.log_request(handler,200)
        self.assertNotIn('secret',str(handler.log_message.call_args))


if __name__=='__main__':unittest.main()
