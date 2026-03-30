#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 AI 写作助手核心功能"""

import sys
import os
import io

# Windows 编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from core.db import init_db, check_dependencies

def test_init():
    """测试初始化"""
    print("=== 测试初始化 ===")
    init_db()
    print("✓ 数据库初始化成功")

    has_jieba = check_dependencies()
    if has_jieba:
        print("✓ jieba 已安装")
    else:
        print("⚠ jieba 未安装（可选）")

def test_material_import():
    """测试素材导入"""
    print("\n=== 测试素材导入 ===")
    from core.input_parser import detect_and_import

    # 测试短文本（不导入）
    result = detect_and_import("写一段文本")
    assert result is None, "短文本不应导入"
    print("✓ 短文本识别正确")

    # 测试长文本（导入）
    long_text = "这是一段测试文本。" * 20
    material_id = detect_and_import(long_text)
    assert material_id is not None, "长文本应该导入"
    print(f"✓ 长文本导入成功: {material_id}")

def test_diff():
    """测试 Diff 计算"""
    print("\n=== 测试 Diff 计算 ===")
    from core.diff_engine import calc_paragraph_diff, calc_sentence_diff

    original = "这是第一段。\n\n这是第二段。"
    final = "这是修改后的第一段。\n\n这是第二段。"

    diff = calc_paragraph_diff(original, final)
    print(f"✓ 段落 Diff: {len(diff['modified'])} 处修改")

    diff = calc_sentence_diff(original, final)
    print(f"✓ 句子 Diff: {len(diff['modified'])} 处修改")

if __name__ == '__main__':
    try:
        test_init()
        test_material_import()
        test_diff()
        print("\n✅ 所有测试通过")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
