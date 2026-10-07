import base64,io,json,threading,wave
import testing_support as tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PIL import Image
import providers
seen=[]
buf=io.BytesIO();Image.new('RGB',(32,32),'blue').save(buf,'PNG');png=buf.getvalue()
buf=io.BytesIO()
with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*16000)
wav=buf.getvalue()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,body,kind='application/json'):
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  assert self.headers['Authorization']=='Bearer test-secret-not-real'
  data=self.rfile.read(int(self.headers.get('Content-Length','0')));seen.append(self.path)
  if self.path.endswith('/images/generations'):self.send(json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode())
  elif self.path.endswith('/audio/speech'):self.send(wav,'audio/wav')
  elif self.path.endswith('/audio/transcriptions'):
   assert b'filename=' in data and b'verbose_json' in data
   self.send(json.dumps({'text':'hello','segments':[{'start':0,'end':1,'text':'hello'}]}).encode())
  elif self.path.endswith('/videos'):
   if self.headers.get('Content-Type','').startswith('application/json'):
    body=json.loads(data)
    if 'input_reference' in body:assert body['input_reference']['image_url'].startswith('data:image/png;base64,')
   else:assert b'filename="reference.png"' in data and b'1280x720' in data
   self.send(b'{"id":"test-video","status":"completed"}')
  else:self.send_error(404)
 def do_GET(self):
  assert self.headers['Authorization']=='Bearer test-secret-not-real'
  if self.path.endswith('/videos/test-video/content'):self.send(b'test-video-content','video/mp4')
  else:self.send_error(404)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
# Disable proxies only in this isolated test process.
import os
os.environ['NO_PROXY']='127.0.0.1,localhost'
with tempfile.TemporaryDirectory() as folder:
 root=Path(folder);providers.CONFIG=root/'providers.json'
 payload={kind:{'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'test-model','api_key':'test-secret-not-real','voice':'alloy','size':'auto'} for kind in providers.KINDS}
 providers.save(payload)
 assert 'test-secret-not-real' not in providers.CONFIG.read_text()
 public=providers.load(public=True);assert all(r['has_key'] and 'key_encrypted' not in r for r in public.values())
 providers.image('test',root/'image.png');assert Image.open(root/'image.png').size==(32,32)
 providers.tts('hello',root/'audio.wav');providers.asr(root/'audio.wav',root/'asr.json');assert '00:00:01,000' in (root/'asr.srt').read_text()
 providers.video('test',root/'video.mp4');assert (root/'video.mp4').read_bytes()==b'test-video-content'
 providers.video('test',root/'video-reference.mp4',root/'image.png')
 payload['video']['video_transport']='multipart';providers.save(payload)
 providers.video('test',root/'video-multipart.mp4',root/'image.png')
 payload['tts']['api_key']='';providers.save(payload);assert providers.configured('tts')[1]=='test-secret-not-real'
 print('PASS: 4 online API contracts, multipart upload, timestamps, secret encryption/redaction and blank-key preservation')
server.shutdown()
