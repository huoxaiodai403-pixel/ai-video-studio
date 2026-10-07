"""Source-attributed directing presets. No network calls or implicit generation."""
import copy
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('camera-basic', '运镜词典 · 基础篇', 'adrianpunk115', '2104172387575222768'),
    ('camera-advanced', '运镜词典 · 进阶篇', 'adrianpunk115', '2104523576020017575'),
    ('image-recipes', '照片编辑与素材 · 12 种玩法', 'khazix0918', '2104401048324743646'),
    ('goodcase', 'GoodCase · 视频模板与工作流', 'aiwarts', '2102240456092626951'),
]

# Editorial summaries; full source text and media remain in the source archive.
CAMERAS = [
    ('locked', '固定镜头', '摄影机固定位置与朝向，主体在画面内行动。', '适合对白、产品与运动对照。'),
    ('pan', '水平摇镜 Pan', '摄影机位置不动，仅水平转动朝向，揭示画外信息。', '摇镜不是摄影机横移。'),
    ('whip', '甩镜 Whip pan', '摄影机快速水平转向，以短暂运动模糊连接两处视线目标。', '写清起点与落点，避免持续乱晃。'),
    ('tilt', '俯仰摇镜 Tilt', '摄影机位置不动，仅向上或向下转动朝向。', '不要与摄影机整体升降混淆。'),
    ('zoom', '光学变焦 Zoom', '摄影机位置不变，通过焦距变化改变景别。', '透视关系保持稳定，不写成向前行走。'),
    ('rack', '焦点转移 Rack focus', '构图与机位固定，焦点从前景目标转移到后景目标。', '指定两个处于不同深度的清晰目标。'),
    ('dolly-in', '推近 Dolly in', '摄影机沿纵深向主体靠近，产生自然透视与视差变化。', '人物保持位置，明确最后的景别。'),
    ('dolly-out', '拉远 Dolly out', '摄影机从主体向后移动，逐渐展示周围空间。', '写明拉远后出现的环境信息。'),
    ('truck', '横移 Truck', '摄影机横向平移，前后景产生视差，朝向保持稳定。', '横移不是站在原地摇镜。'),
    ('pedestal', '升降 Pedestal', '摄影机整体垂直升降，朝向保持稳定。', '升降不是原地抬头或低头。'),
    ('tracking', '跟拍 Tracking', '摄影机与行动中的主体同步移动，保持约定距离与景别。', '分别说明人物路线和摄影机路线。'),
    ('orbit', '环绕 Orbit', '摄影机围绕主体沿圆弧移动，主体留在画面中心。', '短镜头只走一小段圆弧。'),
    ('handheld', '手持 Handheld', '摄影机有克制的身体呼吸式微晃，围绕明确目标拍摄。', '手持是稳定性风格，不等于随机抖动。'),
    ('gimbal', '稳定器跟拍', '摄影机平滑跟随人物路径，稳定地保持距离与高度。', '减少微晃，描述绕障和停止位置。'),
    ('crane', '摇臂 Crane / Jib', '摄影机沿上升或下降的弧线运动，逐步揭示空间。', '弧线运动区别于纯垂直升降。'),
    ('drone', '航拍 Drone', '摄影机从明确高空位置沿路线平稳飞行，保持地标可辨识。', '写明高度、航向和终点，避免穿透建筑。'),
    ('pov', '第一人称 POV', '摄影机代表角色双眼，沿角色实际行走路线观察环境。', '不凭空切换到第三人称视角。'),
    ('fpv', '穿越机 FPV', '摄影机沿连续飞行路线穿过明确通道，仅轻微侧倾转弯。', '高难度；先验证简单路径，避免全滚转与穿墙。'),
    ('roll', '镜头滚转 Roll', '摄影机绕光轴旋转，地平线随之倾斜。', '区别于固定倾斜构图；限制旋转幅度。'),
    ('dolly-zoom', '滑动变焦 Dolly zoom', '摄影机推近同时拉长视野（缩短焦距），主体画面大小不变，背景透视扩张。', '高难度；单一居中主体、明显纵深参照，需实测。'),
    ('long-take', '连续长镜头', '摄影机沿连贯路线完成一次持续拍摄，保留前后动作状态。', '连续性不是慢动作；本地短片需要拆分而非硬塞长时长。'),
    ('composite', '分阶段复合运镜', '先执行第一段摄影机运动，到达明确触发位置后执行第二段。', '短片最多两段，分别写明阶段和衔接条件。'),
]
RECIPES = [
    ('cleanup', '清除背景游客', '1 张原照片', '只移除指定背景游客，以邻近场景自然补全；保留主角、构图和光线。'),
    ('lighting', '修正光线与清晰度', '1 张原照片', '自然修正曝光、白平衡和清晰度，保留现场氛围与材质细节。'),
    ('portrait', '自然人像修饰', '1 张人像照片', '轻微整理肤色与碎发，保留本人身份、皮肤纹理与原有五官比例。'),
    ('polaroid', '拍立得立体手办', '1 张人物照片', '将主角转成可爱的黏土手办，从拍立得相框中探出；保留照片场景线索。'),
    ('postcard', '水彩旅行明信片', '1 张旅行照片', '将旅行地标转为复古水彩明信片，安排留白、地点标题与邮戳元素。'),
    ('landmark', '地标手绘贴纸', '1 张地标照片', '只将指定地标转为手绘贴纸，周围摄影背景保持原样。'),
    ('suitcase', '行李箱旅行拼贴', '多张旅行照片（原例 11 张）', '提取各张旅行照片的代表元素，绘制成二维贴纸并排布在行李箱表面。'),
    ('travel', '人物旅行海报', '人物照片 + 城市地标参考', '以人物为视觉中心，结合城市地标制作旅行海报；保持人物身份与地点特征。'),
    ('concert', '演唱会氛围素材', '人物与演唱会场景参考', '构建广角演唱会现场、背影、应援灯与纸屑，明确人物朝向与舞台位置。'),
    ('food', '食物爆炸悬浮', '1 张食物照片', '让指定食材悬浮与飞溅，保留餐具、人物和原背景，并呈现合理重力与层次。'),
    ('type', '文字涂鸦物体', '1 张目标物体照片', '用与物体主题有关的文字和线条构成目标轮廓，内部适当镂空，保持辨识度。'),
    ('notes', '手写旅行标注', '1 张旅行照片', '添加轻量手写标注、箭头和旅行小涂鸦，避开人脸和重要主体。'),
]

