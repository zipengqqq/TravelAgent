"""
异步工作流定义

使用异步节点构建 LangGraph StateGraph
"""

from langgraph.graph import END, StateGraph, START

from graph.async_config import PlanExecuteState
from graph.async_function import async_route_by_intent, async_should_end
from graph.async_nodes import (
    async_router_node,
    async_planner_node,
    async_executor_node,
    async_direct_answer_node,
    async_reflect_node,
    async_memory_retrieve_node,
    async_memory_save_node
)

# 创建异步工作流
async_workflow = StateGraph(PlanExecuteState)

# 添加所有异步节点
async_workflow.add_node("router", async_router_node)
async_workflow.add_node("planner", async_planner_node)
async_workflow.add_node("executor", async_executor_node)
async_workflow.add_node("reflect", async_reflect_node)
async_workflow.add_node("direct_answer", async_direct_answer_node)
async_workflow.add_node("memory_retrieve", async_memory_retrieve_node)
async_workflow.add_node("memory_save", async_memory_save_node)

# 设置入口点
async_workflow.add_edge(START, "memory_retrieve")

# 记忆检索 -> 路由
async_workflow.add_edge("memory_retrieve", "router")

# 路由条件分支
async_workflow.add_conditional_edges(
    "router",  # 路由节点执行完，进行判断
    async_route_by_intent,  # 判断函数
    {
        "planner": "planner",  # 函数的返回值是planner，则下一个节点是planner
        "direct_answer": "direct_answer"
    }
)

# direct_answer 流程
async_workflow.add_edge("direct_answer", "memory_save")
async_workflow.add_edge("memory_save", END)

# planner 流程
async_workflow.add_edge("planner", "executor")  # 规划 -> 执行者
async_workflow.add_edge("executor", "reflect")  # 执行者 -> 反思

# 反思条件分支
async_workflow.add_conditional_edges(
    "reflect",  # 从反思节点出来
    async_should_end,  # 判断是否结束
    {
        True: "memory_save",  # 如果返回 True，流程结束
        False: "executor"  # 如果返回 False，继续执行
    }
)

async_workflow.add_edge("memory_save", END)

# 编译异步工作流
compiled_async_workflow = async_workflow.compile()
