# 职责：AI 文本生成（带引用、偏好和动态修改支持）
# 依赖内部：db.py, revision_manager.py, distiller.py, config.py
# 依赖外部：anthropic, os, uuid, json, difflib
# 暴露：generate_with_materials(), generate_freeform(), generate_revision(), get_active_prompt()

import os
import uuid
import json
import time
from difflib import SequenceMatcher
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
from .db import get_conn
from .distiller import get_active_prompt
from config import API_CONFIG

def api_call_with_retry(func, *args, **kwargs):
    """API 调用重试机制"""
    for attempt in range(API_CONFIG['max_retries']):
        try:
            return func(*args, **kwargs)
        except RateLimitError:
            if attempt < API_CONFIG['max_retries'] - 1:
                time.sleep(API_CONFIG['retry_delay'] * (2 ** attempt))
            else:
                raise
        except APIConnectionError:
            if attempt < API_CONFIG['max_retries'] - 1:
                time.sleep(API_CONFIG['retry_delay'])
            else:
                raise
        except APIError as e:
            raise

def get_active_preference():
    """获取当前激活的偏好模型（写作偏好）"""
    return get_active_prompt('writing')

def get_modification_prompt():
    """获取修改过程偏好"""
    return get_active_prompt('modification')

def get_final_prompt():
    """获取定稿特征偏好"""
    return get_active_prompt('final')

def get_scenario_prompt(scenario_type):
    """获取特定场景的偏好"""
    return get_active_prompt(f'scenario_{scenario_type}')

def generate_with_materials(material_ids, user_intent, scenario_type=None, writing_purpose=None, session_info=None):
    """基于素材生成带引用的文本"""
    conn = get_conn()
    materials = []
    for mid in material_ids:
        cursor = conn.execute('SELECT id, content FROM materials WHERE id = ?', (mid,))
        row = cursor.fetchone()
        if row:
            materials.append({'id': row[0], 'content': row[1]})
    conn.close()

    # 获取所有偏好
    writing_pref = get_active_preference()
    final_pref = get_final_prompt()
    scenario_pref = get_scenario_prompt(scenario_type) if scenario_type else None

    # 构建 system prompt（整合写作偏好、定稿特征和场景偏好）
    system_parts = ["你是一个专业的写作助手。"]
    if scenario_pref:
        system_parts.append(f"场景偏好：{scenario_pref}")
    if writing_pref:
        system_parts.append(f"写作偏好：{writing_pref}")
    if final_pref:
        system_parts.append(f"定稿特征：{final_pref}")
    if scenario_type:
        system_parts.append(f"当前场景：{scenario_type}")
    if writing_purpose:
        system_parts.append(f"写作目的：{writing_purpose}")
    system_prompt = ' '.join(system_parts)

    materials_text = '\n\n'.join([f"[素材 {i+1}] ID: {m['id']}\n{m['content'][:300]}..."
                                   for i, m in enumerate(materials)])

    prompt = f"""基于以下素材生成文本，使用 Markdown 脚注格式引用：

{materials_text}

用户需求：{user_intent or '请综合以上素材写一段文本'}

要求：
1. 在引用处使用 [^1], [^2] 标记
2. 文末列出：[^1]: {materials[0]['id']} - 原文片段
3. 输出完整内容，方便用户直接在对话框中查看和修改"""

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}"

    client = Anthropic(api_key=api_key)
    response = api_call_with_retry(
        client.messages.create,
        model=API_CONFIG['model'],
        max_tokens=API_CONFIG['max_tokens']['generate'],
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text

def generate_freeform(user_intent, scenario_type=None, writing_purpose=None, session_info=None):
    """无素材创作"""
    # 获取所有偏好
    writing_pref = get_active_preference()
    final_pref = get_final_prompt()
    scenario_pref = get_scenario_prompt(scenario_type) if scenario_type else None

    # 构建 system prompt
    system_parts = ["你是一个专业的写作助手。"]
    if scenario_pref:
        system_parts.append(f"场景偏好：{scenario_pref}")
    if writing_pref:
        system_parts.append(f"写作偏好：{writing_pref}")
    if final_pref:
        system_parts.append(f"定稿特征：{final_pref}")
    if scenario_type:
        system_parts.append(f"当前场景：{scenario_type}")
    if writing_purpose:
        system_parts.append(f"写作目的：{writing_purpose}")
    system_prompt = ' '.join(system_parts)

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}"

    client = Anthropic(api_key=api_key)
    response = api_call_with_retry(
        client.messages.create,
        model="claude-sonnet-4-5-20250929",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_intent}]
    )

    return response.content[0].text

