import asyncio
import os

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI


class StreamCallback(BaseCallbackHandler):
    """自定义回调，用于捕获每个 token 并推送到队列"""

    def __init__(self, queue: asyncio.Queue, node_name: str):
        self.queue = queue
        self.node_name = node_name

    async def on_llm_new_token(self, token: str, **kwargs):
        """LLM 生成新 token 时调用"""
        if token:
            self.queue.put_nowait({
                "type": "token",
                "node": self.node_name,
                "data": {"content": token}
            })

def create_streaming_llm(node_name: str, queue: asyncio.Queue):
    load_dotenv()
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url=os.getenv('DEEPSEEK_BASE_URL'),
        temperature=0.7,
        streaming=True,  # 关键：启用流式输出
        callbacks=[StreamCallback(queue, node_name)]  # 绑定回调
    )
    return llm



