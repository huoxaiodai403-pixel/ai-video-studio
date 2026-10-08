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
EXTENSIONS = {'.py', '.ps1', '.cmd', '.js', '.mjs', '.cjs', '.css', '.html', '.json', '.md', '.yaml', '.yml', '.txt'}
SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b'),
]
EDITIONS = ('development', 'friend')
OVERRIDES = 'packaging/friend-overrides/'
REQUIRED = {'README.md', 'LICENSE', 'VERSION', 'EDITION', 'requirements-studio.txt',
            'runtime-dependencies.json', 'scripts/Install-Studio.ps1', 'scripts/Start-Studio.ps1',
            'scripts/Install-CodexSkill.ps1', 'scripts/studio.py', 'scripts/web_shell.py',
            'scripts/studio_edition.py',
            'scripts/generation_workers.py', 'scripts/code_animation.py',
            'scripts/render_code_animation.cjs', 'skills/ai-video-studio/SKILL.md',
            'skills/ai-video-studio/EDITION',
            'examples/storyboard.json', 'packaging/build_release.py', 'packaging/friend-profile.json'}
REQUIRED_FRIEND_OVERRIDES = {'README.md', 'docs/getting-started.md', 'scripts/home.html',
                            'docs/generation-workshop.md',
                            'docs/architecture.md', 'docs/local-models.md', 'docs/references.md', 'scripts/learn.html', 'scripts/assets.html',
                            'scripts/workflows.html', 'scripts/generation_workers.py',
                            'skills/ai-video-studio/EDITION', 'skills/ai-video-studio/SKILL.md',
                            'skills/ai-video-studio/references/api.md',
                            'skills/ai-video-studio/references/generation.md',
                            'skills/ai-video-studio/references/whiteboard-request.json',
                            'skills/ai-video-studio/agents/openai.yaml'}
FRIEND_FORBIDDEN = {'scripts/' + name for name in (
    'generation_visual.py', 'blender_previs_scene.py', 'investigation_api.py',
    'investigation_draft.py', 'investigation_pipeline.py', 'investigation.html', 'investigation.js',
    'enhancement.py', 'enhance.html', 'music_api.py', 'ace_bgm.py', 'ace_bgm_runtime.py',
    'stable_sfx.py', 'music.html', 'music.js', 'novel.html', 'novel.js', 'production.html',
    'motion.html', 'subtitles.html', 'local-models.html', 'local-models.js', 'models.html',
    'model-library.html', 'model-library.js', 'download_model_plan.py', 'download_ranges.py',
    'download_wan.py', 'verify_local_engines.py', 'science_animation.py', 'local_catalog.py',
    'testing_support.py', 'director.html', 'director.js', 'studio.html')}


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or
            name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/')) or
            PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe source member name')
    return name


def edition_for(root=ROOT, requested=None):
    marker = Path(root) / 'EDITION'
    current = marker.read_text(encoding='utf-8-sig').strip() if marker.is_file() else 'development'
    if current not in EDITIONS or (requested is not None and requested not in EDITIONS):
        raise ValueError('Unknown edition; expected development or friend')
    selected = requested or current
    if current == 'friend' and selected != 'friend':
        raise ValueError('A friend source tree cannot produce a development edition')
    return selected, current


