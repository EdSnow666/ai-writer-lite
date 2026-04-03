# 职责: 智能识别用户输入类型并自动导入素材
# 依赖内部: db.py
# 依赖外部: os, json, uuid, re
# 暴露: detect_and_import(), parse_structured_material()

import os
import json
import uuid
import re
from .db import get_conn


def detect_and_import(user_input):
    """自动识别并导入，返回 material_ids 列表或空列表"""

    # 检测文件路径
    if os.path.isfile(user_input):
        with open(user_input, 'r', encoding='utf-8') as f:
            content = f.read()
        return [save_material(content=content, metadata=json.dumps({'source': 'file', 'path': user_input}))]

    # 检测 JSON
    try:
        data = json.loads(user_input)
        if isinstance(data, dict) and 'content' in data:
            return [save_material(content=data['content'], metadata=json.dumps(data.get('metadata', {})))]
    except (json.JSONDecodeError, ValueError):
        pass

    # 检测多条结构化素材：用 ## N. 笔记_ 分隔（优先于单条检测）
    structured_pattern = r'(##\s*\d+\.\s*笔记_\w+.+?)(?=##\s*\d+\.\s*笔记_|\Z)'
    structured_matches = re.findall(structured_pattern, user_input, re.DOTALL)

    # 处理结构化素材（单条或多条）
    if len(structured_matches) >= 1:
        material_ids = []
        for material_text in structured_matches:
            parsed = parse_structured_material(material_text)
            if parsed:
                mid = save_structured_material(parsed)
                if mid:
                    material_ids.append(mid)
        if material_ids:
            return material_ids

    # 单条结构化素材 fallback（不以 ## N. 笔记_ 开头的情况）
    structured = parse_structured_material(user_input)
    if structured:
        material_id = save_structured_material(structured)
        if material_id:
            return [material_id]

    # 检测多条素材格式：材料1：...材料2：...材料3：...
    material_pattern = r'材料\s*\d+\s*[：:](.*?)(?=材料\s*\d+\s*[：:]|$)'
    matches = re.findall(material_pattern, user_input, re.DOTALL)

    if matches and len(matches) > 1:
        material_ids = []
        for i, content in enumerate(matches, 1):
            content = content.strip()
            if len(content) > 10:
                mid = save_material(content=content, metadata=json.dumps({'source': 'text', 'index': i}))
                material_ids.append(mid)
        return material_ids if material_ids else []

    # 纯文本（长度 > 50 才视为素材）
    if len(user_input.strip()) > 50:
        return [save_material(content=user_input, metadata=json.dumps({'source': 'text'}))]

    return []


