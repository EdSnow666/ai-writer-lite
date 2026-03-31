# 职责：偏好萃取 prompt 构建（无 API 调用）
# 依赖内部：db.py
# 暴露：distill_preferences(), get_active_prompt(), update_system_prompt()

from .db import get_conn

def should_trigger(undistilled_count, distilled_count):
    """判断是否触发萃取"""
    if distilled_count == 0 and undistilled_count >= 3:
        return True
    return undistilled_count >= 10

def should_trigger_process_distill(process_count):
    """判断是否触发修改过程萃取"""
    return process_count >= 5

def should_trigger_final_distill(final_count):
    """判断是否触发定稿萃取"""
    return final_count >= 10

def distill_preferences(edit_records):
    """萃取用户写作偏好 - 返回 prompt"""
    edits_text = '\n\n'.join([
        f"修改 {i+1}:\n原文：{e['ai_original'][:100]}...\n改后：{e['final_text'][:100]}..."
        for i, e in enumerate(edit_records)
    ])

    prompt = f"""分析以下编辑记录，提取用户的写作偏好：

{edits_text}

请总结：
1. 句式偏好
2. 措辞倾向
3. 常见修改类型
4. 禁忌表达

输出格式：简洁的偏好描述（200 字内）"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是写作偏好分析专家\nUSER: {prompt}"

def distill_modification_process(process_records):
    """萃取修改过程偏好 - 返回 prompt"""
    process_text = '\n\n'.join([
        f"轮次 {i+1}:\n修改类型：{p['modification_type']}\n编辑比例：{p['edit_ratio']:.2f}"
        for i, p in enumerate(process_records)
    ])

    prompt = f"""分析以下修改过程，提取用户的修改习惯：

{process_text}

请总结用户的修改模式和偏好。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是修改过程分析专家\nUSER: {prompt}"

def distill_final_versions(final_versions):
    """萃取定稿特征 - 返回 prompt"""
    finals_text = '\n\n'.join([
        f"定稿 {i+1}:\n{f['final_text'][:150]}..."
        for i, f in enumerate(final_versions)
    ])

    prompt = f"""分析以下定稿文本，提取共同特征：

{finals_text}

请总结定稿的共同特点。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是定稿特征分析专家\nUSER: {prompt}"

def distill_scenario_preferences(edit_records, scenario_type):
    """萃取场景化偏好 - 返回 prompt"""
    edits_text = '\n\n'.join([
        f"修改 {i+1}:\n原文：{e['ai_original'][:100]}...\n改后：{e['final_text'][:100]}..."
        for i, e in enumerate(edit_records)
    ])

    prompt = f"""分析 {scenario_type} 场景下的编辑记录，提取写作偏好：

{edits_text}

请总结该场景下的写作偏好。"""

    return f"__ASSISTANT_MODE__\nSYSTEM: 你是场景化写作分析专家\nUSER: {prompt}"

def get_active_prompt(prompt_type='writing'):
    """获取激活的 prompt"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT prompt_text FROM system_prompts
        WHERE prompt_type = ? AND is_active = 1
        ORDER BY created_at DESC LIMIT 1
    ''', (prompt_type,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

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
