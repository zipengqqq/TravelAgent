"""
异步节点实现

将所有同步节点转换为异步
"""

from langchain_core.messages import HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_function
from langgraph.types import interrupt

from graph.async_config import PlanExecuteState, async_llm, Plan
from graph.async_function import async_abstract
from graph.async_memory_rag import async_memory_rag
from graph.prompts import (
    route_prompt, direct_answer_prompt, planner_prompt,
    plan_summary_prompt
)
from graph.stream_callback import create_streaming_llm, get_stream_queue
from mcp_tools.tool_registry import get_mcp_tools
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json


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
    approved = state.get("approved", False)
    cancelled = state.get("cancelled", False)
    plan = state.get("plan", [])

    # 恢复执行时，跳过 interrupt
    if approved:
        logger.info(f"用户已确认计划：{plan}")
        return {}

    # 用户取消，返回空字典，由条件边决定是否结束
    if cancelled:
        logger.info(f"用户已取消任务")
        return {"cancelled": True}

    queue = get_stream_queue()
    await queue.put({"type": "waiting_for_approval", "data": {"plan": plan}})

    # interrupt 等待用户操作
    interrupt({"type": "human_review", "plan": plan})
    return {}


async def async_executor_node(state: PlanExecuteState):
    """ReAct 执行者：使用 MCP 工具执行任务"""
    plan = state['plan']
    task = plan[0]

    logger.info(f"🚀 ReAct 执行者正在执行任务：{task}")

    # 计算当前任务序号
    current_task_num = len(state.get('past_steps', [])) + 1

    # 发送状态
    queue = get_stream_queue()
    await queue.put({
        "type": "status",
        "node": "executor",
        "data": {"status": f"当前正在执行任务{current_task_num}：{task}"}
    })

    # 加载 MCP 工具
    tools = await get_mcp_tools()
    logger.info(f"已加载 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")

    # 将工具转换为函数格式
    functions = [convert_to_openai_function(tool) for tool in tools]
    llm_with_tools = async_llm.bind(functions=functions)

    # ReAct 循环
    messages = [HumanMessage(content=f"请帮我完成以下任务：{task}\n\n请根据任务需求选择合适的工具进行搜索或查询，并总结结果。")]

    max_iterations = len(tools) + 5
    for i in range(max_iterations):
        logger.info(f"ReAct 迭代 {i+1}/{max_iterations}")

        # 调用 LLM
        response = await llm_with_tools.ainvoke(messages)

        # 检查工具调用
        tool_calls = getattr(response, 'tool_calls', None)
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call['name']
                tool_args = tool_call.get('args', {})

                # 查找并调用工具
                tool = next((t for t in tools if t.name == tool_name), None)
                if tool:
                    logger.info(f"调用工具: {tool_name}, 参数: {tool_args}")
                    result = await tool.ainvoke(tool_args)
                    logger.info(f"工具返回结果长度: {len(str(result))}")

                    # 将结果添加到消息历史
                    messages.append(response)
                    messages.append(HumanMessage(content=f"Observation: {result}"))

                    # 发送状态更新
                    await queue.put({
                        "type": "status",
                        "node": "executor",
                        "data": {"status": f"当前正在执行任务{current_task_num}：{task}"}
                    })
                    
                else:
                    logger.warning(f"未找到工具: {tool_name}")
                    messages.append(response)
                    messages.append(HumanMessage(content=f"未找到工具: {tool_name}"))
        else:
            # 没有工具调用，返回最终答案
            result_str = response.content
            logger.info(f"ReAct 执行完成，最终结果长度: {len(result_str)}")

            # 摘要（如果结果太长）
            if len(result_str) > 2000:
                result_str = await async_abstract(result_str)

            return {
                "past_steps": [(task, result_str)],
                "plan": plan[1:]
            }

    # 超过迭代次数
    logger.warning(f"达到最大迭代次数 {max_iterations}")
    final_messages = [m for m in messages if isinstance(m, HumanMessage)]
    result_str = final_messages[-1].content if final_messages else "搜索结果总结"

    return {
        "past_steps": [(task, result_str)],
        "plan": plan[1:]
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
