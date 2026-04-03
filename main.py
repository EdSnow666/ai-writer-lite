#!/usr/bin/env python3
# 职责：AI 写作助手主入口 - 支持对话式交互、动态修改、多轮修改记录
# 依赖内部：core/*
# 暴露：main(), run_interactive(), prompt_custom_prompt_interaction()
# 最后更新：2026-04-03

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import json
import readline
import re
from core.db import init_db, check_dependencies, get_conn
from core.input_parser import detect_and_import
from core.generator import (
    generate_with_materials, generate_freeform, generate_revision,
    generate_revision_opinion, save_summary, get_active_preference, ask_if_finalized,
    analyze_modification_type, get_custom_prompt, save_custom_prompt, extract_ai_model
)
from core.temp_manager import create_draft, read_draft, delete_draft, open_draft, clean_suggestions
from core.revision_manager import (
    start_modification_session, record_first_edit, record_revision_round,
    finalize_session, get_session_history, get_final_versions,
    count_final_versions, reopen_session,
    update_edit_record_final, mark_last_edit_as_final
)
from core.edit_records import save_edit_record, count_undistilled
from core.distiller import (
    should_trigger_distill, distill_preferences, update_system_prompt,
    should_trigger_final_distill, distill_from_final_versions
)
from core.session_state import WritingSession
from config import EDIT_CONFIG
import uuid

def handle_assistant_mode(text, interactive=True):
    """处理 Assistant 模式：输出 prompt 让当前 AI 生成"""
    if not text.startswith("__ASSISTANT_MODE__"):
        return text

    # 解析 prompt
    lines = text.split('\n', 2)
    system_prompt = lines[1].replace("SYSTEM: ", "")
    user_prompt = lines[2].replace("USER: ", "")

    if not interactive:
        # 非交互模式：输出 prompt 供外部 AI 处理
        print("\n" + "="*60)
        print("✨ 正在准备写作内容...")
        print("="*60)
        print(f"\n【System】\n{system_prompt}")
        print(f"\n【User】\n{user_prompt}")
        print("\n" + "="*60)
        print("\n请将生成的 JSON 内容粘贴到下方（单独一行输入 END 结束）：")

        # 读取 AI 输入
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
        except EOFError:
            from core.logger import log_error
            log_error("EOFError: 非交互环境下无法读取输入")
            return ""

        return '\n'.join(lines)

    # 交互模式：等待用户输入
    print("\n" + "="*60)
    print("[Assistant Mode] 请 AI 助手根据以下 prompt 生成内容")
    print("="*60)
    print(f"\n【System】\n{system_prompt}")
    print(f"\n【User】\n{user_prompt}")
    print("\n" + "="*60)
    print("请将生成的内容粘贴到下方：")

    # 读取多行输入
    lines = []
    print("（输入完成后，单独一行输入 END 结束）")
    try:
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
    except EOFError:
        from core.logger import log_error
        log_error("EOFError: 非交互环境下无法读取输入")
        return ""

    return '\n'.join(lines)

# 全局状态
session = WritingSession()

def main():
    """主入口：支持命令行和交互模式"""
    # 初始化
    init_db()
    check_dependencies()

    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        # 命令行模式：处理单个请求
        user_input = ' '.join(sys.argv[1:])
        handle_single_request(user_input)
    else:
        # 交互模式
        run_interactive()

def handle_single_request(user_input):
    """处理单个请求（命令行模式）"""
    # 处理特殊命令
    if user_input.lower() in ['list', 'ls', '列表']:
        list_all_articles()
        return

    if user_input.lower().startswith('resume ') or user_input.lower().startswith('继续 '):
        article_id = user_input.split(' ', 1)[1]
        resume_article(article_id)
        return

    if user_input.lower().startswith('polish ') or user_input.lower().startswith('打磨 '):
        article_id = user_input.split(' ', 1)[1]
        polish_article(article_id)
        return

    if user_input.lower().startswith('polish-inject '):
        parts = user_input.split(' ', 2)
        if len(parts) < 3:
            print("用法: polish-inject <article_id> <json_file_path>")
            return
        article_id = parts[1]
        json_file = parts[2]
        polish_inject(article_id, json_file)
        return

    if user_input.lower().startswith('sync '):
        article_id = user_input.split(' ', 1)[1]
        sync_article(article_id)
        return

    # 新增：save-materials 命令
    if user_input.lower().startswith('save-materials '):
        materials_text = user_input.split(' ', 1)[1]
        cmd_save_materials(materials_text)
        return

    # 新增：generate 命令
    if user_input.lower().startswith('generate '):
        cmd_generate(user_input)
        return

    # 新增：save-article 命令
    if user_input.lower().startswith('save-article '):
        cmd_save_article(user_input)
        return

    # 新增：finalize 命令
    if user_input.lower().startswith('finalize '):
        article_id = user_input.split(' ', 1)[1]
        cmd_finalize(article_id)
        return

    # 新增：distill-preference 命令
    if user_input.lower().startswith('distill-preference '):
        scenario = user_input.split(' ', 1)[1]
        cmd_distill_preference(scenario)
        return

    # 新增：save-preference 命令
    if user_input.lower().startswith('save-preference '):
        cmd_save_preference(user_input)
        return

    # 自动识别素材
    material_ids = detect_and_import(user_input)

    if material_ids:
        print(f"[OK] 已记录 {len(material_ids)} 条素材到数据库")
        print("\n您希望我怎么处理这些材料？")
        # 等待用户输入
        intent = input("> ")
        text = generate_with_materials(material_ids, intent)
        print("\n" + "=" * 50)
        print(text)
        print("=" * 50)
    else:
        print("好的！您有相关的参考材料吗？可以直接粘贴，或者我直接创作。")

def run_interactive():
    """交互模式：支持多轮对话和动态修改"""
    global session

    print("=" * 60)
    print("AI 写作助手 - 交互式写作")
    print("=" * 60)
    print("\n【功能说明】")
    print("1. 直接输入你想写的内容，或粘贴素材")
    print("2. AI 生成后，你可以：")
    print("   - 直接修改文本中的任意段落")
    print("   - 告诉 AI 哪里需要改")
    print("   - 说'定稿'或'完成'结束本次写作")
    print("3. AI 会学习你的修改习惯，越用越懂你")
    print("\n输入 'quit' 退出，'help' 查看帮助")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n【你】> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ('quit', 'exit', 'q'):
                print("再见！")
                break

            if user_input.lower() == 'help':
                show_help()
                continue

            if user_input.lower() == 'status':
                show_status()
                continue

            if user_input.lower() in ('sync', '同步'):
                do_sync_draft()
                continue

            # 检查是否是反馈萃取命令
            if user_input.lower() in ('反馈萃取', '萃取反馈', 'learn feedback'):
                do_distill_feedback()
                continue

            # 检查是否是定稿指令
            if user_input.lower() in ('定稿', '完成', 'finished', 'done', 'finalize'):
                if session.summary_id:
                    do_finalize()
                else:
                    print("当前没有进行中的写作会话")
                continue

            # 检查是否是查看历史
            if user_input.lower() in ('历史', 'history', '查看修改', 'review'):
                if session.summary_id:
                    show_history()
                else:
                    print("当前没有进行中的写作会话")
                continue

            # 处理用户输入
            if session.summary_id and session.ai_original:
                # 多轮修改模式
                handle_revision(user_input)
            else:
                # 首次生成模式
                handle_initial_request(user_input)

        except KeyboardInterrupt:
            print("\n\n会话中断。输入'quit'退出。")
            continue
        except Exception as e:
            print(f"[错误] 发生错误：{e}")
            continue

