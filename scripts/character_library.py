"""Reusable, revisioned character identities shared by all production entries."""
import copy
import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs
from filelock import FileLock
from prompt_library import ROOT
import image_references
import voice_library

LOCK = threading.RLock()


def store():
    from generation_plans import _plain
    return _plain(ROOT/'assets/characters')


def ids(values, maximum=30):
    if not isinstance(values,list) or len(values)>maximum or any(not isinstance(v,str) or not re.fullmatch(r'char-[a-f0-9]{16}',v) for v in values) or len(set(values))!=len(values):
        raise ValueError(f'角色 ID 应唯一，最多 {maximum} 个')
    return list(values)


def resolve(identity, revision=None):
    ids([identity])
    folder=store()/identity
    if revision is not None and (type(revision) is not int or revision<1):
        raise ValueError('无效角色版本')
    path=folder/(f'{revision}.json' if revision else 'current.json')
    if not path.is_file():
        raise ValueError('角色不存在或版本已不可用')
    from generation_plans import _json
    row=_json(path)
    # Early development records stored resolved metadata instead of IDs. Read
    # them without rewriting history, and still verify the referenced content.
    values=row.get('reference_ids',[])
    if any(isinstance(value,dict) for value in values):
        normalized=[]
        for value in values:
            if isinstance(value,dict):
                reference=image_references.resolve(value.get('id'))
                if reference['sha256']!=value.get('sha256'):raise ValueError('角色旧版参考图校验失败')
                normalized.append(reference['id'])
            else:normalized.append(value)
        row['reference_ids']=normalized
    return row


def catalog():
    result=[]
    for path in store().glob('char-*/current.json'):
        row=resolve(path.parent.name)
        row['preview_url']=''
        row['available']=True
        try:
            if row['reference_ids']:
                row['preview_url']=image_references.resolve(row['reference_ids'][0])['preview_url']
            if row['voice_id']:
                voice_library.resolve(row['voice_id'])
        except (ValueError,OSError) as exc:
            row.update(available=False,error=str(exc))
        result.append(row)
    return sorted(result,key=lambda r:r['updated_at'],reverse=True)


def save(value):
    if not isinstance(value,dict) or set(value)-{'id','revision','name','project','appearance','wardrobe','notes','voice_id','reference_ids'}:
        raise ValueError('角色字段格式无效')
    from generation_plans import _text, _atomic
    row={k:_text(value.get(k,''),k,limit,1 if k=='name' else 0) for k,limit in
         [('name',60),('project',120),('appearance',3000),('wardrobe',1500),('notes',3000),('voice_id',100)]}
    row['reference_ids']=[ref['id'] for ref in image_references.validate_ids(value.get('reference_ids',[]))]
    row['name']=voice_library.role_name(row['name'])
    if row['voice_id']:
        voice_library.resolve(row['voice_id'])
    with LOCK:
        base=store(); base.mkdir(parents=True,exist_ok=True)
        with FileLock(str(base/'.library.lock'),timeout=10):
            if value.get('id'):
                previous=resolve(value['id'])
                if value.get('revision')!=previous['revision']:
                    raise ValueError('角色已在其他窗口修改，请重新载入后合并；当前输入保留')
                row.update(id=previous['id'],revision=previous['revision']+1,created_at=previous['created_at'])
            else:
                row.update(id='char-'+uuid.uuid4().hex[:16],revision=1,created_at=time.time())
            row['updated_at']=time.time()
            folder=base/row['id'];folder.mkdir(exist_ok=True)
            _atomic(folder/(str(row['revision'])+'.json'),row)
            _atomic(folder/'current.json',row)
    return copy.deepcopy(row)


def freeze(values):
    rows={}
    for identity in ids(values):
        row=resolve(identity)
        for ref in row['reference_ids']:
            image_references.resolve(ref)
        row['voice']=voice_library.resolve(row['voice_id'])['voice'] if row['voice_id'] else None
        rows[identity]=row
    return rows


def describe(row):
    return '\n'.join(filter(None,[row['name'],row['appearance'],row['wardrobe'],row['notes']]))


def project_cast(links):
    """Resolve explicitly selected versions; library edits never retarget a film."""
    if not isinstance(links,dict) or len(links)>30:raise ValueError('本片角色绑定格式无效')
    result={}
    for name,link in links.items():
        if not isinstance(name,str) or not isinstance(link,dict) or set(link)!={'id','revision'}:
            raise ValueError('角色绑定需要 id 与 revision')
        row=resolve(link['id'],link['revision'])
        if name!=row['name']:raise ValueError('绑定角色名称与保存版本不符，请重新带入角色')
        result[row['id']]=row
    return result


def apply_storyboard(spec):
    cast=project_cast(spec.get('character_links',{}))
    spec['character_snapshots']=copy.deepcopy(cast)
    for scene in spec.get('scenes',[]):
        chosen=ids(scene.get('character_ids',[]),4)
        if any(identity not in cast for identity in chosen):raise ValueError('镜头角色尚未带入本片')
        scene['character_context']='\n'.join(describe(cast[identity]) for identity in chosen)
        refs=list(dict.fromkeys(scene.get('image_reference_ids',[])+[ref for identity in chosen for ref in cast[identity]['reference_ids']]))
        if refs:scene['image_reference_ids']=[row['id'] for row in image_references.validate_ids(refs)]
    return spec


def get(handler, route):
    if route.path!='/api/characters':return False
    identity=parse_qs(route.query).get('id',[''])[0]
    if identity:
        row=resolve(identity)
        row['voice']=voice_library.resolve(row['voice_id'])['voice'] if row['voice_id'] else None
        handler.reply(row)
    else:handler.reply({'characters':catalog()})
    return True


def post(handler,data):
    if handler.path!='/api/characters':return False
    handler.reply(save(data));return True