def zh(value):
    return value.get('zh', value.get('en', '')) if isinstance(value, dict) else value

@lru_cache(maxsize=1)
def catalog():
    folder = ROOT / 'apps/seedance-reference/data'
    def read(name):
        source = folder/name
        return json.loads(source.read_text(encoding='utf-8')) if source.is_file() else {'templates': [], 'skills': [], 'cases': []}
    base, local = read('style-library.json'), read('templates-local.json')
    templates = []
    for original in base['templates'] + local['templates']:
        row = copy.deepcopy(original)
        for key, value in local.get('overrides', {}).get(row['id'], {}).items():
            if isinstance(row.get(key), dict) and isinstance(value, dict): row[key].update(value)
            else: row[key] = value
        templates.append({key: zh(row.get(key, [] if key in ('structure','guidance','pitfalls') else '')) for key in ('id','title','description','category','useWhen','structure','guidance','pitfalls','copyPrompt')} | {'url': 'https://goodcase.ai/templates/' + row['id']})
    sources = [{'id': key, 'title': title, 'url': f'https://x.com/{user}/status/{sid}', 'local': f'https://x.com/{user}/status/{sid}'} for key, title, user, sid in SOURCES]
    cases = read('cases.json')
    cases = cases.get('cases', []) if isinstance(cases, dict) else cases
    return {'sources': sources, 'cameras': [{'id': key,'title': title,'instruction': rule,'tip': tip,'source': sources[0 if i < 12 else 1]['local']} for i,(key,title,rule,tip) in enumerate(CAMERAS)], 'recipes': [{'id':key,'title':title,'references':refs,'instruction':rule,'source':sources[2]['local']} for key,title,refs,rule in RECIPES], 'templates': templates, 'skill_count': len(read('skills.json')['skills']), 'case_count': len(cases)}

def field(data, key, default='', maximum=1200):
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > maximum: raise ValueError(f'{key} 应为不超过 {maximum} 字的文字')
    return value.strip()

def choose(kind, identity):
    return next((row for row in catalog()[kind] if row['id'] == identity), None)

def camera(data):
    row = choose('cameras', data.get('camera'))
    if row is None: raise ValueError('请选择有效运镜')
    parts = [field(data,'subject'), row['instruction']]
    for key, label in [('action','人物动作'),('framing','景别与机位'),('direction','方向与路线'),('speed','速度'),('target','对准目标'),('start','起始构图'),('end','结束构图'),('stability','稳定方式'),('invariants','全程保持')]:
        value = field(data,key)
        if value: parts.append(label+'：'+value+'。')
    parts.append('同一镜头连续拍摄，无切镜、瞬移或穿透实体。')
    prompt = '\n'.join(p for p in parts if p)
    if len(prompt)>5000: raise ValueError('镜头提示词超过 5000 字，请精简')
    return {'prompt':prompt,'tip':row['tip'],'source':row['source']}

def method_context(identity):
    if not identity: return ''
    row = choose('templates', identity)
    if row is None: raise ValueError('未知导演方法')
    return '\n导演方法：'+row['title']+'。作为创作方法参考，不能改变小说事实。将适用的运镜写入各镜头 motion_prompt，保持既定 JSON 格式。不要添加模型未提供的参考图或音频。短镜头只安排一个主要动作，长时间线拆成镜头；不保证多图身份锁定。\n'+json.dumps({key:row[key] for key in ('structure','guidance','pitfalls')}, ensure_ascii=False)

def brief(data):
    kind = data.get('kind')
    if kind not in ('templates','recipes'): raise ValueError('未知模板类型')
    row = choose(kind,data.get('id'))
    if row is None: raise ValueError('请选择有效模板')
    subject = field(data,'subject')
    if not subject: raise ValueError('请填写本次主题或编辑目标')
    if kind == 'recipes':
        prompt = f"图片编辑任务：{row['title']}\n编辑目标：{subject}\n所需参考：{row['references']}\n编辑方法：{row['instruction']}\n必须保留：{field(data,'keep','人物身份、未指定修改的物体与构图')}\n补充要求：{field(data,'extra')}\n这是图片编辑简报，必须向支持参考图编辑的模型提交原图；文字本身不能锁定身份。"
    else:
        prompt = f"视频创作主题：{subject}\n补充约束：{field(data,'extra')}\n采用模板：{row['title']}\n" + '\n'.join(['结构：']+row['structure']+['方法：']+row['guidance']+['避坑：']+row['pitfalls'])
    return {'prompt':prompt}