def ask_scenario(user_input):
    """引导用户选择写作场景和目的"""
    print("\n" + "=" * 60)
    print("【写作场景选择】")
    print("=" * 60)
    print("请问您这次写作的主要场景是？")
    print("1. 学术论文 - 严谨论证，注重引用")
    print("2. 日常笔记 - 简洁明了，便于回顾")
    print("3. 社交媒体 - 吸引力强，适合传播")
    print("4. 工作报告 - 结构清晰，重点突出")
    print("5. 创意写作 - 文采丰富，富有想象")
    print("6. 客观描述 - 中立记录，不做评价")

    while True:
        choice = input("\n请选择 (1-6)> ").strip()
        scenario_map = {
            '1': 'academic',
            '2': 'daily_note',
            '3': 'social_media',
            '4': 'report',
            '5': 'creative',
            '6': 'objective'
        }
        if choice in scenario_map:
            scenario_type = scenario_map[choice]
            break
        print("无效选择，请输入 1-6 之间的数字")

    # 询问写作目的
    print("\n【写作目的】")
    print("这段话/文章主要用于什么目的？")
    print("[提示] 示例：阐述一个观点 / 记录一个事件 / 说服读者 / 汇报进展")
    writing_purpose = input("> ").strip()

    return scenario_type, writing_purpose

def prompt_custom_prompt_interaction(scenario_type):
    """交互式确认自定义 prompt（显示/询问修改/询问创建）"""
    # 获取场景名称映射
    scenario_names = {
        'academic': '学术论文',
        'daily_note': '日常笔记',
        'social_media': '社交媒体',
        'report': '工作报告',
        'creative': '创意写作',
        'objective': '客观描述'
    }
    scenario_name = scenario_names.get(scenario_type, scenario_type)

    print("\n" + "=" * 60)
    print("【自定义 Prompt 设置】")
    print("=" * 60)
    print(f"当前场景：{scenario_name}")

    # 获取已保存的自定义 prompt
    custom_prompt = get_custom_prompt(scenario_type)

    if custom_prompt:
        print("\n当前自定义 Prompt：")
        print("-" * 40)
        print(custom_prompt)
        print("-" * 40)
        print("\n是否修改？(修改/不修改)")

        while True:
            choice = input("> ").strip().lower()
            if choice in ('修改', 'edit', 'change'):
                print("\n请输入新的自定义 Prompt：")
                new_prompt = input("> ").strip()
                if new_prompt:
                    save_custom_prompt(scenario_type, new_prompt)
                    print("\n[OK] 自定义 Prompt 已更新")
                    return new_prompt
                else:
                    print("\n[提示] 输入为空，保留原有 Prompt")
                    return custom_prompt
            elif choice in ('不修改', 'skip', 'no', '保持'):
                print("\n[OK] 保持原有自定义 Prompt")
                return custom_prompt
            else:
                print("无效选择，请输入 '修改' 或 '不修改'")
    else:
        print("\n当前场景未设置自定义 Prompt。")
        print("\n是否创建？(创建/不创建)")

        while True:
            choice = input("> ").strip().lower()
            if choice in ('创建', 'create', 'new', 'add'):
                print("\n请输入自定义 Prompt：")
                print("[提示] 例如：使用简洁的语言，避免复杂长句")
                new_prompt = input("> ").strip()
                if new_prompt:
                    save_custom_prompt(scenario_type, new_prompt)
                    print("\n[OK] 自定义 Prompt 已保存")
                    return new_prompt
                else:
                    print("\n[提示] 输入为空，跳过创建")
                    return None
            elif choice in ('不创建', 'skip', 'no'):
                print("\n[OK] 不设置自定义 Prompt")
                return None
            else:
                print("无效选择，请输入 '创建' 或 '不创建'")

def handle_initial_request(user_input):
    """处理初始请求"""
    global session

    # 尝试识别素材
    material_ids = detect_and_import(user_input)

    # 引导用户选择场景和目的
    scenario_type, writing_purpose = ask_scenario(user_input)

    # 交互式确认自定义 prompt（强制步骤）
    custom_prompt = prompt_custom_prompt_interaction(scenario_type)

    print(f"\n[OK] 场景：{scenario_type} | 目的：{writing_purpose}")

    # Bug #2 修复：明确告知用户素材已保存
    if material_ids:
        print(f"\n✓ 已记录 {len(material_ids)} 条素材到数据库")
        intent = input("【你希望怎么写？】> ")
        text = generate_with_materials(material_ids, intent, scenario_type, writing_purpose, custom_prompt=custom_prompt)
        text = handle_assistant_mode(text)
    else:
        # 无素材创作
        print("\n好的，我来帮你创作。")
        text = generate_freeform(user_input, scenario_type, writing_purpose, custom_prompt=custom_prompt)
        text = handle_assistant_mode(text)

    # 保存摘要
    summary_id = save_summary(
        material_ids,
        user_input,
        text,
        scenario_type,
        writing_purpose
    )

    # 开始修改会话
    session_id = start_modification_session(summary_id)

    # 更新会话状态
    session.start_new(session_id, summary_id, text, scenario_type, writing_purpose)

    # 创建草稿文件
    draft_path = create_draft(summary_id, text)

    # 输出结果
    print("\n" + "=" * 60)
    print("【AI 生成】")
    print("=" * 60)
    print(text)
    print("=" * 60)
    print(f"\n[已保存] 草稿文件：{draft_path}")

    # Bug #3 修复：自动打开草稿文件
    open_draft(draft_path)
    print(f"[已打开] 草稿文件已在编辑器中打开")

    print(f"\n[提示] 接下来你可以：")
    print(f"1. 直接修改草稿文件中的内容")
    print(f"2. 在对话框中粘贴你修改后的文本")
    print(f"\n提示：如果你只做了少量修改（编辑比例<{EDIT_CONFIG['ratio_threshold']:.0%}），")
    print(f"AI 会提示你确认是否继续，因为只有较大修改才会被记录到写作偏好。")
    print()
    print("请粘贴你修改后的文本，或输入 '打磨' 让 AI 提出修改建议：")

def handle_revision(user_input):
    """
    处理修改请求 - 支持两阶段流程：

    第一阶段 (编辑记录)：
    - 用户修改 → AI 分析编辑比例 → 达到阈值则保存到 edit_records
    - 如果用户希望 AI 基于萃取重生成，可以触发重生成

    第二阶段 (打磨轮次，可选)：
    - 用户说"打磨"→ AI 提出修改意见
    - 用户根据意见修改 → 记录到 revision_rounds

    定稿：
    - 用户说"定稿"→ 标记最后一条 edit_record 为 is_final，保存到 final_versions
    """
    global session

    summary_id = session.summary_id
    session_id = session.session_id
    ai_original = session.ai_original
    scenario_type = session.scenario_type
    writing_purpose = session.writing_purpose

    # 检查是否是打磨命令
    if user_input.strip() in ('打磨', 'polish', '建议', '修改意见'):
        handle_polish_request(ai_original, scenario_type, writing_purpose)
        return

    # 检查是否是 AI 重生成请求
    if user_input.strip().startswith('重生成') or user_input.strip().startswith('再生成一个'):
        handle_ai_regenerate(summary_id, session_id, user_input)
        return

    # 默认：用户直接修改文本（第一阶段）
    handle_user_edit(summary_id, session_id, ai_original, user_input)


