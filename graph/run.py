import os
import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from graph.workflow import workflow
from utils.logger_util import logger

if __name__ == "__main__":
    thread_id = '1'
    DB_URI = os.getenv("POSTGRES_URI")
    with ConnectionPool(DB_URI, kwargs={"autocommit": True}) as pool:
        # 1) 初始化PgSaver
        checkpointer = PostgresSaver(pool)

        # 2) 首次运行，必须执行 setup()，它会自动在库里创建两张表（checkpoints、checkpoint_writes）
        checkpointer.setup()

        app = workflow.compile(checkpointer=checkpointer)

        # thread_id 不变即可从数据库续上同一会话的状态（短期记忆）
        config = {"configurable": {"thread_id": thread_id}}

        # 运行第一轮
        question = "我想逛北京一天，给我制定一个计划，只有两个节点"
        # 首轮补齐字段；messages 作为对话历史
        state = {
            "question": question,
            "plan": [],
            "past_steps": [],
            "response": "",
            "route": "",
            "messages": [],
            "user_id": 1,
            "memories": []
        }
        logger.info("第一轮运行开始")
        for event in app.stream(state, config=config):
            pass
        # 输出最终回答
        final_state = app.get_state(config)
        final_response = final_state.values.get('response', '')
        logger.info(f"问题：{question}")
        logger.info(f"最终回答：{final_response}")

        # # 运行第二轮（测试记忆）
        logger.info("第二轮运行开始")
        new_question = "刚才提到了哪些美食"

        new_state = {
            "question": new_question,
            "plan": [],
            "past_steps": [],
            "response": "",
            "route": "",
            "user_id": 1,
            "memories": []
        }

        # 新问题从 START 节点重新跑
        for event in app.stream(new_state, config=config):
            pass

        # 输出最终回答
        final_state = app.get_state(config)
        final_response = final_state.values.get("response", "")
        logger.info(f"问题：{new_question}")
        logger.info(f"最终回答：{final_response}")