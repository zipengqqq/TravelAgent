from langgraph.graph import END, StateGraph, START

from graph.config import PlanExecuteState
from graph.function import route_by_intent, should_end
from graph.nodes import router_node, planner_node, executor_node, direct_answer_node, reflect_node, \
    memory_retrieve_node, memory_save_node

workflow = StateGraph(PlanExecuteState)

workflow.add_node("router", router_node)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("reflect", reflect_node)
workflow.add_node("direct_answer", direct_answer_node)
workflow.add_node("memory_retrieve", memory_retrieve_node)
workflow.add_node("memory_save", memory_save_node)

workflow.add_edge(START, "memory_retrieve")
workflow.add_edge("memory_retrieve", "router")
workflow.add_conditional_edges(
    "router", # 路由节点执行完，进行判断
    route_by_intent, # 判断函数
    {
        "planner": "planner", # 函数的返回值是planner，则下一个节点是planner
        "direct_answer": "direct_answer"
    }
)

# direct_answer流程
workflow.add_edge("direct_answer", "memory_save")
workflow.add_edge("memory_save", END)

# planner流程
workflow.add_edge("planner", "executor")  # 规划 -> 执行者
workflow.add_edge("executor", "reflect")  # 执行者 -> 反思

# 添加条件分支
workflow.add_conditional_edges(
    "reflect",  # 从反思节点出来
    should_end,  # 判断是否结束
    {
        True: "memory_save",  # 如果返回 True，流程结束
        False: "executor"  # 如果返回 False，继续执行
    }
)

workflow.add_edge("memory_save", END)