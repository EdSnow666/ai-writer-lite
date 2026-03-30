# 职责: AI 文本生成（带引用和偏好）
# 依赖内部: db.py
# 依赖外部: anthropic, os, uuid, json
# 暴露: generate_with_materials(), generate_freeform()

import os
import uuid
import json
from anthropic import Anthropic
from .db import get_conn

def get_active_preference():
    """获取当前激活的偏好模型"""
    conn = get_conn()
    cursor = conn.execute('SELECT system_prompt FROM writing_preferences WHERE is_active = 1')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def generate_with_materials(material_ids, user_intent):
    """基于素材生成带引用的文本"""
    conn = get_conn()
    materials = []
    for mid in material_ids:
        cursor = conn.execute('SELECT id, content FROM materials WHERE id = ?', (mid,))
        row = cursor.fetchone()
        if row:
            materials.append({'id': row[0], 'content': row[1]})
    conn.close()

    system_prompt = get_active_preference() or "你是一个专业的写作助手"

    materials_text = '\n\n'.join([f"[素材 {i+1}] ID: {m['id']}\n{m['content'][:200]}..."
                                   for i, m in enumerate(materials)])

    prompt = f"""基于以下素材生成文本，使用 Markdown 脚注格式引用：

{materials_text}

用户需求：{user_intent or '请综合以上素材写一段文本'}

要求：
1. 在引用处使用 [^1], [^2] 标记
2. 文末列出：[^1]: {materials[0]['id']} - 原文片段
"""

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return "⚠️ 请配置 ANTHROPIC_API_KEY 环境变量"

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text

def generate_freeform(user_intent):
    """无素材创作"""
    system_prompt = get_active_preference() or "你是一个专业的写作助手"

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return "⚠️ 请配置 ANTHROPIC_API_KEY 环境变量"

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_intent}]
    )

    return response.content[0].text

def save_summary(material_ids, user_prompt, ai_text):
    """保存摘要到数据库"""
    summary_id = f"sum-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        'INSERT INTO summaries (id, material_ids, user_prompt, ai_original) VALUES (?, ?, ?, ?)',
        (summary_id, json.dumps(material_ids), user_prompt, ai_text)
    )
    conn.commit()
    conn.close()
    return summary_id
