"""Per-capability online providers. Secrets are Windows DPAPI encrypted at rest."""
import base64
import ctypes
import json
import os
import time
import threading
import copy
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlparse,quote
import requests
from PIL import Image,ImageOps
from io import BytesIO
from prompt_library import ROOT

CONFIG=ROOT/'config/providers.json'
KINDS=('image','tts','asr','video','story')
SAVE_LOCK=threading.Lock()
SNAPSHOT=ContextVar('online_provider_snapshot',default=None)


def crypt(value, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_byte))]
    raw=base64.b64decode(value) if decrypt else value.encode()
    buf=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)));target=Blob()
    function=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source),None,None,None,None,0,ctypes.byref(target)):
        raise OSError('Windows 无法读取或保存密钥。')
    try:
        data=ctypes.string_at(target.data,target.size)
        return data.decode() if decrypt else base64.b64encode(data).decode()
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def load(public=False):
    frozen=SNAPSHOT.get()
    data=copy.deepcopy(frozen) if frozen is not None else json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
    for kind in KINDS:
        row=data.setdefault(kind,{'base_url':'','model':'','protocol':'openai','voice':'alloy','size':'auto','video_transport':'json'})
        if public:
            row['has_key']=bool(row.pop('key_encrypted','') or os.getenv('AI_VIDEO_'+kind.upper()+'_KEY'))
    return data


def save(data):
    with SAVE_LOCK:
        return _save(data)


def _save(data):
    current=load()
    for kind in KINDS:
        if kind not in data:continue
        row=data.get(kind,{})
        url=row.get('base_url','').strip().rstrip('/')
        parsed=urlparse(url)
        if url and (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Base URL 应为 http(s) 接口地址，不包含密钥或查询参数。')
        current[kind].update({key:str(row.get(key,current[kind].get(key,''))).strip() for key in ('model','voice','size','video_transport')})
        current[kind].update(base_url=url,protocol='openai')
        if kind=='story':
            mode=row.get('auth_mode',current[kind].get('auth_mode','api_key'))
            if mode not in ('api_key','chatgpt'):raise ValueError('请选择 API Key 或 ChatGPT 账号授权。')
            current[kind]['auth_mode']=mode
        if row.get('api_key'):current[kind]['key_encrypted']=crypt(row['api_key'].strip())
        if row.get('clear_key'):current[kind].pop('key_encrypted',None)
    CONFIG.parent.mkdir(exist_ok=True)
    temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,CONFIG)


def configured(kind):
    row=load()[kind]
    if kind=='story' and row.get('auth_mode')=='chatgpt':
        import chatgpt_auth
        if not chatgpt_auth.status()['connected']:raise ValueError('请先在「在线服务 → 编剧与分镜」登录并授权 ChatGPT。')
        if not row.get('model'):raise ValueError('请从当前账号可用的模型中选择一个并保存。')
        return row,None
    key=crypt(row['key_encrypted'],True) if row.get('key_encrypted') else os.getenv('AI_VIDEO_'+kind.upper()+'_KEY','')
    if not row.get('base_url') or not row.get('model') or not key:
        names={'image':'生图','tts':'配音','asr':'识别与字幕','video':'视频','story':'编剧'}
        missing=[label for field,label in [('base_url','服务地址'),('model','模型名称')] if not row.get(field)]
        if not key:missing.append('API Key')
        raise ValueError(f'请在「在线服务 → {names.get(kind,kind)}」补充'+ '、'.join(missing)+'。')
    if kind=='video' and urlparse(row['base_url']).hostname=='api.openai.com':
        raise ValueError('OpenAI 官方 Videos API 已停用；请配置仍提供该协议的兼容平台，或选择本地 Wan。')
    return row,key


def request(kind,method,path,**kwargs):
    row,key=configured(kind)
    if key is None:raise ValueError('ChatGPT 账号授权请使用编剧入口。')
    try:
        response=requests.request(method,row['base_url']+path,headers={'Authorization':'Bearer '+key},timeout=(30,600),**kwargs)
    except requests.RequestException:
        raise RuntimeError(f'{kind} 在线连接失败，请检查地址或网络。') from None
    if not response.ok:
        tips={401:'API Key 无效或过期，请重新保存。',403:'没有模型访问权限，请检查服务开通状态与授权。',
              404:'服务地址或模型不存在，请确认地址包含正确版本前缀且支持该媒体接口。',
              400:'请求参数不受该模型支持，请检查模型名称、音色或尺寸。',
              422:'该服务不接受当前请求格式，请核对接口兼容性。',
              429:'请求频率或账户额度受限，请稍后重试并检查服务商控制台。'}
        raise RuntimeError(f'在线接口 HTTP {response.status_code}：'+tips.get(response.status_code,'服务暂时失败，请稍后重试。'))
    return response


