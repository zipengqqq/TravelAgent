from typing import Optional, List
from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
    """用户确认规划请求"""
    user_id: int = Field(default=1, description="用户ID")
    thread_id: str = Field(..., description="会话id")
    approved: bool = Field(..., description="是否确认")
    plan: List[str] = Field(default=[], description="用户修改后的规划")
    cancelled: bool = Field(..., description="是否取消")
    question: Optional[str] = Field(default="", description="原始用户问题")
