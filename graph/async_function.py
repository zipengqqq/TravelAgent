"""
异步辅助函数

包含条件路由、终止判断和搜索结果摘要
"""

from graph.async_config import PlanExecuteState, async_llm
from graph.prompts import summary_prompt
from utils.parse_llm_json_util import parse_llm_json


def async_route_by_intent(state: PlanExecuteState):
    """根据意图路由"""
    route = state.get("route")
    return route if route in {"planner", "direct_answer"} else "planner"


def async_should_end(state: PlanExecuteState):
    """判断流程是否需要结束"""
    if state.get('response'):
        return True
    else:
        return False


async def async_abstract(content: str) -> str:
    """异步将搜索结果提取为摘要"""
    response = await async_llm.ainvoke(summary_prompt.format(search_results=content))
    summary = parse_llm_json(response.content).get('summary', '')
    from utils.logger_util import logger
    logger.info(f"搜索结果摘要内容为: {summary}")
    return summary
