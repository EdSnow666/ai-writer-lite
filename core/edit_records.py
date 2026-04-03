# 职责: 编辑记录管理
# 依赖内部: db.py, diff_engine.py
# 依赖外部: uuid, json
# 暴露: save_edit_record(), get_all_edits_for_distill(), get_final_versions_for_distill()

import uuid
import json
from .db import get_conn
from .diff_engine import calc_paragraph_diff, calc_sentence_diff, calc_word_diff_by_paragraph

def save_edit_record(summary_id, ai_original, final_text, suggestions_raw=None, session_id=None):
    """保存编辑记录并计算 diff
    - suggestions_raw: 原始建议列表 JSON（可选，用于打磨轮次）
    - session_id: 会话 ID（可选）
    """
    from .temp_manager import clean_suggestions

    # 清除 AI 建议标记
    ai_original_clean = clean_suggestions(ai_original)
    final_text_clean = clean_suggestions(final_text)

    edit_ratio = 1 - (len(set(ai_original_clean) & set(final_text_clean)) / max(len(ai_original_clean), len(final_text_clean)))

    diff_para = calc_paragraph_diff(ai_original_clean, final_text_clean)
    diff_sent = calc_sentence_diff(ai_original_clean, final_text_clean)
    diff_word = calc_word_diff_by_paragraph(ai_original_clean, final_text_clean)

    record_id = f"edit-{uuid.uuid4().hex[:8]}"
    conn = get_conn()

    if session_id:
        conn.execute(
            '''INSERT INTO edit_records
               (id, summary_id, session_id, ai_original, final_text, edit_ratio, diff_paragraph, diff_sentence, diff_word, suggestions_raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (record_id, summary_id, session_id, ai_original_clean, final_text_clean, edit_ratio,
             json.dumps(diff_para), json.dumps(diff_sent), json.dumps(diff_word), json.dumps(suggestions_raw) if suggestions_raw else None)
        )
    else:
        conn.execute(
            '''INSERT INTO edit_records
               (id, summary_id, ai_original, final_text, edit_ratio, diff_paragraph, diff_sentence, diff_word, suggestions_raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (record_id, summary_id, ai_original_clean, final_text_clean, edit_ratio,
             json.dumps(diff_para), json.dumps(diff_sent), json.dumps(diff_word), json.dumps(suggestions_raw) if suggestions_raw else None)
        )
    conn.commit()
    conn.close()
    return record_id


def get_all_edits_for_distill(limit=50):
    """获取所有编辑记录用于全量萃取（不再区分 is_distilled）"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT ai_original, final_text, edit_ratio, diff_paragraph, diff_sentence, diff_word
        FROM edit_records
        WHERE is_final = 1
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{
        'ai_original': r[0],
        'final_text': r[1],
        'edit_ratio': r[2],
        'diff_paragraph': json.loads(r[3]) if r[3] else None,
        'diff_sentence': json.loads(r[4]) if r[4] else None,
        'diff_word': json.loads(r[5]) if r[5] else None,
    } for r in rows]


def get_final_versions_for_distill(limit=30):
    """获取所有定稿用于全量萃取"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT fv.word_count, e.final_text, s.scenario_type, s.writing_purpose
        FROM final_versions fv
        JOIN edit_records e ON fv.edit_record_id = e.id
        JOIN summaries s ON fv.summary_id = s.id
        ORDER BY fv.created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{
        'final_text': r[1],
        'word_count': r[0],
        'scenario_type': r[2],
        'writing_purpose': r[3],
    } for r in rows]


def count_total_edits():
    """统计编辑记录总数"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM edit_records WHERE is_final = 1')
    count = cursor.fetchone()[0]
    conn.close()
    return count


def count_final_versions():
    """统计定稿总数"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM final_versions')
    count = cursor.fetchone()[0]
    conn.close()
    return count


# 保留旧函数以兼容
def get_undistilled_edits():
    """获取未萃取的编辑记录（兼容旧调用）"""
    return get_all_edits_for_distill(limit=50)

def mark_as_distilled():
    """标记所有记录为已萃取（全量模式下不再需要，保留兼容）"""
    pass  # 全量模式下不再标记

def count_undistilled():
    """统计未萃取记录数（改为统计总数）"""
    return count_total_edits()

def count_distilled_times():
    """统计萃取次数"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM writing_preferences')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def count_undistilled_by_scenario(scenario_type):
    """统计特定场景下记录数"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT COUNT(*) FROM edit_records e
        JOIN summaries s ON e.summary_id = s.id
        WHERE e.is_final = 1 AND s.scenario_type = ?
    ''', (scenario_type,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_undistilled_edits_by_scenario(scenario_type, limit=10):
    """获取特定场景下的编辑记录"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT e.ai_original, e.final_text, s.scenario_type
        FROM edit_records e
        JOIN summaries s ON e.summary_id = s.id
        WHERE e.is_final = 1 AND s.scenario_type = ?
        ORDER BY e.created_at DESC
        LIMIT ?
    ''', (scenario_type, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{'ai_original': r[0], 'final_text': r[1], 'scenario_type': r[2]} for r in rows]
