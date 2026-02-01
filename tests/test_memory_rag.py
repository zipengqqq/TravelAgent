"""
MemoryRAG 单元测试
测试记忆添加和检索功能
"""

import os
import unittest
from dotenv import load_dotenv

from graph.memory_rag import memory_rag
from entity.memory_entity import Memory
from utils.db_util import create_session
from utils.logger_util import logger

load_dotenv()


class TestMemoryRAG(unittest.TestCase):
    """MemoryRAG 测试类"""

    def setUp(self):
        """每个测试前执行"""
        self.test_user_id = 999
        # self._clear_user_memories()

    # def tearDown(self):
    #     """每个测试后执行"""
    #     self._clear_user_memories()

    def _clear_user_memories(self):
        """清空测试用户的记忆"""
        with create_session() as session:
            session.query(Memory).filter(
                Memory.user_id == self.test_user_id
            ).delete()
        logger.info(f"已清空用户 {self.test_user_id} 的记忆")

    def test_add_memory(self):
        """测试添加记忆"""
        logger.info("\n" + "=" * 50)
        logger.info("测试添加记忆")
        logger.info("=" * 50)

        text = "我喜欢去海边旅行，特别是三亚"

        # 执行添加
        memory_rag.add_memory(self.test_user_id, text)

        # 验证数据库中的记录
        with create_session() as session:
            record = session.query(Memory).filter(
                Memory.user_id == self.test_user_id
            ).first()
            self.assertIsNotNone(record, "数据库中应该存在记录")
            self.assertEqual(record.content, text, "内容应该一致")
            self.assertIsNotNone(record.embedding, "向量嵌入不应该为空")
            logger.info(f"数据库记录: content={record.content[:50]}..., embedding维度={len(record.embedding)}")

    def test_search(self):
        """测试搜索记忆"""
        logger.info("\n" + "=" * 50)
        logger.info("测试搜索记忆")
        logger.info("=" * 50)

        # 先添加几条记忆
        memories = [
            "我喜欢吃辣的菜",
            "预算中等，喜欢爬山",
            "去北京旅行，推荐故宫和颐和园"
        ]

        for mem in memories:
            memory_rag.add_memory(self.test_user_id, mem)

        # 测试搜索
        results = memory_rag.search_memories(self.test_user_id, "喜欢什么", top_k=10)
        logger.info(f"搜索结果: {results}")

        self.assertGreater(len(results), 0, "应该搜索到相关记忆")
        logger.info(f"搜索到 {len(results)} 条记忆")

    def test_search_relevant(self):
        """测试搜索相关性"""
        logger.info("\n" + "=" * 50)
        logger.info("测试搜索相关性")
        logger.info("=" * 50)

        # 添加不同主题的记忆
        memories = [
            "我喜欢吃川菜，特别是麻婆豆腐",
            "预算2000元，想住经济型酒店",
            "推荐一些成都的景点",
            "我不喜欢吃甜食"
        ]

        for mem in memories:
            memory_rag.add_memory(self.test_user_id, mem)

        # 搜索美食相关
        results = memory_rag.search_memories(self.test_user_id, "推荐美食", top_k=3)
        logger.info(f"搜索'推荐美食'的结果: {results}")

        # 验证结果与查询相关
        self.assertGreater(len(results), 0, "应该搜索到美食相关的记忆")


if __name__ == '__main__':
    unittest.main()
