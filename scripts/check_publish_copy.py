"""Validate the workbench's publication draft without an external checkout.

Template checks adapted from Simon Skills' MIT-licensed check-publish-copy.py.
See NOTICE.md and apps/simon-skills/LICENSE. This checks document structure,
not factual accuracy, legal compliance, or a platform's current policies.
"""
import argparse
from pathlib import Path
import re

PLATFORMS = ('抖音', '快手', 'B站', '视频号', '小红书（弱化品牌名）', 'YouTube', '知乎', '公众号')
TITLE_LIMITS = {'抖音': 30, '快手': 30, 'B站': 40, '视频号': 30,
                '小红书（弱化品牌名）': 20, 'YouTube': 40, '知乎': 40, '公众号': 30}


def validate(text):
    errors = []
    if not re.search(r'^对应：', text, re.M):
        errors.append('缺少本次成片说明')
    for required in ('共用免责段（各平台正文末尾）', '标题公式（dbs-xhs-title）：'):
        if required not in text:
            errors.append('缺少模板字段：' + required)
    headings = re.findall(r'^## (.+)$', text, re.M)
    if tuple(headings) != PLATFORMS:
        errors.append('发布稿应包含模板规定的八个平台，且顺序一致')
    for name, body in zip(headings, re.split(r'^## .+$', text, flags=re.M)[1:]):
        required = ['主推标题：', '备选标题：']
        if name != '公众号':
            required += ['正文：', '（共用免责段）']
        if name in ('B站', 'YouTube'):
            required.append('章节：')
        if name == 'B站':
            required.append('本期结构：')
        if name in PLATFORMS[:5]:
            required.append('置顶评论：')
        if name == '公众号':
            required.append('摘要：')
        errors.extend(name + ' 缺少 ' + field for field in required if field not in body)
        for match in re.finditer(r'(主推标题|备选标题)：(.+)', body):
            limit = TITLE_LIMITS.get(name, 40)
            if len(match[2].strip()) > limit:
                errors.append(name + ' ' + match[1] + ' 超过模板字数限制 ' + str(limit))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', type=Path)
    args = parser.parse_args()
    errors = validate(args.document.read_text(encoding='utf-8-sig'))
    print('COPY_FAIL\n' + '\n'.join(errors) if errors else 'COPY_OK')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
