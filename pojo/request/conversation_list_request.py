from pydantic import BaseModel, Field


class ConversationListRequest(BaseModel):
    """查询对话列表请求"""
    user_id: int = Field(..., description="用户id")
