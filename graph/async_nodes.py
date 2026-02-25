"""
异步节点实现

将所有同步节点转换为异步
"""

import json
from contextvars import ContextVar
from graph.async_config import PlanExecuteState, async_llm, Response, Plan, async_tavily_tool
from graph.async_function import async_abstract
from graph.async_memory_rag import async_memory_rag
from graph.prompts import (
    route_prompt, direct_answer_prompt, planner_prompt,
    search_query_prompt, plan_summary_prompt
)
from graph.stream_callback import create_streaming_llm, get_stream_queue
from langgraph.types import interrupt, Command
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json


# 使用 contextvar 存储任务序号
_task_num: ContextVar[int] = ContextVar('task_num', default=0)

async def async_router_node(state: PlanExecuteState):
    """路由节点：判断意图"""
    logger.info("🚀路由师正在判断意图")
    question = state["question"]

    prompt = route_prompt.format(
        user_request=question,
        memories=state.get("memories", [])
    )

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

    # 发送状态
    queue = get_stream_queue()
    route_text = "直接问答" if route == "direct_answer" else "规划任务"
    await queue.put({
        "type": "status",
        "data": {"status": f"当前用户意图为{route_text}"}
    })

    return {"route": route}


async def async_direct_answer_node(state: PlanExecuteState):
    """直接回答：无需工具"""
    logger.info("🚀直接回答中")
    question = state["question"]
    queue = get_stream_queue()

    # 发送状态
    await queue.put({
        "type": "status",
        "node": "direct_answer",
        "data": {"status": "正在生成回答..."}
    })

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = direct_answer_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("direct_answer")
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    # 发送状态
    await queue.put({
        "type": "status",
        "node": "direct_answer",
        "data": {"status": "回答生成完成"}
    })

    return {
        "response": raw.content,
        "messages": [("user", question), ("assistant", raw.content)]
    }


async def async_planner_node(state: PlanExecuteState):
    """接收用户问题，生成初始计划"""
    logger.info("🚀规划师正在规划任务")
    question = state["question"]
    queue = get_stream_queue()

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = planner_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )

    raw = await async_llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        parsed = Plan.parse_obj(data)
        steps = parsed.steps
        logger.info(f"规划结果：{steps}")
    except Exception as e:
        logger.error(f"规划解析失败：{e}")
        steps = []

    # 将状态返回给前端
    await queue.put({
        "type": "status",
        "node": "planner",
        "data": {"status": f"规划完成，共有 {len(steps)} 个步骤"}
    })

    logger.info(f"共有 {len(steps)} 个任务")

    # 发送规划到前端
    queue = get_stream_queue()
    await queue.put({
        "type": "approve_plan",
        "data": {
            "plan": steps,
            "message": "请确认以下旅行规划"
        }
    })

    return {"plan": steps}


async def async_human_review_node(state: PlanExecuteState):
    """人机交互节点 - 等待用户审核/修改/取消

    使用 interrupt() 实现真正的节点内部中断
    """
    plan = state.get("plan", [])
    queue = get_stream_queue()

    # 发送等待审批消息给前端
    await queue.put({
        "type": "waiting_for_approval",
        "data": {
            "plan": plan
        }
    })

    # 使用 interrupt 实现真正的中断
    result = interrupt({
        "type": "human_review",
        "plan": plan
    })

    # 处理中断返回的结果
    approved = result.get("approved") if result else None

    if approved is False:
        # 用户取消任务，添加取消消息并结束
        return Command(
            goto="end", # 直接跳转到结束节点
            update={
                "approved": False,
                "messages": [("assistant", "用户取消了任务")]
            }
        )
    else:
        # 用户批准了，继续执行
        return {"approved": True}


async def async_executor_node(state: PlanExecuteState):
    """执行者：取出计划中的第一个任务"""
    plan = state['plan']
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
        # logger.info(f"搜索结果：{search_result}")
        result_str = json.dumps(search_result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"搜索失败：{e}")
        return {"response": f"搜索失败：{e}"}
    logger.info(f"搜索结果长度为：{len(result_str)}")

    # 3）异步提取摘要
    result_str = await async_abstract(result_str)
    logger.info(f"摘要长度为: {len(result_str)}")

    # 计算当前任务序号：已完成任务数 + 1
    current_task_num = len(state.get('past_steps', [])) + 1

    # 返回给前端，当前正在执行的任务
    _task_num.set(_task_num.get() + 1)
    queue = get_stream_queue()
    await queue.put({
        "type": "status",
        "node": "executor",
        "data": {"status": f"当前正在执行任务{_task_num.get()}：{task}"}
    })

    return {
        "past_steps": [(task, result_str)],
        "plan": plan[1:]  # 剔除第一个任务
    }


async def async_plan_summary_node(state: PlanExecuteState):
    """总结计划"""
    if state['plan']:
        logger.info("计划存在，继续循环")
        return {"response": ""}

    past_steps_str = ""
    for step, result in state['past_steps']:
        past_steps_str += f"已完成步骤：{step}\n执行结果：{result}\n"

    queue = get_stream_queue()

    prompt = plan_summary_prompt.format(
        question=state['question'],
        past_steps=past_steps_str
    )

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("reflect")
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    response = raw.content
    logger.info(f"大模型结果为：{response}")

    logger.info("任务完成，生成最终回答。")
    return {
        "response": response,
        "messages": [("user", state['question']), ("assistant", response)]
    }



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
