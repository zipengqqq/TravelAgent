from typing import List

from langchain_community.embeddings import HuggingFaceEmbeddings
from psycopg_pool import ConnectionPool

from utils.id_util import id_worker


class MemoryRAG:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        # 使用本地免费模型 BAAI/bge-m3（中文效果好）
        # 首次运行会自动下载模型（约 2.2GB），之后就在本地运行
        self.embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            encode_kwargs={'normalize_embeddings': True}  # 归一化有助于向量相似度计算
        )

    def add_memory(self, user_id: int, text: str):
        """写入一条记忆：文本 -> 向量 -> DB"""
        # 1. 向量化
        vector = self.embeddings.embed_query(text)
        # 2. 生成 ID
        memory_id = id_worker.get_id()
        # 3. 存入 PG
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memory (id, user_id, content, embedding, create_time) VALUES (%s, %s, %s, %s, NOW())",
                    (memory_id, user_id, text, vector)
                )

    def search_memories(self, user_id: int, query: str, top_k=3) -> List[str]:
        """检索相关记忆：Query -> 向量 -> 相似度搜索"""
        query_vector = self.embeddings.embed_query(query)

        results = []
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                # PGVector 的余弦相似度查询 (<=>)
                cur.execute("""
                    SELECT content
                    FROM memory
                    WHERE user_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (user_id, str(query_vector), top_k))

                rows = cur.fetchall()
                results = [row[0] for row in rows]
        return results