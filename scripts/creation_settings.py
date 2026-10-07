"""Validated, per-task snapshots of local model and creative settings."""
import copy
import json
import os
import subprocess
import uuid
import wave
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/creation.json'
MODEL_ROOT=ROOT/'apps/ComfyUI/models'
VOICES=ROOT/'assets/voices'
DEFAULTS={
 'models':{'image_unet':'qwen-image-2512-Q4_K_M.gguf','image_clip':'qwen_2.5_vl_7b_fp8_scaled.safetensors','image_vae':'qwen_image_vae.safetensors',
 'video_unet':'wan2.2_ti2v_5B_fp16.safetensors','video_clip':'umt5_xxl_fp8_e4m3fn_scaled.safetensors','video_vae':'wan2.2_vae.safetensors',
 'tts_dir':str(ROOT/'apps/index-tts/checkpoints'),'asr_dir':str(ROOT/'models/Qwen3-ASR-1.7B'),'align_dir':str(ROOT/'models/Qwen3-ForcedAligner-0.6B')},
 'image':{'engine':'qwen-image-2512','width':1024,'height':576,'steps':28,'seed':42,'cfg':4.0},
 'motion':{'engine':'wan2.2-5b','width':512,'height':288,'frames':49,'fps':16,'steps':20,'seed':42},
 'output':{'width':1280,'height':720,'fps':25,'subtitle_size':22},
 'voice':{'reference':str(ROOT/'apps/index-tts/examples/voice_01.wav'),'emotion':'平静','intensity':0.6,'speed':1.0,'online_voice':'alloy',
            'duration_factor':1.0,'pitch_semitones':0.0,'formant_shift':1.0,
            'prosody_reference':'','prosody_strength':1.0,
            'engine':'index-tts','qwen_speaker':'Vivian','qwen_instruct':'','qwen_language':'Chinese','qwen_seed':42,'qwen_ref_text':''},
 'story':{'local_url':'http://127.0.0.1:11434/v1','local_model':''}
}
MODEL_TYPES={
 'image_unet':('unet', 'qwen*.gguf'), 'image_clip':('text_encoders','qwen*.safetensors'), 'image_vae':('vae','qwen*.safetensors'),
 'video_unet':('diffusion_models','wan2.2*5B*.safetensors'),'video_clip':('text_encoders','umt5*.safetensors'),'video_vae':('vae','wan2.2*.safetensors')}
EMOTIONS=['高兴','愤怒','悲伤','害怕','厌恶','低落','惊讶','平静']

def merge(base, extra):
    result=copy.deepcopy(base)
    for k,v in (extra or {}).items():
        if k in result:
            result[k]=merge(result[k],v) if isinstance(result[k],dict) and isinstance(v,dict) else copy.deepcopy(v)
    return result

def load():
    return merge(DEFAULTS,json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {})

def number(value,lo,hi,label,integer=False):
    if isinstance(value,bool):raise ValueError(label+'格式错误')
    try:n=float(value)
    except (TypeError,ValueError):raise ValueError(label+'应为数字')
    if not lo<=n<=hi or (integer and n!=int(n)):raise ValueError(f'{label}应在 {lo}–{hi} 范围内')
    return int(n) if integer else n

def validate_voice(v):
    v=merge(DEFAULTS['voice'],v)
    if v['engine'] not in ('index-tts','qwen3-custom','qwen3-design','qwen3-clone'):raise ValueError('未知本地配音引擎')
    if v['qwen_speaker'] not in ('Vivian','Serena','Uncle_Fu','Dylan','Eric','Ryan','Aiden','Ono_Anna','Sohee'):raise ValueError('未知 Qwen 音色')
    if v['qwen_language'] not in ('Chinese','English','Japanese','Korean','German','French','Russian','Portuguese','Spanish','Italian','Auto'):raise ValueError('未知 Qwen 语言')
    if not isinstance(v['qwen_instruct'],str) or len(v['qwen_instruct'])>500:raise ValueError('声音表达描述应不超过500字')
    if not isinstance(v['qwen_ref_text'],str) or len(v['qwen_ref_text'])>2000:raise ValueError('克隆参考原文应不超过2000字')
    v['qwen_seed']=number(v['qwen_seed'],0,2147483647,'声音随机种子',True)
    ref=Path(v['reference'])
    if v['engine'] in ('index-tts','qwen3-clone') and (not ref.is_absolute() or not ref.is_file() or ref.suffix.lower() not in ('.wav','.mp3','.flac','.m4a')):raise ValueError('请选择或上传已有参考音频')
    if v['emotion'] not in EMOTIONS:raise ValueError('未知情感')
    v['intensity']=number(v['intensity'],0,0.8,'情感强度');v['speed']=number(v['speed'],0.5,2,'语速')
    v['duration_factor']=number(v['duration_factor'],0.8,1.2,'合成节奏')
    v['pitch_semitones']=number(v['pitch_semitones'],-3,3,'音高微调')
    v['formant_shift']=number(v['formant_shift'],0.9,1.1,'共振峰微调')
    if not isinstance(v['prosody_reference'],str):raise ValueError('表达参考应为已登记音频或留空')
    if v['prosody_reference']:
        prosody=Path(v['prosody_reference'])
        if not prosody.is_absolute() or not prosody.is_file() or prosody.suffix.lower() not in ('.wav','.mp3','.flac','.m4a'):raise ValueError('表达参考音频不存在')
    v['prosody_strength']=number(v['prosody_strength'],0,1,'表达参考强度')
    if not isinstance(v['online_voice'],str) or len(v['online_voice'])>200:raise ValueError('在线音色 ID 过长')
    return v

