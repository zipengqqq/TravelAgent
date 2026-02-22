import asyncio
import os
from contextvars import ContextVar

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

# 使用 contextvar 存储 queue，避免通过 state 传递（state 会被序列化）
# ContextVar 保证数据每个请求独立，互不干扰
_stream_queue: ContextVar[asyncio.Queue] = ContextVar('stream_queue', default=None)


def set_stream_queue(queue: asyncio.Queue):
    """设置当前请求的 queue"""
    _stream_queue.set(queue)


def get_stream_queue() -> asyncio.Queue | None:
    """获取当前请求的 queue"""
    return _stream_queue.get()


class StreamCallback(BaseCallbackHandler):
    """自定义回调，用于捕获每个 token 并推送到队列"""

    def __init__(self, node_name: str):
        self.node_name = node_name

    def on_llm_new_token(self, token: str, **kwargs):
        """LLM 生成新 token 时调用"""
        if token:
            queue = get_stream_queue()
            if queue:
                queue.put_nowait({
                    "type": "token",
                    "node": self.node_name,
                    "data": {"content": token}
                })


def create_streaming_llm(node_name: str):
    """创建支持流式的 LLM"""
    load_dotenv()
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url=os.getenv('DEEPSEEK_BASE_URL'),
        temperature=0.7,
        streaming=True,
        callbacks=[StreamCallback(node_name)]
    )
    return llm



