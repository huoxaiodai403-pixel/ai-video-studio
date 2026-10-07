"""Rebuild this installation's CPU import receipts; never download or load models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {
    'qwen': ('qwen-tts', 'apps/qwen-tts/installation.json', ('qwen_tts', 'torch', 'torchaudio', 'soundfile', 'transformers')),
    'ace': ('ace-step', 'manifests/ace-step.import-probe.json', ('torch', 'torchaudio', 'torchao', 'soundfile', 'acestep.handler', 'acestep.llm_inference', 'acestep.inference')),
    'sfx': ('stable-audio-3', 'manifests/stable-audio-3.import-probe.json', ('numpy', 'soundfile', 'sentencepiece', 'ai_edge_litert.compiled_model', 'ai_edge_litert.cpu_options', 'ai_edge_litert.hardware_accelerator')),
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)


def probe(engine):
    app, receipt, modules = ENGINES[engine]
    app=ROOT/'apps'/app
    python=app/'.venv/Scripts/python.exe'
    if not python.is_file():raise FileNotFoundError('先安装独立运行环境：'+str(python))
    # Modules are fixed in source, never user-submitted code. The child gets no GPU.
    code='import importlib,json,sys; names=json.loads(sys.argv[1]); [importlib.import_module(name) for name in names]; print(json.dumps({"imports":names,"python":sys.version,"cuda_initialized":bool(sys.modules.get("torch") and sys.modules["torch"].cuda.is_initialized())}))'
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONUTF8='1')
    result=subprocess.run([str(python),'-c',code,json.dumps(list(modules))],cwd=app,env=env,
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
    data={'ready':False,'import_verified':False,'checked_at':time.time(),'gpu_run':False,'model_initialized':False}
    if result.returncode:
        data['message']='离线 CPU 依赖导入失败：'+result.stderr[-2000:]
    else:
        try:
            imported=json.loads(result.stdout.strip().splitlines()[-1])
            if imported['cuda_initialized']:raise ValueError('导入时意外初始化了 CUDA')
            data.update(imported,ready=True,import_verified=True,message='本机离线 CPU 导入通过；未加载模型、未运行推理。')
        except (ValueError,KeyError,IndexError) as error:data['message']='无法核对导入结果：'+str(error)
    destination=ROOT/receipt
    if destination.is_file():
        try:previous=json.loads(destination.read_text(encoding='utf-8'))
        except (OSError,ValueError):previous={}
        previous.update(data);data=previous
    write(destination,data)
    return data


def verify_sfx_models():
    import stable_sfx
    records=[]
    for name,size,expected in stable_sfx.MODEL_FILES:
        path=stable_sfx.MODELS/name
        if not path.is_file() or path.stat().st_size!=size:raise ValueError('缺少或尺寸不符：'+str(path))
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
        actual=digest.hexdigest()
        if actual!=expected:raise ValueError('SHA256 不符：'+str(path))
        value={'sha256':actual,'size':size,'verified_at':time.time()}
        write(path.with_name(path.name+'.verified.json'),value)
        records.append({'file':name,**value})
    return records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',required=True,choices=ENGINES)
    parser.add_argument('--verify-models',action='store_true',help='SFX: hash all three installed files; downloads nothing')
    args=parser.parse_args()
    if args.verify_models and args.engine!='sfx':parser.error('--verify-models 目前仅用于 SFX；ACE 使用公开下载清单校验器')
    result=probe(args.engine)
    if result['ready'] and args.verify_models:result['model_files']=verify_sfx_models()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['ready']:raise SystemExit(1)


if __name__=='__main__':main()
