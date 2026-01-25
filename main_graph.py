import json
import operator
import os
from typing import Annotated, List, Tuple, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import END, StateGraph, START
from pydantic import BaseModel, Field
import uuid

from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

load_dotenv()
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
    streaming=True  # 开启流式
)
tavily_tool = TavilySearch(max_results=5)


class PlanExecuteState(TypedDict):
    """定义状态"""
    question: str  # 用户问题
    plan: List[str]  # 待执行的任务列表
    past_steps: Annotated[List[Tuple], operator.add]  # 已完成的步骤（步骤名，结果）
    response: str  # 最终回复


class Plan(BaseModel):
    """(结构化输出) 规划列表"""
    steps: List[str] = Field(description="一系列具体的步骤，例如查询天气，查询景点等")  # 计划列表结构


class Response(BaseModel):
    """（结构化输出）重新规划或结束"""
    response: str = Field(description="最终回答，如果还需要继续执行步骤，则为空字符串")
    next_plan: List[str] = Field(description="剩余未完成的步骤列表")


def planner_node(state: PlanExecuteState):
    """接收用户问题，生成初始计划"""
    logger.info("🚀规划师正在规划任务")
    question = state["question"]

    # 如果是多轮对话，past_steps其中会有之前的执行记录
    past_steps_context = ""
    if state.get("past_steps"):
        past_info = "\n".join([f"步骤：{step}，结果摘要：{res[:50]}..." for step, res in state["past_steps"]])
        past_steps_context = f"\n\n已知历史信息（不用重复查询）：\n{past_info}"

    system_prompt = "你是一个旅游规划专家。仅输出 JSON。字段：steps(string[])。不要任何额外文本或解释。"
    user_prompt = f"用户需求：{question}{past_steps_context}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    raw = llm.invoke(messages)
    try:
        data = parse_llm_json(raw.content)
        parsed = Plan.model_validate(data)
        steps = parsed.steps
        logger.info(f"规划结果：{steps}")
    except Exception as e:
        logger.error(f"规划解析失败：{e}")
        steps = []
    return {"plan": steps}


def executor_node(state: PlanExecuteState):
    """执行者：取出计划中的第一个任务"""
    plan = state['plan']
    if not plan:
        logger.error("计划为空")
        return {"past_steps": [], "response": ""}
    task = plan[0]

    logger.info(f"🚀执行者正在执行任务：{task}")

    # 1) 生成搜索关键词
    search_query_prompt = [
        {"role": "system",
         "content": "你是一个搜索助手，请把用户的任务转换为最适合搜索引擎搜索的关键词。只输出关键词，不要其他废话。"},
        {"role": "user", "content": f"任务：{task}"}
    ]
    keywords_text = llm.invoke(search_query_prompt)
    search_query = keywords_text.content.strip()
    logger.info(f"搜索关键词：{search_query}")

    # 2）调用 Tavily工具
    try:
        search_result = tavily_tool.invoke(search_query)
        result_str = json.dumps(search_result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"搜索失败：{e}")
        return {"response": f"搜索失败：{e}"}

    logger.info(f"搜索结果长度为：{len(result_str)}")

    return {
        "past_steps": [(task, result_str)],
        "plan": plan[1:] # 剔除第一个任务
    }


def reflect_node(state: PlanExecuteState):
    """重新规划器：根据执行结果，判断是否需要重新规划"""
    logger.info(f"🚀重新规划师正在判断是否需要重新规划")
    past_steps_str = ""
    for step, result in state['past_steps']:
        past_steps_str += f"已完成步骤：{step}\n执行结果：{result}\n"

    current_plan_str = "\n".join(state['plan'])

    system_prompt = (
        "你是一个任务调度系统。仅输出 JSON。字段：response(string)、next_plan(string[])。\n"
        "当信息足够时，将 next_plan 设为空数组，并在 response 中给出最终 Markdown 回答；\n"
        "当信息不足时，response 设为空字符串，并更新 next_plan（字符串数组）。\n"
        "不要任何额外文本或解释。"
    )

    user_prompt = (
        f"原始目标：{state['question']}\n"
        f"历史：{past_steps_str}\n"
        f"当前计划：{current_plan_str}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    raw = llm.invoke(messages)
    try:
        data = parse_llm_json(raw.content)
        result = Response.model_validate(data)
    except Exception as e:
        logger.error(f"重新规划解析失败：{e}")
        result = Response(response="", next_plan=[])

    if result.response and result.response.strip() != "":
        logger.info("任务完成，生成最终回答。")
        return {"response": result.response, "plan": []}
    else:
        logger.info(f"重新规划师决策：继续执行，剩余计划：{len(result.next_plan)}个步骤")
        logger.info(f"剩余计划：{result.next_plan}")
        return {"plan": result.next_plan}


def should_end(state: PlanExecuteState):
    """判断流程是否需要结束"""
    if state.get('response'):
        return True
    else:
        return False


workflow = StateGraph(PlanExecuteState)

workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("reflect", reflect_node)

workflow.add_edge(START, "planner")  # 开始 -> 规划
workflow.add_edge("planner", "executor")  # 规划 -> 执行者
workflow.add_edge("executor", "reflect")  # 执行者 -> 反思

# 添加条件分支
workflow.add_conditional_edges(
    "reflect",  # 从反思节点出来
    should_end,  # 判断是否结束
    {
        True: END,  # 如果返回 True，流程结束
        False: "executor"  # 如果返回 False，继续执行
    }
)



if __name__ == "__main__":
    uuid = uuid.uuid4().hex
    DB_URI = os.getenv("POSTGRES_URI")
    with ConnectionPool(DB_URI) as pool:
        # 1) 初始化PgSaver
        checkpointer = PostgresSaver(pool)

        # 2) 首次运行，必须执行 setup()，它会自动在库里创建两张表（checkpoints、checkpoint_writes）
        checkpointer.setup()

        app = workflow.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": uuid}}

        # 运行第一轮
        question = "我想去洛阳玩两天，想去白马寺，小街天府，龙门石窟，给我两天的游玩计划。"
        state = {"question": question}
        logger.info("第一轮运行开始")
        for event in app.stream(state, config=config):
            pass
        # 输出最终回答
        final_state = app.get_state(config)
        final_response = final_state.values.get('response', '')
        logger.info(f"问题：{question}")
        logger.info(f"最终回答：{final_response}")

        # 运行第二轮（测试记忆）
        logger.info("第二轮运行开始")
        new_question = "刚才说的小街天府，有什么好吃的"
        app.update_state(config, {"question": new_question, "response": ""})
        # 传入None，表示延续状态
        for event in app.stream(None, config=config):
            pass
        # 输出最终回答
        final_state = app.get_state(config)
        final_response = final_state.values.get('response', '')
        logger.info(f"问题：{question}")
        logger.info(f"最终回答：{final_response}")
