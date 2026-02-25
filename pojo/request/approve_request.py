from typing import Optional, List
from pydantic import BaseModel, Field


class ApproveRequest(BaseModel):
    """用户确认规划请求"""
    thread_id: str = Field(..., description="会话id")
    approved: bool = Field(..., description="是否确认")
    plan: List[str] = Field(..., description="用户修改后的规划")
    cancelled: bool = Field(..., description="是否取消")
