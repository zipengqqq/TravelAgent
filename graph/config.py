import operator
import os
from typing import Annotated, List, Tuple, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field

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
    route: str # 路由意图
    messages: Annotated[List[Tuple], operator.add] # 对话历史
    user_id: int # 用户id，当前固定为1


class Plan(BaseModel):
    """(结构化输出) 规划列表"""
    steps: List[str] = Field(description="一系列具体的步骤，例如查询天气，查询景点等")  # 计划列表结构


class Response(BaseModel):
    """（结构化输出）重新规划或结束"""
    response: str = Field(description="最终回答，如果还需要继续执行步骤，则为空字符串")
    next_plan: List[str] = Field(description="剩余未完成的步骤列表")


