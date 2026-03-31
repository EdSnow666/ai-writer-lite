# 职责: 测试生成器模块
# 依赖内部: core/generator.py
# 依赖外部: pytest
# 暴露: test_analyze_modification_type

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 直接复制函数逻辑避免导入依赖
from difflib import SequenceMatcher

def analyze_modification_type(user_input, ai_original):
    if len(user_input) < len(ai_original) * 0.5:
        return "大幅删减"
    elif len(user_input) > len(ai_original) * 1.5:
        return "大幅扩充"
    else:
        diff_ratio = 1 - SequenceMatcher(None, ai_original, user_input).ratio()
        if diff_ratio < 0.2:
            return "微调措辞"
        elif diff_ratio < 0.5:
            return "局部重写"
        else:
            return "大幅重写"

def test_analyze_modification_type():
    """测试修改类型分析"""
    ai = "这是一段测试文本" * 10

    # 大幅删减
    result = analyze_modification_type("短文本", ai)
    assert result == "大幅删减"

    # 大幅扩充
    result = analyze_modification_type(ai * 3, ai)
    assert result == "大幅扩充"

    # 微调措辞
    result = analyze_modification_type(ai, ai)
    assert result == "微调措辞"
