import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from pojo.request.chat_request import ChatRequest
from pojo.request.conversation_add_request import ConversationAddRequest
from pojo.request.conversation_list_request import ConversationListRequest
from pojo.request.conversation_select_request import ConversationSelectRequest

from service.assistant_service import AssistantService
from utils.api_response_uti import build_response

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


@router.post("/conversation/add", summary="新增对话")
async def add_conversation(request: ConversationAddRequest):
    """新增对话，返回创建的记录"""
    conversation = await assistant_service.add_conversation(request)
    return build_response(conversation)


@router.post("/conversation/list", summary="查询对话列表")
async def list_conversations(request: ConversationListRequest):
    """查询用户的所有对话"""
    return build_response(assistant_service.list_conversations(request.user_id))

@router.post("/conversation/select", summary="查看对话")
async def select_conversation(request: ConversationSelectRequest):
    """查看对话内容，即AI与用户的所有交互记录"""
    return build_response(await assistant_service.select_conversation(request.thread_id))



