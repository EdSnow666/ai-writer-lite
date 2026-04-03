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
    conn.execute('PRAGMA foreign_keys=ON;')  # 启用外键约束

    # materials 表 - 支持结构化素材字段（与 knowledge_graph Card 表对齐）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source_type TEXT,
            metadata TEXT,
            note_id TEXT,
            title TEXT,
            book_title TEXT,
            page_number INTEGER,
            tags TEXT,
            status TEXT,
            highlights TEXT,
            ocr_text TEXT,
            original_summary TEXT,
            review_notes TEXT,
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
            scenario_type TEXT,
            writing_purpose TEXT,
            ai_model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP
        )
    ''')

    # edit_records 表 - 用户主动修改记录（第一阶段）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS edit_records (
            id TEXT PRIMARY KEY,
            summary_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            ai_original TEXT,
            final_text TEXT,
            edit_ratio REAL,
            diff_paragraph TEXT,
            diff_sentence TEXT,
            diff_word TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_distilled INTEGER DEFAULT 0,
            is_final INTEGER DEFAULT 0,
            suggestions_raw TEXT,
            FOREIGN KEY (summary_id) REFERENCES summaries(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES modification_sessions(id) ON DELETE CASCADE
        )
    ''')

    # 为现有表添加 suggestions_raw 字段（如果不存在）
    try:
        conn.execute('ALTER TABLE edit_records ADD COLUMN suggestions_raw TEXT')
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 为 summaries 表添加 ai_model 字段（如果不存在）
    try:
        conn.execute('ALTER TABLE summaries ADD COLUMN ai_model TEXT')
    except sqlite3.OperationalError:
        pass  # 字段已存在

    # 为 materials 表添加结构化素材字段（迁移，与 Card 表对齐）
    material_new_fields = [
        ('note_id', 'TEXT'),
        ('title', 'TEXT'),
        ('book_title', 'TEXT'),
        ('page_number', 'INTEGER'),
        ('tags', 'TEXT'),
        ('status', 'TEXT'),
        ('highlights', 'TEXT'),
        ('ocr_text', 'TEXT'),
        ('original_summary', 'TEXT'),
        ('review_notes', 'TEXT'),
    ]
    for field_name, field_type in material_new_fields:
        try:
            conn.execute(f'ALTER TABLE materials ADD COLUMN {field_name} {field_type}')
        except sqlite3.OperationalError:
            pass  # 字段已存在

    # system_prompts 表 - 存储激活的偏好 prompt
    conn.execute('''
        CREATE TABLE IF NOT EXISTS system_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_type TEXT NOT NULL,
            prompt_text TEXT,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            prompt_type TEXT DEFAULT 'writing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')

    # revision_rounds 表 - 打磨轮次记录（第二阶段，可选）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS revision_rounds (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            round_num INTEGER,
            ai_opinion TEXT,
            suggestion_type TEXT,
            user_modified TEXT,
            user_responded INTEGER DEFAULT 0,
            edit_ratio REAL,
            suggestions_raw TEXT,
            user_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES modification_sessions(id) ON DELETE CASCADE
        )
    ''')

    # 为现有表添加新字段（兼容旧数据库结构）
    # 旧字段名映射：ai_suggestion -> ai_opinion, modification_type -> suggestion_type
    migration_fields = [
        ('ai_opinion', 'ALTER TABLE revision_rounds ADD COLUMN ai_opinion TEXT'),
        ('suggestion_type', 'ALTER TABLE revision_rounds ADD COLUMN suggestion_type TEXT'),
        ('user_responded', 'ALTER TABLE revision_rounds ADD COLUMN user_responded INTEGER DEFAULT 0'),
        ('suggestions_raw', 'ALTER TABLE revision_rounds ADD COLUMN suggestions_raw TEXT'),
        ('user_feedback', 'ALTER TABLE revision_rounds ADD COLUMN user_feedback TEXT'),
    ]
    for field_name, alter_sql in migration_fields:
        try:
            conn.execute(alter_sql)
        except sqlite3.OperationalError:
            pass  # 字段已存在

    # 迁移旧字段数据（如果存在旧字段名）
    try:
        # 检查是否有旧的 ai_suggestion 字段
        cursor = conn.execute('PRAGMA table_info(revision_rounds)')
        columns = [col[1] for col in cursor.fetchall()]

        if 'ai_suggestion' in columns and 'ai_opinion' in columns:
            # 将 ai_suggestion 数据复制到 ai_opinion（如果 ai_opinion 为空）
            conn.execute('''
                UPDATE revision_rounds
                SET ai_opinion = ai_suggestion
                WHERE ai_opinion IS NULL AND ai_suggestion IS NOT NULL
            ''')

        if 'modification_type' in columns and 'suggestion_type' in columns:
            # 将 modification_type 数据复制到 suggestion_type
            conn.execute('''
                UPDATE revision_rounds
                SET suggestion_type = modification_type
                WHERE suggestion_type IS NULL AND modification_type IS NOT NULL
            ''')
    except Exception as e:
        pass  # 迁移失败不影响主流程

    # final_versions 表 - 记录用户定稿
    conn.execute('''
        CREATE TABLE IF NOT EXISTS final_versions (
            id TEXT PRIMARY KEY,
            summary_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            edit_record_id TEXT NOT NULL,
            total_rounds INTEGER,
            word_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (summary_id) REFERENCES summaries(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES modification_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (edit_record_id) REFERENCES edit_records(id) ON DELETE CASCADE
        )
    ''')

    # modification_sessions 表 - 记录完整修改会话
    conn.execute('''
        CREATE TABLE IF NOT EXISTS modification_sessions (
            id TEXT PRIMARY KEY,
            summary_id TEXT NOT NULL,
            session_start TIMESTAMP,
            session_end TIMESTAMP,
            total_rounds INTEGER DEFAULT 0,
            is_finalized INTEGER DEFAULT 0,
            final_version_id TEXT,
            first_edit_recorded INTEGER DEFAULT 0,
            FOREIGN KEY (summary_id) REFERENCES summaries(id) ON DELETE CASCADE
        )
    ''')

    # writing_scenarios 表 - 写作场景定义
    conn.execute('''
        CREATE TABLE IF NOT EXISTS writing_scenarios (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            prompt_template TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # scenario_preferences 表 - 每个场景的独立偏好
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scenario_preferences (
            id TEXT PRIMARY KEY,
            scenario_type TEXT NOT NULL,
            version INTEGER,
            preference_summary TEXT,
            system_prompt TEXT,
            distilled_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (scenario_type) REFERENCES writing_scenarios(id) ON DELETE CASCADE
        )
    ''')

    # user_custom_prompts 表 - 用户自定义 prompt（支持历史版本）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_custom_prompts (
            id TEXT PRIMARY KEY,
            scenario_type TEXT NOT NULL,
            custom_prompt TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (scenario_type) REFERENCES writing_scenarios(id) ON DELETE CASCADE
        )
    ''')

    # 初始化默认写作场景
    default_scenarios = [
        ('academic', '学术论文', '学术写作场景，注重严谨性、引用规范、论证逻辑'),
        ('daily_note', '日常笔记', '日常记录场景，简洁明了，便于回顾'),
        ('social_media', '社交媒体', '小红书/微博等社交平台，注重吸引力和传播性'),
        ('report', '工作报告', '职场汇报场景，结构清晰，重点突出'),
        ('creative', '创意写作', '文学创作场景，注重文采和想象力'),
        ('objective', '客观描述', '史料整理/客观记录场景，保持中立，不做主观评价'),
    ]
    for sid, name, desc in default_scenarios:
        conn.execute(
            'INSERT OR IGNORE INTO writing_scenarios (id, name, description) VALUES (?, ?, ?)',
            (sid, name, desc)
        )

    conn.commit()

    # 创建索引以提升查询性能
    create_indexes(conn)

    cleanup_expired_drafts()
    return conn

def create_indexes(conn):
    """创建数据库索引"""
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_edit_records_session ON edit_records(session_id, created_at)',
        'CREATE INDEX IF NOT EXISTS idx_edit_records_summary ON edit_records(summary_id)',
        'CREATE INDEX IF NOT EXISTS idx_revision_rounds_session ON revision_rounds(session_id, round_num)',
        'CREATE INDEX IF NOT EXISTS idx_final_versions_session ON final_versions(session_id)',
        'CREATE INDEX IF NOT EXISTS idx_final_versions_edit ON final_versions(edit_record_id)',
        'CREATE INDEX IF NOT EXISTS idx_sessions_summary ON modification_sessions(summary_id)',
        'CREATE INDEX IF NOT EXISTS idx_scenario_prefs_type ON scenario_preferences(scenario_type, is_active)',
        'CREATE INDEX IF NOT EXISTS idx_writing_prefs_active ON writing_preferences(is_active, prompt_type)',
        'CREATE INDEX IF NOT EXISTS idx_custom_prompts_scenario ON user_custom_prompts(scenario_type, is_active, created_at)',
    ]
    for idx_sql in indexes:
        try:
            conn.execute(idx_sql)
        except Exception as e:
            pass  # 索引已存在
    conn.commit()

def get_conn():
    """获取数据库连接（设置 text_factory 确保中文正确读取）"""
    conn = sqlite3.connect(DB_PATH)
    conn.text_factory = str
    conn.execute('PRAGMA foreign_keys=ON;')  # 每次连接都启用外键
    return conn

def check_dependencies():
    """检查依赖，缺失仅提示"""
    try:
        import jieba
        return True
    except ImportError:
        pass  # 静默处理，不影响用户体验
        return False
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
