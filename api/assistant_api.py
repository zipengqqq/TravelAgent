import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from pojo.request.chat_request import ChatRequest
from service.assistant_service import AssistantService

router = APIRouter()
assistant_service = AssistantService()


async def event_generator(request: ChatRequest):
    """生成 SSE 事件"""
    try:
        async for chunk in assistant_service.chat(request):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n"


@router.post("/chat", summary='聊天助手')
async def chat(request: ChatRequest):
    """SSE实现流式输出"""
    if assistant_service is None:
        raise RuntimeError("AssistantService 未初始化")
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


