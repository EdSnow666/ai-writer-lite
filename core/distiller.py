# 职责: 写作偏好萃取和管理
# 依赖内部: db.py
# 依赖外部: anthropic, os, uuid, json
# 暴露: should_trigger(), distill_preferences(), update_system_prompt()

import os
import uuid
import json
from anthropic import Anthropic
from .db import get_conn

def should_trigger(undistilled_count, distilled_count):
    """判断是否触发萃取"""
    if distilled_count == 0 and undistilled_count >= 3:
        return True
    return undistilled_count >= 10

def distill_preferences(edit_records):
    """萃取偏好，无 API Key 则跳过"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("💡 提示：配置 ANTHROPIC_API_KEY 可启用自动偏好萃取")
        return None

    edits_text = '\n\n'.join([
        f"修改 {i+1}:\n原文: {e['ai_original'][:100]}...\n改后: {e['final_text'][:100]}..."
        for i, e in enumerate(edit_records)
    ])

    prompt = f"""分析以下编辑记录，提取用户的写作偏好：

{edits_text}

请总结：
1. 句式偏好
2. 措辞倾向
3. 常见修改类型
4. 禁忌表达

输出格式：简洁的偏好描述（200字内）"""

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text

def update_system_prompt(preferences, version=None):
    """更新并激活新的偏好模型"""
    if version is None:
        conn = get_conn()
        cursor = conn.execute('SELECT MAX(version) FROM writing_preferences')
        max_ver = cursor.fetchone()[0]
        version = (max_ver or 0) + 1
        conn.close()

    pref_id = f"pref-{uuid.uuid4().hex[:8]}"
    system_prompt = f"你是一个专业的写作助手。用户的写作偏好：{preferences}"

    conn = get_conn()
    conn.execute('UPDATE writing_preferences SET is_active = 0')
    conn.execute(
        'INSERT INTO writing_preferences (id, version, preference_summary, system_prompt, is_active) VALUES (?, ?, ?, ?, 1)',
        (pref_id, version, preferences, system_prompt)
    )
    conn.commit()
    conn.close()
    return pref_id
