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

