# 职责: 测试配置模块
# 依赖内部: config.py
# 依赖外部: pytest
# 暴露: test_api_config, test_edit_config

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import API_CONFIG, EDIT_CONFIG

def test_api_config():
    """测试 API 配置完整性"""
    assert 'model' in API_CONFIG
    assert 'max_retries' in API_CONFIG
    assert 'retry_delay' in API_CONFIG
    assert 'max_tokens' in API_CONFIG

    assert isinstance(API_CONFIG['max_retries'], int)
    assert API_CONFIG['max_retries'] > 0
    assert isinstance(API_CONFIG['retry_delay'], (int, float))

    tokens = API_CONFIG['max_tokens']
    assert 'generate' in tokens
    assert 'opinion' in tokens
    assert 'distill_writing' in tokens

def test_edit_config():
    """测试编辑配置"""
    assert 'ratio_threshold' in EDIT_CONFIG
    assert 0 < EDIT_CONFIG['ratio_threshold'] < 1