def friend_profile(root=ROOT):
    value = json.loads((Path(root) / 'packaging/friend-profile.json').read_text(encoding='utf-8'))
    keys = {'schema', 'edition', 'description', 'include', 'overrides'}
    if (not isinstance(value, dict) or set(value) != keys or value.get('schema') != 1 or
            value.get('edition') != 'friend' or not isinstance(value.get('description'), str)):
        raise ValueError('Invalid friend profile schema')
    for field in ('include', 'overrides'):
        rows = value[field]
        if not isinstance(rows, list) or not rows or any(not isinstance(row, str) for row in rows):
            raise ValueError('Friend profile requires an explicit nonempty ' + field + ' list')
        if len(rows) != len(set(rows)):
            raise ValueError('Duplicate paths in friend profile: ' + field)
        for row in rows:
            safe_name(row)
            if row.startswith(OVERRIDES) or set(PurePosixPath(row).parts) & {'config', 'projects', 'models', 'logs', 'cache', '.git', '.venv', 'node_modules'}:
                raise ValueError('Private or override source cannot appear in friend profile')
            if (row in FRIEND_FORBIDDEN or PurePosixPath(row).name.startswith('test_') or
                    row.startswith(('docs/frontend-', 'apps/investigation-renderer/'))):
                raise ValueError('Development-only source cannot appear in friend profile: ' + row)
    if not REQUIRED.issubset(value['include']) or not set(value['overrides']).issubset(value['include']):
        raise ValueError('Friend profile omits required runtime files or includes undeclared overrides')
    if not REQUIRED_FRIEND_OVERRIDES.issubset(value['overrides']):
        raise ValueError('Friend profile omits required product/skill overrides')
    return value


def sources(root=ROOT):
    files = set()
    # Fail the build for absent, unpatched or modified renderer files.
    bundled_simon = set(validate_bundle(root))
    files.update(bundled_simon)
    for name in ('.gitignore', '.gitattributes', 'README.md', 'LICENSE', 'NOTICE.md', 'VERSION', 'EDITION', 'EDITION-MANIFEST.json',
                 'AGENTS.md', 'requirements-studio.txt', 'runtime-dependencies.json', 'Install.cmd', 'Start.cmd'):
        path = root/name
        if path.is_file(): files.add(path)
    for path in (root/'scripts').glob('*'):
        if path.suffix in EXTENSIONS and path.name not in EXCLUDED_SCRIPTS and path.is_file(): files.add(path)
    for folder in ('docs', 'skills', 'examples', 'packaging', '.github'):
        for path in (root/folder).rglob('*'):
            if '__pycache__' not in path.parts and (path.suffix in EXTENSIONS or path.name == 'EDITION') and path.is_file(): files.add(path)
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