def generate_revision(user_input, ai_original, session_info=None):
    """
    动态修改：用户修改部分内容后，AI 分析并重写整个段落
    用于第一轮修改
    """
    mod_pref = get_modification_prompt()

    # 分析用户修改的类型
    modification_type = analyze_modification_type(user_input, ai_original)

    system_parts = ["你是一个专业的写作助手，擅长分析用户的修改并重写全文。"]
    if mod_pref:
        system_parts.append(f"修改偏好：{mod_pref}")
    system_prompt = ' '.join(system_parts)

    prompt = f"""用户修改了以下文本：

【AI 原文】
{ai_original}

【用户修改后】
{user_input}

请分析用户的修改意图，并重写整个段落，保持用户的修改风格。

修改类型：{modification_type}

要求：
1. 保留用户修改的部分和精神
2. 重写其余部分以匹配用户的风格
3. 输出完整的重写结果"""

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}"

    client = Anthropic(api_key=api_key)
    response = api_call_with_retry(
        client.messages.create,
        model=API_CONFIG['model'],
        max_tokens=API_CONFIG['max_tokens']['generate'],
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text, modification_type

def generate_revision_opinion(text, scenario_type=None, writing_purpose=None):
    """
    打磨轮次：AI 对用户文本提出修改建议
    返回：(opinions_text, suggestions_list, suggestion_types)
    - opinions_text: 完整的修改意见文本（用于显示给用户）
    - suggestions_list: 结构化建议列表 [{problem, advice, anchor}]
    - suggestion_types: comma 分隔的建议类型
    """
    system_parts = ["你是一个专业的写作编辑，擅长发现文本问题并提出建设性修改建议。"]

    if scenario_type:
        system_parts.append(f"当前场景：{scenario_type}")
    if writing_purpose:
        system_parts.append(f"写作目的：{writing_purpose}")

    system_prompt = ' '.join(system_parts)

    # 将文本按段落分割，便于 AI 定位
    paragraphs = text.strip().split('\n\n')
    paragraph_index = '\n'.join([f"段落{i+1}: {p[:50]}..." for i, p in enumerate(paragraphs)])

    prompt = f"""请站在**读者视角**分析以下文本，找出让你感到以下问题的地方：
- 没说清楚、晦涩难懂
- 逻辑跳跃、缺乏论证
- 缺乏说服力、论据不足
- 语言冗余、不够精炼
- 不符合场景风格

原文：
{text}

【段落索引】
{paragraph_index}

输出格式（严格按 JSON 格式）：
{{
    "suggestions": [
        {{
            "problem": "读者视角的问题描述，如'这里读起来有点跳，缺少过渡'",
            "advice": "具体修改建议，如'加一句简短回答作为桥梁'",
            "anchor": "段落 1" 或 "段落 2-3" 或 "全文"
        }}
    ]
}}

要求：
- problem 字段：用自然的口语化表达，站在读者角度说"这里读起来..."，不要用"type:"等标签
- advice 字段：给出具体可操作的修改建议
- anchor 字段：标注问题所在的段落位置（如"段落 1"、"段落 2-3"、"全文"）
- 每条建议 50 字以内
"""

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key or not API_CONFIG.get('enabled', False):
        return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}", [], ""

    client = Anthropic(api_key=api_key)
    response = api_call_with_retry(
        client.messages.create,
        model=API_CONFIG['model'],
        max_tokens=API_CONFIG['max_tokens']['opinion'],
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}]
    )

    opinions_text = response.content[0].text

    # 尝试解析 JSON
    suggestions = []
    try:
        import json
        # 提取 JSON 部分
        json_match = opinions_text
        if '```json' in opinions_text:
            json_match = opinions_text.split('```json')[1].split('```')[0]
        elif '{' in opinions_text:
            json_match = opinions_text[opinions_text.find('{'):opinions_text.rfind('}')+1]
        data = json.loads(json_match)
        suggestions = data.get('suggestions', [])
    except (json.JSONDecodeError, ValueError, IndexError):
        # 解析失败，返回原始文本
        suggestions = []

    # 解析建议类型（从 problem 字段推断）
    suggestion_types = []
    type_keywords = {
        '结构': ['逻辑', '结构', '跳跃', '过渡', '衔接'],
        '表达': ['表达', '晦涩', '难懂', '句子'],
        '论据': ['论据', '论证', '说服力', '支持'],
        '精炼': ['冗余', '精炼', '简洁', '删减'],
        '场景': ['场景', '风格']
    }
    for sug in suggestions:
        problem = sug.get('problem', '')
        for t, keywords in type_keywords.items():
            if any(kw in problem for kw in keywords) and t not in suggestion_types:
                suggestion_types.append(t)
                break
        else:
            if '通用' not in suggestion_types:
                suggestion_types.append('通用')

    # 生成显示文本（自然语言格式，不带 type 标签）
    display_text = "【AI 修改建议】\n\n"
    for i, sug in enumerate(suggestions, 1):
        problem = sug.get('problem', '')
        advice = sug.get('advice', '')
        anchor = sug.get('anchor', '')
        location = f"[{anchor}]" if anchor else ""
        display_text += f"{i}. {location} {problem} → {advice}\n"

    return display_text, suggestions, ','.join(suggestion_types)


def analyze_modification_type(user_input, ai_original):
    """分析用户修改的类型"""
    if len(user_input) < len(ai_original) * 0.5:
        return "大幅删减"
    elif len(user_input) > len(ai_original) * 1.5:
        return "大幅扩充"
    else:
        # 使用 SequenceMatcher 计算编辑距离
        diff_ratio = 1 - SequenceMatcher(None, ai_original, user_input).ratio()
        if diff_ratio < 0.2:
            return "微调措辞"
        elif diff_ratio < 0.5:
            return "局部重写"
        else:
            return "大幅重写"

def ask_if_finalized(round_num):
    """询问用户是否定稿"""
    if round_num >= 3:
        return f"这是第 {round_num} 轮修改了。您对当前版本满意吗？如果满意，请说'定稿'或'完成'，我将继续优化；如果还有其他想法，请告诉我需要改哪里。"
    else:
        return f"还需要继续调整吗？您可以：\n1. 直接修改文本中的某段，我来重写\n2. 告诉我具体需要改哪里\n3. 说'定稿'或'完成'结束本次写作"

def save_summary(material_ids, user_prompt, ai_text, scenario_type=None, writing_purpose=None):
    """保存摘要到数据库"""
    summary_id = f"sum-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        'INSERT INTO summaries (id, material_ids, user_prompt, ai_original, scenario_type, writing_purpose) VALUES (?, ?, ?, ?, ?, ?)',
        (summary_id, json.dumps(material_ids), user_prompt, ai_text, scenario_type, writing_purpose)
    )
    conn.commit()
    conn.close()
    return summary_id
