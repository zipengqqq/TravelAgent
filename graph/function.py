from graph.config import PlanExecuteState, llm
from graph.prompts import summary_prompt
from utils.parse_llm_json_util import parse_llm_json


def route_by_intent(state: PlanExecuteState):
    route = state.get("route")
    return route if route in {"planner", "direct_answer"} else "planner"


def should_end(state: PlanExecuteState):
    """判断流程是否需要结束"""
    if state.get('response'):
        return True
    else:
        return False

def abstract(content: str):
    """将搜索结果提取为摘要"""
    response = llm.invoke(summary_prompt.format(search_results=content))
    summary = parse_llm_json(response.content).get('summary', '')
    from utils.logger_util import logger
    logger.info(f"搜索结果摘要内容为: {summary}")
    return summary
