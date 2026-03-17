"""
最小 ReAct Agent 核心 - 工具优先

将所有能力（记忆、路由、规划、执行、总结）都作为工具暴露给 Agent，
让 Agent 自主决定使用哪些工具以及使用顺序。
"""

import os
from typing import AsyncGenerator

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from graph.tools.core_tools import CORE_TOOLS, create_llm
from mcp_tools.tool_registry import get_mcp_tools
from utils.logger_util import logger

# LangChain OpenAI 客户端需要 OPENAI_API_KEY
from dotenv import load_dotenv
load_dotenv()
if os.getenv('DEEPSEEK_API_KEY') and not os.getenv('OPENAI_API_KEY'):
    os.environ['OPENAI_API_KEY'] = os.getenv('DEEPSEEK_API_KEY')


# ========== 系统提示词 ==========

AGENT_SYSTEM_PROMPT = """你是一个智能旅行助手。

## 可用工具
- retrieve_memories: 检索用户历史记忆
- route_intent: 判断用户意图（planner=需要规划，direct_answer=直接回答）
- create_travel_plan: 创建旅行规划
- execute_plan_steps: 执行规划步骤
- summarize_and_respond: 总结并回答
- direct_answer: 直接回答
- save_memory: 保存对话到记忆

## 工作流程（你自主决定）

根据用户输入，自主决定调用哪些工具：

1. 可以先调用 retrieve_memories 了解用户偏好
2. 调用 route_intent 判断意图
3. 如果需要规划：
   - 调用 create_travel_plan 创建规划
   - 等待用户审批后调用 execute_plan_steps 执行
   - 最后调用 summarize_and_respond 生成回答
4. 如果不需要规划：
   - 直接调用 direct_answer 回答
5. 对话结束后调用 save_memory 保存记忆

记住：你自主决定工作流程，可以根据实际情况灵活调整。"""


# ========== 主 Agent 类 ==========

class MinimalReActAgent:
    """最小 ReAct Agent - 工具优先"""

    def __init__(self):
        self._agent = None
        self._llm = create_llm(streaming=False)
        self._initialized = False
        self._mcp_tools = []

    async def _ensure_initialized(self):
        """初始化 Agent"""
        if self._initialized:
            return

        self._mcp_tools = await get_mcp_tools()
        logger.info(f"[Agent] 已加载 {len(self._mcp_tools)} 个 MCP 工具")

        all_tools = CORE_TOOLS + self._mcp_tools
        logger.info(f"[Agent] 创建 agent, LLM: {self._llm.model_name}, 工具数量: {len(all_tools)}")
        self._agent = create_agent(self._llm, all_tools, system_prompt=AGENT_SYSTEM_PROMPT)

        self._initialized = True
        logger.info("[Agent] 初始化完成")

    async def chat(self, question: str, user_id: int = 1) -> AsyncGenerator[dict, None]:
        """处理用户对话"""
        await self._ensure_initialized()

        queue = get_stream_queue()
        if queue:
            await queue.put({"type": "status", "data": {"status": "开始处理..."}})

        messages = [HumanMessage(content=question)]

        try:
            result = await self._agent.ainvoke({"messages": messages})
            output = result.get("output", "")

            # 保存记忆
            await save_memory.ainvoke({
                "user_id": user_id,
                "question": question,
                "answer": output
            })

            if queue:
                yield {"type": "workflow_end", "data": {}}

        except Exception as e:
            logger.error(f"Agent 执行出错: {e}")
            if queue:
                yield {"type": "error", "data": {"message": str(e)}}

    async def execute_approved_plan(self, question: str, steps: list, user_id: int = 1):
        """执行已审批的规划"""
        await self._ensure_initialized()

        queue = get_stream_queue()
        if queue:
            await queue.put({"type": "status", "data": {"status": "执行规划..."}})

        try:
            execution_result = await execute_plan_steps.ainvoke({
                "question": question,
                "steps": steps
            })

            if queue:
                await queue.put({"type": "status", "data": {"status": "生成回答..."}})

            final_answer = summarize_and_respond.invoke({
                "question": question,
                "past_steps": execution_result
            })

            await save_memory.ainvoke({
                "user_id": user_id,
                "question": question,
                "answer": final_answer
            })

            if queue:
                yield {"type": "workflow_end", "data": {}}

        except Exception as e:
            logger.error(f"执行规划出错: {e}")
            if queue:
                yield {"type": "error", "data": {"message": str(e)}}


# 全局实例
minimal_react_agent = MinimalReActAgent()
