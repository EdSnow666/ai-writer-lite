# 职责：AI 文本生成 prompt 构建（无 API 调用）
# 依赖内部：db.py, distiller.py
# 依赖外部：无
# 暴露：generate_with_materials(), generate_freeform(), generate_revision(), generate_revision_opinion()

from .db import get_conn
from .distiller import get_active_prompt

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
    """基于素材生成带引用的文本 - 返回 prompt"""
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

    materials_text = '\n\n'.join([f"[素材 {i+1}] ID: {m['id']}\n{m['content'][:300]}..."
                                   for i, m in enumerate(materials)])

    prompt = f"""基于以下素材生成文本，使用 Markdown 脚注格式引用：

{materials_text}

用户需求：{user_intent or '请综合以上素材写一段文本'}

要求：
1. 在引用处使用 [^1], [^2] 标记
2. 文末列出：[^1]: {materials[0]['id']} - 原文片段
3. 输出完整内容，方便用户直接在对话框中查看和修改"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}"

def generate_freeform(user_intent, scenario_type=None, writing_purpose=None):
    """无素材创作 - 返回 prompt"""
    writing_pref = get_active_preference()
    final_pref = get_final_prompt()
    scenario_pref = get_scenario_prompt(scenario_type) if scenario_type else None

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

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {user_intent}"

def analyze_modification_type(user_input, ai_original):
    """分析修改类型"""
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, ai_original, user_input).ratio()
    if ratio > 0.8:
        return "微调"
    elif ratio > 0.5:
        return "中度修改"
    else:
        return "大幅改写"

def generate_revision(user_input, ai_original, session_info=None):
    """动态修改：用户修改部分内容后，AI 分析并重写整个段落"""
    mod_pref = get_modification_prompt()
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

请分析用户的修改意图，并重写整个段落，保持用户的修改风格。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}", modification_type

def generate_revision_opinion(text, scenario_type=None, writing_purpose=None):
    """打磨轮次：AI 对用户文本提出修改建议 - 返回 prompt 和空列表"""
    system_parts = ["你是一个专业的写作编辑，擅长发现文本问题并提出建设性修改建议。"]
    if scenario_type:
        system_parts.append(f"当前场景：{scenario_type}")
    if writing_purpose:
        system_parts.append(f"写作目的：{writing_purpose}")
    system_prompt = ' '.join(system_parts)

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

**重要**：必须严格输出 JSON 格式，不要添加任何解释文字，直接输出 JSON 对象。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}", [], ""

def save_summary(material_ids, user_prompt, ai_text, scenario_type=None, writing_purpose=None):
    """保存摘要到数据库"""
    import uuid
    conn = get_conn()
    summary_id = str(uuid.uuid4())[:8]
    conn.execute('''
        INSERT INTO summaries (id, material_ids, user_prompt, ai_text, scenario_type, writing_purpose)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (summary_id, ','.join(material_ids), user_prompt, ai_text, scenario_type, writing_purpose))
    conn.commit()
    conn.close()
    return summary_id

def ask_if_finalized(round_num):
    """根据轮次数主动询问是否定稿"""
    if round_num >= 3:
        return "已经修改了多轮，是否满意当前版本？可以输入'定稿'结束。"
    return "继续修改或输入'定稿'完成。"

