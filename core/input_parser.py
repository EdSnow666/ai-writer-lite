# 职责: 智能识别用户输入类型并自动导入素材
# 依赖内部: db.py
# 依赖外部: os, json, uuid
# 暴露: detect_and_import()

import os
import json
import uuid
from .db import get_conn

def detect_and_import(user_input):
    """自动识别并导入，返回 material_id 或 None"""

    # 检测文件路径
    if os.path.isfile(user_input):
        with open(user_input, 'r', encoding='utf-8') as f:
            content = f.read()
        return save_material(content, json.dumps({'source': 'file', 'path': user_input}))

    # 检测 JSON
    try:
        data = json.loads(user_input)
        if isinstance(data, dict) and 'content' in data:
            return save_material(data['content'], json.dumps(data.get('metadata', {})))
    except (json.JSONDecodeError, ValueError):
        pass

    # 纯文本（长度 > 50 才视为素材）
    if len(user_input.strip()) > 50:
        return save_material(user_input, json.dumps({'source': 'text'}))

    return None

def save_material(content, metadata):
    """保存素材到数据库"""
    material_id = f"mat-{uuid.uuid4().hex[:8]}"
    conn = get_conn()
    conn.execute(
        'INSERT INTO materials (id, content, metadata) VALUES (?, ?, ?)',
        (material_id, content, metadata)
    )
    conn.commit()
    conn.close()
    return material_id
