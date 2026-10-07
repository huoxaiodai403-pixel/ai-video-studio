"""Wan2.2 I2V A14B dual-expert GGUF graph; no model loading or network here.

Based on Comfy-Org's video_wan2_2_14B_i2v workflow, standard (no LoRA)
branch: euler/simple, CFG 3.5, shift 5, half the steps per expert.
"""
import uuid

from model_profiles import components


ENGINE = 'wan2.2-a14b'
NEGATIVE = 'blurry, distorted anatomy, flicker, subtitles, watermark, static image, low quality'


def validate(image, steps, frames, width, height):
    if not isinstance(image, str) or not image.strip():
        raise ValueError('Wan2.2 A14B 是图生视频引擎，必须提供首帧图片')
    for name, value, minimum in [('steps', steps, 2), ('frames', frames, 5),
                                  ('width', width, 16), ('height', height, 16)]:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f'A14B {name} 必须是至少 {minimum} 的整数')
    if frames % 4 != 1:
        raise ValueError('A14B 帧数必须为 4n+1，例如 81')
    if width % 16 or height % 16:
        raise ValueError('A14B 宽高必须为 16 的倍数')


def workflow(prompt, image, steps=20, frames=81, seed=42, width=832, height=480, models=None):
    validate(image, steps, frames, width, height)
    names = {row['role']: row['name'] for row in components('motion', ENGINE, models)}
    required = {'unet_high', 'unet_low', 'clip', 'vae'}
    if not required.issubset(names):
        raise ValueError('A14B profile 缺少高/低噪声专家、文本编码器或 VAE')
    split = steps // 2
    sampler = {'steps': steps, 'cfg': 3.5, 'sampler_name': 'euler', 'scheduler': 'simple',
               'positive': ['6', 0], 'negative': ['6', 1]}
    return {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': names['unet_high']}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': names['clip'], 'type': 'wan', 'device': 'cpu'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': names['vae']}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': prompt}},
        '5': {'class_type': 'CLIPTextEncode', 'inputs': {'clip': ['2', 0], 'text': NEGATIVE}},
        '6': {'class_type': 'WanImageToVideo', 'inputs': {
            'positive': ['4', 0], 'negative': ['5', 0], 'vae': ['3', 0],
            'width': width, 'height': height, 'length': frames, 'batch_size': 1, 'start_image': ['11', 0]}},
        '7': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['1', 0], 'shift': 5.0}},
        '8': {'class_type': 'KSamplerAdvanced', 'inputs': {
            **sampler, 'model': ['7', 0], 'latent_image': ['6', 2], 'noise_seed': seed,
            'add_noise': 'enable', 'start_at_step': 0, 'end_at_step': split, 'return_with_leftover_noise': 'enable'}},
        '9': {'class_type': 'VAEDecodeTiled', 'inputs': {
            'samples': ['15', 0], 'vae': ['3', 0], 'tile_size': 256, 'overlap': 64,
            'temporal_size': 128, 'temporal_overlap': 16}},
        '10': {'class_type': 'SaveImage', 'inputs': {
            'images': ['9', 0], 'filename_prefix': 'AI-Video/Wan-A14B/' + uuid.uuid4().hex[:12]}},
        '11': {'class_type': 'LoadImage', 'inputs': {'image': image}},
        '12': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': names['unet_low']}},
        '13': {'class_type': 'ModelSamplingSD3', 'inputs': {'model': ['12', 0], 'shift': 5.0}},
        '14': {'class_type': 'KSamplerAdvanced', 'inputs': {
            **sampler, 'model': ['13', 0], 'latent_image': ['8', 0], 'noise_seed': 0,
            'add_noise': 'disable', 'start_at_step': split, 'end_at_step': steps,
            'return_with_leftover_noise': 'disable'}},
        '15': {'class_type': 'SaveLatent', 'inputs': {
            'samples': ['14', 0], 'filename_prefix': 'AI-Video/Wan-A14B/latents/' + uuid.uuid4().hex[:12]}},
    }
