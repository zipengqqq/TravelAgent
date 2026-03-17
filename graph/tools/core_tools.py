"""
核心工具集合 - 将 LangGraph 节点封装为工具

这些工具代替了之前的 LangGraph 节点，让 Agent 可以自主决定使用哪些工具。
"""

import json
import os
from typing import List

from dotenv import load_dotenv
from langchain_core.tools import tool

from graph.async_memory_rag import async_memory_rag
from graph.prompts import (
    route_prompt, direct_answer_prompt, planner_prompt,
    plan_summary_prompt
)
from graph.stream_callback import get_stream_queue, create_streaming_llm
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json

load_dotenv()

# LangChain OpenAI 客户端需要 OPENAI_API_KEY
if os.getenv('DEEPSEEK_API_KEY') and not os.getenv('OPENAI_API_KEY'):
    os.environ['OPENAI_API_KEY'] = os.getenv('DEEPSEEK_API_KEY')


# ========== LLM 工厂 ==========

def create_llm(streaming: bool = False, temperature: float = 0.7):
    """创建 LLM 实例"""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url=os.getenv('DEEPSEEK_BASE_URL'),
        temperature=temperature,
        streaming=streaming,
        max_retries=2
    )


# ========== 核心工具 ==========

@tool
async def retrieve_memories(query: str, user_id: int = 1) -> str:
    """检索用户的长期记忆"""
    logger.info(f"[记忆] 检索: {query[:50]}...")
    memories = await async_memory_rag.search_memories(user_id, query, top_k=5)
    if memories:
        return "用户历史记忆：\n" + "\n".join([f"- {m}" for m in memories])
    return "暂无相关记忆"


@tool
async def save_memory(user_id: int, question: str, answer: str) -> str:
    """保存对话到长期记忆"""
    logger.info(f"[记忆] 保存: {question[:30]}...")
    conversation = f"用户：{question}\nAI：{answer}"
    await async_memory_rag.add_memory(user_id, conversation)
    return "已保存到记忆"


@tool
async def route_intent(question: str, context: str = "") -> str:
    """路由用户意图：planner 需要规划，direct_answer 直接回答"""
    logger.info(f"[路由] 判断: {question[:50]}...")

    prompt = route_prompt.format(user_request=question, memories=context)
    llm = create_llm(streaming=False, temperature=0.0)
    raw = await llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        route = str(data.get("route", "")).strip()
    except Exception as e:
        route = "direct_answer"

    if route not in {"planner", "direct_answer"}:
        route = "direct_answer"

    logger.info(f"[路由] 结果: {route}")
    return route


@tool
async def create_travel_plan(question: str, context: str = "") -> str:
    """创建旅行规划，返回 JSON 格式的步骤列表"""
    logger.info(f"[规划] 创建: {question[:50]}...")

    prompt = planner_prompt.format(user_request=question, messages="", memories=context)
    llm = create_llm(streaming=False)
    raw = await llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        steps = data.get("steps", [])
        logger.info(f"[规划] 完成，共 {len(steps)} 个步骤")
    except Exception as e:
        logger.error(f"[规划] 解析失败：{e}")
        steps = []

    # 返回包含步骤的结果
    return json.dumps({"steps": steps, "question": question, "need_approval": True}, ensure_ascii=False)


@tool
async def execute_plan_steps(question: str, steps: list) -> str:
    """执行旅行规划步骤"""
    logger.info(f"[执行] 开始执行，共 {len(steps)} 个步骤")

    from mcp_tools.tool_registry import get_mcp_tools
    tools = await get_mcp_tools()
    from graph.middleware import log_tool_call

    llm = create_llm(streaming=False)
    system_prompt = """你是一个专业的旅行助手。执行用户已确认的规划步骤。"""

    from langchain.agents import create_agent
    agent = create_agent(llm, tools, system_prompt=system_prompt, middleware=[log_tool_call])

    results = []
    for i, step in enumerate(steps, 1):
        logger.info(f"[执行] 步骤 {i}/{len(steps)}: {step}")

        queue = get_stream_queue()
        if queue:
            await queue.put({
                "type": "status",
                "node": "executor",
                "data": {"status": f"执行步骤 {i}/{len(steps)}：{step}"}
            })

        context = f"""用户问题：{question}\n当前步骤（第 {i}/{len(steps)} 步）：{step}\n请执行并给出结果。"""

        try:
            result = await agent.ainvoke({"input": context})
            step_result = result.get("output", "完成")
        except Exception as e:
            step_result = f"出错：{str(e)}"

        results.append(f"【步骤 {i}】{step}\n结果：{step_result}")

    return "\n\n".join(results)


@tool
def summarize_and_respond(question: str, past_steps: str) -> str:
    """总结执行结果并生成最终回答"""
    logger.info("[总结] 生成最终回答")

    prompt = plan_summary_prompt.format(question=question, past_steps=past_steps)
    streaming_llm = create_streaming_llm("final")

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, streaming_llm.ainvoke(prompt))
        raw = future.result()

    return raw.content


@tool
def direct_answer(question: str, context: str = "", messages: str = "") -> str:
    """直接回答用户问题"""
    logger.info(f"[回答] 直接回答: {question[:50]}...")

    prompt = direct_answer_prompt.format(
        user_request=question,
        memories=context,
        messages=messages
    )

    streaming_llm = create_streaming_llm("direct_answer")

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, streaming_llm.ainvoke(prompt))
        raw = future.result()

    return raw.content


# ========== 工具集合 ==========

import asyncio

CORE_TOOLS = [
    retrieve_memories,
    save_memory,
    route_intent,
    create_travel_plan,
    execute_plan_steps,
    summarize_and_respond,
    direct_answer,
]
