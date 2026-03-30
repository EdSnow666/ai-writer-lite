#!/usr/bin/env python3
# 职责: AI 写作助手主入口
# 依赖内部: core/*
# 暴露: main()

import sys
import json
from core.db import init_db, check_dependencies, get_conn
from core.input_parser import detect_and_import
from core.generator import generate_with_materials, generate_freeform, save_summary, get_active_preference
from core.temp_manager import create_draft, read_draft, delete_draft
from core.diff_engine import calc_paragraph_diff, calc_sentence_diff, calc_word_diff_by_paragraph
from core.distiller import should_trigger, distill_preferences, update_system_prompt
import uuid

def main():
    # 初始化
    init_db()
    check_dependencies()

    # 解析命令行参数
    if len(sys.argv) < 2:
        print("用法: python main.py <用户输入>")
        return

    user_input = ' '.join(sys.argv[1:])

    # 自动识别素材
    material_id = detect_and_import(user_input)

    if material_id:
        print(f"✓ 已导入素材")
        print("\n您希望我怎么处理这些材料？")
    else:
        print("好的！您有相关的参考材料吗？可以直接粘贴，或者我直接创作。")

if __name__ == '__main__':
    main()
