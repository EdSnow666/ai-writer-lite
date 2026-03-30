# 职责: 临时草稿文件管理
# 依赖外部: os
# 暴露: create_draft(), read_draft(), delete_draft()

import os

TEMP_DIR = os.path.expanduser('~/.claude/skills/ai-writer-lite/temp')

def create_draft(summary_id, content):
    """创建临时草稿文件"""
    os.makedirs(TEMP_DIR, exist_ok=True)
    path = os.path.join(TEMP_DIR, f'draft_{summary_id}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def read_draft(summary_id):
    """读取修改后的草稿"""
    path = os.path.join(TEMP_DIR, f'draft_{summary_id}.md')
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def delete_draft(summary_id):
    """删除草稿文件"""
    path = os.path.join(TEMP_DIR, f'draft_{summary_id}.md')
    if os.path.exists(path):
        os.remove(path)
