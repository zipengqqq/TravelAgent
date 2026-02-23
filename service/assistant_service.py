import asyncio
import inspect
import os
from datetime import datetime

from langchain_openai import ChatOpenAI

from graph.async_workflow import async_workflow, compiled_async_workflow
from graph.stream_callback import set_stream_queue
from pojo.entity.conversation_entity import Conversation
from pojo.request.chat_request import ChatRequest
from pojo.request.conversation_add_request import ConversationAddRequest
from pojo.request.conversation_delete_request import ConversationDeleteRequest
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
        """流式chatbox实现 - token 级别"""
        await self._ensure_initialized()

        question = request.question
        thread_id = request.thread_id
        user_id = request.user_id

        queue = asyncio.Queue()
        workflow_done = False

        # 使用 contextvars 设置 queue（避免放入 state 导致序列化失败）
        set_stream_queue(queue)

        state = {
            "question": question,
            "plan": [],
            "past_steps": [],
            "response": "",
            "route": "",
            "messages": [],
            "user_id": user_id,
            "memories": []
        }

        config = {"configurable": {"thread_id": thread_id}}

        # 后台运行工作流
        async def run_workflow():
            # nonlocal关键字，可以读取外部变量workflow_done并且修改它，如果不加这个关键字，那么workflow_node就不会被修改
            nonlocal workflow_done
            try:
                async for event in self._app.astream(state, config=config):
                    # 这里可以处理节点级别的事件（如果需要）
                    pass
            except Exception as e:
                logger.error(f"工作流执行出错: {e}")
                await queue.put({"type": "error", "data": {"message": str(e)}})
            finally:
                await queue.put({"type": "workflow_end"})
                workflow_done = True

        # 启动工作流任务
        workflow_task = asyncio.create_task(run_workflow())

        try:
            while True:
                # 检查是否结束
                if workflow_done and queue.empty():
                    break

                # 从队列获取事件（token 或结束信号）
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield {
                        "type": "heartbeat",
                        "data": {}
                    }
                    continue

                if event.get("type") == "token": # 处理 token 事件
                    yield {
                        "type": "token",
                        "node": event.get("node"),
                        "data": event.get("data", {})
                    }
                elif event.get("type") == "workflow_end": # 处理工作流结束
                    yield {
                        "type": "workflow_end",
                        "data": {}
                    }
                elif event.get("type") == "error": # 处理错误
                    yield {
                        "type": "error",
                        "data": event.get("data", {})
                    }
                elif event.get("type") == "status": # 处理状态
                    yield {
                        "type": "status",
                        "data": event.get("data", "")
                    }

        except asyncio.CancelledError:
            workflow_task.cancel()
        finally:
            if not workflow_task.done():
                workflow_task.cancel()

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

    async def delete_conversation(self, request: ConversationDeleteRequest):
        """删除对话"""
        with create_session() as session:
            deleted_count = session.query(Conversation).filter(
                Conversation.thread_id == int(request.thread_id)
            ).delete()
            logger.info(f"删除对话: thread_id={request.thread_id}, deleted_count={deleted_count}")
            return {"deleted_count": deleted_count}

    async def _generate_conversation_name(self, question):
        """给对话起名字"""
        prompt = name_conversation_prompt.format(question=question)
        raw = await llm.ainvoke(prompt)
        response = parse_llm_json(raw.content)
        logger.info(f"LLM响应: {response}")
        return response.get('res', '')

