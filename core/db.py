# 职责: SQLite 数据库初始化和连接管理
# 依赖外部: sqlite3
# 暴露: init_db(), get_conn(), check_dependencies(), cleanup_expired_drafts()

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser('~/.claude/skills/ai-writer-lite/data/writer.db')

def init_db():
    """初始化数据库，启用 WAL 模式，自动清理过期文件"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')

    # materials 表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source_type TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # summaries 表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id TEXT PRIMARY KEY,
            material_ids TEXT,
            user_prompt TEXT,
            ai_original TEXT,
            final_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP
        )
    ''')

    # edit_records 表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS edit_records (
            id TEXT PRIMARY KEY,
            summary_id TEXT,
            ai_original TEXT,
            final_text TEXT,
            edit_ratio REAL,
            diff_paragraph TEXT,
            diff_sentence TEXT,
            diff_word TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_distilled INTEGER DEFAULT 0
        )
    ''')

    # writing_preferences 表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS writing_preferences (
            id TEXT PRIMARY KEY,
            version INTEGER,
            preference_summary TEXT,
            system_prompt TEXT,
            distilled_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')

    conn.commit()
    cleanup_expired_drafts()
    return conn

def get_conn():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

def check_dependencies():
    """检查依赖，缺失仅提示"""
    try:
        import jieba
        return True
    except ImportError:
        print("⚠️  建议安装 jieba 以获得更好的中文分词效果")
        print("运行：pip install jieba")
        return False

def cleanup_expired_drafts(hours=24):
    """清理过期临时文件"""
    temp_dir = os.path.expanduser('~/.claude/skills/ai-writer-lite/temp')
    if not os.path.exists(temp_dir):
        return

    cutoff = datetime.now() - timedelta(hours=hours)
    for file in os.listdir(temp_dir):
        if file.startswith('draft_'):
            path = os.path.join(temp_dir, file)
            if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                os.remove(path)
