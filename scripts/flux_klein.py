"""Official native FLUX.2 klein 4B distilled graph with ordered references."""
import uuid
from model_profiles import components


def workflow(prompt, seed=42, width=1024, height=576, references=None, models=None):
    files = {row['role']: row['name'] for row in components('image', 'flux2-klein-4b', models)}
    references = references or []
    if len(references) > 4:
        raise ValueError('FLUX.2 klein 最多接受 4 张有序参考图')
    graph = {
        '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': files['unet'], 'weight_dtype': 'default'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': files['clip'], 'type': 'flux2', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': files['vae']}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['2', 0]}},
        '5': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['4', 0]}},
        '6': {'class_type': 'EmptyFlux2LatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '7': {'class_type': 'CFGGuider', 'inputs': {'model': ['1', 0], 'positive': ['4', 0], 'negative': ['5', 0], 'cfg': 1.0}},
        '8': {'class_type': 'SamplerCustomAdvanced', 'inputs': {'noise': ['11', 0], 'guider': ['7', 0],
              'sampler': ['12', 0], 'sigmas': ['13', 0], 'latent_image': ['6', 0]}},
        '9': {'class_type': 'VAEDecode', 'inputs': {'samples': ['8', 0], 'vae': ['3', 0]}},
        '10': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0], 'filename_prefix': 'AI-Video/FluxKlein/'+uuid.uuid4().hex[:12]}},
        '11': {'class_type': 'RandomNoise', 'inputs': {'noise_seed': seed}},
        '12': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        '13': {'class_type': 'Flux2Scheduler', 'inputs': {'steps': 4, 'width': width, 'height': height}},
    }
    positive, negative = ['4', 0], ['5', 0]
    for index, name in enumerate(references):
        load, scale, encode, pos, neg = map(str, range(20+index*5, 25+index*5))
        graph[load] = {'class_type': 'LoadImage', 'inputs': {'image': name}}
        graph[scale] = {'class_type': 'ImageScaleToTotalPixels', 'inputs': {'image': [load, 0],
                         'upscale_method': 'area', 'megapixels': 1.0, 'resolution_steps': 16}}
        graph[encode] = {'class_type': 'VAEEncode', 'inputs': {'pixels': [scale, 0], 'vae': ['3', 0]}}
        graph[pos] = {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': positive, 'latent': [encode, 0]}}
        graph[neg] = {'class_type': 'ReferenceLatent', 'inputs': {'conditioning': negative, 'latent': [encode, 0]}}
        positive, negative = [pos, 0], [neg, 0]
    graph['7']['inputs'].update(positive=positive, negative=negative)
    return graph
