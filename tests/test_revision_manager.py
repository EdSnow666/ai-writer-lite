# 职责: 测试修改会话管理
# 依赖内部: core/revision_manager.py, core/db.py
# 依赖外部: pytest
# 暴露: test_check_edit_ratio, test_session_lifecycle

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.revision_manager import check_edit_ratio
from config import EDIT_CONFIG

def test_check_edit_ratio():
    """测试编辑比例计算"""
    ai = "这是原文"
    user = "这是修改后的文本"

    ratio, should_proceed = check_edit_ratio(ai, user)
    assert 0 <= ratio <= 1
    assert isinstance(should_proceed, bool)

    # 测试相同文本
    ratio, should_proceed = check_edit_ratio(ai, ai)
    assert ratio == 0
    assert should_proceed == False

    # 测试大幅修改
    ratio, should_proceed = check_edit_ratio(ai, user * 10)
    assert ratio >= EDIT_CONFIG['ratio_threshold']
    assert should_proceed == True
