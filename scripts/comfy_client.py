import json
import time
import uuid
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8188'
HTTP = requests.Session()
HTTP.trust_env = False  # Local inference must not use the system Internet proxy.


def workflow(prompt, negative='', seed=42, width=1024, height=576, steps=28, models=None, cfg=4.0,
             engine='qwen-image-2512', references=None):
    if engine=='flux2-klein-4b':
        if steps!=4 or cfg!=1:raise ValueError('FLUX.2 klein 4B 蒸馏版需要 4 步、CFG 1')
        from flux_klein import workflow as flux_workflow
        return flux_workflow(prompt,seed,width,height,references,models)
    if engine!='qwen-image-2512':raise ValueError('未知生图引擎')
    if references:raise ValueError('参考图编辑目前需要 FLUX.2 klein 4B')
    from creation_settings import load
    models=models or load()['models']
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': 'qwen-image-2512-Q4_K_M.gguf'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen_2.5_vl_7b_fp8_scaled.safetensors', 'type': 'qwen_image', 'device': 'cpu'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_vae.safetensors'}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'text': negative, 'clip': ['2', 0]}},
        '6': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '7': {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.1}},
        '8': {'class_type': 'KSampler', 'inputs': {'model': ['7', 0], 'positive': ['4', 0], 'negative': ['5', 0], 'latent_image': ['6', 0], 'seed': seed, 'steps': steps, 'cfg': 4.0, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0}},
        '9': {'class_type': 'VAEDecode', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0]}},
        '10': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0], 'filename_prefix': 'AI-Video/Qwen'}},
    }
    graph['1']['inputs']['unet_name']=models['image_unet']
    graph['2']['inputs']['clip_name']=models['image_clip']
    graph['3']['inputs']['vae_name']=models['image_vae']
    graph['8']['inputs']['cfg']=cfg
    return graph


def generate(spec, output, timeout=3600):
    from model_profiles import require
    from image_references import checked_paths
    started=time.monotonic()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    engine=spec.get('engine','qwen-image-2512')
    require('image',engine,spec.get('models'))
    references=checked_paths(spec.get('reference_images',[]))
    if references and engine!='flux2-klein-4b':raise ValueError('参考图编辑目前需要 FLUX.2 klein 4B')
    uploaded=[]
    for path in references:
        with path.open('rb') as stream:
            response=HTTP.post(URL+'/upload/image',files={'image':(uuid.uuid4().hex+path.suffix,stream)},timeout=60)
        response.raise_for_status()
        row=response.json()
        uploaded.append((row.get('subfolder','').strip('/')+'/' if row.get('subfolder') else '')+row['name'])
    graph = workflow(spec['prompt'], spec.get('negative_prompt', ''), spec.get('seed', 42), spec.get('width', 1024), spec.get('height', 576), spec.get('steps', 28),spec.get('models'),spec.get('cfg',4.0),engine,uploaded)
    output.with_suffix('.workflow.json').write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
    response = HTTP.post(URL + '/prompt', json={'prompt': graph, 'client_id': str(uuid.uuid4())}, timeout=30)
    if not response.ok:
        raise RuntimeError(response.text)
    prompt_id = response.json()['prompt_id']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = HTTP.get(URL + '/history/' + prompt_id, timeout=30)
        response.raise_for_status()
        record = response.json().get(prompt_id)
        if record:
            output.with_suffix('.history.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            if record.get('status', {}).get('status_str') == 'error':
                raise RuntimeError(json.dumps(record['status'], ensure_ascii=False))
            images = record.get('outputs', {}).get('10', {}).get('images', [])
            if images:
                image = HTTP.get(URL + '/view', params=images[0], timeout=120)
                image.raise_for_status()
                output.write_bytes(image.content)
                from PIL import Image
                with Image.open(output) as generated:
                    generated.load();actual_width,actual_height=generated.size
                output.with_suffix('.generation.json').write_text(json.dumps({
                    'engine':engine,'prompt_id':prompt_id,'elapsed_seconds':round(time.monotonic()-started,3),
                    'width':actual_width,'height':actual_height,'steps':spec.get('steps',28),
                    'cfg':spec.get('cfg',4.0),'seed':spec.get('seed',42),
                    'reference_sha256':[row['sha256'] for row in spec.get('reference_images',[])],
                    'negative_prompt_used':engine=='qwen-image-2512','local_inference':True,
                },ensure_ascii=False,indent=2),encoding='utf-8')
                return str(output)
            if record.get('status',{}).get('completed') or record.get('status',{}).get('status_str')=='success':
                raise RuntimeError('ComfyUI 已完成任务但没有输出图片，请检查保存图像节点')
        time.sleep(2)
    raise TimeoutError(f'ComfyUI task {prompt_id} has not completed; inspect the queue before retrying.')


def unload():
    response = HTTP.post(URL + '/free', json={'unload_models': True, 'free_memory': True}, timeout=30)
    response.raise_for_status()
