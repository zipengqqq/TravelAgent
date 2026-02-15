"""
LangGraph 节点级别流式输出示例 - 工作流模块

使用回调 + 独立任务实现真正的流式输出
"""

import asyncio
from typing import TypedDict, List, Annotated, Any
import operator

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage


# ==================== 1. 定义状态类型 ====================
class GraphState(TypedDict):
    """图状态定义"""
    messages: Annotated[List, operator.add]
    node_outputs: dict


# ==================== 2. Token 流式回调 ====================
class StreamCallback(BaseCallbackHandler):
    """自定义回调，用于捕获每个 token 并推送到队列"""

    def __init__(self, queue: asyncio.Queue, node_name: str):
        self.queue = queue
        self.node_name = node_name

    async def on_llm_new_token(self, token: str, **kwargs):
        """LLM 生成新 token 时调用"""
        if token:
            self.queue.put_nowait({
                "type": "token",
                "node": self.node_name,
                "data": {"content": token}
            })

    async def on_llm_end(self, response: Any, **kwargs):
        """LLM 完成时调用"""
        self.queue.put_nowait({
            "type": "node_end",
            "node": self.node_name
        })

    async def on_llm_error(self, error: Exception, **kwargs):
        """LLM 错误时调用"""
        self.queue.put_nowait({
            "type": "error",
            "node": self.node_name,
            "data": {"message": str(error)}
        })


# 全局变量
_workflow_queue: asyncio.Queue = None


def set_queue(queue: asyncio.Queue):
    global _workflow_queue
    _workflow_queue = queue


# ==================== 3. 创建带回调的 LLM ====================
def create_streaming_llm(node_name: str):
    """创建带流式回调的 LLM"""
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="sk-321ba53567a24d5ab9f116ad6790cc66",
        temperature=0.7,
        streaming=True,
        callbacks=[StreamCallback(_workflow_queue, node_name)]
    )


# ==================== 4. 定义图节点 ====================
async def node_a(state: GraphState):
    """节点 A: 简单的文本处理"""
    await _workflow_queue.put({
        "type": "node_start",
        "node": "node_a",
        "data": {"message": "开始执行节点 A..."}
    })

    await asyncio.sleep(0.5)

    output = "这是节点 A 的输出"
    return {"node_outputs": {**state.get("node_outputs", {}), "node_a": output}}


async def node_b(state: GraphState):
    """节点 B: 调用 LLM"""
    await _workflow_queue.put({
        "type": "node_start",
        "node": "node_b",
        "data": {"message": "开始执行节点 B - LLM 生成中..."}
    })

    llm = create_streaming_llm("node_b")
    response = await llm.ainvoke([
        HumanMessage(content="请用一句话介绍旅游的好处")
    ])

    return {
        "node_outputs": {**state.get("node_outputs", {}), "node_b": response.content}
    }


async def node_c(state: GraphState):
    """节点 C: 另一个 LLM 节点"""
    await _workflow_queue.put({
        "type": "node_start",
        "node": "node_c",
        "data": {"message": "开始执行节点 C - 正在写诗..."}
    })

    await asyncio.sleep(2)

    llm = create_streaming_llm("node_c")
    response = await llm.ainvoke([
        HumanMessage(content="请写一首关于春天的七言绝句")
    ])

    return {
        "node_outputs": {**state.get("node_outputs", {}), "node_c": response.content}
    }


# ==================== 5. 构建工作流 ====================
def create_workflow():
    workflow = StateGraph(GraphState)
    workflow.add_node("node_a", node_a)
    workflow.add_node("node_b", node_b)
    workflow.add_node("node_c", node_c)

    workflow.set_entry_point("node_a")
    workflow.add_edge("node_a", "node_b")
    workflow.add_edge("node_b", "node_c")
    workflow.add_edge("node_c", END)

    return workflow.compile()


async def run_workflow(queue: asyncio.Queue):
    """运行工作流"""
    set_queue(queue)

    workflow = create_workflow()
    initial_state = {"messages": [], "node_outputs": {}}

    async for event in workflow.astream(initial_state):
        pass
