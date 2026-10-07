"""Local prompt reference search and Qwen scene template compilation."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'apps/prompt-library'
DATA = REPO / 'data/cases.json'


def cases():
    return json.loads(DATA.read_text(encoding='utf-8'))['cases'] if DATA.is_file() else []


def search(query='', limit=30, library='image'):
    words = query.lower().split()
    rows = []
    video_data = ROOT/'apps/seedance-reference/data/cases.json'
    dataset = cases() if library == 'image' else json.loads(video_data.read_text(encoding='utf-8'))['cases'] if video_data.is_file() else []
    for case in dataset:
        haystack = json.dumps(case, ensure_ascii=False).lower()
        score = sum(word in haystack for word in words)
        if not words or score:
            rows.append((score, case))
    rows.sort(key=lambda row: row[0], reverse=True)
    return [case for _, case in rows[:limit]]


def compile_prompt(subject, style, composition, palette, case_id=None, reference_text=''):
    selected = next((c for c in cases() if c['id'] == case_id), None)
    prompt = '\n'.join([
        f'一帧用于中文短片的电影画面。画面内容：{subject}。',
        f'视觉风格：{style}。构图：{composition}。配色：{palette}。',
        '主体清楚，信息层级清晰，画面底部预留字幕空间。画面中不要出现文字、标注、徽标或水印。',
        f'补充画面要求：{reference_text}' if reference_text else '',
    ]).strip()
    return {
        'model': 'Qwen-Image-2512-Q4_K_M', 'prompt': prompt,
        'negative_prompt': '模糊，低画质，文字，乱码，水印，肢体畸形，混乱构图',
        'source_case_id': case_id,
        'source_url': selected['githubUrl'] if selected else None,
        'original_prompt': selected['prompt'] if selected else None,
        'adaptation': '依据案例提炼镜头、构图、光线或材质方法；按当前分镜改写题材与主体，不照搬案例人物和事件。',
        'source_commit': source_commit() if selected else None,
    }


def source_commit():
    if not (REPO/'.git').exists(): return None
    try:
        return subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('query', nargs='?', default='')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--library', choices=['image','seedance'], default='image')
    args = parser.parse_args()
    print(json.dumps(search(args.query, args.limit, args.library), ensure_ascii=False, indent=2))
