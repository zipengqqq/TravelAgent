import asyncio
import inspect
import os
from datetime import datetime

from langchain_openai import ChatOpenAI

from graph.async_workflow import async_workflow, compiled_async_workflow
from pojo.entity.conversation_entity import Conversation
from pojo.request.chat_request import ChatRequest
from pojo.request.conversation_add_request import ConversationAddRequest
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
    streaming=True,  # 开启流式
    max_retries=2  # 添加重试
)

class AssistantService:
    def __init__(self):
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._app = None
        self._pool = None
        self._checkpointer = None

    async def _ensure_initialized(self):
        """初始化工作流"""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            db_uri = os.getenv("POSTGRES_URI")

            if db_uri:
                try:
                    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                    from psycopg_pool import AsyncConnectionPool

                    self._pool = AsyncConnectionPool(db_uri, kwargs={"autocommit": True}, min_size=2, max_size=10)
                    await self._pool.open()
                    self._checkpointer = AsyncPostgresSaver(self._pool)

                    setup = getattr(self._checkpointer, "setup", None)
                    if setup is not None:
                        maybe_awaitable = setup()
                        if inspect.isawaitable(maybe_awaitable):
                            await maybe_awaitable

                    self._app = async_workflow.compile(checkpointer=self._checkpointer)
                    logger.info("AssistantService 初始化完成（启用 Postgres checkpointer）")
                except Exception as e:
                    logger.warning(f"AssistantService 初始化 checkpointer 失败，将使用无持久化工作流: {e}")
                    self._app = compiled_async_workflow
            else:
                self._app = compiled_async_workflow
                logger.info("AssistantService 初始化完成（未配置 POSTGRES_URI，使用无持久化工作流）")

            self._initialized = True

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("AssistantService 连接池已关闭")

    async def chat(self, request: ChatRequest):
        """流式chatbox实现"""
        await self._ensure_initialized()

        question = request.question
        thread_id = request.thread_id
        user_id = request.user_id

        state = {
            "question": question,
            "plan": [],
            "past_steps": [],
            "response": "",
            "route": "",
            "messages": [],
            "user_id": user_id,
            "memories": [],
        }

        config = {"configurable": {"thread_id": thread_id}}

        # 使用 astream 进行流式输出
        async for event in self._app.astream(state, config=config):
            # 提取每个节点的输出
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    # 流结束
                    yield {
                        "type": "end",
                        "data": {
                            "thread_id": thread_id,
                            "response": node_output.get("response", ""),
                            "route": node_output.get("route", ""),
                            "memories": node_output.get("memories", []),
                        }
                    }
                elif node_name == "router":
                    yield {
                        "type": "node",
                        "node": "router",
                        "data": {"route": node_output.get("route", "")}
                    }
                elif node_name == "planner":
                    yield {
                        "type": "node",
                        "node": "planner",
                        "data": {"plan": node_output.get("plan", [])}
                    }
                elif node_name == "executor":
                    yield {
                        "type": "node",
                        "node": "executor",
                        "data": {"past_step": node_output.get("past_step", None)}
                    }
                elif node_name == "reflect":
                    response = node_output.get("response", "")
                    if response:
                        yield {
                            "type": "chunk",
                            "data": {"response": response}
                        }
                elif node_name == "direct_answer":
                    response = node_output.get("response", "")
                    if response:
                        yield {
                            "type": "chunk",
                            "data": {"response": response}
                        }

    async def add_conversation(self, request: ConversationAddRequest):
        """新增对话"""
        thread_id = id_worker.get_id()
        id = id_worker.get_id()

        # 给对话起名字
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
            logger.info(f"新增对话成功: id={record.id}, user_id={request.user_id}, thread_id={thread_id}")
            return record.to_dict()

    def list_conversations(self, user_id: int):
        """查询用户的所有对话"""
        with create_session() as session:
            conversations = session.query(Conversation).filter(
                Conversation.user_id == user_id
            ).all()
            logger.info(f"查询对话列表成功: user_id={user_id}, count={len(conversations)}")
            return [conversation.to_dict() for conversation in conversations]

    async def select_conversation(self, thread_id: str):
        """查看对话内容，返回用户问题和AI回复"""
        await self._ensure_initialized()
        config = {"configurable": {"thread_id": thread_id}}
        state = await self._app.aget_state(config)
        messages = state.values.get("messages", [])
        logger.info(f"查询对话内容成功: thread_id={thread_id}, messages_count={len(messages)}")

        # 提取用户问题和AI回复
        result = []
        for msg in messages:
            role, content = msg
            result.append({
                "role": role,
                "content": content
            })
        return result

    async def _generate_conversation_name(self, question):
        """给对话起名字"""
        prompt = name_conversation_prompt.format(question=question)
        raw = await llm.ainvoke(prompt)
        response = parse_llm_json(raw.content)
        logger.info(f"LLM响应: {response}")
        return response.get('res', '')