def handle_user_edit(summary_id, session_id, ai_original, user_modified):
    """
    第一阶段：处理用户主动修改
    记录到 edit_records 表
    """
    global session

    # 检查是否是在打磨轮次中的修改
    if session.waiting_for_polish:
        # 这是打磨轮次，记录到 revision_rounds
        handle_polish_round(
            session_id,
            session.last_ai_opinion or '',
            session.last_suggestion_type or '',
            ai_original,
            user_modified
        )
        session.waiting_for_polish = False
        return

    record_id, success, edit_ratio = record_first_edit(summary_id, session_id, ai_original, user_modified)

    if not success:
        # 编辑比例太低，提示用户
        print("\n" + "=" * 60)
        print("[ ! ]  编辑比例检测")
        print("=" * 60)
        print(f"当前编辑比例：{edit_ratio:.1%}（低于阈值{EDIT_CONFIG['ratio_threshold']:.0%}）")
        print("\n你只做了少量修改/一段修改，这可能不足以代表你的写作偏好。")
        print("\n请选择：")
        print("1. 继续修改（推荐）- 输入 '继续' 或直接粘贴更多修改")
        print("2. 强制保存 - 输入 '保存'，即使编辑比例低也会记录")
        print("3. 进入打磨轮次 - 输入 '打磨'，AI 会提出修改建议")
        print("4. AI 重生成 - 输入 '重生成'，基于你的修改完全重写")
        print("\n[提示] 建议：继续修改能让 AI 更好地学习你的写作风格")

        choice = input("> ").strip().lower()

        if choice in ('保存', 'force'):
            # 强制保存
            conn = get_conn()
            from core.edit_records import save_edit_record
            suggestions_raw = getattr(session, 'last_suggestions', None)
            edit_record_id = save_edit_record(summary_id, ai_original, user_modified, suggestions_raw)
            conn.execute('UPDATE modification_sessions SET first_edit_recorded = 1 WHERE id = ?', (session_id,))
            conn.commit()
            conn.close()
            print(f"\n[OK] 已强制保存到 edit_records: {edit_record_id}")
            session.mark_first_edit_done()
            session.ai_original = user_modified
        elif choice in ('打磨', 'polish'):
            handle_polish_request(ai_original, session.scenario_type, session.writing_purpose)
            return
        elif choice.startswith('重生成'):
            handle_ai_regenerate(summary_id, session_id, user_modified, ai_original)
            return
        else:
            # 继续修改，不保存
            print("\n好的，请继续修改你的文本。")
            return

    # 成功记录第一轮修改
    session.mark_first_edit_done()
    session.ai_original = user_modified

    print("\n" + "=" * 60)
    print("[OK] 第一轮修改已记录")
    print("=" * 60)
    print(f"编辑比例：{edit_ratio:.1%}")
    print(f"记录 ID: {record_id}")
    print("\n接下来：")
    print("1. 输入 '打磨' - AI 提出修改建议，帮助进一步打磨")
    print("2. 继续修改文本 - AI 记录你的修改过程")
    print("3. 输入 '重生成' - AI 基于你的修改完全重写")
    print("4. 输入 '定稿' - 结束当前写作会话")

    # 主动询问是否定稿
    finalize_prompt = ask_if_finalized(session.round_num)
    print(f"\n[提示] {finalize_prompt}")


def handle_polish_request(ai_original, scenario_type, writing_purpose):
    """
    第二阶段：AI 提出修改意见，直接注入到草稿文件中
    格式：%%（问题：XX，建议：XX，用户反馈：）%%
    返回：(opinions, suggestions, suggestion_types)
    """
    from core.logger import log_info, log_debug, log_error
    global session

    log_info(f"handle_polish_request 开始")
    log_debug(f"输入文本长度: {len(ai_original)}, 场景: {scenario_type}, 目的: {writing_purpose}")

    # 打磨前交互式确认自定义 prompt（强制步骤）
    custom_prompt = prompt_custom_prompt_interaction(scenario_type)

    # 获取结构化建议
    opinions, suggestions, suggestion_types = generate_revision_opinion(ai_original, scenario_type, writing_purpose, custom_prompt=custom_prompt)
    log_debug(f"generate_revision_opinion 返回: opinions长度={len(opinions) if opinions else 0}, suggestions数量={len(suggestions) if suggestions else 0}")

    # 检查是否是 Assistant Mode（API 禁用）
    if opinions.startswith("__ASSISTANT_MODE__"):
        # 让当前 AI 生成（根据是否交互模式决定）
        interactive = session.session_id is not None  # 有会话ID说明是交互模式
        ai_response = handle_assistant_mode(opinions, interactive=False)  # polish命令始终非交互

        # 解析 AI 返回的 JSON
        if ai_response:
            import json
            try:
                response_data = json.loads(ai_response)
                suggestions = response_data.get('suggestions', [])
                log_debug(f"解析 JSON 成功，suggestions 数量: {len(suggestions)}")

                # 生成 opinions 文本（用于显示）
                opinions_lines = []
                for i, sug in enumerate(suggestions, 1):
                    opinions_lines.append(f"{i}. {sug.get('anchor', '全文')}")
                    opinions_lines.append(f"   问题：{sug.get('problem', '')}")
                    opinions_lines.append(f"   建议：{sug.get('advice', '')}")
                opinions = '\n'.join(opinions_lines)

                # 提取建议类型（暂时留空）
                suggestion_types = "通用"
            except json.JSONDecodeError as e:
                log_error(f"JSON 解析失败: {e}")
                log_error(f"AI 返回内容: {ai_response[:200]}")
                opinions = ai_response
                suggestions = []
        else:
            opinions = ""
            suggestions = []

    log_debug(f"handle_assistant_mode 处理后: opinions长度={len(opinions) if opinions else 0}, suggestions数量={len(suggestions)}")

    # 保存 AI 意见和类型，供用户修改后记录
    session.last_ai_opinion = opinions
    session.last_suggestion_type = suggestion_types
    session.waiting_for_polish = True
    session.last_suggestions = suggestions  # 保存结构化建议

    # 将建议注入到草稿文件
    summary_id = session.summary_id
    log_debug(f"session.summary_id = {summary_id}")
    if summary_id:
        # 读取当前草稿
        from core.temp_manager import read_draft, inject_suggestions, open_draft, clean_suggestions, DRAFTS_DIR
        import os
        log_info(f"读取草稿文件: {summary_id}")
        current_draft = read_draft(summary_id)
        if current_draft:
            log_debug(f"草稿文件读取成功，长度: {len(current_draft)}")
            # 先清理旧建议，再注入新建议
            clean_draft = clean_suggestions(current_draft)
            log_debug(f"清理后长度: {len(clean_draft)}")
            updated_draft = inject_suggestions(clean_draft, suggestions)
            log_debug(f"注入后长度: {len(updated_draft)}")
            # 保存回文件
            draft_path = os.path.join(DRAFTS_DIR, f'draft_{summary_id}.md')
            with open(draft_path, 'w', encoding='utf-8') as f:
                f.write(updated_draft)
            log_info(f"草稿文件已保存: {draft_path}")

            # 打开文件
            log_info(f"打开草稿文件: {summary_id}")
            open_draft(summary_id)

            # 显示建议和提示
            print("\n" + "=" * 60)
            print("【AI 修改建议】")
            print("=" * 60)
            print(opinions)
            print("=" * 60)
            print(f"\n建议类型：{suggestion_types or '通用'}")
            print("\n[OK] 建议已注入到草稿文件中")
            print("[OK] 草稿文件已打开，请在编辑器中修改")
            print("\n【使用说明】")
            print("1. 在文中找到 %%...%% 标记的建议（紧跟在对应段落后）")
            print("2. 直接在文中修改，或在 '用户反馈：' 后填写想法")
            print("3. 修改完成后保存文件，回到这里输入 'sync' 同步")
            print("4. [注意] 定稿时 %%...%% 内容会自动移除，无需手动删除！")
            print("\n[提示] 提示：修改完成后，请务必输入 'sync' 让 AI 记录你的修改")
        else:
            # 没有草稿文件，创建一个新的
            log_info("草稿文件不存在，创建新草稿")
            from core.temp_manager import create_draft
            from core.temp_manager import inject_suggestions, open_draft
            updated_draft = inject_suggestions(ai_original, suggestions)
            create_draft(summary_id, updated_draft)
            log_info(f"新草稿已创建: {summary_id}")
            open_draft(summary_id)
            log_info(f"草稿文件已打开: {summary_id}")

            # 显示建议和提示
            print("\n" + "=" * 60)
            print("【AI 修改建议】")
            print("=" * 60)
            print(opinions)
            print("=" * 60)
            print(f"\n建议类型：{suggestion_types or '通用'}")
            print("\n[OK] 建议已注入到草稿文件中")
            print("[OK] 草稿文件已打开，请在编辑器中修改")
            print("\n【使用说明】")
            print("1. 在文中找到 %%...%% 标记的建议（紧跟在对应段落后）")
            print("2. 直接在文中修改，或在 '用户反馈：' 后填写想法")
            print("3. 修改完成后保存文件，回到这里输入 'sync' 同步")
            print("4. [注意] 定稿时 %%...%% 内容会自动移除，无需手动删除！")
            print("\n[提示] 提示：修改完成后，请务必输入 'sync' 让 AI 记录你的修改")
    else:
        log_error("session.summary_id 为空，无法注入建议")
        print("\n请根据以上建议修改文本，然后粘贴修改后的内容：")

    log_info(f"handle_polish_request 完成，返回 opinions, suggestions, suggestion_types")
    return (opinions, suggestions, suggestion_types)


