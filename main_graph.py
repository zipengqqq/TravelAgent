import os
import operator
from typing import Annotated, List, Tuple, TypedDict, Union
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.prompts import ChatPromptTemplate
from utils.logger_util import logger
from langgraph.graph import END, StateGraph, START
from pydantic import BaseModel, Field

load_dotenv()
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
    streaming=True  # 开启流式
)

class PlanExecuteState(TypedDict):
    """定义状态"""
    question: str # 用户问题
    plan: List[str] # 待执行的任务列表
    past_steps: Annotated[List[Tuple], operator.add] # 已完成的步骤（步骤名，结果）
    response: str # 最终回复

class Plan(BaseModel):
    """(结构化输出) 规划列表"""
    steps: List[str] = Field(description="一系列具体的步骤，例如查询天气，查询景点等") # 计划列表结构

class Response(BaseModel):
    """（结构化输出）重新规划或结束"""
    response: str = Field(description="最终回答，如果还需要继续执行步骤，则为空字符串")
    next_plan: List[str] = Field(description="剩余未完成的步骤列表")

def planner_node(state: PlanExecuteState):
    """接收用户问题，生成初始计划"""
    logger.info("🚀规划师正在规划任务")
    question = state["question"]
    system_prompt = "你是一个旅游规划专家，请根据用户的需求，制定一个清晰的分布执行计划。"
    user_prompt = f"用户需求：{question}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # 调用模型，获取结构化输出
    structured_llm  = llm.with_structured_output(Plan)
    response = structured_llm.invoke(messages)
    return {"plan": response.steps}

def executor_node(state: PlanExecuteState):
    """执行者：取出计划中的第一个任务"""
    plan = state['plan']
    task = plan[0]

    logger.info(f"🚀执行者正在执行任务：{task}")

    # 1) 生成搜索关键词
    search_query_prompt = [
        {"role": "system", "content": "你是一个搜索助手，请把用户的任务转换为最适合搜索引擎搜索的关键词。只输出关键词，不要其他废话。"},
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
        "past_steps": [(task, result_str)]
    }

def replanner_node(state: PlanExecuteState):
    """重新规划器：根据执行结果，判断是否需要重新规划"""
    logger.info(f"🚀重新规划师正在判断是否需要重新规划")
    past_steps_str = ""
    for step, result in state['past_steps']:
        past_steps_str += f"已完成步骤：{step}\n执行结果：{result}\n"
    current_plan_str = "\n".join(state['plan'])

    system_prompt = (
        "你是一个任务调度系统。\n"
        "1. 检查'已完成步骤'的信息是否足以回答用户的'原始目标'。\n"
        "2. 如果足够，请在response字段中输出最终的回答（Markdown 格式），并将new_plan设为空列表。\n"
        "3. 如果不足够，请根据执行结果更新剩余的计划（去掉已完成的，或者添加新的步骤），填入new_plan字段。"
    )

    user_prompt = (
        f"原始目标：{state['question']}\n"
        f"已完成步骤：{past_steps_str}\n"
        f"当前计划：{current_plan_str}\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    structured_llm = llm.with_structured_output(Response)
    result = structured_llm.invoke(messages)

    if result.response and result.response.strip() != "":
        logger.info("任务完成，生成最终回答。")
        return {"response": result.response, "plan": []}
    else:
        logger.info(f"重新规划师决策：继续执行，剩余计划：{len(result.next_plan)}个步骤")
        return {"plan": result.next_plan}

def should_end(state: PlanExecuteState):
    """判断流程是否需要结束"""
    if state['response']:
        return True
    else:
        return False

workflow = StateGraph(PlanExecuteState)

workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("replanner", replanner_node)

workflow.add_edge(START, "planner")         # 开始 -> 规划
workflow.add_edge("planner", "executor")    # 规划 -> 执行者
workflow.add_edge("executor", "replanner")  # 执行者 -> 反思

# 添加条件分支
workflow.add_conditional_edges(
    "replanner", # 从反思节点出来
    should_end, # 判断是否结束
    {
        True: END, # 如果返回 True，流程结束
        False: "executor" # 如果返回 False，继续执行
    }
)

app = workflow.compile()

if __name__ == "__main__":
    question = "我想去洛阳玩玩，帮我查查龙门石窟明天的天气，以及门票价格。"
    state = {"question": question}

    for event in app.stream(state):
        # event是一个字典，key是节点名称，value是该节点输出的state
        for node_name, node_state in event.items():
            # 因为已经在节点中处理了日志，这里不需要重复打印
            pass

    # 获取最终回答
    final_response = node_state['response']
    logger.info(f"最终回答：{final_response}")
