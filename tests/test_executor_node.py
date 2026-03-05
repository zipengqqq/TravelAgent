"""
直接调用 async_executor_node 测试
"""
import asyncio
import sys
sys.path.insert(0, '/Users/penn/work/TravelAgent')

from graph.async_config import PlanExecuteState
from graph.async_nodes import async_executor_node
from graph.stream_callback import set_stream_queue


async def main():
    # 创建队列并设置
    queue = asyncio.Queue()
    set_stream_queue(queue)

    # 构造输入状态
    state: PlanExecuteState = {
        "question": "北京今天天气怎么样？",
        # "plan": ["从北京市天安门到上海外滩怎么走？"],
        "plan": ["我在郑州中原区国弘时代广场，离我家有多远，我家在中原区东史马小区"],
        "past_steps": [],
        "response": "",
        "route": "planner",
        "messages": [],
        "user_id": 1,
        "memories": [],
        "approved": False,
        "cancelled": False,
    }

    print("开始调用 async_executor_node...")
    result = await async_executor_node(state)
    print("执行结果:", result)


if __name__ == "__main__":
    asyncio.run(main())
