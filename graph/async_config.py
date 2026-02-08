"""
异步 LLM 配置

配置 DeepSeek Chat API 的异步调用
创建异步 Tavily Search 包装器（使用 httpx）
"""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pydantic.v1 import BaseModel as V1BaseModel

load_dotenv()

# 异步 LLM 配置
async_llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
    streaming=True,  # 开启流式
    max_retries=2  # 添加重试
)


# Tavily Search 的异步包装器
class AsyncTavilySearch(BaseTool):
    """异步 Tavily Search 工具包装器"""

    name: str = "async_tavily_search"
    description: str = "Async search the web using Tavily Search API"
    max_results: int = 5
    api_key: str = os.getenv('TAVILY_API_KEY', '')
    timeout: int = 30
    _client: httpx.AsyncClient | None = None
    _executor: ThreadPoolExecutor | None = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def _arun(self, query: str) -> str:
        """异步执行搜索"""
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY not found in environment variables")

        # 创建异步 HTTP 客户端
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": self.max_results,
                "search_depth": "basic",
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
            }

            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # 提取搜索结果
            results = data.get("results", [])
            return json.dumps(results, ensure_ascii=False, indent=2)

    async def ainvoke(self, query: str) -> Any:
        """异步调用搜索"""
        return await self._arun(query)

    async def invoke(self, query: str) -> Any:
        """同步调用（用于兼容）"""
        return await self._arun(query)

    def _run(self, query: str) -> str:
        """同步执行（LangChain 兼容）"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._arun(query))

    async def close(self):
        """清理资源"""
        if self._executor:
            self._executor.shutdown(wait=True)


# 异步 Tavily Search 实例
async_tavily_tool = AsyncTavilySearch(max_results=5)


# 保持同步版本兼容性（用于直接调用同步方法）
tavily_tool = TavilySearch(max_results=5)


# 状态定义（与同步版本一致）
from typing import Annotated, List, Tuple, TypedDict
import operator


class PlanExecuteState(TypedDict):
    """定义状态"""
    question: str  # 用户问题
    plan: List[str]  # 待执行的任务列表
    past_steps: Annotated[List[Tuple], operator.add]  # 已完成的步骤（步骤名，结果）
    response: str  # 最终回复
    route: str  # 路由意图
    messages: Annotated[List[Tuple], operator.add]  # 对话历史
    user_id: int  # 用户id，当前固定为1
    memories: List[str]  # 长期记忆


# 结构化输出模型
class Plan(V1BaseModel):
    """(结构化输出) 规划列表"""
    steps: List[str] = Field(description="一系列具体的步骤，例如查询天气，查询景点等")  # 计划列表结构


class Response(V1BaseModel):
    """（结构化输出）重新规划或结束"""
    response: str = Field(description="最终回答，如果还需要继续执行步骤，则为空字符串")
    next_plan: List[str] = Field(description="剩余未完成的步骤列表")