def entries(root=ROOT, edition=None):
    """Return validated relative member bytes; friend is an exact source allowlist."""
    root = Path(root).resolve()
    selected, current = edition_for(root, edition)
    result = {path.relative_to(root).as_posix(): path.read_bytes() for path in sources(root)}
    previous = result.pop('EDITION-MANIFEST.json', None)
    profile = None
    if selected == 'friend':
        profile = friend_profile(root)
        applied_overrides = set(profile['overrides'])
        if current == 'friend' and previous:
            applied_overrides.update(json.loads(previous).get('overridden_paths', []))
        if not applied_overrides.issubset(profile['include']):
            raise ValueError('Previous friend override targets are outside the source profile')
        included = set(profile['include']) - {'EDITION', 'EDITION-MANIFEST.json', 'skills/ai-video-studio/EDITION'}
        generated_overrides = set(profile['overrides']) if current == 'development' else set()
        missing = included - result.keys() - generated_overrides
        if missing:
            raise ValueError('Friend profile source files are missing: ' + ', '.join(sorted(missing)))
        result = {name: result[name] for name in sorted(included) if name in result}
        if current == 'development':
            for path in (root / OVERRIDES).rglob('*'):
                if path.is_file():
                    name = path.relative_to(root / OVERRIDES).as_posix()
                    if name not in profile['include']:
                        raise ValueError('Friend override target is outside the source profile: ' + name)
                    applied_overrides.add(name)
            for name in sorted(applied_overrides):
                path = root / OVERRIDES / name
                if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root / OVERRIDES.rstrip('/')):
                    raise ValueError('Required friend override is missing or unsafe: ' + name)
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError('Unexpected large friend override: ' + name)
                data = path.read_bytes()
                if any(pattern.search(data) for pattern in SECRET_PATTERNS):
                    raise ValueError('Possible credential found in friend override: ' + name)
                result[name] = data
        # An exported friend tree contains already-overridden source, not private
        # templates. It can rebuild itself, but cannot opt back into development.
        if any(name.startswith(OVERRIDES) for name in result):
            raise ValueError('Friend source must not contain override templates')
    result['EDITION'] = (selected + '\n').encode('utf-8')
    result['skills/ai-video-studio/EDITION'] = (selected + '\n').encode('utf-8')
    if missing := REQUIRED - result.keys():
        raise ValueError('Missing release source: ' + ', '.join(sorted(missing)))
    version = result['VERSION'].decode('utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid VERSION')
    manifest = {'schema': 1, 'edition': selected, 'version': version,
                'files': [{'path': name, 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(result.items())],
                'privacy_excludes': ['models', 'private config', 'projects', 'voice recordings', 'reference media', 'logs', 'caches']}
    if profile:
        manifest['profile_sha256'] = hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        manifest['overridden_paths'] = sorted(applied_overrides)
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
    return {'edition': source_entries['EDITION'].decode().strip(), 'files': len(source_entries),
            'destination': str(destination.resolve())}


def archive(path, entries, version, edition='development'):
    if edition not in EDITIONS or not entries:
        raise ValueError('Archive requires a known edition and nonempty entries')
    manifest={'version':version,'edition':edition,'files':[],'excludes':['models','private config','projects','voice recordings','reference media','logs','caches']}
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
    parser.add_argument('--edition',choices=EDITIONS)
    parser.add_argument('--export-source',type=Path,help='Export source only into a new or empty directory')
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    if args.list and args.export_source:
        parser.error('--list and --export-source are mutually exclusive')
    selected, _ = edition_for(ROOT, args.edition)
    source_entries = entries(ROOT, selected)
    if args.list:
        print('\n'.join(sorted(source_entries)));return
    if args.export_source:
        print(json.dumps(export_source(args.export_source, source_entries),ensure_ascii=False,indent=2));return
    version=source_entries['VERSION'].decode('utf-8').strip()
    args.output.mkdir(parents=True,exist_ok=True)
    prefix='ai-video-studio-'+selected+'-'+version
    package={prefix+'/'+name:data for name,data in source_entries.items()}
    reports=[archive(args.output/(prefix+'-windows.zip'),package,version,selected)]
    skill_prefix='ai-video-studio-'+selected+'-skill-'+version
    skill={skill_prefix+'/ai-video-studio/'+name.removeprefix('skills/ai-video-studio/'):data
           for name,data in source_entries.items() if name.startswith('skills/ai-video-studio/')}
    skill[skill_prefix+'/Install-CodexSkill.ps1']=source_entries['scripts/Install-CodexSkill.ps1']
    skill[skill_prefix+'/LICENSE']=source_entries['LICENSE']
    skill[skill_prefix+'/EDITION']=(selected+'\n').encode()
    repository = 'ai-video-studio-dev' if selected == 'development' else 'ai-video-studio'
    capabilities = ('The development workbench retains advanced local-model and experimental generation workflows. '
                    'These need their own installed models or services.\r\n' if selected == 'development' else
                    'The friend workbench provides code animation, whiteboard, narration and the shared media library. '
                    'It does not include experimental character/Blender generation or advanced model installation.\r\n')
    skill[skill_prefix+'/INSTALL.txt'] = (
        'Edition: '+selected+'\r\nRun: powershell -NoProfile -ExecutionPolicy Bypass -File .\\Install-CodexSkill.ps1\r\n'
        'Start a new Codex chat and use $ai-video-studio. Install the workbench separately. '
        'Windows CPU speech and code animation need no media-model weights.\r\n'+capabilities+
        'Workbench: https://github.com/huoxaiodai403-pixel/'+repository+'\r\n').encode('utf-8')
    reports.append(archive(args.output/(skill_prefix+'.zip'),skill,version,selected))
    (args.output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in reports),encoding='ascii')
    (args.output/'release-manifest.json').write_text(json.dumps({'version':version,'edition':selected,'archives':reports},indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
