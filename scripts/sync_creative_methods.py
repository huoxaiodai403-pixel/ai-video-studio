"""Project the pinned creative methods and editable examples into the web catalog.

Run after changing either source catalog. Tests compare the projection to prevent
installed article skills disappearing from the workflow picker again.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / 'skills/ai-video-studio/references'
START = '/* creative-methods:start */'
END = '/* creative-methods:end */'
# Category, web engine, preparation, and the actual web delivery boundary.
PRESENTATION = {
    'huashu-art-motion': ('animation', 'code-animation', '一个要解释的机制；图表需准备真实数据、单位与来源。', '网页生成可编辑的二维代码动画；复杂视觉语法可交给 Codex 深入制作。'),
    'vox-director': ('knowledge', 'character-story', '讲解文稿、可使用的图片与素材来源。', '网页先生成配图与旁白；精细纸张分层和拼贴运动由 Codex 配合制作。'),
    'hand-drawn-video-prompts': ('knowledge', 'code-animation', '一句核心观点，以及对应的可见比喻。', '网页生成二维手绘动效与旁白；角色表演可换用角色叙事工作流。'),
    'stickman-video-director': ('story', 'code-animation', '短故事、角色比例，以及每一镜的主要动作。', '网页制作二维动作叙事；需要模型生成的连续表演时使用角色叙事。'),
    'kid-papercraft': ('story', 'code-animation', '祝福内容；需要出现姓名和年龄时自行填写。', '网页制作二维纸艺动效与配音；立体角色动画需另行制作。'),
    'classical-poem-silk-video': ('knowledge', 'character-story', '核对过的诗词原文、作者，以及希望出现的意象。', '网页生成国风配图、朗诵与字幕；精细局部雨水、涟漪合成可交给 Codex。'),
    'hbg-life-simulation': ('story', 'character-story', '人物经历、角色关系与可核实资料，先选一个章节。', '网页生成有声漫画短章；长篇需分章补齐素材并逐段检查。'),
    'simon-skills': ('knowledge', 'whiteboard', '一个问题、关键词和图形之间的关系。', '在白板编辑器制作逐笔画面、旁白、字幕与封面；调查长片有独立入口。'),
    'director': ('story', 'code-animation', '故事视角、角色约定、起因与结尾。', '网页制作二维故事动画；写实表演可转角色叙事，复杂场景交给 Codex。'),
    'book-sales-video': ('knowledge', 'character-story', '书名、作者、核实过的原文与个人观点，注明引用来源。', '网页制作有声书评短片；不自动抓取或核验书籍内容。'),
}


def catalog():
    sources = json.loads((REFERENCES / 'creative-sources.json').read_text('utf-8'))['skills']
    production = {row['id']: row for row in json.loads((REFERENCES / 'creative-production-catalog.json').read_text('utf-8'))['methods']}
    rows = []
    for source in sources:
        identity = source['id']
        category, route, preparation, delivery = PRESENTATION[identity]
        if route != 'whiteboard':
            delivery += ' 可输入自己的主题与原稿，通过所选编剧和生成器重新制作；也可由 Codex 接管同一工程。示例复刻为独立选项。'
        example = json.loads((ROOT / production[identity]['example']).read_text('utf-8'))
        if route == 'whiteboard':
            example = example['storyboard']
        rows.append(dict(id=identity, title=source['title'], category=category, route=route,
                         customStyle=__import__('creative_custom').STYLES.get(identity,''),
                         preparation=preparation, delivery=delivery, guidance=source['guidance'],
                         sampleTitle=example['title'], source=source['upstream_url'],
                         example={key: example.get(key, '') for key in ('title', 'brief', 'style', 'character')},
                         shots=[{key: scene.get(key, '') for key in ('narration', 'visual', 'action', 'camera')}
                                for scene in example.get('scenes', [])] if route != 'whiteboard' else []))
    return rows


def projection():
    return START + '\nconst creativeMethods = ' + json.dumps(catalog(), ensure_ascii=False, indent=2) + ';\n' + END


if __name__ == '__main__':
    target = ROOT / 'scripts/workflows.js'
    text = target.read_text('utf-8')
    start, end = text.index(START), text.index(END) + len(END)
    target.write_text(text[:start] + projection() + text[end:], encoding='utf-8')
