"""
长期记忆集成测试
测试场景：验证对话历史检索、偏好记忆、规划场景等
"""

import os
import unittest
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

from graph.workflow import workflow
from graph.memory_rag import memory_rag
from utils.logger_util import logger

load_dotenv()


class TestLongMemoryIntegration(unittest.TestCase):
    """长期记忆集成测试"""

    def setUp(self):
        """每个测试前执行"""
        self.thread_id = 'test_long_memory'
        self.user_id = 999
        self.DB_URI = os.getenv("POSTGRES_URI")
        self.pool = ConnectionPool(self.DB_URI, kwargs={"autocommit": True})

        # 初始化 checkpointer
        self.checkpointer = PostgresSaver(self.pool)
        self.checkpointer.setup()

        self.app = workflow.compile(checkpointer=self.checkpointer)
        self.config = {"configurable": {"thread_id": self.thread_id}}

        # 清空用户历史记忆
        # self._clear_user_memories()

    # def tearDown(self):
    #     """每个测试后执行"""
    #     # 清空用户历史记忆
    #     self._clear_user_memories()

    def _clear_user_memories(self):
        """清空测试用户的记忆"""
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memory WHERE user_id = %s", (self.user_id,))
                conn.commit()
        logger.info(f"已清空用户 {self.user_id} 的记忆")

    def _run_round(self, question: str) -> str:
        """执行一轮对话"""
        state = {
            "question": question,
            "plan": [],
            "past_steps": [],
            "response": "",
            "route": "",
            "messages": [],
            "user_id": self.user_id,
            "memories": []
        }

        for event in self.app.stream(state, config=self.config):
            pass

        final_state = self.app.get_state(self.config)
        return final_state.values.get("response", "")

    def test_preference_memory(self):
        """测试 1: 偏好记忆 - 用户表达偏好后，后续对话能体现"""
        logger.info("\n" + "=" * 60)
        logger.info("测试 1: 偏好记忆")
        logger.info("=" * 60)

        # 第一轮：表达偏好
        question1 = "我喜欢吃辣的菜，预算中等，喜欢爬山"
        logger.info(f"问题：{question1}")
        response1 = self._run_round(question1)
        logger.info(f"回答：{response1[:100]}...")

        # 第二轮：基于偏好的推荐
        question2 = "推荐一些成都的美食"
        logger.info(f"\n问题：{question2}")
        response2 = self._run_round(question2)
        logger.info(f"回答：{response2}")


    def test_preference_memory_2(self):
        """测试 2: 偏好记忆 - 用户表达偏好后，后续对话能体现"""
        logger.info("\n" + "=" * 60)
        logger.info("测试 2: 偏好记忆")
        logger.info("=" * 60)

        # 第一轮：表达偏好
        question1 = "不知道晚上吃什么了"
        logger.info(f"问题：{question1}")
        response1 = self._run_round(question1)
        logger.info(f"回答：{response1}...")


    def test_planning_with_memory(self):
        """测试 2: 规划场景 - 规划时考虑历史记忆"""
        logger.info("\n" + "=" * 60)
        logger.info("测试 2: 规划场景")
        logger.info("=" * 60)

        question = "规划去成都三天行程"
        logger.info(f"\n问题：{question}")
        response = self._run_round(question)
        logger.info(f"回答：{response}")


if __name__ == '__main__':
    unittest.main()
