"""Local image/video engine profiles; existing models remain available."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT/'apps/ComfyUI/models'
PROFILES = {
    'image': {
        'qwen-image-2512': {
            'name': 'Qwen-Image 2512 · 原有插画', 'max_references': 0,
            'defaults': {'width': 1024, 'height': 576, 'steps': 28, 'cfg': 4.0},
            'components': [('unet', 'unet', 'qwen-image-2512-Q4_K_M.gguf', 'image_unet'),
                           ('clip', 'text_encoders', 'qwen_2.5_vl_7b_fp8_scaled.safetensors', 'image_clip'),
                           ('vae', 'vae', 'qwen_image_vae.safetensors', 'image_vae')]},
        'flux2-klein-4b': {
            'name': 'FLUX.2 klein 4B · 参考图编辑', 'max_references': 4,
            'defaults': {'width': 1024, 'height': 576, 'steps': 4, 'cfg': 1.0},
            'components': [('unet', 'diffusion_models', 'flux-2-klein-4b-fp8.safetensors', None),
                           ('clip', 'text_encoders', 'qwen_3_4b.safetensors', None),
                           ('vae', 'vae', 'flux2-vae.safetensors', None)]},
    },
    'motion': {
        'wan2.2-a14b': {
            'name': 'Wan2.2 A14B · 图生视频 Q4_K_M',
            'defaults': {'width': 832, 'height': 480, 'steps': 20, 'frames': 81, 'fps': 16},
            'components': [('unet_high', 'diffusion_models', 'wan2.2_i2v_high_noise_14B_Q4_K_M.gguf', None),
                           ('unet_low', 'diffusion_models', 'wan2.2_i2v_low_noise_14B_Q4_K_M.gguf', None),
                           ('clip', 'text_encoders', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'video_clip'),
                           ('vae', 'vae', 'wan_2.1_vae.safetensors', None)]},
        'wan2.2-5b': {
            'name': 'Wan2.2 5B · 原有动态镜头',
            'defaults': {'width': 512, 'height': 288, 'steps': 20, 'frames': 49, 'fps': 16},
            'components': [('unet', 'diffusion_models', 'wan2.2_ti2v_5B_fp16.safetensors', 'video_unet'),
                           ('clip', 'text_encoders', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 'video_clip'),
                           ('vae', 'vae', 'wan2.2_vae.safetensors', 'video_vae')]},
    },
}


def profile(kind, engine):
    if kind not in PROFILES or engine not in PROFILES[kind]:
        raise ValueError('未知图像或视频引擎')
    return PROFILES[kind][engine]


def components(kind, engine, models=None):
    rows = []
    for role, folder, default, key in profile(kind, engine)['components']:
        name = (models or {}).get(key, default) if key else default
        if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('模型名称必须是当前模型目录内的相对路径')
        base = (MODEL_ROOT/folder).resolve()
        path = (base/name).resolve()
        if not path.is_relative_to(base):
            raise ValueError('模型路径越界')
        if role == 'unet' and engine == 'qwen-image-2512' and not path.is_file():
            base = (MODEL_ROOT/'diffusion_models').resolve()
            path = (base/name).resolve()
            if not path.is_relative_to(base):
                raise ValueError('模型路径越界')
        exists = path.is_file() and path.stat().st_size > 1024
        rows.append({'role': role, 'folder': folder, 'name': name, 'path': str(path),
                     'exists': exists, 'bytes': path.stat().st_size if path.is_file() else 0})
    return rows


def require(kind, engine, models=None):
    rows = components(kind, engine, models)
    missing = [row['name'] for row in rows if not row['exists']]
    if missing:
        raise ValueError(profile(kind, engine)['name']+' 尚缺模型：'+', '.join(missing))
    return rows


def catalog(kind, models=None):
    result = []
    for engine, data in PROFILES[kind].items():
        rows = components(kind, engine, models)
        result.append({'id': engine, 'name': data['name'], 'defaults': dict(data['defaults']),
                       'max_references': data.get('max_references', 0), 'components': rows,
                       'ready': all(row['exists'] for row in rows)})
    return result