def handle_ai_regenerate(summary_id, session_id, user_modified, ai_original=None):
    """
    AI 基于用户修改完全重写
    生成后更新 ai_original，用户可继续修改
    """
    global session

    if ai_original is None:
        ai_original = session.ai_original

    print("\n【AI 重生成中...】")
    scenario_type = session.scenario_type
    writing_purpose = session.writing_purpose

    revised_text, mod_type = generate_revision(user_modified, ai_original)
    revised_text = handle_assistant_mode(revised_text)

    # 创建新的 edit_record
    conn = get_conn()
    from core.edit_records import save_edit_record
    suggestions_raw = getattr(session, 'last_suggestions', None)
    edit_record_id = save_edit_record(summary_id, ai_original, revised_text, suggestions_raw)
    conn.execute('UPDATE modification_sessions SET first_edit_recorded = 1 WHERE id = ?', (session_id,))
    conn.commit()
    conn.close()

    # 更新会话状态
    session.ai_original = revised_text
    session.round_num += 1

    print("\n" + "=" * 60)
    print(f"[OK] AI 重生成完成（修改类型：{mod_type}）")
    print("=" * 60)
    print(revised_text)
    print("=" * 60)
    print(f"\n新记录 ID: {edit_record_id}")

    # 主动询问是否定稿
    finalize_prompt = ask_if_finalized(session.round_num)
    print(f"\n[提示] {finalize_prompt}")


def handle_polish_round(session_id, ai_opinion, suggestion_type, prev_text, user_modified):
    """
    处理打磨轮次（第二阶段）
    记录 AI 意见、用户修改、响应情况到 revision_rounds
    """
    global session

    session.start_polish_round()
    polish_round = session.polish_round

    # 解析用户反馈
    from core.temp_manager import parse_user_feedback
    feedbacks = parse_user_feedback(user_modified)

    # 记录到 revision_rounds（包含原始建议和用户反馈）
    suggestions_raw = getattr(session, 'last_suggestions', [])
    revision_id, responded, ratio = record_revision_round(
        session_id=session_id,
        round_num=polish_round,
        ai_opinion=ai_opinion,
        suggestion_type=suggestion_type,
        user_modified=user_modified,
        prev_text=prev_text,
        suggestions_raw=suggestions_raw,
        user_feedback=feedbacks
    )

    # 显示反馈摘要
    if feedbacks:
        responded_count = sum(1 for f in feedbacks if f['responded'])
        print(f"\n[OK] 检测到 {len(feedbacks)} 条用户反馈，其中 {responded_count} 条有填写内容")

    session.ai_original = user_modified
    session.complete_polish_round()

    print("\n" + "=" * 60)
    print(f"[OK] 打磨轮次 #{polish_round} 已记录")
    print("=" * 60)
    print(f"编辑比例：{ratio:.1%}")
    print(f"用户响应：{'是' if responded else '否'}")
    print(f"记录 ID: {revision_id}")
    print("\n接下来：")
    print("1. 输入 '打磨' - AI 继续提出修改建议")
    print("2. 继续修改文本 - 进一步打磨")
    print("3. 输入 '定稿' - 结束当前写作会话")

    # 主动询问是否定稿
    finalize_prompt = ask_if_finalized(session.round_num)
    print(f"\n[提示] {finalize_prompt}")

