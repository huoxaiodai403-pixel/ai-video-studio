"""Friend edition worker: render self-contained code animation only."""
import argparse
import json
from pathlib import Path


def blender_path():
    return None


def normalize(kind, payload):
    if kind != 'code-animation':
        raise ValueError('朋友版仅支持代码动画和手绘白板')
    import code_animation
    return code_animation.normalize(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['code-animation'])
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        request = json.loads((args.directory/'render-request.json').read_text(encoding='utf-8'))
        import code_animation
        result = code_animation.render(request['payload'], args.directory, preview=request['preview'])
        (args.directory/'render-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        (args.directory/'failure.json').write_text(json.dumps({'error': str(exc)}, ensure_ascii=False), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
