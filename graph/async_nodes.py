"""
异步节点实现

将所有同步节点转换为异步
"""

import json

from graph.async_config import PlanExecuteState, async_llm, Response, Plan, async_tavily_tool
from graph.async_function import async_abstract
from graph.async_memory_rag import async_memory_rag
from graph.prompts import (
    route_prompt, direct_answer_prompt, planner_prompt,
    search_query_prompt, reflect_prompt
)
from graph.stream_callback import create_streaming_llm
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json


async def async_router_node(state: PlanExecuteState):
    """路由节点：判断意图"""
    logger.info("🚀路由师正在判断意图")
    question = state["question"]
    queue = state.get("queue")

    prompt = route_prompt.format(
        user_request=question,
        memories=state.get("memories", [])
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("router", queue)
        router_llm = streaming_llm.bind(temperature=0.0)
    else:
        router_llm = async_llm.bind(temperature=0.0)

    raw = await router_llm.ainvoke(prompt)
    try:
        data = parse_llm_json(raw.content)
        route = str(data.get("route", "")).strip()
    except Exception as e:
        logger.error(f"路由解析失败：{e}")
        route = ""

    if route not in {"planner", "direct_answer"}:
        logger.info(f"路由结果无效，默认走 direct_answer: {route}")
        route = "direct_answer"

    logger.info(f"用户意图：{route}")
    return {"route": route}


async def async_direct_answer_node(state: PlanExecuteState):
    """直接回答：无需工具"""
    logger.info("🚀直接回答中")
    question = state["question"]
    queue = state.get("queue")

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = direct_answer_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("direct_answer", queue)
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    return {
        "response": raw.content,
        "messages": [("user", question), ("assistant", raw.content)]
    }


async def async_planner_node(state: PlanExecuteState):
    """接收用户问题，生成初始计划"""
    logger.info("🚀规划师正在规划任务")
    question = state["question"]
    queue = state.get("queue")

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = planner_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("planner", queue)
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        parsed = Plan.model_validate(data)
        steps = parsed.steps
        logger.info(f"规划结果：{steps}")
    except Exception as e:
        logger.error(f"规划解析失败：{e}")
        steps = []
    logger.info(f"共有 {len(steps)} 个步骤")
    return {"plan": steps}


async def async_executor_node(state: PlanExecuteState):
    """执行者：取出计划中的第一个任务"""
    plan = state['plan']
    if not plan:
        logger.error("计划为空")
        return {"past_steps": [], "response": ""}
    task = plan[0]

    logger.info(f"🚀执行者正在执行任务：{task}")

    # 1) 异步生成搜索关键词
    search_query_prompt_text = search_query_prompt.format(task=task)
    keywords_text = await async_llm.ainvoke(search_query_prompt_text)
    search_query = keywords_text.content.strip()
    logger.info(f"搜索关键词：{search_query}")

    # 2）异步调用 Tavily 工具
    try:
        search_result = await async_tavily_tool.ainvoke(search_query)
        logger.info(f"搜索结果：{search_result}")
        result_str = json.dumps(search_result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"搜索失败：{e}")
        return {"response": f"搜索失败：{e}"}
    logger.info(f"搜索结果长度为：{len(result_str)}")

    # 3）异步提取摘要
    result_str = await async_abstract(result_str)
    logger.info(f"摘要长度为: {len(result_str)}")

    return {
        "past_steps": [(task, result_str)],
        "plan": plan[1:]  # 剔除第一个任务
    }


async def async_reflect_node(state: PlanExecuteState):
    """重新规划器：根据执行结果，判断是否需要重新规划"""
    logger.info(f"🚀反思节点正在判断是否需要重新规划")
    past_steps_str = ""
    for step, result in state['past_steps']:
        past_steps_str += f"已完成步骤：{step}\n执行结果：{result}\n"

    current_plan_str = "\n".join(state['plan'])
    queue = state.get("queue")

    prompt = reflect_prompt.format(
        question=state['question'],
        past_steps=past_steps_str,
        current_plan=current_plan_str,
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("reflect", queue)
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        logger.info(f"大模型结果为：{data}")
        result = Response.model_validate(data)
    except Exception as e:
        logger.error(f"反思节点解析失败：{e}")
        result = Response(response="", next_plan=[])

    if result.response and result.response.strip() != "":
        logger.info("任务完成，生成最终回答。")
        return {
            "response": result.response,
            "plan": [],
            "messages": [("user", state['question']), ("assistant", result.response)]
        }
    else:
        logger.info(f"反思节点决策：继续执行，剩余计划：{len(result.next_plan)}个步骤")
        logger.info(f"剩余计划：{result.next_plan}")
        return {"plan": result.next_plan}


async def async_memory_retrieve_node(state: PlanExecuteState):
    """记忆检索节点：根据用户问题，从长期记忆中检索相关记忆"""
    user_id = state["user_id"]
    question = state["question"]

    # 异步检索相关历史记忆
    memories = await async_memory_rag.search_memories(user_id, question, top_k=5)
    logger.info(f"检索到 {len(memories)} 条相关记忆")
    return {"memories": memories}


async def async_memory_save_node(state: PlanExecuteState):
    """记忆保存节点：根据用户问题和执行结果，将新记忆保存到长期记忆中"""
    user_id = state["user_id"]
    question = state["question"]
    response = state.get('response', '')

    conversation = f"用户：{question}\nAI：{response}"
    await async_memory_rag.add_memory(user_id, conversation)
    logger.info(f"已保存对话到长期记忆")
