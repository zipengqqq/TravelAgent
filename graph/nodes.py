import json

from entity.user_profiles_entity import UserProfile
from graph.config import PlanExecuteState, tavily_tool, Response, Plan
from graph.config import llm
from graph.function import abstract
from graph.prompts import route_prompt, direct_answer_prompt, planner_prompt, search_query_prompt, reflect_prompt, \
    profile_prompt
from utils.db_util import create_session
from utils.logger_util import logger
from utils.parse_llm_json_util import parse_llm_json

OLD_PROFILE_NULL_MSG = "当前还未生成用户画像"

def router_node(state: PlanExecuteState):
    """路由节点：判断意图"""
    logger.info("🚀路由师正在判断意图")
    question = state["question"]

    prompt = route_prompt.format(user_request=question)
    router_llm = llm.bind(temperature=0.0)
    raw = router_llm.invoke(prompt)
    try:
        data = parse_llm_json(raw.content)
        route = str(data.get("route", "")).strip()
    except Exception as e:
        logger.error(f"路由解析失败：{e}")
        route = ""

    if route not in {"planner", "direct_answer"}:
        logger.info(f"路由结果无效，默认走 direct_answer: {route}")
        route = "direct_answer"

    logger.info(f"用户意图：{route}")
    return {"route": route}


def direct_answer_node(state: PlanExecuteState):
    """直接回答：无需工具"""
    logger.info("🚀直接回答中")
    question = state["question"]

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = direct_answer_prompt.format(user_request=question, messages=messages)
    raw = llm.invoke(prompt)
    return {"response": raw.content, "messages": [("user", question), ("assistant", raw.content)]}


def planner_node(state: PlanExecuteState):
    """接收用户问题，生成初始计划"""
    logger.info("🚀规划师正在规划任务")
    question = state["question"]

    # 格式化对话历史
    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = planner_prompt.format(user_request=question, messages=messages)

    raw = llm.invoke(prompt)
    try:
        data = parse_llm_json(raw.content)
        parsed = Plan.model_validate(data)
        steps = parsed.steps
        logger.info(f"规划结果：{steps}")
    except Exception as e:
        logger.error(f"规划解析失败：{e}")
        steps = []
    logger.info(f"共有 {len(steps)} 个步骤")
    return {"plan": steps}


def executor_node(state: PlanExecuteState):
    """执行者：取出计划中的第一个任务"""
    plan = state['plan']
    if not plan:
        logger.error("计划为空")
        return {"past_steps": [], "response": ""}
    task = plan[0]

    logger.info(f"🚀执行者正在执行任务：{task}")

    # 1) 生成搜索关键词
    search_query_prompt_text = search_query_prompt.format(task=task)
    keywords_text = llm.invoke(search_query_prompt_text)
    search_query = keywords_text.content.strip()
    logger.info(f"搜索关键词：{search_query}")

    # 2）调用 Tavily工具
    try:
        search_result = tavily_tool.invoke(search_query)
        result_str = json.dumps(search_result, ensure_ascii=False)
    except Exception as e:
        logger.error(f"搜索失败：{e}")
        return {"response": f"搜索失败：{e}"}
    logger.info(f"搜索结果长度为：{len(result_str)}")

    # 3）提取摘要
    result_str = abstract(result_str)
    logger.info(f"摘要长度为: {len(result_str)}")

    return {
        "past_steps": [(task, result_str)],
        "plan": plan[1:] # 剔除第一个任务
    }


def reflect_node(state: PlanExecuteState):
    """重新规划器：根据执行结果，判断是否需要重新规划"""
    logger.info(f"🚀反思节点正在判断是否需要重新规划")
    past_steps_str = ""
    for step, result in state['past_steps']:
        past_steps_str += f"已完成步骤：{step}\n执行结果：{result}\n"

    current_plan_str = "\n".join(state['plan'])

    prompt = reflect_prompt.format(
        question=state['question'],
        past_steps=past_steps_str,
        current_plan=current_plan_str,
    )

    raw = llm.invoke(prompt)
    try:
        data = parse_llm_json(raw.content)
        logger.info(f"大模型结果为：{data}")
        result = Response.model_validate(data)
    except Exception as e:
        logger.error(f"反思节点解析失败：{e}")
        result = Response(response="", next_plan=[])

    if result.response and result.response.strip() != "":
        logger.info("任务完成，生成最终回答。")
        return {"response": result.response, "plan": [], "messages": [("user", state['question']), ("assistant", result.response)]}
    else:
        logger.info(f"反思节点决策：继续执行，剩余计划：{len(result.next_plan)}个步骤")
        logger.info(f"剩余计划：{result.next_plan}")
        return {"plan": result.next_plan}

def profile_node(state: PlanExecuteState):
    """用户画像节点：根据用户问题，生成用户画像"""
    logger.info("🚀用户画像节点正在生成用户画像")

    # 1) 获取旧画像
    old_profile = None
    with create_session() as session:
        record = session.query(UserProfile).filter(
            UserProfile.user_id == state["user_id"]
        ).first()
        if record:
            old_profile = record.profiles
            logger.info(f"用户旧画像：{old_profile}")
    if not old_profile:
        old_profile = OLD_PROFILE_NULL_MSG

    # 2) 生成新画像
    try:
        conversation = f"用户问题：{state['question']}\nAI回答：{state.get('response', '')}"
        prompt = profile_prompt.format(
            old_profile=old_profile,
            conversation_text=conversation,
        )
        response = llm.invoke(prompt)
        data = parse_llm_json(response.content)
        logger.info(f"用户画像节点生成用户画像：{data}")

        # 3) 保存新画像
        with create_session() as session:
            if old_profile == OLD_PROFILE_NULL_MSG:
                # 第一次生成画像
                record = UserProfile(
                    user_id=state["user_id"],
                    profiles=data,
                )
                session.add(record)
            else:
                # 更新用户画像
                session.query(UserProfile).filter(
                    UserProfile.user_id == state["user_id"]
                ).update({"profiles": data})
    except Exception as e:
        logger.error(f"用户画像节点保存用户画像失败：{e}")


