import asyncio
import inspect
import json
import os
from datetime import date, datetime

from graph.async_workflow import async_workflow, compiled_async_workflow
from pojo.entity.conversation_entity import Conversation
from pojo.request.chat_request import ChatRequest
from pojo.request.conversation_add_request import ConversationAddRequest
from utils.db_util import create_session
from utils.id_util import id_worker
from utils.logger_util import logger


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

    def add_conversation(self, request: ConversationAddRequest):
        """新增对话"""
        thread_id = id_worker.get_id()
        id = id_worker.get_id()
        with create_session() as session:
            record = Conversation(
                id=id,
                user_id=request.user_id,
                thread_id=thread_id,
                create_time=datetime.now(),
                name=str(thread_id)
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