def parse_structured_material(text):
    """
    解析结构化素材格式，返回字段字典或 None
    字段名与 knowledge_graph Card 表对齐

    支持格式：
    ## N. 笔记_XXXXX
    **书名**: xxx | **页码**: xxx | **标签**: xxx | **状态**: xxx

    ### 高亮
    > xxx

    ### 正文
    xxx

    ### 原书摘要
    xxx

    ### 批注
    xxx
    """
    result = {}

    # 提取 title（笔记_XXXXX 格式）
    title_match = re.search(r'笔记_(\w+)', text)
    if not title_match:
        return None  # 不是结构化素材格式

    note_id = title_match.group(1)
    result['note_id'] = note_id
    result['title'] = f'笔记_{note_id}'

    # 提取元数据行
    meta_line_match = re.search(r'\*\*书名\*\*[：:]\s*(.+?)(?=\n|$)', text)
    if meta_line_match:
        meta_line = meta_line_match.group(1)
        parts = re.split(r'\s*\|\s*', meta_line)
        for part in parts:
            if '**页码**' in part:
                page_match = re.search(r'\*\*页码\*\*[：:]\s*(\d+)', part)
                if page_match:
                    result['page_number'] = int(page_match.group(1))
            elif '**标签**' in part:
                tags_match = re.search(r'\*\*标签\*\*[：:]\s*(.+)', part)
                if tags_match:
                    result['tags'] = tags_match.group(1).strip()
            elif '**状态**' in part:
                status_match = re.search(r'\*\*状态\*\*[：:]\s*(\w+)', part)
                if status_match:
                    result['status'] = status_match.group(1)
            else:
                result['book_title'] = part.strip()

    # 提取高亮（### 高亮 后的内容，对应 Card.highlights）
    highlight_match = re.search(r'###\s*高亮\s*\n(.*?)(?=###|\Z)', text, re.DOTALL)
    if highlight_match:
        highlight_text = highlight_match.group(1).strip()
        highlight_text = re.sub(r'^>\s*', '', highlight_text, flags=re.MULTILINE)
        highlight_text = re.sub(r'\*\*', '', highlight_text)
        result['highlights'] = highlight_text.strip()

    # 提取正文（### 正文 后的内容，对应 Card.ocr_text）
    body_match = re.search(r'###\s*正文\s*\n(.*?)(?=###|\Z)', text, re.DOTALL)
    if body_match:
        result['ocr_text'] = body_match.group(1).strip()

    # 提取原书摘要
    summary_match = re.search(r'###\s*原书摘要\s*\n(.*?)(?=###|\Z)', text, re.DOTALL)
    if summary_match:
        result['original_summary'] = summary_match.group(1).strip()

    # 提取批注（对应 Card.review_notes）
    annotation_match = re.search(r'###\s*批注\s*\n(.*?)(?=###|\Z)', text, re.DOTALL)
    if annotation_match:
        result['review_notes'] = annotation_match.group(1).strip()

    # content 字段：高亮 + 正文（用于兼容旧逻辑）
    content_parts = []
    if result.get('highlights'):
        content_parts.append(f"【高亮】\n{result['highlights']}")
    if result.get('ocr_text'):
        content_parts.append(f"【正文】\n{result['ocr_text']}")
    result['content'] = '\n\n'.join(content_parts) if content_parts else ''

    return result if result.get('content') else None


def save_structured_material(parsed_data):
    """保存结构化素材到数据库（自动去重），字段与 Card 表对齐"""
    conn = get_conn()

    note_id = parsed_data.get('note_id', '')
    content = parsed_data.get('content', '')

    # 去重检查：优先按 note_id 去重，其次按 content 去重
    existing = None
    if note_id:
        cursor = conn.execute('SELECT id FROM materials WHERE note_id = ?', (note_id,))
        existing = cursor.fetchone()

    if not existing and content:
        cursor = conn.execute('SELECT id FROM materials WHERE content = ?', (content,))
        existing = cursor.fetchone()

    if existing:
        conn.close()
        print(f"[OK] 素材已存在，跳过重复导入: {existing[0]}")
        return existing[0]

    # 创建新素材（字段名与 Card 表对齐）
    material_id = f"mat-{uuid.uuid4().hex[:8]}"
    conn.execute('''
        INSERT INTO materials (
            id, content, source_type, metadata,
            note_id, title, book_title, page_number, tags, status,
            highlights, ocr_text, original_summary, review_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        material_id,
        content,
        'structured',
        json.dumps({'source': 'structured'}),
        parsed_data.get('note_id'),
        parsed_data.get('title'),
        parsed_data.get('book_title'),
        parsed_data.get('page_number'),
        parsed_data.get('tags'),
        parsed_data.get('status'),
        parsed_data.get('highlights'),
        parsed_data.get('ocr_text'),
        parsed_data.get('original_summary'),
        parsed_data.get('review_notes'),
    ))
    conn.commit()
    conn.close()
    return material_id


def save_material(content, metadata):
    """保存普通素材到数据库（自动去重）"""
    conn = get_conn()

    # 去重检查：查找相同内容的已有素材
    cursor = conn.execute('SELECT id FROM materials WHERE content = ?', (content,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing[0]

    # 不存在则创建新素材
    material_id = f"mat-{uuid.uuid4().hex[:8]}"
    conn.execute(
        'INSERT INTO materials (id, content, metadata) VALUES (?, ?, ?)',
        (material_id, content, metadata)
    )
    conn.commit()
    conn.close()
    return material_id
