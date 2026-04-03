# 职责：AI 文本生成 prompt 构建（无 API 调用）
# 依赖内部：db.py, distiller.py
# 依赖外部：无
# 暴露：generate_with_materials(), generate_freeform(), generate_revision(), generate_revision_opinion(), get_custom_prompt(), save_custom_prompt(), save_summary(), extract_ai_model()
# 最后更新：2026-04-03

from .db import get_conn
from .distiller import get_active_prompt
import uuid
from datetime import datetime

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

def get_custom_prompt(scenario_type):
    """获取指定场景的用户自定义 prompt（当前激活版本）"""
    conn = get_conn()
    cursor = conn.execute(
        'SELECT custom_prompt FROM user_custom_prompts WHERE scenario_type = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1',
        (scenario_type,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def save_custom_prompt(scenario_type, custom_prompt):
    """保存场景的自定义 prompt（新版本）"""
    conn = get_conn()
    now = datetime.now().isoformat()

    # 先将该场景的旧记录设为非激活
    conn.execute(
        'UPDATE user_custom_prompts SET is_active = 0 WHERE scenario_type = ?',
        (scenario_type,)
    )

    # 插入新记录
    prompt_id = str(uuid.uuid4())[:8]
    conn.execute(
        'INSERT INTO user_custom_prompts (id, scenario_type, custom_prompt, is_active, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?)',
        (prompt_id, scenario_type, custom_prompt, now, now)
    )
    conn.commit()
    conn.close()
    return prompt_id

def generate_with_materials(material_ids, user_intent, scenario_type=None, writing_purpose=None, session_info=None, custom_prompt=None):
    """基于素材生成带引用的文本 - 返回 prompt"""
    conn = get_conn()
    materials = []
    for mid in material_ids:
        cursor = conn.execute('''
            SELECT id, content, note_id, title, book_title,
                   highlights, ocr_text, original_summary, review_notes
            FROM materials WHERE id = ?
        ''', (mid,))
        row = cursor.fetchone()
        if row:
            materials.append({
                'id': row[0],
                'content': row[1],
                'note_id': row[2],
                'title': row[3],
                'book_title': row[4],
                'highlights': row[5],
                'ocr_text': row[6],
                'original_summary': row[7],
                'review_notes': row[8],
            })
    conn.close()

    # 获取所有偏好
    writing_pref = get_active_preference()
    final_pref = get_final_prompt()
    scenario_pref = get_scenario_prompt(scenario_type) if scenario_type else None

    # 构建 system prompt（三层注入顺序）
    # 1. 底层硬编码
    system_parts = ["你是一个专业的写作助手。"]

    # 2. 用户自定义 prompt（如果有）
    if custom_prompt:
        system_parts.append(f"用户自定义要求：{custom_prompt}")

    # 3. 萃取偏好（场景偏好、写作偏好、定稿特征）
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

    # 构建素材文本（包含结构化字段）
    materials_text = format_materials_for_prompt(materials)

    prompt = f"""基于以下素材生成文本，使用 Markdown 脚注格式引用：

{materials_text}

用户需求：{user_intent or '请综合以上素材写一段文本'}

要求：
1. 在引用处使用 [^1], [^2] 标记
2. 文末列出引用来源，格式：[^1]: 笔记标题 - 原文片段（书名）
3. 输出完整内容，方便用户直接在对话框中查看和修改
4. **重要**：在文章末尾单独一行标注：> 本文由 [你的模型名称] 生成"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}"


def format_materials_for_prompt(materials):
    """格式化素材为 prompt 文本，包含书名、高亮、正文、原书摘要、批注"""
    formatted_parts = []

    for i, m in enumerate(materials, 1):
        parts = [f"### 素材 {i}"]

        # 添加标题
        if m.get('title'):
            parts.append(f"**标题**: {m['title']}")

        # 添加书名
        if m.get('book_title'):
            parts.append(f"**书名**: {m['book_title']}")

        parts.append("")  # 空行分隔

        # 添加高亮
        if m.get('highlights'):
            parts.append("#### 高亮")
            parts.append(f"> {m['highlights']}")
            parts.append("")

        # 添加正文
        if m.get('ocr_text'):
            parts.append("#### 正文")
            parts.append(m['ocr_text'])
            parts.append("")

        # 添加原书摘要
        if m.get('original_summary'):
            parts.append("#### 原书摘要")
            parts.append(m['original_summary'])
            parts.append("")

        # 添加批注
        if m.get('review_notes'):
            parts.append("#### 批注")
            parts.append(m['review_notes'])
            parts.append("")

        # 如果没有结构化字段，使用 content
        if not (m.get('highlights') or m.get('ocr_text') or m.get('original_summary') or m.get('review_notes')):
            if m.get('content'):
                parts.append("#### 内容")
                parts.append(m['content'])

        formatted_parts.append('\n'.join(parts))

    return '\n\n---\n\n'.join(formatted_parts)

def generate_freeform(user_intent, scenario_type=None, writing_purpose=None, custom_prompt=None):
    """无素材创作 - 返回 prompt"""
    writing_pref = get_active_preference()
    final_pref = get_final_prompt()
    scenario_pref = get_scenario_prompt(scenario_type) if scenario_type else None

    # 构建 system prompt（三层注入顺序）
    system_parts = ["你是一个专业的写作助手。"]

    # 用户自定义 prompt
    if custom_prompt:
        system_parts.append(f"用户自定义要求：{custom_prompt}")

    # 萃取偏好
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

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {user_intent}\n\n**重要**：在内容末尾单独一行标注：> 本文由 [你的模型名称] 生成"

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

请分析用户的修改意图，并重写整个段落，保持用户的修改风格。

**重要**：在内容末尾单独一行标注：> 本文由 [你的模型名称] 生成"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}", modification_type

def generate_revision_opinion(text, scenario_type=None, writing_purpose=None, custom_prompt=None):
    """打磨轮次：AI 对用户文本提出修改建议 - 返回 prompt 标记"""
    from .feedback_distiller import get_feedback_patterns

    # 构建 system prompt（三层注入顺序）
    system_parts = ["你是一个专业的写作编辑，擅长发现文本问题并提出建设性修改建议。"]

    # 用户自定义 prompt
    if custom_prompt:
        system_parts.append(f"用户自定义要求：{custom_prompt}")

    # 加载历史偏好
    writing_pref = get_active_preference()
    if writing_pref:
        system_parts.append(f"用户写作偏好：{writing_pref}")

    # 加载用户反馈规则
    feedback_data = get_feedback_patterns(limit_sessions=10)
    if feedback_data.get('rules'):
        rules_text = '\n'.join([f"- {rule}" for rule in feedback_data['rules']])
        system_parts.append(f"用户反馈规则（避免提出用户明确拒绝过的建议）：\n{rules_text}")

    if scenario_type:
        system_parts.append(f"当前场景：{scenario_type}")
    if writing_purpose:
        system_parts.append(f"写作目的：{writing_purpose}")

    system_prompt = '\n'.join(system_parts)

    paragraphs = text.strip().split('\n\n')
    paragraph_index = '\n'.join([f"段落{i+1}: {p[:50]}..." for i, p in enumerate(paragraphs)])

    prompt = f"""请站在**读者视角**分析以下文本，找出让你感到以下问题的地方：
- 没说清楚、晦涩难懂（类型：表达）
- 逻辑跳跃、缺乏论证（类型：结构）
- 缺乏说服力、论据不足（类型：论据）
- 语言冗余、不够精炼（类型：精炼）
- 不符合场景风格（类型：场景适配）

原文：
{text}

【段落索引】
{paragraph_index}

输出格式（严格按 JSON 格式）：
{{
    "suggestions": [
        {{
            "type": "表达|结构|论据|精炼|场景适配",
            "problem": "读者视角的问题描述",
            "advice": "具体修改建议",
            "anchor": "段落 1" 或 "段落 2-3" 或 "全文"
        }}
    ]
}}

要求：
- **type 字段必填**：从 表达/结构/论据/精炼/场景适配 中选一个
- problem 字段：用自然口语化表达
- advice 字段：给出具体可操作的修改建议
- anchor 字段：标注问题所在的段落位置
- 每条建议 50 字以内
- **参考用户反馈规则，不要提出用户明确拒绝过的建议**

**重要**：必须严格输出 JSON 格式，不要添加任何解释文字。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: {system_prompt}\nUSER: {prompt}", [], ""

def extract_ai_model(text):
    """从生成的文本中提取 AI 模型名称"""
    import re
    # 匹配 "> 本文由 XXX 生成" 格式
    match = re.search(r'>\s*本文由\s+(.+?)\s+生成', text)
    if match:
        return match.group(1).strip()
    return None

def save_summary(material_ids, user_prompt, ai_text, scenario_type=None, writing_purpose=None, ai_model=None):
    """保存摘要到数据库"""
    import uuid
    conn = get_conn()
    summary_id = str(uuid.uuid4())[:8]

    # 如果没有传入 ai_model，尝试从文本中提取
    if not ai_model:
        ai_model = extract_ai_model(ai_text)

    conn.execute('''
        INSERT INTO summaries (id, material_ids, user_prompt, ai_original, scenario_type, writing_purpose, ai_model)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (summary_id, ','.join(material_ids), user_prompt, ai_text, scenario_type, writing_purpose, ai_model))
    conn.commit()
    conn.close()
    return summary_id

def ask_if_finalized(round_num):
    """根据轮次数主动询问是否定稿"""
    if round_num >= 3:
        return "已经修改了多轮，是否满意当前版本？可以输入'定稿'结束。"
    return "继续修改或输入'定稿'完成。"