def story(messages, **options):
    row,_=configured('story')
    if row.get('auth_mode')=='chatgpt':
        import chatgpt_auth
        return chatgpt_auth.generate(row['model'],messages)
    response=request('story','POST','/chat/completions',json={'model':row['model'],'messages':messages,**options})
    try:content=response.json()['choices'][0]['message']['content']
    finally:response.close()
    if not isinstance(content,str) or not content.strip():raise ValueError('编剧模型未返回文本，请确认该模型支持对话。')
    return content


def provenance(kind,output):
    row,_=configured(kind)
    Path(output).with_suffix('.provider.json').write_text(json.dumps({'backend':'online','protocol':'openai','base_url':row['base_url'],'model':row['model']},indent=2),encoding='utf-8')


def image(prompt,output,size=None):
    row,_=configured('image')
    response=request('image','POST','/images/generations',json={'model':row['model'],'prompt':prompt,'n':1,'size':size or row.get('size') or 'auto'}).json()
    item=response['data'][0]
    if item.get('b64_json'):raw=base64.b64decode(item['b64_json'])
    else:
        # Asset URL is provider output; never forward the API authorization header.
        result=requests.get(item['url'],timeout=180);result.raise_for_status();raw=result.content
    Image.open(BytesIO(raw)).convert('RGB').save(output,'PNG');provenance('image',output)


def tts(text,output,voice=None,speed=None):
    row,_=configured('tts')
    body={'model':row['model'],'input':text,'voice':voice or row.get('voice') or 'alloy','response_format':'wav'}
    if speed is not None:body['speed']=speed
    raw=request('tts','POST','/audio/speech',json=body).content
    Path(output).write_bytes(raw);provenance('tts',output)


def stamp(seconds):
    ms=round(float(seconds)*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def asr(audio,output,words=False):
    row,_=configured('asr')
    with Path(audio).open('rb') as f:
        result=request('asr','POST','/audio/transcriptions',data={'model':row['model'],'response_format':'verbose_json','timestamp_granularities[]':'word' if words else 'segment'},files={'file':(Path(audio).name,f)}).json()
    if words:
        aligned=[{'text':w['word'],'start':w['start'],'end':w['end']} for w in result.get('words',[])]
        if not aligned:raise ValueError('识别模型未返回逐词时间戳。请使用支持 verbose_json + word 时间戳的模型；也可选择自带时间戳的 Edge 或火山配音。')
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        provenance('asr',output)
        return aligned
    segments=result.get('segments',[])
    if not segments:raise ValueError('该在线识别模型没有返回时间戳；请换用支持 verbose_json/segments 的模型，或选择本地识别。')
    for item in segments:
        if float(item['end'])<=float(item['start']):raise ValueError('在线识别返回无效时间戳。')
    Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    Path(output).with_suffix('.srt').write_text('\n'.join(f'{i}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["text"].strip()}\n' for i,s in enumerate(segments,1)),encoding='utf-8')
    provenance('asr',output)
    return segments


def video(prompt,output,image_path=None):
    row,_=configured('video');body={'model':row['model'],'prompt':prompt,'seconds':'4','size':row.get('size') if row.get('size') not in ('','auto') else '1280x720'}
    raw=None
    if image_path:
        try:width,height=map(int,body['size'].split('x'))
        except ValueError:raise ValueError('视频尺寸应为 宽x高，例如 1280x720。')
        if not 64<=width<=4096 or not 64<=height<=4096:raise ValueError('视频尺寸超出支持范围。')
        buffer=BytesIO();ImageOps.fit(Image.open(image_path).convert('RGB'),(width,height)).save(buffer,format='PNG');raw=buffer.getvalue()
    if row.get('video_transport','json')=='multipart':
        files={key:(None,str(value)) for key,value in body.items()}
        if raw:files['input_reference']=('reference.png',raw,'image/png')
        result=request('video','POST','/videos',files=files).json()
    else:
        if raw:body['input_reference']={'image_url':'data:image/png;base64,'+base64.b64encode(raw).decode()}
        result=request('video','POST','/videos',json=body).json()
    task=quote(str(result['id']),safe='')
    Path(output).with_suffix('.remote-job.json').write_text(json.dumps({'id':result['id'],'status':result.get('status')}),encoding='utf-8')
    end=time.monotonic()+3600
    while time.monotonic()<end:
        if result.get('status')=='completed':
            Path(output).write_bytes(request('video','GET',f'/videos/{task}/content').content);provenance('video',output);return
        if result.get('status') in ('failed','cancelled'):raise RuntimeError('在线视频生成失败，请在厂商后台查看任务 '+str(result['id']))
        time.sleep(5);result=request('video','GET',f'/videos/{task}').json()
    raise TimeoutError('在线视频任务仍未完成；任务 ID 已保存，请勿重复提交。')
