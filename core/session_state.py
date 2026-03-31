# 职责：会话状态管理类
# 依赖内部：无
# 暴露：WritingSession

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class WritingSession:
    """写作会话状态管理"""
    summary_id: Optional[str] = None
    session_id: Optional[str] = None
    round_num: int = 0
    ai_original: Optional[str] = None
    is_finalized: bool = False
    scenario_type: Optional[str] = None
    writing_purpose: Optional[str] = None
    first_edit_done: bool = False
    polish_round: int = 0
    waiting_for_polish: bool = False
    last_ai_opinion: Optional[str] = None
    last_suggestion_type: Optional[str] = None

    def validate(self):
        """验证状态一致性"""
        if self.session_id and not self.summary_id:
            raise ValueError("session_id 存在但 summary_id 为空")
        if self.polish_round > 0 and not self.first_edit_done:
            raise ValueError("打磨轮次存在但第一轮修改未完成")
        if self.is_finalized and not self.session_id:
            raise ValueError("已定稿但 session_id 为空")

    def reset(self):
        """重置会话状态"""
        self.summary_id = None
        self.session_id = None
        self.round_num = 0
        self.ai_original = None
        self.is_finalized = False
        self.scenario_type = None
        self.writing_purpose = None
        self.first_edit_done = False
        self.polish_round = 0
        self.waiting_for_polish = False
        self.last_ai_opinion = None
        self.last_suggestion_type = None

    def is_active(self) -> bool:
        """检查会话是否活跃"""
        return self.summary_id is not None and not self.is_finalized

    def start_new(self, session_id: str, summary_id: str, ai_text: str,
                  scenario_type: Optional[str] = None, writing_purpose: Optional[str] = None):
        """开始新会话"""
        self.reset()
        self.summary_id = summary_id
        self.session_id = session_id
        self.ai_original = ai_text
        self.scenario_type = scenario_type
        self.writing_purpose = writing_purpose
        self.round_num = 0
        self.validate()

    def mark_first_edit_done(self):
        """标记第一轮修改完成"""
        self.first_edit_done = True
        self.round_num += 1

    def start_polish_round(self):
        """开始打磨轮次"""
        if not self.first_edit_done:
            raise ValueError("必须先完成第一轮修改")
        self.polish_round += 1
        self.waiting_for_polish = True

    def complete_polish_round(self):
        """完成打磨轮次"""
        self.waiting_for_polish = False
        self.round_num += 1

    def finalize(self):
        """标记为定稿"""
        self.is_finalized = True
        self.validate()