def do_finalize():
    """定稿处理 - 清理 %%...%% 标记后保存最终稿"""
    global session

    if not session.summary_id:
        print("当前没有进行中的会话")
        return

    # 获取最终文本（先清理 %%...%% 标记）
    final_text = session.ai_original
    # 尝试读取草稿文件并清理标记
    summary_id = session.summary_id
    draft_content = read_draft(summary_id)
    if draft_content:
        # 清理打磨建议标记
        final_text = clean_suggestions(draft_content)

    session_id = session.session_id

    # 先将最后一条 edit_record 标记为 is_final=1
    mark_last_edit_as_final(session_id)

    # 定稿
    final_id = finalize_session(session_id, final_text)

    print(f"\n[OK] 已定稿！ID: {final_id}")
    print(f"总共经过 {session.round_num} 轮修改")
    print(f"其中打磨轮次：{session.polish_round} 轮")

    # 检查是否触发写作偏好萃取（全量模式）
    total_edits = count_undistilled()  # 现在返回总数
    conn = get_conn()
    cursor = conn.execute('SELECT COALESCE(MAX(distilled_count), 0) FROM writing_preferences WHERE prompt_type = "writing" AND is_active = 1')
    last_distill_count = cursor.fetchone()[0]
    conn.close()

    if should_trigger_distill(total_edits, last_distill_count):
        print(f"\n[提示] 全量萃取：共 {total_edits} 条记录，上次萃取时 {last_distill_count} 条...")
        do_distill_now(total_edits)

    # 检查是否触发用户反馈萃取
    from core.feedback_distiller import should_trigger_feedback_distill, distill_user_feedback
    from core.distiller import update_system_prompt
    should_trigger_fb, count = should_trigger_feedback_distill()
    if should_trigger_fb:
        print(f"\n[提示] 检测到 {count} 条用户反馈，正在萃取学习...")
        feedback_pref = distill_user_feedback()
        if feedback_pref:
            print(f"[OK] 用户反馈偏好萃取完成：\n{feedback_pref[:200]}...")

    # 检查是否触发定稿萃取
    final_count = count_final_versions()
    if should_trigger_final_distill(final_count):
        print("\n[提示] 检测到足够的定稿，正在萃取定稿特征...")
        do_distill_finals()

    # 重置会话
    session.finalize()
    session.reset()

    print("\n开始新的写作会话吧！")

def do_sync_draft():
    """同步草稿文件到数据库"""
    global session

    if not session.summary_id:
        print("当前没有进行中的会话")
        return

    summary_id = session.summary_id
    ai_original = session.ai_original

    # 读取草稿文件
    user_modified = read_draft(summary_id)

    if not user_modified:
        print("草稿文件不存在或为空")
        return

    # 计算编辑比例
    from difflib import SequenceMatcher
    edit_ratio = 1 - SequenceMatcher(None, ai_original, user_modified).ratio()

    # 保存到数据库（包含原始建议）
    suggestions_raw = getattr(session, 'last_suggestions', None)
    edit_record_id = save_edit_record(summary_id, ai_original, user_modified, suggestions_raw)

    print(f"\n[OK] 草稿已同步到数据库")
    print(f"  记录 ID: {edit_record_id}")
    print(f"  编辑比例：{edit_ratio:.2%}")
    print(f"\n是否要将此版本作为新的 AI 建议并重写？(y/n)")

    choice = input("> ").strip().lower()
    if choice in ('y', 'yes', '是'):
        session.round_num += 1
        round_num = session.round_num

        # 生成修改后的版本
        revised_text, mod_type = generate_revision(user_modified, ai_original)
        revised_text = handle_assistant_mode(revised_text)

        # 记录修改轮次
        session_id = session.session_id
        record_revision(
            summary_id=summary_id,
            session_id=session_id,
            round_num=round_num,
            ai_suggestion=ai_original,
            user_modified=user_modified,
            modification_type=mod_type
        )

        session.ai_original = revised_text
        print(f"\n[OK] 已重写完成（第{round_num}轮）")
        print("\n" + "=" * 60)
        print(revised_text)
        print("=" * 60)

def do_distill_now(total_edits=0):
    """全量萃取偏好（支持场景化）"""
    from core.edit_records import get_all_edits_for_distill
    from core.distiller import distill_scenario_preferences
    import uuid

    global session
    scenario_type = session.scenario_type

    # 优先使用场景化萃取
    if scenario_type:
        print(f"\n🔍 正在全量萃取 {scenario_type} 场景的写作偏好...")
        records = get_all_edits_for_distill(limit=50)
        if records:
            pref = distill_scenario_preferences(scenario_type)
            if pref:
                update_system_prompt(pref, prompt_type='writing', scenario_type=scenario_type)
                print(f"[OK] 场景偏好萃取完成：{pref[:100]}...")
                return

    # 回退到通用萃取（全量模式）
    print(f"\n🔍 正在全量萃取写作偏好...")
    records = get_all_edits_for_distill(limit=50)

    if not records:
        print("没有需要萃取的记录")
        return

    pref = distill_preferences(records)
    if pref:
        # 保存偏好并记录当前萃取的记录数
        conn = get_conn()
        pref_id = f"pref-{uuid.uuid4().hex[:8]}"
        conn.execute('''
            INSERT INTO writing_preferences (id, version, preference_summary, system_prompt, distilled_count, is_active, prompt_type)
            VALUES (?, 1, ?, ?, ?, 1, 'writing')
        ''', (pref_id, pref[:500], pref, total_edits))
        # 将旧偏好设为非激活
        conn.execute('UPDATE writing_preferences SET is_active = 0 WHERE id != ? AND prompt_type = "writing"', (pref_id,))
        conn.commit()
        conn.close()
        print(f"[OK] 全量萃取完成（共 {total_edits} 条记录）：{pref[:100]}...")

def do_distill_feedback():
    """立即萃取用户反馈偏好"""
    from core.feedback_distiller import should_trigger_feedback_distill, distill_user_feedback
    from core.distiller import get_feedback_patterns

    should_trigger, count = should_trigger_feedback_distill()
    if not should_trigger:
        print(f"\n[提示] 当前只有 {count} 条用户反馈，至少需要 5 条才能萃取")
        return

    print(f"\n🔍 正在萃取 {count} 条用户反馈...")
    feedback_pref = distill_user_feedback()
    if feedback_pref:
        print(f"[OK] 用户反馈偏好萃取完成：\n{feedback_pref}")

        # 显示学习的规则
        feedback_data = get_feedback_patterns(limit_sessions=10)
        if feedback_data.get('rules'):
            print("\n【学习到的规则】")
            for rule in feedback_data['rules']:
                print(f"  - {rule}")

def do_distill_finals():
    """全量萃取定稿特征"""
    from core.edit_records import get_final_versions_for_distill
    from core.distiller import distill_from_final_versions

    finals = get_final_versions_for_distill(limit=30)
    if not finals:
        return

    pref = distill_from_final_versions(finals)
    if pref:
        update_system_prompt(pref, prompt_type='final')
        print(f"[OK] 定稿特征萃取完成：{pref[:100]}...")

def show_history():
    """显示修改历史"""
    history = get_session_history(session.summary_id)
    if not history:
        print("暂无修改历史")
        return

    print("\n【修改历史】")
    for h in history:
        print(f"\n第{h['round_num']}轮：{h['modification_type']} (编辑比例：{h['edit_ratio']:.2f})")

def show_status():
    """显示当前状态"""
    if not session.summary_id:
        print("当前没有进行中的写作会话")
        return

    print(f"\n【当前会话】")
    print(f"  摘要 ID: {session.summary_id}")
    print(f"  会话 ID: {session.session_id}")
    print(f"  修改轮数：{session.round_num}")
    print(f"  首轮编辑：{'已完成' if session.first_edit_done else '未完成'}")

