# 职责：多轮修改会话管理，记录修改过程和定稿
# 依赖内部：db.py, diff_engine.py, config.py
# 依赖外部：uuid, json, datetime
# 暴露：start_modification_session(), record_first_edit(), record_revision_round(), finalize_session(), get_session_history()

import uuid
import json
from datetime import datetime
from difflib import SequenceMatcher
from .db import get_conn
from .diff_engine import calc_paragraph_diff
from config import EDIT_CONFIG

def start_modification_session(summary_id):
    """开始一个新的修改会话"""
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        '''INSERT INTO modification_sessions (id, summary_id, session_start, total_rounds, is_finalized, first_edit_recorded)
           VALUES (?, ?, ?, 0, 0, 0)''',
        (session_id, summary_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return session_id

def check_edit_ratio(ai_text, user_text):
    """
    检查编辑比例，判断是否达到记录阈值
    返回：(edit_ratio, should_proceed)
    """
    if not ai_text or not user_text:
        return 0.0, True

    # 使用 SequenceMatcher 计算编辑距离
    edit_ratio = 1 - SequenceMatcher(None, ai_text, user_text).ratio()

    # 达到阈值，直接通过
    if edit_ratio >= EDIT_CONFIG['ratio_threshold']:
        return edit_ratio, True

    # 未达到阈值，提示用户
    return edit_ratio, False

def record_first_edit(summary_id, session_id, ai_original, user_modified, is_regenerated=False):
    """
    记录用户主动修改到 edit_records 表（使用事务保护）
    - is_regenerated: 是否是 AI 重生成后的修改（True=可以继续修改，False=达到阈值保存）
    返回：(record_id, success, edit_ratio)
    """
    edit_ratio, should_proceed = check_edit_ratio(ai_original, user_modified)

    if not should_proceed and not is_regenerated:
        return None, False, edit_ratio

    # 计算 diff
    diff_para = calc_paragraph_diff(ai_original, user_modified)

    record_id = f"edit-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    try:
        conn.execute('BEGIN TRANSACTION')
        conn.execute(
            '''INSERT INTO edit_records (id, summary_id, session_id, ai_original, final_text, edit_ratio, diff_paragraph, is_final)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)''',
            (record_id, summary_id, session_id, ai_original, user_modified, edit_ratio, json.dumps(diff_para))
        )

        # 标记 session 的 first_edit_recorded = 1
        conn.execute(
            'UPDATE modification_sessions SET first_edit_recorded = 1 WHERE id = ?',
            (session_id,)
        )
        conn.commit()
        conn.close()
        return record_id, True, edit_ratio
    except Exception as e:
        conn.rollback()
        conn.close()
        raise

def update_edit_record_final(edit_record_id):
    """
    标记某条 edit_record 为最终稿（is_final=1）
    同时将其他同 session 的记录设为 is_final=0
    """
    conn = get_conn()
    # 先获取该记录所在的 session_id
    cursor = conn.execute('SELECT session_id FROM edit_records WHERE id = ?', (edit_record_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    session_id = row[0]

    # 将该 session 的所有记录设为 is_final=0
    conn.execute('UPDATE edit_records SET is_final = 0 WHERE session_id = ?', (session_id,))

    # 将指定记录设为 is_final=1
    conn.execute('UPDATE edit_records SET is_final = 1 WHERE id = ?', (edit_record_id,))

    conn.commit()
    conn.close()
    return True

def mark_last_edit_as_final(session_id):
    """
    将会话中最后一条 edit_record 标记为最终稿
    """
    conn = get_conn()
    cursor = conn.execute('''
        SELECT id FROM edit_records
        WHERE session_id = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (session_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    last_edit_id = row[0]

    # 清除该 session 所有 is_final 标记
    conn.execute('UPDATE edit_records SET is_final = 0 WHERE session_id = ?', (session_id,))

    # 标记最后一条为 is_final=1
    conn.execute('UPDATE edit_records SET is_final = 1 WHERE id = ?', (last_edit_id,))

    conn.commit()
    conn.close()
    return last_edit_id

def record_revision_round(session_id, round_num, ai_opinion, suggestion_type, user_modified, prev_text, suggestions_raw=None, user_feedback=None):
    """
    记录打磨轮次到 revision_rounds 表
    - ai_opinion: AI 提出的修改意见（完整文本）
    - suggestion_type: 建议类型 comma 分隔（如"结构，论据"）
    - user_modified: 用户修改后的文本（含%%...%%标记）
    - prev_text: 修改前的文本（用于计算编辑比例和判断用户是否响应）
    - suggestions_raw: 原始建议列表 JSON（可选）
    - user_feedback: 用户反馈 JSON（可选）
    """
    # 计算编辑比例，判断用户是否实际修改
    if prev_text and user_modified:
        edit_ratio = 1 - SequenceMatcher(None, prev_text, user_modified).ratio()
        user_responded = 1 if edit_ratio > 0.05 else 0  # 5% 以上变化算响应
    else:
        edit_ratio = 0
        user_responded = 0

    revision_id = f"rev-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        '''INSERT INTO revision_rounds (id, session_id, round_num, ai_opinion, suggestion_type, user_modified, user_responded, edit_ratio, suggestions_raw, user_feedback)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (revision_id, session_id, round_num, ai_opinion, suggestion_type, user_modified, user_responded, edit_ratio, json.dumps(suggestions_raw) if suggestions_raw else None, json.dumps(user_feedback) if user_feedback else None)
    )

    # 更新会话的轮数
    conn.execute(
        'UPDATE modification_sessions SET total_rounds = ?, session_end = ? WHERE id = ?',
        (round_num, datetime.now().isoformat(), session_id)
    )
    conn.commit()
    conn.close()

    return revision_id, user_responded, edit_ratio

def get_session_rounds(session_id):
    """获取会话的所有打磨轮次"""
    conn = get_conn()
    cursor = conn.execute(
        '''SELECT round_num, ai_opinion, suggestion_type, user_modified, user_responded, edit_ratio, created_at
           FROM revision_rounds WHERE session_id = ?
           ORDER BY round_num''',
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [{
        'round_num': row[0],
        'ai_opinion': row[1],
        'suggestion_type': row[2],
        'user_modified': row[3],
        'user_responded': row[4],
        'edit_ratio': row[5],
        'created_at': row[6]
    } for row in rows]

def get_session_edits(session_id):
    """获取会话的所有编辑记录"""
    conn = get_conn()
    cursor = conn.execute(
        '''SELECT id, ai_original, final_text, edit_ratio, is_final, created_at
           FROM edit_records WHERE session_id = ?
           ORDER BY created_at''',
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [{
        'id': row[0],
        'ai_original': row[1],
        'final_text': row[2],
        'edit_ratio': row[3],
        'is_final': row[4],
        'created_at': row[5]
    } for row in rows]

def finalize_session(session_id, final_text):
    """标记会话为定稿（使用事务保护）"""
    conn = get_conn()
    try:
        conn.execute('BEGIN TRANSACTION')

        # 获取会话信息
        cursor = conn.execute('SELECT summary_id, total_rounds FROM modification_sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return None

        summary_id, total_rounds = row

        # 获取最后一条 edit_record 的 ID
        last_edit_id = mark_last_edit_as_final(session_id)
        if not last_edit_id:
            conn.rollback()
            conn.close()
            return None

        # 创建定稿记录（引用 edit_record，不存储冗余文本）
        final_id = f"final-{uuid.uuid4().hex[:8]}"
        conn.execute(
            '''INSERT INTO final_versions (id, summary_id, session_id, edit_record_id, total_rounds, word_count)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (final_id, summary_id, session_id, last_edit_id, total_rounds, len(final_text))
        )

        # 更新会话状态
        conn.execute(
            '''UPDATE modification_sessions
               SET is_finalized = 1, final_version_id = ?, session_end = ?
               WHERE id = ?''',
            (final_id, datetime.now().isoformat(), session_id)
        )

        conn.commit()
        conn.close()
        return final_id
    except Exception as e:
        conn.rollback()
        conn.close()
        raise

def reopen_session(summary_id):
    """
    重新打开一个已定稿的会话，继续修改
    返回新的 session_id
    """
    conn = get_conn()

    # 检查是否已有未结束的 session
    cursor = conn.execute(
        '''SELECT id FROM modification_sessions
           WHERE summary_id = ? AND is_finalized = 0
           ORDER BY session_start DESC LIMIT 1''',
        (summary_id,)
    )
    row = cursor.fetchone()

    if row:
        # 返回现有的未结束 session
        conn.close()
        return row[0]

    # 创建新的 session
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    conn.execute(
        '''INSERT INTO modification_sessions (id, summary_id, session_start, total_rounds, is_finalized, first_edit_recorded)
           VALUES (?, ?, ?, 0, 0, 1)''',  # first_edit_recorded=1 因为已经记录过了
        (session_id, summary_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return session_id

def get_session_history(summary_id):
    """获取某摘要的完整修改历史（包括 edits 和 revisions）"""
    conn = get_conn()

    # 获取 session
    cursor = conn.execute(
        'SELECT id, total_rounds, is_finalized, final_version_id FROM modification_sessions WHERE summary_id = ?',
        (summary_id,)
    )
    sessions = cursor.fetchall()

    history = []
    for session in sessions:
        session_id = session[0]

        # 获取编辑记录
        edits_cursor = conn.execute(
            '''SELECT id, ai_original, final_text, edit_ratio, is_final, created_at
               FROM edit_records WHERE session_id = ?
               ORDER BY created_at''',
            (session_id,)
        )
        edits = edits_cursor.fetchall()

        for row in edits:
            history.append({
                'type': 'edit',
                'session_id': session_id,
                'id': row[0],
                'ai_original': row[1],
                'final_text': row[2],
                'edit_ratio': row[3],
                'is_final': row[4],
                'created_at': row[5]
            })

        # 获取打磨轮次
        rounds_cursor = conn.execute(
            '''SELECT round_num, ai_opinion, suggestion_type, user_modified, user_responded, edit_ratio
               FROM revision_rounds WHERE session_id = ?
               ORDER BY round_num''',
            (session_id,)
        )
        rounds = rounds_cursor.fetchall()

        for row in rounds:
            history.append({
                'type': 'revision',
                'session_id': session_id,
                'round_num': row[0],
                'ai_opinion': row[1],
                'suggestion_type': row[2],
                'user_modified': row[3],
                'user_responded': row[4],
                'edit_ratio': row[5],
                'is_finalized': session[2]
            })

    conn.close()
    return history

def get_final_versions(limit=50):
    """获取定稿列表"""
    conn = get_conn()
    cursor = conn.execute(
        '''SELECT fv.id, fv.summary_id, er.final_text, fv.total_rounds, fv.word_count, fv.created_at
           FROM final_versions fv
           JOIN edit_records er ON fv.edit_record_id = er.id
           ORDER BY fv.created_at DESC LIMIT ?''',
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [{
        'id': row[0],
        'summary_id': row[1],
        'final_text': row[2],
        'total_rounds': row[3],
        'word_count': row[4],
        'created_at': row[5]
    } for row in rows]

def get_undistilled_finals():
    """获取未萃取的定稿"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT er.final_text, fv.total_rounds
        FROM final_versions fv
        JOIN edit_records er ON fv.edit_record_id = er.id
        LEFT JOIN writing_preferences wp ON wp.version = fv.total_rounds
        WHERE wp.id IS NULL
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{'final_text': r[0], 'total_rounds': r[1]} for r in rows]

def count_final_versions():
    """统计定稿数量"""
    conn = get_conn()
    cursor = conn.execute('SELECT COUNT(*) FROM final_versions')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_revision_process_data(session_id):
    """获取打磨过程数据，用于萃取用户响应模式"""
    conn = get_conn()
    cursor = conn.execute(
        '''SELECT ai_opinion, suggestion_type, user_modified, user_responded, edit_ratio
           FROM revision_rounds WHERE session_id = ?
           ORDER BY round_num''',
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    return [{
        'ai_opinion': r[0],
        'suggestion_type': r[1],
        'user_modified': r[2],
        'user_responded': r[3],
        'edit_ratio': r[4]
    } for r in rows]

def get_user_response_patterns(limit_sessions=20):
    """
    获取用户响应模式数据，用于萃取
    分析用户对哪种建议类型最倾向响应
    """
    conn = get_conn()
    cursor = conn.execute('''
        SELECT suggestion_type, user_responded, edit_ratio, COUNT(*) as cnt
        FROM revision_rounds
        GROUP BY suggestion_type, user_responded
        ORDER BY cnt DESC
        LIMIT ?
    ''', (limit_sessions,))
    rows = cursor.fetchall()
    conn.close()

    return [{
        'suggestion_type': r[0],
        'user_responded': r[1],
        'edit_ratio': r[2],
        'count': r[3]
    } for r in rows]