def model_file(key,name):
    folder,pattern=MODEL_TYPES[key]
    # GGUF may be in unet or diffusion_models; expose only existing matching families.
    folders=[folder,'diffusion_models'] if key=='image_unet' else [folder]
    for sub in folders:
        root=(MODEL_ROOT/sub).resolve();p=(root/name).resolve()
        if p.is_relative_to(root) and p.is_file() and p.match(pattern):return p
    raise ValueError(f'{key} 模型不存在或不属于当前工作流支持的模型系列')

def validate(data, *, check_models=True, check_voice=True):
    c=merge(load(),data)
    # A saved pre-engine snapshot must retain its original workflow when a new
    # global default is selected. Partial requests still inherit current defaults.
    for kind,legacy in [('image','qwen-image-2512'),('motion','wan2.2-5b')]:
        saved=(data or {}).get(kind)
        if isinstance(saved,dict) and 'engine' not in saved and {'width','height','steps','seed'}.issubset(saved):
            c[kind]['engine']=legacy
    import model_profiles
    for kind in ('image','motion'):
        model_profiles.profile(kind,c[kind]['engine'])
    for kind in ('image','motion','output'):
        d=c[kind]
        for axis in ('width','height'):
            d[axis]=number(d[axis],256,1920,kind+' '+axis,True)
            divisor=32 if kind=='motion' else 16 if kind=='image' else 2
            if d[axis]%divisor:raise ValueError(f'{kind} 尺寸必须为 {divisor} 的倍数')
        if kind=='image' and d['width']*d['height']>1572864:raise ValueError('当前显存预设限制单张画布不超过 1536×1024 像素')
        if kind=='motion' and d['width']*d['height']>524288:raise ValueError('当前显存预设限制动态画布不超过 524288 像素')
    for kind in ('image','motion'):
        c[kind]['steps']=number(c[kind]['steps'],1 if kind=='image' else 4,60 if kind=='image' else 40,'步数',True)
        c[kind]['seed']=number(c[kind]['seed'],0,2147483647,'种子',True)
    c['image']['cfg']=number(c['image']['cfg'],1,10,'CFG')
    if c['image']['engine']=='flux2-klein-4b' and (c['image']['steps']!=4 or c['image']['cfg']!=1):
        raise ValueError('FLUX.2 klein 4B 蒸馏版请使用 4 步、CFG 1')
    c['motion']['frames']=number(c['motion']['frames'],17,81,'动态帧数',True)
    if (c['motion']['frames']-1)%4:raise ValueError('动态帧数必须为 4n+1')
    for kind in ('motion','output'):c[kind]['fps']=number(c[kind]['fps'],8,30,'帧率',True)
    c['output']['subtitle_size']=number(c['output']['subtitle_size'],12,48,'字幕字号',True)
    if check_voice:c['voice']=validate_voice(c['voice'])
    # Model names stay bounded even for online-only use, where local files are optional.
    for k in MODEL_TYPES:
        name=c['models'][k]
        if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('无效的模型文件名：'+k)
    if check_models:
        for k in MODEL_TYPES:model_file(k,c['models'][k])
        for kind in ('image','motion'):
            model_profiles.require(kind,c[kind]['engine'],c['models'])
        for k,marker in [('tts_dir','config.yaml'),('asr_dir','config.json'),('align_dir','config.json')]:
            p=Path(c['models'][k])
            if not p.is_absolute() or not (p/marker).is_file():raise ValueError(k+' 必须指向完整模型目录')
    from urllib.parse import urlparse
    url=urlparse(c['story']['local_url'])
    if url.scheme not in ('http','https') or url.hostname not in ('127.0.0.1','localhost','::1') or url.query or url.username:raise ValueError('本地编剧接口必须为本机 OpenAI 兼容地址')
    return c

