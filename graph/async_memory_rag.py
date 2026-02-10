"""
异步记忆 RAG（检索增强生成）

使用 ThreadPoolExecutor 包装 HuggingFaceEmbeddings（无原生异步支持）
使用异步数据库会话进行读写操作
"""

import asyncio
import datetime
import platform
from concurrent.futures import ThreadPoolExecutor
from typing import List

from langchain_huggingface import HuggingFaceEmbeddings

from pojo.entity.memory_entity import Memory
from utils.async_db_util import create_async_session
from utils.id_util import id_worker
from utils.logger_util import logger


class AsyncMemoryRAG:
    """异步记忆 RAG 类"""

    def __init__(self):
        # 使用本地免费模型 BAAI/bge-m3（中文效果好）
        # 首次运行会自动下载模型（约 2.2GB），之后就在本地运行

        # 自动检测系统并选择合适的设备
        system = platform.system()
        if system == "Darwin":
            # macOS (Apple Silicon) 使用 MPS (Metal Performance Shaders)
            device = "mps"
            logger.info("检测到 macOS，使用 MPS 加速")
        else:
            # Windows/Linux 使用 CUDA (如果有 NVIDIA GPU)，否则使用 CPU
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"检测到 {system}，使用 {'CUDA' if device == 'cuda' else 'CPU'}")
            except ImportError:
                device = "cpu"
                logger.info(f"检测到 {system}，使用 CPU")

        logger.info(f"初始化 AsyncMemoryRAG，使用 BAAI/bge-m3 嵌入模型 (设备: {device})")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="models/BAAI/bge-m3",  # 使用本地模型路径
            model_kwargs={'device': device},
            encode_kwargs={'normalize_embeddings': True}  # 归一化有助于向量相似度计算
        )
        # 线程池用于执行同步的嵌入操作
        self.executor = ThreadPoolExecutor(max_workers=2)

    def _embed_query_sync(self, text: str) -> List[float]:
        """同步执行向量嵌入"""
        return self.embeddings.embed_query(text)

    async def _embed_query(self, text: str) -> List[float]:
        """异步包装向量嵌入"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._embed_query_sync, text)

    async def add_memory(self, user_id: int, text: str):
        """异步写入一条记忆：文本 -> 向量 -> DB"""
        logger.info(f"为用户 {user_id} 添加记忆: {text[:50]}...")

        # 1. 异步向量化
        vector = await self._embed_query(text)

        # 2. 生成 ID
        memory_id = id_worker.get_id()

        # 3. 异步存入 PG
        async with create_async_session() as session:
            record = Memory(
                id=memory_id,
                user_id=user_id,
                content=text,
                embedding=vector,
                create_time=datetime.datetime.now()
            )
            session.add(record)

        logger.info(f"记忆已保存，ID: {memory_id}")

    async def search_memories(self, user_id: int, query: str, top_k=3) -> List[str]:
        """异步检索相关记忆：Query -> 向量 -> 相似度搜索"""
        logger.info(f"为用户 {user_id} 搜索记忆，查询: {query[:50]}..., top_k={top_k}")

        # 1. 异步向量化查询
        query_vector = await self._embed_query(query)

        results = []
        async with create_async_session() as session:
            # 使用原生 SQL 执行 pgvector 查询
            from sqlalchemy import text

            # PostgreSQL pgvector 使用方括号格式，直接使用 Python 列表字符串
            query_vector_str = str(query_vector)

            # 构建动态 SQL（因为 asyncpg 对 ::vector 转换处理有问题）
            # 使用字符串拼接处理向量转换
            sql = f"""
                SELECT content
                FROM memory
                WHERE user_id = :user_id
                ORDER BY embedding <=> '{query_vector_str}'::vector
                LIMIT :limit
            """

            result = await session.execute(
                text(sql),
                {
                    "user_id": user_id,
                    "limit": top_k
                }
            )
            rows = result.fetchall()
            results = [row[0] for row in rows]

        logger.info(f"搜索完成，找到 {len(results)} 条相关记忆")
        return results

    async def close(self):
        """清理资源"""
        self.executor.shutdown(wait=True)


# 全局异步实例
async_memory_rag = AsyncMemoryRAG()
