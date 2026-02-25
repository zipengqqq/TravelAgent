"""
LangGraph 人机交互示例 - 使用 Command 模式
展示如何使用 Command 替代 interrupt 实现人机交互
"""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel


# ============ 状态定义 ============
class AgentState(TypedDict):
    """智能体状态"""
    messages: list
    plan: list | None
    current_step: int
    user_input: str | None
    approved: bool | None


# ============ 节点函数 ============
def planner_node(state: AgentState):
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


def human_review_node(state: AgentState) -> Command:
    """人机交互节点 - 等待用户审核/修改

    使用 interrupt() 实现中断，返回 Command 继续执行
    """
    plan = state.get("plan", [])

    # 构建展示给用户的计划信息
    plan_summary = "请审核以下计划：\n\n"
    for item in plan:
        plan_summary += f"步骤 {item['step']}: {item['action']} (状态: {item['status']})\n"

    plan_summary += "\n请点击「批准」继续执行，或点击「修改」调整计划。"

    # 使用 interrupt 实现中断，暂停工作流
    # 返回 Command 用于恢复执行（用户批准后调用）
    result = interrupt({
        "type": "human_review",
        "plan": plan,
        "message": plan_summary
    })

    # 当用户调用 update_state 恢复后，这里会收到结果
    # 使用 Command 继续执行
    return Command(
        goto="executor",
        update={
            "messages": state["messages"] + [AIMessage(content=plan_summary)],
            "approved": result.get("approved"),
            "user_input": result.get("user_input"),
        }
    )


def executor_node(state: AgentState) -> Command:
    """执行节点 - 执行计划中的步骤

    使用 interrupt() 在每个步骤执行后等待用户审核
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if current_step < len(plan):
        # 执行当前步骤
        plan[current_step]["status"] = "completed"
        plan[current_step]["result"] = f"已完成: {plan[current_step]['action']}"

        # 使用 interrupt 暂停，等待用户审批
        result = interrupt({
            "type": "step_approval",
            "current_step": current_step,
            "step_info": plan[current_step],
            "total_steps": len(plan)
        })

        # 用户批准后继续
        next_step = current_step + 1

        # 检查是否还有步骤未完成
        if next_step < len(plan):
            return Command(
                goto="executor",  # 继续执行下一个步骤
                update={
                    "plan": plan,
                    "current_step": next_step,
                    "approved": result.get("approved") if result else True
                }
            )
        else:
            return Command(
                goto="final_response",
                update={
                    "plan": plan,
                    "current_step": next_step,
                    "approved": result.get("approved") if result else True
                }
            )

    # 没有更多步骤，结束
    return Command(goto="final_response")


def final_response_node(state: AgentState):
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

    # 用户未批准，返回审核节点
    if approved is False:
        return "human_review"

    # 用户已批准（或首次进入），检查是否还有步骤未完成
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if current_step < len(plan):
        return "executor"
    else:
        return "end"


# ============ 构建工作流 ============
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

    # 人机审核节点后继续执行器（用户批准后）
    workflow.add_edge("human_review", "executor")

    # 从执行器出来 - 循环执行或结束（通过 Command 控制）
    workflow.add_edge("final_response", END)

    # 编译时添加检查点
    return workflow.compile(checkpointer=checkpointer)


# 全局工作流实例
graph = create_human_loop_graph()


# ============ 测试运行 ============
if __name__ == "__main__":
    import uuid

    # 测试工作流
    initial_state = {
        "messages": [HumanMessage(content="我想去日本旅行一周")],
        "plan": None,
        "current_step": 0,
        "user_input": None,
        "approved": None
    }

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    print("=== 初始状态 ===")
    result = graph.invoke(initial_state, config)
    print("Result keys:", result.keys() if hasattr(result, 'keys') else result)