def sync_article(article_id):
    """同步草稿文件的修改到数据库"""
    from core.logger import log_info, log_debug
    from core.temp_manager import read_draft, parse_user_feedback, clean_suggestions
    from core.edit_records import save_edit_record
    from core.revision_manager import mark_last_edit_as_final, finalize_session
    from difflib import SequenceMatcher
    from datetime import datetime
    import json
    global session

    log_info(f"开始同步文章: {article_id}")

    # 加载文章和会话
    conn = get_conn()
    article = conn.execute("SELECT * FROM summaries WHERE id=?", (article_id,)).fetchone()
    if not article:
        print(f"错误: 找不到文章 {article_id}")
        sys.exit(1)

    session_data = conn.execute("""
        SELECT id FROM modification_sessions
        WHERE summary_id=? ORDER BY session_start DESC LIMIT 1
    """, (article_id,)).fetchone()

    if not session_data:
        session_id = start_modification_session(article_id)
    else:
        session_id = session_data[0]

    # 获取上一次的草稿内容（从最近的 revision_round 或原始 ai_text）
    last_round = conn.execute("""
        SELECT user_modified FROM revision_rounds
        WHERE session_id=? ORDER BY created_at DESC LIMIT 1
    """, (session_id,)).fetchone()

    if last_round:
        from core.temp_manager import clean_suggestions
        prev_text = clean_suggestions(last_round[0])
    else:
        prev_text = article[3]  # ai_text 字段

    conn.close()

    # 读取当前草稿文件
    draft_content = read_draft(article_id)
    if not draft_content:
        print("错误: 草稿文件不存在")
        sys.exit(1)

    # 解析用户反馈
    feedbacks = parse_user_feedback(draft_content)
    log_info(f"解析到 {len(feedbacks)} 条用户反馈")

    # 读取临时保存的 AI 建议
    import os
    draft_dir = os.path.expanduser('~/.claude/skills/ai-writer-lite/drafts')
    temp_sugg_file = os.path.join(draft_dir, f'suggestions_{article_id}.json')
    suggestions_raw = None
    if os.path.exists(temp_sugg_file):
        with open(temp_sugg_file, 'r', encoding='utf-8') as f:
            suggestions_raw = json.load(f)
        log_info(f"读取到 {len(suggestions_raw)} 条 AI 建议")

    # 清洗建议标记，获取主文本
    clean_text = clean_suggestions(draft_content)

    # 计算编辑比例
    edit_ratio = 1 - SequenceMatcher(None, prev_text, clean_text).ratio()

    print(f"\n{'='*60}")
    print("【同步结果】")
    print(f"{'='*60}")
    print(f"本次打磨建议数: {len(feedbacks)}")
    print(f"编辑比例: {edit_ratio:.1%}")

    # 显示反馈摘要
    if feedbacks:
        responded = sum(1 for f in feedbacks if f['responded'])
        print(f"有效反馈: {responded}/{len(feedbacks)}")
        print(f"\n【反馈详情】")
        for i, fb in enumerate(feedbacks, 1):
            if fb['responded']:
                print(f"第 {i} 条建议: {fb['problem'][:30]}...")
                print(f"   反馈: {fb['user_feedback'][:50]}...")

    # 记录到 revision_rounds（打磨轮次）
    conn = get_conn()
    polish_round = conn.execute("""
        SELECT COUNT(*) FROM revision_rounds WHERE session_id=?
    """, (session_id,)).fetchone()[0] + 1

    # 从建议中提取类型（多个类型用逗号分隔）
    suggestion_types = set()
    if suggestions_raw:
        for sugg in suggestions_raw:
            stype = sugg.get('type', '').strip()
            if stype:
                suggestion_types.add(stype)

    suggestion_type = ','.join(sorted(suggestion_types)) if suggestion_types else "未分类"

    revision_id, user_responded, _ = record_revision_round(
        session_id=session_id,
        round_num=polish_round,
        ai_opinion="",
        suggestion_type=suggestion_type,
        user_modified=clean_text,
        prev_text=prev_text,
        suggestions_raw=suggestions_raw,
        user_feedback=feedbacks
    )

    # 删除临时建议文件
    if os.path.exists(temp_sugg_file):
        os.remove(temp_sugg_file)
        log_info(f"已删除临时建议文件: {temp_sugg_file}")

    # 更新 modification_sessions
    conn.execute("""
        UPDATE modification_sessions
        SET total_rounds=?, session_end=?
        WHERE id=?
    """, (polish_round, datetime.now().isoformat(), session_id))
    conn.commit()
    conn.close()

    log_info(f"已记录 revision_round: {revision_id}")

    # 保存到 edit_records（如果有实际文本修改）
    if edit_ratio > 0.05:
        edit_record_id = save_edit_record(article_id, prev_text, clean_text, None, session_id)
        log_info(f"已保存 edit_record: {edit_record_id}")

    print(f"\n[OK] 已同步到数据库")
    print(f"记录 ID: {revision_id}")
    print(f"第 {polish_round} 次打磨")

    # 询问是否定稿（仅在交互模式下）
    try:
        print(f"\n是否定稿？(y/n): ", end='', flush=True)
        choice = input().strip().lower()
    except EOFError:
        return  # 非交互模式下跳过定稿询问

    if choice == 'y':
        # 定稿处理
        final_text = clean_text

        # 保存最终版本到 edit_records（如果还没保存）
        if edit_ratio <= 0.05:
            edit_record_id = save_edit_record(article_id, prev_text, clean_text, None, session_id)
            log_info(f"定稿时保存 edit_record: {edit_record_id}")

        final_id = finalize_session(session_id, final_text)

        print(f"\n[OK] 已定稿！ID: {final_id}")
        print(f"共打磨 {polish_round} 次")

        # 检查是否触发反馈萃取
        from core.feedback_distiller import should_trigger_feedback_distill, distill_user_feedback
        should_trigger, count = should_trigger_feedback_distill()
        if should_trigger:
            print(f"\n🔍 检测到 {count} 条用户反馈，正在萃取学习...")
            feedback_pref = distill_user_feedback()
            if feedback_pref:
                print(f"[OK] 用户反馈偏好萃取完成")

        # 检查是否触发定稿萃取
        from core.distiller import should_trigger_final_distill, count_final_versions
        final_count = count_final_versions()
        if should_trigger_final_distill(final_count):
            print("\n🔍 检测到足够的定稿，正在萃取定稿特征...")
            from core.distiller import do_distill_finals
            do_distill_finals()
    else:
        print("\n[提示] 可以继续修改或输入 'polish 文章ID' 进行下一轮打磨")