def save(data):
    c=validate(data);CONFIG.parent.mkdir(exist_ok=True)
    temp=CONFIG.with_name('creation-'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,CONFIG)
    return c

def inventory():
    choices={};items=[]
    for key,(folder,pattern) in MODEL_TYPES.items():
        matches=[]
        for sub in ([folder,'diffusion_models'] if key=='image_unet' else [folder]):
            for p in (MODEL_ROOT/sub).rglob(pattern):
                name=p.relative_to(MODEL_ROOT/sub).as_posix()
                if name not in matches:matches.append(name);items.append({'kind':key,'name':name,'path':str(p),'bytes':p.stat().st_size})
        choices[key]=matches
    config=load()
    for k in ('tts_dir','asr_dir','align_dir'):
        p=Path(config['models'][k]);items.append({'kind':k,'name':p.name,'path':str(p),'bytes':sum(x.stat().st_size for x in p.rglob('*') if x.is_file()),'exists':p.is_dir()})
    voices=[]
    for folder in (ROOT/'apps/index-tts/examples',VOICES):
        for p in folder.glob('*.wav'):
            if p.name.startswith('emo_'):continue
            voices.append({'name':p.stem,'path':str(p)})
    import model_profiles
    return {'settings':config,'choices':choices,'models':items,'voices':voices,'emotions':EMOTIONS,
            'image_engines':model_profiles.catalog('image',config['models']),
            'motion_engines':model_profiles.catalog('motion',config['models'])}

def voice_for(spec,scene):
    c=spec.get('settings',load());v=merge(c['voice'],spec.get('characters',{}).get(scene.get('speaker',''),{}))
    if scene.get('voice'):v=merge(v,scene['voice'])
    if spec.get('voice_reference') and not spec.get('settings'):v['reference']=spec['voice_reference']
    return v

def emotion_vector(v):
    result=[0.0]*8;result[EMOTIONS.index(v['emotion'])]=v['intensity'];return result

def encode_speed(audio,speed):
    if speed==1:return
    audio=Path(audio);temp=audio.with_name(audio.stem+'.speed.wav')
    subprocess.run([str(ROOT/'tools/ffmpeg.exe'),'-v','error','-y','-i',str(audio),'-filter:a',f'atempo={speed}',str(temp)],check=True)
    os.replace(temp,audio)

def process_voice(audio, voice):
    """Apply small, independent tempo, pitch and spectral-envelope adjustments.

    Resampling first moves both the envelope and pitch. Rubber Band then
    restores the requested pitch/tempo while preserving the moved envelope.
    This changes timbre; it does not classify or guarantee a speaker's gender.
    """
    speed=number(voice.get('speed',1),0.5,2,'语速')
    semitones=number(voice.get('pitch_semitones',0),-3,3,'音高微调')
    formant=number(voice.get('formant_shift',1),0.9,1.1,'共振峰微调')
    audio=Path(audio)
    if semitones==0 and formant==1:
        encode_speed(audio,speed)
        return {'engine':'ffmpeg-atempo' if speed!=1 else 'none','speed':speed}
    with wave.open(str(audio)) as wav:
        sample_rate=wav.getframerate()
    filters=[]
    actual_formant=1.0
    if formant!=1:
        shifted_rate=round(sample_rate*formant)
        actual_formant=shifted_rate/sample_rate
        filters.extend([f'asetrate={shifted_rate}',f'aresample={sample_rate}'])
    pitch=2**(semitones/12)
    filters.append(f'rubberband=pitch={pitch/actual_formant:.12g}:tempo={speed/actual_formant:.12g}:formant=preserved:pitchq=quality')
    filters.append('alimiter=limit=0.95:level=false:latency=true')
    temporary=audio.with_name(audio.stem+'.tone-'+uuid.uuid4().hex[:8]+'.wav')
    try:
        subprocess.run([str(ROOT/'tools/ffmpeg.exe'),'-hide_banner','-v','error','-y','-i',str(audio),
                        '-af',','.join(filters),'-ar',str(sample_rate),'-c:a','pcm_s16le',str(temporary)],check=True)
        os.replace(temporary,audio)
    finally:
        temporary.unlink(missing_ok=True)
    return {'engine':'ffmpeg-rubberband','filters':filters,'speed':speed,
            'pitch_semitones':semitones,'formant_shift':actual_formant}
