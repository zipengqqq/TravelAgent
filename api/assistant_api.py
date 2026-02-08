from fastapi import APIRouter

from pojo.request.chat_request import ChatRequest
from service.assistant_service.assistant_service import AssistantService

router = APIRouter()
assistant_service = AssistantService()

@router.post("/chat", summary='聊天助手')
async def chat(request: ChatRequest):
    """SSE实现流式输出"""
    if assistant_service is None:
        raise RuntimeError("AssistantService 未初始化")
    return await assistant_service.chat(request)


