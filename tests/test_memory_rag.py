import os
import unittest
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from graph.memory_rag import MemoryRAG, memory_rag

"""测试类初始化"""

class TestMemoryRAG(unittest.TestCase):
    """MemoryRAG 测试类"""

    def test_add_memory(self):
        """测试添加记忆"""
        text = "我喜欢去海边旅行，特别是三亚"

        # 执行添加
        self.memory_rag.add_memory(999, text)

        # 验证数据库中的记录
        with self.memory_rag.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content, user_id FROM memory WHERE user_id = %s",
                    (self.test_user_id,)
                )
                row = cur.fetchone()
                print(f"数据库记录: content={row[0]}, user_id={row[1]}")


    def test_search(self):
        results = memory_rag.search_memories(999, "旅行", top_k=10)
        print(results)


if __name__ == '__main__':
    unittest.main()
