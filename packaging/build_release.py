"""Build source-only Windows and Codex-skill archives from an explicit allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from simon_source import validate_bundle
EXCLUDED_SCRIPTS = {
    'benchmark_image.py', 'benchmark_motion.py', 'inspect_wheels.py', 'integrate_director.py',
    'verify_archive.py', 'verify_director_sources.py', 'verify_video.py', 'verify_workbench.py',
    'download_wan.py',
}
EXTENSIONS = {'.py', '.ps1', '.cmd', '.js', '.mjs', '.cjs', '.css', '.html', '.json', '.md', '.yaml', '.yml', '.txt'}
SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b'),
]


def sources(root=ROOT):
    files = set()
    # Fail the build for absent, unpatched or modified renderer files.
    bundled_simon = set(validate_bundle(root))
    files.update(bundled_simon)
    for name in ('.gitignore', '.gitattributes', 'README.md', 'LICENSE', 'NOTICE.md', 'VERSION',
                 'AGENTS.md', 'requirements-studio.txt', 'runtime-dependencies.json', 'Install.cmd', 'Start.cmd'):
        path = root/name
        if path.is_file(): files.add(path)
    for path in (root/'scripts').glob('*'):
        if path.suffix in EXTENSIONS and path.name not in EXCLUDED_SCRIPTS and path.is_file(): files.add(path)
    for folder in ('docs', 'skills', 'examples', 'packaging', '.github'):
        for path in (root/folder).rglob('*'):
            if '__pycache__' not in path.parts and path.suffix in EXTENSIONS and path.is_file(): files.add(path)
    for path in (root/'assets/brand').glob('*'):
        if path.suffix in {'.svg', '.png', '.ico'} and path.is_file(): files.add(path)
    renderer = root/'apps/investigation-renderer'
    for name in ('package.json', 'package-lock.json', 'bun.lock', 'contract.mjs', 'contract.test.mjs',
                 'render.mjs', 'README.md', 'NOTICE.md', 'LICENSE.simon-skills', '.gitignore'):
        path = renderer/name
        if path.is_file(): files.add(path)
    for folder in ('src', 'fonts'):
        for path in (renderer/folder).rglob('*'):
            if path.is_file() and path.suffix in EXTENSIONS | {'.jsx', '.tsx', '.woff2'}: files.add(path)
    for path in (root/'workflows').glob('*'):
        if path.is_file() and (path.suffix == '.json' or path.name == 'simon-windows.patch'): files.add(path)
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Source must be a regular file inside the repository: '+str(path))
        limit = 30*1024*1024 if path in bundled_simon and path.name == 'Xiaolai-Regular.ttf' else 10*1024*1024
        if path.stat().st_size > limit:
            raise ValueError('Unexpected large source file: '+str(path.relative_to(root)))
        data=path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError('Possible credential found; review file before publishing: '+str(path.relative_to(root)))
    return sorted(files, key=lambda p:p.relative_to(root).as_posix())


def archive(path, entries, version):
    manifest={'version':version,'files':[],'excludes':['models','private config','projects','voice recordings','reference media','logs','caches']}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(entries.items()):
            if name.startswith('/') or '..' in Path(name).parts: raise ValueError('Unsafe archive member')
            item=zipfile.ZipInfo(name, (2026,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            item.external_attr=0o644<<16;output.writestr(item,data)
            manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        first=next(iter(entries)).split('/')[0]
        member=zipfile.ZipInfo(first+'/PACKAGE-MANIFEST.json',(2026,1,1,0,0,0));member.compress_type=zipfile.ZIP_DEFLATED
        output.writestr(member,json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
    with zipfile.ZipFile(path) as check:
        if check.testzip():raise ValueError('Archive CRC verification failed')
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'members':len(entries)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--list',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'dist');args=parser.parse_args()
    files=sources()
    if args.list:
        print('\n'.join(p.relative_to(ROOT).as_posix() for p in files));return
    required=('README.md','LICENSE','requirements-studio.txt','runtime-dependencies.json','scripts/Install-Studio.ps1','scripts/Install-CodexSkill.ps1',
              'skills/ai-video-studio/SKILL.md','examples/storyboard.json')
    names={p.relative_to(ROOT).as_posix() for p in files}
    if missing:=set(required)-names:raise ValueError('Missing release source: '+', '.join(sorted(missing)))
    version=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid VERSION')
    args.output.mkdir(parents=True,exist_ok=True)
    prefix='ai-video-studio-'+version
    entries={prefix+'/'+p.relative_to(ROOT).as_posix():p.read_bytes() for p in files}
    reports=[archive(args.output/(prefix+'-windows.zip'),entries,version)]
    skill_root=ROOT/'skills/ai-video-studio';skill_prefix='ai-video-studio-skill-'+version
    skill={skill_prefix+'/ai-video-studio/'+p.relative_to(skill_root).as_posix():p.read_bytes() for p in files if p.is_relative_to(skill_root)}
    skill[skill_prefix+'/Install-CodexSkill.ps1']=(ROOT/'scripts/Install-CodexSkill.ps1').read_bytes()
    skill[skill_prefix+'/LICENSE']=(ROOT/'LICENSE').read_bytes()
    skill[skill_prefix+'/INSTALL.txt']=b'Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\\Install-CodexSkill.ps1\r\nStart a new Codex chat and use $ai-video-studio. Install the workbench separately. Codex writes storyboards and can use its built-in image tool when available. CPU whiteboard previews need no media model or API key; Windows CPU speech and Edge online speech can produce narration and subtitles without model weights or API keys. Generative video needs its own service or local model.\r\nWorkbench: https://github.com/huoxaiodai403-pixel/ai-video-studio\r\n'
    reports.append(archive(args.output/(skill_prefix+'.zip'),skill,version))
    (args.output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in reports),encoding='ascii')
    (args.output/'release-manifest.json').write_text(json.dumps({'version':version,'archives':reports},indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