def polish_inject(article_id, json_file):
    """注入 AI 生成的打磨建议到草稿文件"""
    from core.logger import log_info, log_debug, log_error
    import json
    import os

    log_info(f"开始注入打磨建议: article_id={article_id}, json_file={json_file}")

    # 读取 JSON 文件
    if not os.path.exists(json_file):
        print(f"错误: JSON 文件不存在: {json_file}")
        sys.exit(1)

    with open(json_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            suggestions = data.get('suggestions', [])
            log_info(f"成功读取 JSON，建议数量: {len(suggestions)}")
        except json.JSONDecodeError as e:
            log_error(f"JSON 解析失败: {e}")
            print(f"错误: JSON 格式不正确: {e}")
            sys.exit(1)

    # 查找草稿文件
    draft_dir = os.path.expanduser('~/.claude/skills/ai-writer-lite/drafts')
    parts = article_id.split('_', 1)
    possible_names = [
        f"draft_{article_id}.md",
        f"draft_{parts[1]}_{parts[0]}.md" if len(parts) == 2 else None
    ]

    draft_file = None
    for name in possible_names:
        if name:
            path = os.path.normpath(os.path.join(draft_dir, name))
            if os.path.exists(path):
                draft_file = path
                break

    if not draft_file:
        print(f"错误: 找不到草稿文件")
        sys.exit(1)

    # 读取草稿内容
    with open(draft_file, 'r', encoding='utf-8') as f:
        current_draft = f.read()

    # 清理旧建议并注入新建议
    from core.temp_manager import clean_suggestions, inject_suggestions
    clean_draft = clean_suggestions(current_draft)
    updated_draft = inject_suggestions(clean_draft, suggestions)

    # 保存回文件
    with open(draft_file, 'w', encoding='utf-8') as f:
        f.write(updated_draft)

    log_info(f"建议已注入到草稿文件: {draft_file}")

    # 保存建议到临时文件供 sync 使用
    temp_sugg_file = os.path.join(draft_dir, f'suggestions_{article_id}.json')
    with open(temp_sugg_file, 'w', encoding='utf-8') as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)
    log_info(f"建议已保存到临时文件: {temp_sugg_file}")

    # 打开文件
    from core.temp_manager import open_draft
    open_draft(article_id)

    print("\n" + "=" * 60)
    print("【打磨建议注入完成】")
    print("=" * 60)
    print(f"建议数量: {len(suggestions)}")
    print(f"草稿文件: {draft_file}")
    print("\n[OK] 草稿文件已打开，请在编辑器中修改")
    print("\n【使用说明】")
    print("1. 在文中找到 %%...%% 标记的建议（紧跟在对应段落后）")
    print("2. 直接在文中修改，或在 '用户反馈：' 后填写想法")
    print("3. 修改完成后保存文件")
    print("4. [注意] 定稿时 %%...%% 内容会自动移除，无需手动删除！")

def polish_article(article_id):
    """非交互式打磨文章 - 输出 prompt 后退出"""
    from core.logger import log_info, log_debug, log_error
    global session

    log_info(f"开始打磨文章: {article_id}")

    # 加载文章
    conn = get_conn()
    article = conn.execute("SELECT * FROM summaries WHERE id=?", (article_id,)).fetchone()

    if not article:
        conn.close()
        log_error(f"找不到文章: {article_id}")
        print(f"找不到文章: {article_id}")
        sys.exit(1)

    log_debug(f"文章加载成功，场景类型: {article[7] if len(article) > 7 else None}")

    scenario_type = article[7] if len(article) > 7 else None
    writing_purpose = article[8] if len(article) > 8 else None

    # 加载会话状态
    session_data = conn.execute("""
        SELECT total_rounds, is_finalized, id
        FROM modification_sessions
        WHERE summary_id=?
        ORDER BY session_start DESC
        LIMIT 1
    """, (article_id,)).fetchone()

    if session_data:
        session_id = session_data[2]
    else:
        session_id = start_modification_session(article_id)

    conn.close()

    # 读取草稿文件
    import os
    draft_dir = os.path.expanduser('~/.claude/skills/ai-writer-lite/drafts')
    parts = article_id.split('_', 1)
    possible_names = [
        f"draft_{article_id}.md",
        f"draft_{parts[1]}_{parts[0]}.md" if len(parts) == 2 else None
    ]

    log_debug(f"查找草稿文件，可能的文件名: {[n for n in possible_names if n]}")

    draft_file = None
    for name in possible_names:
        if name:
            path = os.path.normpath(os.path.join(draft_dir, name))
            if os.path.exists(path):
                draft_file = path
                log_info(f"找到草稿文件: {draft_file}")
                break

    if not draft_file:
        log_error(f"找不到草稿文件，article_id={article_id}")
        print(f"找不到草稿文件")
        sys.exit(1)

    with open(draft_file, 'r', encoding='utf-8') as f:
        ai_original = f.read()

    log_debug(f"草稿文件读取成功，长度: {len(ai_original)} 字符")

    # 清理旧的打磨建议
    from core.temp_manager import clean_suggestions
    cleaned_original = clean_suggestions(ai_original)
    log_debug(f"清理前长度: {len(ai_original)}, 清理后长度: {len(cleaned_original)}")

    # 获取场景的自定义 prompt
    custom_prompt = get_custom_prompt(scenario_type)

    # 生成 prompt
    from core.generator import generate_revision_opinion
    prompt_text, _, _ = generate_revision_opinion(cleaned_original, scenario_type, writing_purpose, custom_prompt=custom_prompt)

    # 解析并输出 prompt
    lines = prompt_text.split('\n', 2)
    system_prompt = lines[1].replace("SYSTEM: ", "")
    user_prompt = lines[2].replace("USER: ", "")

    print("\n" + "="*60)
    print("[AI 请求] 请根据以下 prompt 生成 JSON 格式的打磨建议")
    print("="*60)
    print(f"\n【System】\n{system_prompt}")
    print(f"\n【User】\n{user_prompt}")
    print("\n" + "="*60)
    print(f"\n[提示] 请将生成的 JSON 保存到文件，然后运行：")
    print(f"  python main.py \"polish-inject {article_id} <json_file_path>\"")
    print("="*60)

    log_info("polish_article 输出 prompt 完成，退出")
    sys.exit(99)

def list_all_articles():
    """列出所有文章"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, user_prompt, created_at
        FROM summaries
        ORDER BY created_at DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    if not rows:
        print("暂无文章")
        return

    print("\n【所有文章】")
    for row in rows:
        print(f"  {row[0]} - {row[1][:50]} ({row[2]})")

def resume_article(article_id):
    """恢复文章继续打磨"""
    global session

    conn = get_conn()
    article = conn.execute("SELECT * FROM summaries WHERE id=?", (article_id,)).fetchone()

    if not article:
        conn.close()
        print(f"找不到文章: {article_id}")
        return

    # 加载会话
    session.summary_id = article_id
    session.scenario_type = article[7] if len(article) > 7 else None
    session.writing_purpose = article[8] if len(article) > 8 else None

    # 加载会话状态
    session_data = conn.execute("""
        SELECT total_rounds, is_finalized, id
        FROM modification_sessions
        WHERE summary_id=?
        ORDER BY session_start DESC
        LIMIT 1
    """, (article_id,)).fetchone()

    if session_data:
        session.session_id = session_data[2]
        session.is_finalized = bool(session_data[1])

        # 统计实际打磨次数（按时间分组，同一分钟内算一次）
        actual_rounds = conn.execute("""
            SELECT COUNT(DISTINCT strftime('%Y-%m-%d %H:%M', created_at))
            FROM revision_rounds WHERE session_id=?
        """, (session.session_id,)).fetchone()[0]
        session.polish_round = actual_rounds
    else:
        session.polish_round = 0
        session.is_finalized = False

    conn.close()

    # 读取草稿文件
    import os
    import glob
    draft_dir = os.path.expanduser('~/.claude/skills/ai-writer-lite/drafts')

    # 尝试多种文件名格式
    possible_names = [
        f"draft_{article_id}.md",
        f"draft_{article_id.replace('_', '_')}.md",
    ]

    # 如果 ID 格式是 YYYYMMDD_name，也尝试 name_YYYYMMDD
    parts = article_id.split('_', 1)
    if len(parts) == 2:
        possible_names.append(f"draft_{parts[1]}_{parts[0]}.md")

    draft_file = None
    for name in possible_names:
        path = os.path.normpath(os.path.join(draft_dir, name))
        if os.path.exists(path):
            draft_file = path
            break

    if draft_file:
        with open(draft_file, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"\n【文章内容】\n{content}\n")
    else:
        print(f"找不到草稿文件，尝试过: {possible_names}")

    print(f"  打磨轮次：{session.polish_round}")
    print(f"  场景类型：{session.scenario_type or '未指定'}")
    print(f"  写作目的：{session.writing_purpose or '未指定'}")
    print(f"  是否定稿：{'是' if session.is_finalized else '否'}")
    print(f"\n[提示] 文章已加载，草稿文件路径：{draft_file if draft_file else '未找到'}")
    print("[提示] 使用 'polish <article_id>' 命令生成打磨建议（非交互式）")

def show_help():
    """显示帮助"""
    print("""
