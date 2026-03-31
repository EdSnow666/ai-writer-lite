# -*- coding: utf-8 -*-
from core.db import get_conn
import re
import json

conn = get_conn()

# 获取 slow ai 的 summary
cursor = conn.execute('SELECT id FROM summaries WHERE id LIKE "%slow%" ORDER BY created_at DESC LIMIT 1')
row = cursor.fetchone()
print('Summary ID:', row)

if row:
    summary_id = row[0]

    # 获取 session 状态
    cursor = conn.execute('''
        SELECT id, total_rounds, is_finalized
        FROM modification_sessions
        WHERE summary_id = ?
        ORDER BY session_start DESC LIMIT 1
    ''', (summary_id,))
    session = cursor.fetchone()

    if session:
        print('Session ID:', session[0])
        print('总轮数:', session[1])
        print('是否定稿:', '是' if session[2] else '否')

        # 获取最新编辑稿
        cursor = conn.execute('''
            SELECT final_text FROM edit_records
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (session[0],))
        edit = cursor.fetchone()

        if edit:
            current_text = edit[0]
            print('\n=== 当前最新稿 ===')
            print(current_text)

            # 清理 %%...%% 标记
            clean_text = re.sub(r'%%.*?%%', '', current_text, flags=re.DOTALL)
            print('\n=== 清理后文本 (用于打磨) ===')
            print(clean_text)

conn.close()
