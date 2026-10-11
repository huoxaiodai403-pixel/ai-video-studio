"""Official ACE-Step runtime calls, imported only by the locked offline worker."""
import gc
import time


def render(request, work, app, models):
    """Initialize fixed local models, generate a single instrumental WAV, release CUDA."""
    import torch
    import soundfile as sf
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler
    from acestep.inference import GenerationParams, GenerationConfig, generate_music

    if not torch.cuda.is_available():
        raise RuntimeError('ACE-Step 配乐任务需要可用 CUDA；未静默改用 CPU 生成')
    torch.cuda.reset_peak_memory_stats()
    dit = llm = None
    try:
        started = time.monotonic()
        dit, llm = AceStepHandler(), LLMHandler()
        message, ready = dit.initialize_service(
            project_root=str(app), config_path='acestep-v15-turbo', device='cuda',
            use_flash_attention=False, compile_model=False, offload_to_cpu=True,
            offload_dit_to_cpu=True, quantization=None, use_mlx_dit=False)
        if not ready:
            raise RuntimeError('ACE-Step DiT 初始化失败：' + message)
        if request['thinking']:
            message, ready = llm.initialize(
                checkpoint_dir=str(models), lm_model_path='acestep-5Hz-lm-1.7B',
                backend='pt', device='cuda', offload_to_cpu=True, dtype=torch.bfloat16)
            if not ready:
                raise RuntimeError('ACE-Step LM 初始化失败：' + message)
        load_seconds = time.monotonic() - started
        params = GenerationParams(
            task_type='text2music', caption=request['prompt'], lyrics='[Instrumental]',
            instrumental=True, vocal_language='unknown', duration=request['duration_seconds'],
            bpm=request['bpm'], keyscale='C Major', timesignature='4',
            inference_steps=8, seed=request['seed'], thinking=request['thinking'],
            use_cot_caption=False, use_cot_lyrics=False, use_cot_language=False,
            enable_normalization=True, normalization_db=-1.0,
            fade_in_duration=0.5, fade_out_duration=1.0)
        config = GenerationConfig(batch_size=1, allow_lm_batch=False,
                                  use_random_seed=False, seeds=[request['seed']], audio_format='wav')
        started = time.monotonic()
        result = generate_music(dit, llm, params, config, save_dir=str(work))
        if not result.success or len(result.audios) != 1 or not result.audios[0].get('path'):
            raise RuntimeError('ACE-Step 生成失败：' + str(result.error))
        # torchaudio can emit float WAV; expose a predictable PCM16 file to the
        # workbench while retaining the original official output in this take.
        samples, sample_rate = sf.read(result.audios[0]['path'], dtype='float32', always_2d=True)
        pcm_path = work / 'bgm-pcm16.wav'
        sf.write(str(pcm_path), samples, sample_rate, subtype='PCM_16', format='WAV')
        runtime = {'backend': getattr(llm, 'llm_backend', 'pt') if request['thinking'] else 'dit-only',
                   'torch_version': torch.__version__, 'cuda_runtime': torch.version.cuda,
                   'peak_allocated_cuda_bytes': torch.cuda.max_memory_allocated(),
                   'peak_reserved_cuda_bytes': torch.cuda.max_memory_reserved(),
                   'quantization': getattr(dit, 'quantization', None), 'compile_model': False,
                   'cpu_offload': True, 'dit_cpu_offload': True,
                   'load_seconds': round(load_seconds, 3),
                   'generation_seconds': round(time.monotonic() - started, 3),
                   'parameters': params.to_dict(), 'config': config.to_dict(),
                   'official_output': result.audios[0]['path'], 'output_subtype': 'PCM_16',
                   'actual_audio_parameters': result.audios[0].get('params', {})}
        return pcm_path, runtime
    finally:
        del dit, llm
        gc.collect()
        torch.cuda.empty_cache()