【可用命令】
  quit / exit / q  - 退出
  help             - 显示帮助
  status           - 显示当前会话状态
  history          - 查看修改历史
  sync / 同步      - 将草稿文件的修改同步到数据库
  打磨 / polish    - AI 提出修改建议（不直接改文本）
  定稿 / 完成      - 结束当前写作会话
  萃取反馈         - 手动触发用户反馈偏好萃取

【写作流程】
1. 首次输入：AI 根据你的需求生成初稿
2. 第一轮修改（编辑记录）：
   - 直接粘贴修改后的文本
   - 编辑比例≥30% → 自动保存到 edit_records
   - 编辑比例<30% → 提示确认是否继续
3. 打磨轮次（第二轮及以后）：
   - 输入"打磨"→ AI 提出修改建议
   - 根据建议修改文本并粘贴
   - AI 记录修改意见采纳情况到 revision_rounds
   - 可在 %%...%% 后填写用户反馈，AI 会学习
4. 定稿：保存到 final_versions，可重新开始修改轮

【用户反馈学习】
- 在打磨建议的 %%...%% 标记后填写你的反馈
- 例如：%%（问题：XX，建议：XX，用户反馈：这是时事新闻，读者都知道，不用冗余）%%
- AI 会学习你对建议的接受/拒绝模式
- 积累 5 条反馈后可手动输入"萃取反馈"来学习

【提示】
- 草稿文件保存在 ~/.claude/skills/ai-writer-lite/drafts/
- 第一轮修改只有达到 30% 编辑比例才会记录到写作偏好
- 打磨轮次 AI 只提建议，不直接修改文本
- 不同写作场景的偏好独立学习
- 定稿时 %%...%% 内容会自动移除，无需手动删除
""")

def cmd_save_materials(materials_text):
    """命令：保存素材"""
    from core.db import get_conn

    # 检测重复
    conn = get_conn()
    note_ids = re.findall(r'笔记_(\w+)', materials_text)
    duplicates = []
    for nid in note_ids:
        cursor = conn.execute('SELECT id FROM materials WHERE note_id = ?', (nid,))
        if cursor.fetchone():
            duplicates.append(nid)
    conn.close()

    material_ids = detect_and_import(materials_text)
    if material_ids:
        print(f"[OK] 已保存 {len(material_ids)} 条素材")
        print(f"[MATERIAL_IDS] {','.join(material_ids)}")
        if duplicates:
            print(f"[WARNING] 检测到 {len(duplicates)} 条重复素材已跳过: {', '.join(duplicates)}")
    else:
        print("[错误] 未识别到有效素材")

def cmd_generate(user_input):
    """命令：生成文章"""
    import json
    parts = user_input.split(' ', 1)[1]
    try:
        params = json.loads(parts)
        material_ids = params.get('material_ids', [])
        scenario = params.get('scenario', 'daily_note')
        purpose = params.get('purpose', '')
        intent = params.get('intent', '')

        # 获取场景的自定义 prompt
        custom_prompt = get_custom_prompt(scenario)

        prompt = generate_with_materials(material_ids, intent, scenario, purpose, custom_prompt=custom_prompt)
        result = handle_assistant_mode(prompt, interactive=False)
        print(result)
    except json.JSONDecodeError:
        print("[错误] 参数格式错误，需要 JSON 格式")
        print('用法: generate \'{"material_ids":["mat-xxx"],"scenario":"social_media","purpose":"阐述观点","intent":"写文章"}\'')

def cmd_save_article(user_input):
    """命令：保存文章"""
    import json
    parts = user_input.split(' ', 1)[1]
    try:
        params = json.loads(parts)
        material_ids = params.get('material_ids', [])
        scenario = params.get('scenario', 'daily_note')
        purpose = params.get('purpose', '')
        content = params.get('content', '')
        ai_model = params.get('ai_model')  # 可选，如果不提供则自动提取

        # 如果没有传入 ai_model，尝试从内容中提取
        if not ai_model:
            ai_model = extract_ai_model(content)

        summary_id = save_summary(material_ids, purpose, content, scenario, purpose, ai_model)
        draft_path = create_draft(summary_id, content)
        open_draft(summary_id)

        print(f"[OK] 文章已保存")
        if ai_model:
            print(f"[AI_MODEL] {ai_model}")
        print(f"[SUMMARY_ID] {summary_id}")
        print(f"[DRAFT_PATH] {draft_path}")
    except json.JSONDecodeError:
        print("[错误] 参数格式错误，需要 JSON 格式")

def cmd_finalize(summary_id):
    """命令：定稿文章"""
    mark_last_edit_as_final(summary_id)

    # 获取场景信息
    conn = get_conn()
    cursor = conn.execute('SELECT scenario_type FROM summaries WHERE id = ?', (summary_id,))
    row = cursor.fetchone()
    scenario_type = row[0] if row else None

    # 获取该场景上次萃取后的新增记录数
    cursor = conn.execute('''
        SELECT COUNT(*) FROM edit_records e
        JOIN summaries s ON e.summary_id = s.id
        WHERE s.scenario_type = ?
    ''', (scenario_type,))
    scenario_total = cursor.fetchone()[0]

    cursor = conn.execute(
        'SELECT COUNT(*) FROM system_prompts WHERE prompt_type = ?',
        (f'scenario_{scenario_type}',)
    )
    scenario_distilled = cursor.fetchone()[0]
    conn.close()

    print(f"[OK] 文章已定稿：{summary_id}")

    if should_trigger_distill(scenario_total, scenario_distilled):
        cmd_distill_preference(scenario_type)

def cmd_distill_preference(scenario_type):
    """命令：萃取偏好（全量模式）"""
    from core.distiller import distill_scenario_preferences

    pref = distill_scenario_preferences(scenario_type)
    if not pref:
        print("[错误] 无法生成偏好 prompt")
        return

    print(pref)

def cmd_save_preference(user_input):
    """命令：保存偏好"""
    import json
    parts = user_input.split(' ', 1)[1]
    params = json.loads(parts)
    preference_text = params.get('preference', '')
    scenario_type = params.get('scenario', None)

    update_system_prompt(preference_text, prompt_type='writing', scenario_type=scenario_type)
    print(f"[OK] 偏好已保存")

if __name__ == '__main__':
    main()
