from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="用户问题")
    thread_id: str = Field(..., description="会话id")
    user_id: int = Field(..., description="用户id")