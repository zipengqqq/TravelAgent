from typing import List
import os

from langchain_huggingface import HuggingFaceEmbeddings

from utils.db_util import create_session
from utils.id_util import id_worker
from utils.logger_util import logger
from entity.memory_entity import Memory


class MemoryRAG:
    def __init__(self):
        # 使用本地免费模型 BAAI/bge-m3（中文效果好）
        # 首次运行会自动下载模型（约 2.2GB），之后就在本地运行
        logger.info("初始化 MemoryRAG，使用 BAAI/bge-m3 嵌入模型 (GPU)")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="models/BAAI/bge-m3",  # 使用本地模型路径
            model_kwargs={'device': 'cuda'},  # 使用 GPU
            encode_kwargs={'normalize_embeddings': True}  # 归一化有助于向量相似度计算
        )

    def add_memory(self, user_id: int, text: str):
        """写入一条记忆：文本 -> 向量 -> DB"""
        logger.info(f"为用户 {user_id} 添加记忆: {text[:50]}...")
        # 1. 向量化
        vector = self.embeddings.embed_query(text)
        # 2. 生成 ID
        memory_id = id_worker.get_id()
        # 3. 存入 PG
        with create_session() as session:
            record = Memory(
                id=memory_id,
                user_id=user_id,
                content=text,
                embedding=vector
            )
            session.add(record)
        logger.info(f"记忆已保存，ID: {memory_id}")


    def search_memories(self, user_id: int, query: str, top_k=3) -> List[str]:
        """检索相关记忆：Query -> 向量 -> 相似度搜索"""
        logger.info(f"为用户 {user_id} 搜索记忆，查询: {query[:50]}..., top_k={top_k}")
        query_vector = self.embeddings.embed_query(query)

        results = []
        with create_session() as session:
            # 使用原始连接执行 pgvector 查询（避免 SQLAlchemy 占位符冲突）
            conn = session.connection()
            cur = conn.connection.cursor()
            cur.execute("""
                SELECT content
                FROM memory
                WHERE user_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (user_id, str(query_vector), top_k))
            rows = cur.fetchall()
            results = [row[0] for row in rows]
        logger.info(f"搜索完成，找到 {len(results)} 条相关记忆")
        return results


# 全局实例
memory_rag = MemoryRAG()
