from pydantic import BaseModel, Field


class ConversationAddRequest(BaseModel):
    """新增对话请求"""
    user_id: int = Field(..., description="用户id")