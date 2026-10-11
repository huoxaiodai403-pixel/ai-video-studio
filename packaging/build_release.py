"""Build source-only Windows and Codex-skill archives from an explicit allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
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
EXTENSIONS = {'.py', '.ps1', '.cmd', '.js', '.mjs', '.cjs', '.tsx', '.css', '.html', '.json', '.md', '.yaml', '.yml', '.txt'}
SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b'),
]
# Kept as an internal compatibility marker, not a product variant.
REQUIRED = {'README.md', 'LICENSE', 'VERSION', 'EDITION', 'requirements-studio.txt',
            'runtime-dependencies.json', 'scripts/Install-Studio.ps1', 'scripts/Start-Studio.ps1',
            'scripts/Install-CodexSkill.ps1', 'scripts/studio.py', 'scripts/web_shell.py',
            'scripts/Studio-Setup.ps1', 'scripts/studio_launcher.py', 'scripts/renderer_health.py', 'scripts/studio-storage.js',
            'scripts/studio_edition.py', 'scripts/provider_worker.py', 'scripts/tool-draft-state.js',
            'scripts/generation_workers.py', 'scripts/code_animation.py',
            'scripts/render_code_animation.cjs', 'skills/ai-video-studio/SKILL.md',
            'skills/ai-video-studio/EDITION', 'examples/storyboard.json',
            'packaging/build_release.py', 'packaging/source-profile.json'}


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or
            name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/')) or
            PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe source member name')
    return name


def source_profile(root=ROOT):
    value = json.loads((Path(root) / 'packaging/source-profile.json').read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or set(value) != {'schema', 'description', 'include'}
            or value.get('schema') != 1 or not isinstance(value.get('description'), str)
            or not isinstance(value.get('include'), list)):
        raise ValueError('Invalid source profile')
    rows = value['include']
    if not rows or any(not isinstance(row, str) for row in rows) or len(rows) != len(set(rows)):
        raise ValueError('Source profile requires unique explicit file names')
    for name in rows:
        safe_name(name)
        if (set(PurePosixPath(name).parts) & {'config', 'projects', 'models', 'logs', 'cache', 'dist', '.git', '.venv', 'node_modules'}
                or name.startswith(('packaging/friend-overrides/', 'docs/frontend-'))
                or name == 'packaging/friend-profile.json' or PurePosixPath(name).name.startswith('test_')):
            raise ValueError('Private or obsolete source is not distributable: ' + name)
    if not REQUIRED.issubset(rows):
        raise ValueError('Source profile omits required runtime files')
    return value


def sources(root=ROOT):
    root = Path(root).resolve()
    bundled = set(validate_bundle(root))
    profile = source_profile(root)
    files = {root / name for name in profile['include']}
    if not bundled.issubset(files):
        raise ValueError('Source profile omits the verified whiteboard renderer')
    for path in files:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Source must be a regular file inside the repository: ' + str(path))
        limit = 30 * 1024 * 1024 if path in bundled and path.name == 'Xiaolai-Regular.ttf' else 10 * 1024 * 1024
        if path.stat().st_size > limit:
            raise ValueError('Unexpected large source file: ' + str(path.relative_to(root)))
        if any(pattern.search(path.read_bytes()) for pattern in SECRET_PATTERNS):
            raise ValueError('Possible credential found; review file before publishing: ' + str(path.relative_to(root)))
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def entries(root=ROOT, edition=None):
    """One source package; optional model adapters use the same codebase."""
    if edition not in (None, 'development'):
        raise ValueError('There is one workbench package; remove the legacy edition argument')
    root = Path(root).resolve()
    result = {path.relative_to(root).as_posix(): path.read_bytes() for path in sources(root)}
    for name in ('EDITION', 'skills/ai-video-studio/EDITION'):
        result[name] = b'development\n'
    if missing := REQUIRED - result.keys():
        raise ValueError('Missing release source: ' + ', '.join(sorted(missing)))
    version = result['VERSION'].decode('utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid VERSION')
    manifest = {'schema': 2, 'product': 'ai-video-studio', 'version': version,
                'local_models': 'optional, installed separately',
                'files': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(result.items())],
                'profile_sha256': hashlib.sha256(result['packaging/source-profile.json']).hexdigest(),
                'privacy_excludes': ['models', 'private config', 'projects', 'voice recordings', 'reference media', 'logs', 'caches']}
    result['EDITION-MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    return result


def export_source(destination, source_entries):
    """Only create files in a new/empty directory. Never delete or overwrite."""
    destination = Path(destination)
    if destination.is_symlink() or getattr(destination, 'is_junction', lambda: False)():
        raise ValueError('Source export destination must not be a link')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Source export requires a nonexistent or empty directory')
    for name in source_entries:
        safe_name(name)
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(source_entries.items()):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(data)
    return {'product': 'ai-video-studio', 'files': len(source_entries),
            'destination': str(destination.resolve())}


def archive(path, entries, version, edition='development'):
    if edition != 'development' or not entries:
        raise ValueError('Archive requires the single workbench source and nonempty entries')
    manifest={'version':version,'product':'ai-video-studio','files':[],'excludes':['models','private config','projects','voice recordings','reference media','logs','caches']}
    prefixes = {safe_name(name).split('/')[0] for name in entries}
    if len(prefixes) != 1 or any('/' not in name for name in entries):
        raise ValueError('Archive members must share one source directory')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(entries.items()):
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--export-source',type=Path,help='Export source only into a new or empty directory')
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    if args.list and args.export_source:
        parser.error('--list and --export-source are mutually exclusive')
    selected = 'development'
    source_entries = entries(ROOT)
    if args.list:
        print('\n'.join(sorted(source_entries)));return
    if args.export_source:
        print(json.dumps(export_source(args.export_source, source_entries),ensure_ascii=False,indent=2));return
    version=source_entries['VERSION'].decode('utf-8').strip()
    args.output.mkdir(parents=True,exist_ok=True)
    prefix='ai-video-studio-'+version
    package={prefix+'/'+name:data for name,data in source_entries.items()}
    reports=[archive(args.output/(prefix+'-windows.zip'),package,version,selected)]
    skill_prefix='ai-video-studio-skill-'+version
    skill={skill_prefix+'/ai-video-studio/'+name.removeprefix('skills/ai-video-studio/'):data
           for name,data in source_entries.items() if name.startswith('skills/ai-video-studio/')}
    skill[skill_prefix+'/Install-CodexSkill.ps1']=source_entries['scripts/Install-CodexSkill.ps1']
    skill[skill_prefix+'/LICENSE']=source_entries['LICENSE']
    skill[skill_prefix+'/EDITION']=(selected+'\n').encode()
    skill[skill_prefix+'/INSTALL.txt'] = (
        'AI Video Studio — one workbench.\r\n'
        'Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\\Install-CodexSkill.ps1\r\n'
        'Start a new Codex chat and use $ai-video-studio. Install the workbench separately. '
        'Windows CPU speech, imported media and CPU renderers need no AI model weights.\r\n'
        'Local models are optional and require separate environments and weights. '
        'Online services use your configured provider.\r\n').encode('utf-8')
    reports.append(archive(args.output/(skill_prefix+'.zip'),skill,version,selected))
    (args.output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in reports),encoding='ascii')
    (args.output/'release-manifest.json').write_text(json.dumps({'version':version,'product':'ai-video-studio','archives':reports},indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
