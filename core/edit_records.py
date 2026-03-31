# 职责: 编辑记录管理
# 依赖内部: db.py, diff_engine.py
# 依赖外部: uuid, json
# 暴露: save_edit_record(), get_undistilled_edits(), mark_as_distilled()

import uuid
import json
from .db import get_conn
from .diff_engine import calc_paragraph_diff, calc_sentence_diff, calc_word_diff_by_paragraph

def save_edit_record(summary_id, ai_original, final_text, suggestions_raw=None):
    """保存编辑记录并计算 diff
    - suggestions_raw: 原始建议列表 JSON（可选，用于打磨轮次）
    """
    edit_ratio = 1 - (len(set(ai_original) & set(final_text)) / max(len(ai_original), len(final_text)))

    diff_para = calc_paragraph_diff(ai_original, final_text)
    diff_sent = calc_sentence_diff(ai_original, final_text)
    diff_word = calc_word_diff_by_paragraph(ai_original, final_text)

    record_id = f"edit-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        '''INSERT INTO edit_records
           (id, summary_id, ai_original, final_text, edit_ratio, diff_paragraph, diff_sentence, diff_word, suggestions_raw)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (record_id, summary_id, ai_original, final_text, edit_ratio,
         json.dumps(diff_para), json.dumps(diff_sent), json.dumps(diff_word), json.dumps(suggestions_raw) if suggestions_raw else None)
    )
    conn.commit()
    conn.close()
    return record_id

def get_undistilled_edits():
    """获取未萃取的编辑记录"""
    conn = get_conn()
    cursor = conn.execute('SELECT ai_original, final_text FROM edit_records WHERE is_distilled = 0')
    rows = cursor.fetchall()
    conn.close()
    return [{'ai_original': r[0], 'final_text': r[1]} for r in rows]

def mark_as_distilled():
    """标记所有记录为已萃取"""
    conn = get_conn()
    conn.execute('UPDATE edit_records SET is_distilled = 1 WHERE is_distilled = 0')
    conn.commit()
    conn.close()

def count_undistilled():
    """统计未萃取记录数"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM edit_records WHERE is_distilled = 0')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def count_distilled_times():
    """统计萃取次数"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM writing_preferences')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def count_undistilled_by_scenario(scenario_type):
    """统计特定场景下未萃取的记录数"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT COUNT(*) FROM edit_records e
        JOIN summaries s ON e.summary_id = s.id
        WHERE e.is_distilled = 0 AND s.scenario_type = ?
    ''', (scenario_type,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_undistilled_edits_by_scenario(scenario_type, limit=10):
    """获取特定场景下未萃取的编辑记录"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT e.ai_original, e.final_text, s.scenario_type
        FROM edit_records e
        JOIN summaries s ON e.summary_id = s.id
        WHERE e.is_distilled = 0 AND s.scenario_type = ?
        LIMIT ?
    ''', (scenario_type, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{'ai_original': r[0], 'final_text': r[1], 'scenario_type': r[2]} for r in rows]
