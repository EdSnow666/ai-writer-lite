# -*- coding: utf-8 -*-
# 职责: 数据库结构迁移脚本
# 依赖外部: sqlite3
# 暴露: migrate_database()

import sqlite3
import os
import sys
from datetime import datetime

# Windows 控制台 UTF-8 支持
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.expanduser('~/.claude/skills/ai-writer-lite/data/writer.db')

def migrate_database():
    """迁移旧数据库结构到新版本"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys=OFF;')  # 迁移时暂时关闭外键

    try:
        print("🔄 开始数据库迁移...")

        # 1. 为 edit_records 添加 session_id
        print("\n[1/3] 迁移 edit_records 表...")
        try:
            conn.execute('ALTER TABLE edit_records ADD COLUMN session_id TEXT')
            print("  ✓ 添加 session_id 字段")
        except sqlite3.OperationalError:
            print("  ⊙ session_id 字段已存在")

        # 填充 session_id（从 modification_sessions 反向关联）
        cursor = conn.execute('''
            SELECT e.id, e.summary_id, m.id as session_id
            FROM edit_records e
            LEFT JOIN modification_sessions m ON e.summary_id = m.summary_id
            WHERE e.session_id IS NULL
        ''')
        rows = cursor.fetchall()
        for edit_id, summary_id, session_id in rows:
            if session_id:
                conn.execute('UPDATE edit_records SET session_id = ? WHERE id = ?', (session_id, edit_id))
        print(f"  ✓ 更新了 {len(rows)} 条记录的 session_id")

        # 2. 为 revision_rounds 添加 session_id
        print("\n[2/3] 迁移 revision_rounds 表...")
        try:
            conn.execute('ALTER TABLE revision_rounds ADD COLUMN session_id TEXT')
            print("  ✓ 添加 session_id 字段")
        except sqlite3.OperationalError:
            print("  ⊙ session_id 字段已存在")

        # 填充 session_id
        cursor = conn.execute('''
            SELECT r.id, r.summary_id, m.id as session_id
            FROM revision_rounds r
            LEFT JOIN modification_sessions m ON r.summary_id = m.summary_id
            WHERE r.session_id IS NULL
        ''')
        rows = cursor.fetchall()
        for rev_id, summary_id, session_id in rows:
            if session_id:
                conn.execute('UPDATE revision_rounds SET session_id = ? WHERE id = ?', (session_id, rev_id))
        print(f"  ✓ 更新了 {len(rows)} 条记录的 session_id")

        # 3. 为 final_versions 添加 session_id 和 edit_record_id
        print("\n[3/3] 迁移 final_versions 表...")
        try:
            conn.execute('ALTER TABLE final_versions ADD COLUMN session_id TEXT')
            print("  ✓ 添加 session_id 字段")
        except sqlite3.OperationalError:
            print("  ⊙ session_id 字段已存在")

        try:
            conn.execute('ALTER TABLE final_versions ADD COLUMN edit_record_id TEXT')
            print("  ✓ 添加 edit_record_id 字段")
        except sqlite3.OperationalError:
            print("  ⊙ edit_record_id 字段已存在")

        # 填充 session_id 和 edit_record_id
        cursor = conn.execute('''
            SELECT f.id, f.summary_id, m.id as session_id
            FROM final_versions f
            LEFT JOIN modification_sessions m ON f.summary_id = m.summary_id
            WHERE f.session_id IS NULL
        ''')
        rows = cursor.fetchall()
        for final_id, summary_id, session_id in rows:
            if session_id:
                # 获取该 session 的最后一条 edit_record
                edit_cursor = conn.execute('''
                    SELECT id FROM edit_records
                    WHERE session_id = ?
                    ORDER BY created_at DESC LIMIT 1
                ''', (session_id,))
                edit_row = edit_cursor.fetchone()
                edit_record_id = edit_row[0] if edit_row else None

                conn.execute(
                    'UPDATE final_versions SET session_id = ?, edit_record_id = ? WHERE id = ?',
                    (session_id, edit_record_id, final_id)
                )
        print(f"  ✓ 更新了 {len(rows)} 条记录的 session_id 和 edit_record_id")

        conn.commit()
        print("\n✅ 迁移完成！")

        # 验证数据完整性
        print("\n📊 数据完整性检查...")
        check_integrity(conn)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 迁移失败: {e}")
        raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON;')
        conn.close()

def check_integrity(conn):
    """检查数据完整性"""
    checks = [
        ("edit_records 缺失 session_id",
         "SELECT COUNT(*) FROM edit_records WHERE session_id IS NULL"),
        ("revision_rounds 缺失 session_id",
         "SELECT COUNT(*) FROM revision_rounds WHERE session_id IS NULL"),
        ("final_versions 缺失 session_id",
         "SELECT COUNT(*) FROM final_versions WHERE session_id IS NULL"),
        ("final_versions 缺失 edit_record_id",
         "SELECT COUNT(*) FROM final_versions WHERE edit_record_id IS NULL"),
    ]

    all_ok = True
    for name, query in checks:
        count = conn.execute(query).fetchone()[0]
        if count > 0:
            print(f"  ⚠️  {name}: {count} 条")
            all_ok = False
        else:
            print(f"  ✓ {name}: 0 条")

    if all_ok:
        print("\n✅ 所有数据完整")
    else:
        print("\n⚠️  存在数据缺失，可能需要手动修复")

if __name__ == '__main__':
    migrate_database()
