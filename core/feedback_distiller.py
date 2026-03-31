# 职责：用户反馈萃取 - 分析用户对 AI 建议的反馈模式
# 依赖内部：db.py
# 依赖外部：json, os
# 暴露：distill_user_feedback(), get_feedback_patterns(), should_trigger_feedback_distill()

import json
import os
from .db import get_conn


def get_feedback_records(limit=20):
    """获取带有用户反馈的记录"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT suggestion_type, user_feedback, user_responded, edit_ratio
        FROM revision_rounds
        WHERE user_feedback IS NOT NULL AND user_feedback != ''
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [{
        'suggestion_type': row[0],
        'user_feedback': json.loads(row[1]) if row[1] else [],
        'user_responded': row[2],
        'edit_ratio': row[3]
    } for row in rows]


def analyze_feedback_pattern(feedbacks):
    """
    分析用户反馈模式
    返回：{pattern_type: [examples]}
    """
    patterns = {
        'accepted': [],      # 用户接受的建议
        'rejected': [],      # 用户拒绝/提出异议的建议
        'modified': [],      # 用户部分采纳的建议
        'no_response': []    # 用户未回应的建议
    }

    for feedback in feedbacks:
        for fb in feedback.get('user_feedback', []):
            user_text = fb.get('user_feedback', '')
            problem = fb.get('problem', '')
            advice = fb.get('advice', '')

            if not user_text:
                patterns['no_response'].append({
                    'problem': problem,
                    'advice': advice,
                    'feedback': user_text
                })
                continue

            # 简单的情感分析
            # 拒绝/异议关键词
            reject_keywords = ['不用', '不需要', '冗余', '多余', '已知', '大家都知道', '不必', '不要', '没必要', '重复']
            # 接受关键词
            accept_keywords = ['好的', '可以', '行', '采纳', '对', '是', '同意', '确实']

            is_reject = any(kw in user_text for kw in reject_keywords)
            is_accept = any(kw in user_text for kw in accept_keywords)

            entry = {
                'problem': problem,
                'advice': advice,
                'feedback': user_text,
                'reason': extract_reason(user_text)
            }

            if is_reject:
                patterns['rejected'].append(entry)
            elif is_accept:
                patterns['accepted'].append(entry)
            else:
                # 有反馈内容但不是明确接受/拒绝，算部分采纳
                patterns['modified'].append(entry)

    return patterns


def extract_reason(feedback_text):
    """从用户反馈中提取原因"""
    # 尝试提取"因为"、"这是"等后面的内容
    reason_markers = ['因为', '这是', '凡是', '都', '其实', '毕竟']

    for marker in reason_markers:
        if marker in feedback_text:
            idx = feedback_text.find(marker)
            return feedback_text[idx:]

    return feedback_text


def distill_user_feedback(records=None):
    """
    萃取用户反馈偏好
    返回：偏好摘要字符串
    """
    if records is None:
        records = get_feedback_records()

    if not records:
        return None

    patterns = analyze_feedback_pattern(records)

    # 生成偏好摘要
    summary_parts = []

    # 1. 用户拒绝的模式
    if patterns['rejected']:
        rejected_reasons = [p.get('reason', '') for p in patterns['rejected']]
        # 统计最常见的原因类型
        reason_types = {}
        for reason in rejected_reasons:
            # 提取原因类型
            if '冗余' in reason or '多余' in reason or '重复' in reason:
                reason_types['简洁优先'] = reason_types.get('简洁优先', 0) + 1
            elif '已知' in reason or '大家都知道' in reason:
                reason_types['信任读者'] = reason_types.get('信任读者', 0) + 1
            elif '新闻' in reason or '时事' in reason:
                reason_types['时事新闻'] = reason_types.get('时事新闻', 0) + 1
            else:
                reason_types['其他'] = reason_types.get('其他', 0) + 1

        if reason_types:
            top_reasons = sorted(reason_types.items(), key=lambda x: x[1], reverse=True)
            summary_parts.append(f"用户拒绝的建议主要因为：{', '.join([r[0] for r in top_reasons[:3]])}")

    # 2. 用户接受的.mode
    if patterns['accepted']:
        summary_parts.append(f"用户接受了 {len(patterns['accepted'])} 条建议")

    # 3. 具体偏好规则
    preference_rules = []

    # 分析拒绝反馈，生成具体规则
    for entry in patterns['rejected'][:5]:  # 最多取 5 条
        reason = entry.get('reason', '')
        advice = entry.get('advice', '')

        # 从原因中提取规则
        if '冗余' in reason or '多余' in reason:
            preference_rules.append(f"避免添加{advice}类的过渡，保持简洁")
        elif '已知' in reason or '大家都知道' in reason:
            preference_rules.append("读者已知的背景信息不需要额外解释")
        elif '新闻' in reason or '时事' in reason:
            preference_rules.append("时事新闻内容，假设读者有一定了解，不添加冗余过渡")

    if preference_rules:
        summary_parts.append("偏好规则：\n- " + "\n- ".join(preference_rules))

    # 4. 典型反馈示例
    if patterns['rejected']:
        example = patterns['rejected'][0]
        summary_parts.append(f"示例：'{example['feedback']}'")

    return '\n'.join(summary_parts)


def get_feedback_patterns(limit_sessions=10):
    """
    获取用户反馈模式数据，用于 Prompt 注入
    返回：{context: str, rules: list}
    """
    records = get_feedback_records(limit=limit_sessions * 5)  # 每条 session 平均 5 条反馈

    if not records:
        return {'context': '', 'rules': []}

    patterns = analyze_feedback_pattern(records)

    # 生成上下文
    context_parts = []

    if patterns['rejected']:
        context_parts.append("【用户拒绝的建议类型】")
        for entry in patterns['rejected'][:3]:
            context_parts.append(f"- 问题：{entry['problem']}")
            context_parts.append(f"  AI 建议：{entry['advice']}")
            context_parts.append(f"  用户反馈：{entry['feedback']}")

    if patterns['accepted']:
        context_parts.append("\n【用户接受的建议类型】")
        for entry in patterns['accepted'][:3]:
            context_parts.append(f"- 问题：{entry['problem']}")
            context_parts.append(f"  AI 建议：{entry['advice']}")
            context_parts.append(f"  用户反馈：{entry['feedback']}")

    # 生成规则
    rules = []

    # 从拒绝反馈中提取规则
    for entry in patterns['rejected']:
        reason = entry.get('reason', '')
        if '冗余' in reason or '多余' in reason or '重复' in reason:
            rules.append("避免添加冗余的过渡句")
        if '已知' in reason or '大家都知道' in reason:
            rules.append("读者已知的信息不要重复解释")
        if '新闻' in reason or '时事' in reason:
            rules.append("时事新闻内容不要添加已知背景的过渡")

    # 去重
    rules = list(dict.fromkeys(rules))

    return {
        'context': '\n'.join(context_parts),
        'rules': rules
    }


def should_trigger_feedback_distill():
    """检查是否应该触发反馈萃取（至少 5 条反馈记录）"""
    conn = get_conn()
    cursor = conn.execute('''
        SELECT COUNT(*) FROM revision_rounds
        WHERE user_feedback IS NOT NULL AND user_feedback != ''
    ''')
    count = cursor.fetchone()[0]
    conn.close()
    return count >= 5, count
