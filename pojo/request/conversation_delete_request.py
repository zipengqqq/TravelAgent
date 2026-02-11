from pydantic import BaseModel, Field


class ConversationDeleteRequest(BaseModel):
    """删除对话请求"""
    thread_id: str = Field(..., description="会话id")
