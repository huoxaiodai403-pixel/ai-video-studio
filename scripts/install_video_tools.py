"""Install pinned video Skills as isolated project dependencies; never execute their setup scripts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def git(args, cwd):
    env = os.environ.copy(); env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes'
    subprocess.run(['git', *args], cwd=cwd, env=env, check=True,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def main(selected=None):
    manifest = json.loads((ROOT/'workflows/video-tools.json').read_text(encoding='utf-8'))
    skills = manifest['skills']
    if selected:
        unknown = set(selected) - {skill['id'] for skill in skills}
        if unknown: raise ValueError('未知视频技能：'+', '.join(sorted(unknown)))
        skills = [skill for skill in skills if skill['id'] in selected]
    base = ROOT/'tools/video-skills'; base.mkdir(parents=True,exist_ok=True)
    for skill in skills:
        if skill['id'] == 'imagegen': continue  # Built into Codex; image provider/import adapter lives in the workbench.
        needed = []
        for source in skill['paths']:
            name = skill['entry'] if source == '.' else Path(source).name
            target = base/name
            marker = target/'.studio-source.json'
            if target.exists():
                if marker.is_file() and json.loads(marker.read_text(encoding='utf-8')).get('ref') == skill['ref']:
                    continue
                raise ValueError('已有未核验或其他版本的技能，已保留：'+str(target))
            needed.append((source,target))
        if not needed: continue
        with tempfile.TemporaryDirectory(prefix='video-skills-') as temp:
            checkout = Path(temp)
            git(['init'],checkout)
            git(['remote','add','origin','git@github.com:'+skill['repo']+'.git'],checkout)
            try: git(['fetch','--depth=1','--filter=blob:none','origin',skill['ref']],checkout)
            except subprocess.CalledProcessError:
                git(['remote','set-url','origin','https://github.com/'+skill['repo']+'.git'],checkout)
                git(['fetch','--depth=1','--filter=blob:none','origin',skill['ref']],checkout)
            if all(source != '.' for source,_ in needed):
                git(['sparse-checkout','init','--cone'],checkout)
                git(['sparse-checkout','set',*[source for source,_ in needed]],checkout)
            git(['checkout','--detach','FETCH_HEAD'],checkout)
            for source,target in needed:
                folder = checkout/source
                if not (folder/'SKILL.md').is_file(): raise ValueError('上游缺少 SKILL.md：'+skill['repo'])
                for path in folder.rglob('*'):
                    if '.git' in path.parts: continue
                    if path.is_symlink(): raise ValueError('技能含符号链接，未安装：'+str(path))
                shutil.copytree(folder,target,ignore=shutil.ignore_patterns('.git','node_modules','__pycache__','.venv*'))
                (target/'.studio-source.json').write_text(json.dumps({'repo':skill['repo'],'ref':skill['ref'],'path':source},indent=2),encoding='utf-8')
                print('Installed '+target.name,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', action='append', help='Install only this pinned skill; repeat for more than one')
    main(parser.parse_args().skill)
