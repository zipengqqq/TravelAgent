"""
LangGraph 人机交互示例
展示如何在 LangGraph 工作流中实现人类参与（Human-in-the-Loop）
支持在节点处暂停等待用户确认或输入
"""

from typing import TypedDict, Literal

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command


# ============ 状态定义 ============
class AgentState(TypedDict):
    """智能体状态"""
    messages: list
    plan: list | None
    current_step: int
    user_input: str | None
    approved: bool | None


# ============ 异步节点函数 ============
async def planner_node(state: AgentState):
    """规划节点 - 生成执行计划"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if isinstance(last_message, HumanMessage):
        question = last_message.content

        # 模拟旅行规划
        if "旅行" in question or "旅游" in question:
            plan = [
                {"step": 1, "action": "搜索目的地信息", "status": "pending"},
                {"step": 2, "action": "查找交通方式", "status": "pending"},
                {"step": 3, "action": "推荐酒店", "status": "pending"},
                {"step": 4, "action": "制定行程安排", "status": "pending"},
            ]
        else:
            plan = [
                {"step": 1, "action": "理解问题", "status": "pending"},
                {"step": 2, "action": "搜索相关信息", "status": "pending"},
                {"step": 3, "action": "生成回答", "status": "pending"},
            ]

        return {
            "plan": plan,
            "current_step": 0,
            "approved": None,
            "user_input": None
        }

    return {}


async def human_review_node(state: AgentState):
    """人机交互节点 - 等待用户审核/修改

    使用 interrupt() 实现真正的节点内部中断
    """
    plan = state.get("plan", [])

    # 构建展示给用户的计划信息
    plan_summary = "请审核以下计划：\n\n"
    for item in plan:
        plan_summary += f"步骤 {item['step']}: {item['action']} (状态: {item['status']})\n"

    plan_summary += "\n请点击「批准」继续执行，或点击「修改」调整计划。"

    # 使用 interrupt 实现真正的中断
    # interrupt入参会在抛出异常时，显示，result是用户批准后返回的数据
    result = interrupt({
        "type": "human_review",
        "plan": plan,
        "message": plan_summary
    })

    # 处理中断返回的结果
    approved = result.get("approved") if result else None
    user_input = result.get("user_input") if result else None

    if approved is False:
        # 用户修改了计划，返回审核节点重新显示
        return Command(
            goto="human_review",
            update={
                "messages": state["messages"] + [AIMessage(content=plan_summary)],
                "approved": None,  # 重置为 None，重新进入审核
                "user_input": "modified"
            }
        )
    else:
        # 用户批准了，去执行器
        return {
            "messages": state["messages"] + [AIMessage(content=plan_summary)],
            "approved": approved,
            "user_input": user_input,
        }


async def executor_node(state: AgentState):
    """执行节点 - 一次性执行所有计划步骤"""
    plan = state.get("plan", [])

    # 一次性执行所有步骤
    for item in plan:
        item["status"] = "completed"
        item["result"] = f"已完成: {item['action']}"

    return {
        "plan": plan,
        "current_step": len(plan)
    }


async def final_response_node(state: AgentState):
    """最终响应节点 - 生成最终回答"""
    plan = state.get("plan", [])

    # 汇总执行结果
    summary = "计划执行完成！以下是执行结果：\n\n"
    for item in plan:
        summary += f"✅ 步骤 {item['step']}: {item['action']}\n"
        if "result" in item:
            summary += f"   结果: {item['result']}\n"

    return {
        "messages": state["messages"] + [AIMessage(content=summary)]
    }


def should_continue(state: AgentState) -> Literal["executor", "human_review", "end"]:
    """路由函数 - 决定下一步"""
    approved = state.get("approved")

    # 首次进入（approved 为 None），先去 human_review 让用户审核
    if approved is None:
        return "human_review"

    # 用户未批准，返回审核节点
    if approved is False:
        return "human_review"

    # 用户已批准，去 executor 执行所有步骤
    return "executor"


def should_skip_planner(state: AgentState) -> Literal["continue_execution", "planner"]:
    """检查是否需要跳过 planner（当已有 plan 时）"""
    if state.get("plan") is not None:
        return "continue_execution"
    return "planner"


def should_stop(state: AgentState) -> Literal["executor", "end"]:
    """检查是否需要继续执行"""
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if current_step < len(plan):
        return "executor"
    else:
        return "end"


# ============ 构建工作流 ============
# 内存检查点存储
checkpointer = MemorySaver()


def create_human_loop_graph():
    """创建人机交互工作流"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("final_response", final_response_node)

    # 设置入口点
    workflow.set_entry_point("planner")

    # 添加条件边 - 从 planner 出来
    workflow.add_conditional_edges(
        "planner",
        should_continue,
        {
            "human_review": "human_review",
            "executor": "executor",
            "end": END
        }
    )

    # 执行器执行完后直接到最终响应节点
    workflow.add_edge("executor", "final_response")

    # 人机审核节点后继续执行器（用户批准后）
    workflow.add_edge("human_review", "executor")
    workflow.add_edge("final_response", END)

    # 编译时添加检查点
    return workflow.compile(checkpointer=checkpointer)


# 全局工作流实例
graph = create_human_loop_graph()


# ============ 测试运行 ============
if __name__ == "__main__":
    import asyncio

    async def test():
        initial_state = {
            "messages": [HumanMessage(content="我想去日本旅行一周")],
            "plan": None,
            "current_step": 0,
            "user_input": None,
            "approved": None
        }

        config = {"configurable": {"thread_id": "test-thread"}}

        print("=== 初始状态 ===")
        try:
            async for event in graph.astream(initial_state, config, stream_mode="values"):
                print("Event keys:", event.keys() if hasattr(event, 'keys') else event)
        except Exception as e:
            print("Error:", type(e).__name__, str(e))

    asyncio.run(test())
