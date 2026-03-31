# 职责：临时草稿文件管理
# 依赖外部：os, subprocess
# 暴露：create_draft(), read_draft(), delete_draft(), open_draft(), inject_suggestions()

import os
import subprocess

# 支持两个目录
TEMP_DIR = os.path.expanduser('~/.claude/skills/ai-writer-lite/temp')
DRAFTS_DIR = os.path.expanduser('~/.claude/skills/ai-writer-lite/drafts')

def get_draft_path(summary_id):
    """获取草稿文件路径（优先查找 drafts 目录）"""
    # 先检查 drafts 目录
    drafts_path = os.path.join(DRAFTS_DIR, f'draft_{summary_id}.md')
    if os.path.exists(drafts_path):
        return drafts_path, DRAFTS_DIR
    # 再检查 temp 目录
    temp_path = os.path.join(TEMP_DIR, f'draft_{summary_id}.md')
    if os.path.exists(temp_path):
        return temp_path, TEMP_DIR
    # 默认返回 drafts 目录
    return os.path.join(DRAFTS_DIR, f'draft_{summary_id}.md'), DRAFTS_DIR

def create_draft(summary_id, content):
    """创建临时草稿文件（保存到 drafts 目录）"""
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    path = os.path.join(DRAFTS_DIR, f'draft_{summary_id}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

def read_draft(summary_id):
    """读取修改后的草稿"""
    path, _ = get_draft_path(summary_id)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def delete_draft(summary_id):
    """删除草稿文件"""
    path, _ = get_draft_path(summary_id)
    if os.path.exists(path):
        os.remove(path)

def open_draft(summary_id):
    """
    打开草稿文件（使用系统默认编辑器）
    Windows: 使用 start 命令
    """
    from .logger import log_info, log_error
    import os

    path, _ = get_draft_path(summary_id)
    log_info(f"open_draft: 尝试打开文件 {path}")

    if not os.path.exists(path):
        log_error(f"文件不存在：{path}")
        print(f"文件不存在：{path}")
        return False

    try:
        # Windows 使用 start 命令
        os.system(f'start "" "{path}"')
        log_info(f"文件已打开：{path}")
        return True
    except Exception as e:
        log_error(f"打开文件失败：{e}")
        print(f"打开文件失败：{e}")
        return False

def inject_suggestions(content, suggestions):
    """
    将 AI 建议注入到内容中
    格式：%%（问题：XX，建议：XX，用户反馈：）%%

    支持段落定位：
    - 如果建议包含 anchor 字段（如"段落 1"、"段落 2-3"），注入到对应段落后（紧跟段落文字）
    - 如果建议是"全文"或未指定 anchor，添加到文末

    返回：注入建议后的内容
    """
    from .logger import log_debug, log_info

    log_info(f"inject_suggestions: 输入内容长度 {len(content)}, 建议数量 {len(suggestions) if suggestions else 0}")

    if not suggestions:
        log_debug("没有建议需要注入")
        return content

    # 将内容按段落分割
    paragraphs = content.split('\n\n')
    log_debug(f"内容分割为 {len(paragraphs)} 个段落")

    # 按段落分组建议
    paragraph_suggestions = {}  # {paragraph_index: [suggestions]}
    global_suggestions = []

    for sug in suggestions:
        anchor = sug.get('anchor', '')
        if not anchor:
            global_suggestions.append(sug)
            continue

        # 解析 anchor（如"段落 1"、"段落 2-3"）
        if anchor == '全文' or anchor == 'global':
            global_suggestions.append(sug)
        elif anchor.startswith('段落'):
            try:
                # 处理"段落 1"或"段落 1-2"格式
                range_part = anchor.replace('段落', '')
                if '-' in range_part:
                    start, end = range_part.split('-')
                    for i in range(int(start) - 1, min(int(end), len(paragraphs))):
                        if i not in paragraph_suggestions:
                            paragraph_suggestions[i] = []
                        paragraph_suggestions[i].append(sug)
                else:
                    idx = int(range_part) - 1
                    if 0 <= idx < len(paragraphs):
                        if idx not in paragraph_suggestions:
                            paragraph_suggestions[idx] = []
                        paragraph_suggestions[idx].append(sug)
            except (ValueError, IndexError):
                global_suggestions.append(sug)
        else:
            global_suggestions.append(sug)

    log_debug(f"段落建议分组: {len(paragraph_suggestions)} 个段落有建议, 全局建议: {len(global_suggestions)} 条")

    # 将建议注入到对应段落后（紧跟段落文字，不加额外空行）
    result_paragraphs = []
    for i, para in enumerate(paragraphs):
        # 如果该段落有建议，将建议紧跟在段落后
        if i in paragraph_suggestions:
            suggestion_lines = []
            for sug in paragraph_suggestions[i]:
                # 简洁格式：只有问题和建议，没有 type
                suggestion_lines.append(f"%%（问题：{sug.get('problem', '')}，建议：{sug.get('advice', '')}，用户反馈：）%%")
            suggestion_block = '\n'.join(suggestion_lines)
            # 建议紧跟段落，用单个换行分隔
            result_paragraphs.append(para + '\n' + suggestion_block)
            log_debug(f"段落 {i+1} 注入了 {len(paragraph_suggestions[i])} 条建议")
        else:
            result_paragraphs.append(para)

    # 将全局建议添加到文末
    if global_suggestions:
        suggestion_lines = []
        for sug in global_suggestions:
            suggestion_lines.append(f"%%（问题：{sug.get('problem', '')}，建议：{sug.get('advice', '')}，用户反馈：）%%")
        global_block = '\n\n--- AI 打磨建议（全文）---\n' + '\n'.join(suggestion_lines) + '\n--- 建议结束 ---'
        result_paragraphs.append(global_block)
        log_debug(f"文末添加了 {len(global_suggestions)} 条全局建议")

    result = '\n\n'.join(result_paragraphs)
    log_info(f"inject_suggestions: 输出长度 {len(result)}")
    return result

def clean_suggestions(content):
    """
    清理打磨建议（移除 %%...%% 格式的内容和表格格式的建议）
    用于生成最终稿
    """
    from .logger import log_debug
    import re

    log_debug(f"clean_suggestions: 输入长度 {len(content)}")

    # 移除所有 %%...%% 格式的内容
    cleaned = re.sub(r'%%.*?%%', '', content, flags=re.DOTALL)
    log_debug(f"移除 %%...%% 后长度: {len(cleaned)}")

    # 移除 AI 打磨建议标记（支持"全文"括号）
    cleaned = re.sub(r'\n?--- AI 打磨建议（全文）---.*?--- 建议结束 ---\n?', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\n?--- AI 打磨建议 ---.*?--- 建议结束 ---\n?', '', cleaned, flags=re.DOTALL)
    log_debug(f"移除 AI 打磨建议标记后长度: {len(cleaned)}")

    # 移除表格格式的打磨建议（## AI 打磨建议 开头的部分）
    cleaned = re.sub(r'\n---\n\n## AI 打磨建议.*', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\n## AI 打磨建议.*', '', cleaned, flags=re.DOTALL)
    log_debug(f"移除表格格式建议后长度: {len(cleaned)}")

    # 清理多余空行（3 个或以上连续空行缩减为 2 个）
    cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)

    log_debug(f"clean_suggestions: 输出长度 {len(cleaned.strip())}")
    return cleaned.strip()


def parse_user_feedback(content):
    """
    从内容中提取用户反馈
    格式：%%（问题：XX，建议：XX，用户反馈：实际反馈内容）%%
    返回：[{problem, advice, user_feedback, responded}]
    """
    import re
    feedbacks = []

    # 匹配 %%...%% 格式
    pattern = r'%%（问题：(.*?)，建议：(.*?)，用户反馈：(.*?)）%%'
    matches = re.findall(pattern, content, flags=re.DOTALL)

    for match in matches:
        problem, advice, feedback = match
        feedbacks.append({
            'problem': problem.strip(),
            'advice': advice.strip(),
            'user_feedback': feedback.strip(),
            'responded': len(feedback.strip()) > 0  # 有反馈内容算响应
        })

    return feedbacks
