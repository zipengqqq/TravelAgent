import asyncio
import json
import os
import re
import traceback
from datetime import datetime
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from graph.minimal_agent import minimal_react_agent
from graph.tools.core_tools import save_memory, execute_plan_steps, summarize_and_respond
from graph.stream_callback import set_stream_queue, get_stream_queue, create_streaming_llm
from pojo.entity.conversation_entity import Conversation
from pojo.request.chat_request import ChatRequest
from pojo.request.conversation_add_request import ConversationAddRequest
from pojo.request.conversation_delete_request import ConversationDeleteRequest
from pojo.request.approve_request import ApproveRequest
from service.prompts import name_conversation_prompt
from utils.db_util import create_session
from utils.id_util import id_worker
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
    streaming=True,
    max_retries=2
)


class AssistantService:
    """基于 MinimalReActAgent 的助手服务"""

    def __init__(self):
        self._initialized = False
        self._pending_plans = {}  # thread_id -> {question, plan}

    async def _ensure_initialized(self):
        if self._initialized:
            return
        await minimal_react_agent._ensure_initialized()
        self._initialized = True

    async def close(self):
        pass

    async def chat(self, request: ChatRequest) -> AsyncGenerator[dict, None]:
        await self._ensure_initialized()

        question = request.question
        thread_id = request.thread_id
        user_id = request.user_id

        queue = asyncio.Queue()
        set_stream_queue(queue)

        try:
            await queue.put({"type": "status", "data": {"status": "思考中..."}})

            # 调用 Agent
            logger.info(f"[Chat] 开始调用 Agent，问题: {question[:50]}...")
            result = await minimal_react_agent._agent.ainvoke(
                {"messages": [HumanMessage(content=question)]}
            )
            messages = result.get("messages", [])

            # 先提取 tool 结果中的 steps
            steps = []
            output = ""
            for msg in messages:
                # 检查是否是 tool 结果
                if hasattr(msg, 'type') and msg.type == 'tool' and hasattr(msg, 'content'):
                    try:
                        tool_data = json.loads(msg.content)
                        if 'steps' in tool_data and tool_data.get('need_approval'):
                            steps = tool_data['steps']
                            logger.info(f"[Chat] 从工具结果提取 steps: {len(steps)} 个")
                    except Exception as e:
                        logger.info(f"[Chat] 解析 tool 消息失败: {e}")

            # 获取 AI 的最后回复
            for msg in reversed(messages):
                if hasattr(msg, 'type') and msg.type == 'ai' and hasattr(msg, 'content') and msg.content:
                    output = msg.content
                    break

            logger.info(f"[Chat] Agent 输出: {output[:200]}...")

            if steps:
                # 需要审批
                self._pending_plans[thread_id] = {
                    "question": question,
                    "plan": steps
                }
                await queue.put({
                    "type": "waiting_for_approval",
                    "data": {"plan": steps, "question": question}
                })
                yield {
                    "type": "waiting_for_approval",
                    "data": {"plan": steps, "question": question}
                }
            else:
                # 直接返回回答
                await queue.put({"type": "status", "data": {"status": "生成回答..."}})

                # 直接流式输出 agent 的回复
                for i in range(0, len(output), 10):
                    chunk = output[i:i+10]
                    yield {"type": "token", "data": {"content": chunk}}

                # 保存记忆
                await save_memory.ainvoke({
                    "user_id": user_id,
                    "question": question,
                    "answer": output
                })

                await queue.put({"type": "workflow_end", "data": {}})
                yield {"type": "workflow_end", "data": {}}

        except Exception as e:
            logger.error(f"对话处理出错: {e}")
            traceback.print_exc()
            yield {"type": "error", "data": {"message": str(e)}}

    def _extract_steps(self, output: str) -> list:
        """从输出中提取步骤"""
        steps = []
        try:
            match = re.search(r'\{[\s\S]*\}', output)
            if match:
                data = json.loads(match.group())
                if "steps" in data and data["steps"]:
                    steps = data["steps"]
        except:
            pass
        return steps

    async def add_conversation(self, request: ConversationAddRequest):
        thread_id = id_worker.get_id()
        id = id_worker.get_id()

        name = await self._generate_conversation_name(request.question)
        name = name if name else f"对话_{thread_id}"
        with create_session() as session:
            record = Conversation(
                id=id,
                user_id=request.user_id,
                thread_id=thread_id,
                create_time=datetime.now(),
                name=name
            )
            session.add(record)
            return record.to_dict()

    def list_conversations(self, user_id: int):
        with create_session() as session:
            conversations = session.query(Conversation).filter(
                Conversation.user_id == user_id
            ).all()
            return [conversation.to_dict() for conversation in conversations]

    async def select_conversation(self, thread_id: str):
        return []

    async def delete_conversation(self, request: ConversationDeleteRequest):
        with create_session() as session:
            deleted_count = session.query(Conversation).filter(
                Conversation.thread_id == int(request.thread_id)
            ).delete()
            return {"deleted_count": deleted_count}

    async def _generate_conversation_name(self, question):
        prompt = name_conversation_prompt.format(question=question)
        raw = await llm.ainvoke(prompt)
        response = parse_llm_json(raw.content)
        return response.get('res', '')

    async def approve(self, request: ApproveRequest) -> AsyncGenerator[dict, None]:
        await self._ensure_initialized()

        thread_id = request.thread_id
        user_id = request.user_id

        # 获取待审批的计划
        question = request.question
        steps = request.plan

        if thread_id in self._pending_plans:
            pending = self._pending_plans[thread_id]
            question = question or pending.get("question", "")
            steps = steps or pending.get("plan", [])

        if request.cancelled:
            if thread_id in self._pending_plans:
                del self._pending_plans[thread_id]
            yield {"type": "workflow_end", "data": {"message": "已取消"}}
            return

        if not steps:
            yield {"type": "error", "data": {"message": "没有可执行的计划"}}
            return

        queue = asyncio.Queue()
        set_stream_queue(queue)

        if thread_id in self._pending_plans:
            del self._pending_plans[thread_id]

        try:
            await queue.put({"type": "status", "data": {"status": "执行规划..."}})

            # 执行规划
            execution_result = await execute_plan_steps.ainvoke({
                "question": question,
                "steps": steps
            })

            await queue.put({"type": "status", "data": {"status": "生成回答..."}})

            final_answer = summarize_and_respond.invoke({
                "question": question,
                "past_steps": execution_result
            })

            # 保存记忆
            await save_memory.ainvoke({
                "user_id": user_id,
                "question": question,
                "answer": final_answer
            })

            yield {"type": "workflow_end", "data": {}}

        except Exception as e:
            logger.error(f"执行规划出错: {e}")
            yield {"type": "error", "data": {"message": str(e)}}
