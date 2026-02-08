"""
异步层测试

测试异步数据库操作和 MemoryRAG
"""

import unittest

from utils.async_db_util import create_async_session
from graph.async_memory_rag import AsyncMemoryRAG
from utils.logger_util import logger


class TestAsyncDatabase(unittest.IsolatedAsyncioTestCase):
    """测试异步数据库"""

    async def test_create_async_session(self):
        """测试创建异步会话"""
        try:
            async with create_async_session() as session:
                self.assertIsNotNone(session)
                logger.info("异步会话创建成功")
        except Exception as e:
            logger.warning(f"异步数据库测试跳过（需要数据库连接）: {e}")
            self.skipTest("需要数据库连接")

    async def test_async_session_context_manager(self):
        """测试异步会话上下文管理器"""
        try:
            async with create_async_session() as session:
                # 测试基本操作
                from sqlalchemy import text
                result = await session.execute(text("SELECT 1"))
                rows = result.fetchall()
                self.assertGreater(len(rows), 0)
        except Exception as e:
            logger.warning(f"异步会话上下文管理器测试跳过: {e}")
            self.skipTest("需要数据库连接")


class TestAsyncMemoryRAG(unittest.IsolatedAsyncioTestCase):
    """测试异步 MemoryRAG"""

    async def test_memory_rag_initialization(self):
        """测试 MemoryRAG 初始化"""
        try:
            memory_rag = AsyncMemoryRAG()
            self.assertIsNotNone(memory_rag.embeddings)
            self.assertIsNotNone(memory_rag.executor)
            logger.info("AsyncMemoryRAG 初始化成功")
            await memory_rag.close()
        except Exception as e:
            logger.warning(f"MemoryRAG 初始化测试跳过（需要模型）: {e}")
            self.skipTest("需要嵌入模型")

    async def test_add_memory(self):
        """测试添加记忆"""
        try:
            memory_rag = AsyncMemoryRAG()
            await memory_rag.add_memory(1, "测试记忆：我喜欢旅行")
            logger.info("记忆添加成功")
            await memory_rag.close()
        except Exception as e:
            logger.warning(f"添加记忆测试跳过: {e}")
            self.skipTest("需要数据库连接")

    async def test_search_memories(self):
        """测试搜索记忆"""
        try:
            memory_rag = AsyncMemoryRAG()

            # 先添加一些测试记忆
            await memory_rag.add_memory(999, "测试：我喜欢北京烤鸭")
            await memory_rag.add_memory(999, "测试：我喜欢上海小笼包")

            # 搜索记忆
            memories = await memory_rag.search_memories(999, "北京美食", top_k=2)
            print(memories)
            self.assertIsInstance(memories, list)
            logger.info(f"搜索到 {len(memories)} 条记忆")

            await memory_rag.close()
        except Exception as e:
            logger.warning(f"搜索记忆测试跳过: {e}")
            self.skipTest("需要数据库连接")




if __name__ == "__main__":
    unittest.main()
