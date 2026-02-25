"""
人机交互示例 - FastAPI 服务
提供 REST API 支持前端进行人机交互
"""

import asyncio
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.errors import GraphInterrupt

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from learn.human_in_loop.workflow import graph, AgentState, checkpointer


app = FastAPI(title="LangGraph 人机交互演示")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 内存存储 ============
# 存储会话状态
sessions = {}


# ============ 请求模型 ============
class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: Optional[str] = None


class ApproveRequest(BaseModel):
    """批准请求"""
    session_id: str
    approved: bool
    modified_plan: Optional[list] = None


class GetStateRequest(BaseModel):
    """获取状态请求"""
    session_id: str


# ============ API 路由 ============

@app.get("/")
async def root():
    """返回前端页面"""
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """开始新的对话

    使用 interrupt 后，工作流会在中断处抛出 GraphInterrupt 异常
    """
    session_id = request.session_id or str(uuid.uuid4())

    # 初始化状态
    initial_state: AgentState = {
        "messages": [HumanMessage(content=request.message)],
        "plan": None,
        "current_step": 0,
        "user_input": None,
        "approved": None
    }

    # 使用 config 设置 thread_id 用于状态恢复
    config = {"configurable": {"thread_id": session_id}}

    result = None
    try:
        # 执行工作流，interrupt 会抛出异常中断执行
        async for event in graph.astream(initial_state, config, stream_mode="values"):
            result = event
    except GraphInterrupt:
        # ⭐ 捕获 interrupt 中断，获取中断前的状态
        pass

    # 返回当前状态和 session_id
    return {
        "session_id": session_id,
        "state": format_state(result),
        "waiting_for_approval": True,  # interrupt 后一定需要用户审批
        "messages": format_messages(result.get("messages", []))
    }


@app.post("/api/approve")
async def approve(request: ApproveRequest):
    """用户审核/批准

    使用 interrupt 后，update_state 会将值传递给 interrupt 并继续执行
    """
    session_id = request.session_id
    config = {"configurable": {"thread_id": session_id}}

    # 获取当前状态
    current_state = await graph.aget_state(config)

    if current_state is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 转换为字典
    state_dict = dict(current_state.values) if hasattr(current_state, 'values') else current_state

    # 使用 update_state 更新状态并继续执行
    # interrupt 会接收这个返回值并继续执行
    update_values = {
        "approved": request.approved,
        "user_input": "approved" if request.approved else "needs_modification"
    }

    # 如果用户修改了计划，更新计划并重置步骤
    if request.modified_plan:
        update_values["plan"] = request.modified_plan
        update_values["current_step"] = 0

    await graph.aupdate_state(config, update_values)

    # 继续执行工作流
    result = None
    try:
        async for event in graph.astream(None, config, stream_mode="values"):
            result = event
    except GraphInterrupt:
        # 捕获下一个中断（可能是步骤审批）
        pass

    # 检查是否完成（所有步骤都已执行）
    is_complete = result.get("current_step", 0) >= len(result.get("plan", []))

    return {
        "session_id": session_id,
        "state": format_state(result),
        "waiting_for_approval": not is_complete,  # 如果还有步骤未完成，继续等待审批
        "messages": format_messages(result.get("messages", [])),
        "completed": is_complete
    }


@app.post("/api/state")
async def get_state(request: GetStateRequest):
    """获取当前状态"""
    session_id = request.session_id
    config = {"configurable": {"thread_id": session_id}}

    # 获取当前状态
    current_state = await graph.aget_state(config)

    if current_state is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 转换为字典
    state_dict = dict(current_state.values) if hasattr(current_state, 'values') else current_state
    is_complete = state_dict.get("current_step", 0) >= len(state_dict.get("plan", []))

    return {
        "session_id": request.session_id,
        "state": format_state(state_dict),
        "waiting_for_approval": not is_complete and state_dict.get("approved") is None and state_dict.get("plan") is not None,
        "messages": format_messages(state_dict.get("messages", [])),
        "completed": is_complete
    }


# ============ 辅助函数 ============
def format_state(state: AgentState) -> dict:
    """格式化状态用于前端展示"""
    return {
        "plan": state.get("plan", []),
        "current_step": state.get("current_step", 0),
        "approved": state.get("approved"),
        "user_input": state.get("user_input")
    }


def format_messages(messages: list) -> list:
    """格式化消息用于前端展示"""
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"type": "human", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"type": "ai", "content": msg.content})
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
