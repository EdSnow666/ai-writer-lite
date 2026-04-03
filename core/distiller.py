# 职责：偏好萃取 prompt 构建（无 API 调用）
# 依赖内部：db.py, edit_records.py
# 暴露：distill_preferences(), distill_from_final_versions(), get_active_prompt(), update_system_prompt()

from .db import get_conn
from .edit_records import get_all_edits_for_distill, get_final_versions_for_distill, count_total_edits, count_final_versions

def should_trigger_distill(total_count, last_distill_count):
    """
    判断是否触发萃取（全量模式）

    冷启动机制：
    - 总数 ≤ 10：每次有新增都萃取
    - 总数 10-20：每两条萃取一次
    - 总数 ≥ 20：每 5 条萃取一次
    """
    if total_count < 1:
        return False

    new_count = total_count - last_distill_count

    if total_count <= 10:
        return new_count >= 1
    elif total_count <= 20:
        return new_count >= 2
    else:
        return new_count >= 5


def should_trigger_final_distill(final_count):
    """判断是否触发定稿萃取"""
    return final_count >= 1


def distill_preferences(edit_records=None):
    """
    萃取用户写作偏好（全量模式）
    - 每次都读取全部历史记录
    - 返回 prompt
    """
    if edit_records is None:
        edit_records = get_all_edits_for_distill()

    if not edit_records:
        return None

    # 全量分析：完整展示 AI 原文和用户修改（不限制条数）
    edits_text = '\n\n---\n\n'.join([
        f"【修改 {i+1}】\nAI 原文：\n{e['ai_original']}\n\n用户修改后：\n{e['final_text']}"
        for i, e in enumerate(edit_records)
    ])

    prompt = f"""分析以下全部编辑记录，提取用户的写作偏好（全量萃取）：

{edits_text}

请从以下维度分析：
1. **句式偏好**：用户喜欢什么样的句子结构？
2. **措辞倾向**：用户偏好哪些词汇、避免哪些表达？
3. **修改模式**：用户最常见的修改类型是什么？
4. **禁忌表达**：用户明确不喜欢或会修改掉的表达
5. **风格特征**：用户的整体写作风格

输出格式：
## 写作偏好
[简洁的偏好描述，200 字内]

## 禁忌表达
- [列出用户会修改掉的表达]

## 风格建议
[给 AI 的写作建议]"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是写作偏好分析专家，负责从用户修改记录中萃取写作偏好\nUSER: {prompt}"


def distill_from_final_versions(final_versions=None):
    """
    从定稿中萃取偏好（全量模式）
    - 读取所有定稿内容
    - 分析共同特征
    """
    if final_versions is None:
        final_versions = get_final_versions_for_distill()

    if not final_versions:
        return None

    # 按场景分组展示（不限制条数）
    by_scenario = {}
    for fv in final_versions:
        scenario = fv.get('scenario_type') or 'general'
        if scenario not in by_scenario:
            by_scenario[scenario] = []
        by_scenario[scenario].append(fv)

    scenario_text = ""
    for scenario, versions in by_scenario.items():
        scenario_text += f"\n### 场景：{scenario}\n"
        for i, v in enumerate(versions):
            scenario_text += f"\n【定稿 {i+1}】({v.get('word_count', 0)} 字)\n{v['final_text']}\n"

    prompt = f"""分析以下全部定稿内容，提取写作特征（全量萃取）：

{scenario_text}

请从以下维度分析：
1. **结构特征**：定稿的段落结构、开头结尾模式
2. **语言风格**：用词特点、句式长短
3. **场景差异**：不同场景下的写作特点差异
4. **共同特征**：所有定稿的共同点

输出格式：
## 整体风格
[描述]

## 场景化建议
- academic: [学术写作建议]
- social_media: [社交媒体建议]
- report: [报告建议]
..."""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是写作风格分析专家，负责从定稿中萃取风格特征\nUSER: {prompt}"


def distill_scenario_preferences(scenario_type):
    """萃取场景化偏好（全量模式）"""
    from .edit_records import get_undistilled_edits_by_scenario

    edit_records = get_undistilled_edits_by_scenario(scenario_type, limit=50)

    if not edit_records:
        return None

    edits_text = '\n\n---\n\n'.join([
        f"【修改 {i+1}】\nAI 原文：\n{e['ai_original']}\n\n用户修改后：\n{e['final_text']}"
        for i, e in enumerate(edit_records)
    ])

    prompt = f"""分析 {scenario_type} 场景下的全部编辑记录，提取该场景的写作偏好：

{edits_text}

请总结 {scenario_type} 场景下的：
1. 特定的句式偏好
2. 场景相关的措辞
3. 该场景下的禁忌表达

输出格式：简洁的场景偏好描述（150 字内）"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是场景化写作分析专家\nUSER: {prompt}"


def get_active_prompt(prompt_type='writing'):
    """获取激活的 prompt"""
    try:
        conn = get_conn()
        cursor = conn.execute('''
            SELECT prompt_text FROM system_prompts
            WHERE prompt_type = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
        ''', (prompt_type,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def update_system_prompt(prompt_text, prompt_type='writing', scenario_type=None):
    """更新系统 prompt"""
    conn = get_conn()
    conn.execute('UPDATE system_prompts SET is_active = 0 WHERE prompt_type = ?', (prompt_type,))

    if scenario_type:
        prompt_type = f'scenario_{scenario_type}'

    conn.execute('''
        INSERT INTO system_prompts (prompt_type, prompt_text, is_active)
        VALUES (?, ?, 1)
    ''', (prompt_type, prompt_text))
    conn.commit()
    conn.close()


# 保留旧函数名以兼容
def distill_modification_process(process_records):
    """萃取修改过程偏好（保留兼容）"""
    process_text = '\n\n'.join([
        f"轮次 {i+1}:\n修改类型：{p.get('modification_type', '未知')}\n编辑比例：{p.get('edit_ratio', 0):.2f}"
        for i, p in enumerate(process_records)
    ])

    prompt = f"""分析以下修改过程，提取用户的修改习惯：

{process_text}

请总结用户的修改模式和偏好。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是修改过程分析专家\nUSER: {prompt}"


def distill_final_versions(final_versions):
    """萃取定稿特征（保留兼容）"""
    finals_text = '\n\n'.join([
        f"定稿 {i+1}:\n{f['final_text']}"
        for i, f in enumerate(final_versions)
    ])

    prompt = f"""分析以下定稿文本，提取共同特征：

{finals_text}

请总结定稿的共同特点。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是定稿特征分析专家\nUSER: {prompt}"


def count_final_versions_in_db():
    """统计定稿数量"""
    return count_final_versions()
