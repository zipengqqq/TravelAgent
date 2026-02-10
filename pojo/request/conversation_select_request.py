from pydantic import BaseModel, Field


class ConversationSelectRequest(BaseModel):
    """查看对话请求"""
    thread_id: str = Field(..., description="对话的thread_id")
