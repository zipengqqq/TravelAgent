import os
import uuid

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from graph.workflow import workflow
from utils.logger_util import logger

if __name__ == "__main__":
    uuid = uuid.uuid4().hex
    DB_URI = os.getenv("POSTGRES_URI")
    with ConnectionPool(DB_URI) as pool:
        # 1) 初始化PgSaver
        checkpointer = PostgresSaver(pool)

        # 2) 首次运行，必须执行 setup()，它会自动在库里创建两张表（checkpoints、checkpoint_writes）
        checkpointer.setup()

        app = workflow.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": uuid}}

        # 运行第一轮
        question = "我想逛北京一天，给我制定一个计划，只有两个节点"
        state = {"question": question}
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
        app.update_state(config, {"question": new_question, "response": ""})
        # 传入None，表示延续状态
        for event in app.stream(None, config=config):
            pass
        # 输出最终回答
        final_state = app.get_state(config)
        final_response = final_state.values.get('response', '')
        logger.info(f"问题：{question}")
        logger.info(f"最终回答：{final_response}")