import ast
import re
import os
import operator as op

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from utils.logger_util import logger

load_dotenv()

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
    temperature=0.0,
    streaming=False,
)

STOP_SEQS = ["\nObservation:", "Observation:"]
# stop 参数，会在生成指定内容前，停止大模型继续生成，把前面已经生成的内容返回
llm_step = llm.bind(stop=STOP_SEQS)

# 2. 定义简单的工具
def get_weather(location):
    """模拟查询天气的工具"""
    return f"{location} 今天天气晴朗，气温 25 度。"

_ALLOWED_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}


def _safe_arith_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_arith_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_arith_eval(node.left), _safe_arith_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_arith_eval(node.operand))
    raise ValueError("仅支持数字与 + - * / ** % 及括号")


def calculate(expression: str) -> str:
    """安全的算术计算工具"""
    try:
        tree = ast.parse(expression, mode="eval")
        value = _safe_arith_eval(tree)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    except Exception as e:
        return f"计算错误: {e}"

tools = {
    "get_weather": get_weather,
    "calculate": calculate
}

REACT_PROMPT = """
你是一个遵循 ReAct（Reason + Act）格式的助理。你可以使用工具获得信息或完成计算。

可用工具（Action）：
- get_weather: 查询天气，Action Input 为城市名称（例如 北京）
- calculate: 计算数学表达式，Action Input 为表达式（例如 3*99）

严格按以下两种之一输出，不要输出其它内容：
1)
Thought: （简短说明下一步）
Action: get_weather 或 calculate
Action Input: （纯输入，不要加引号，不要加多余解释）

2)
Thought: （简短说明已得到答案）
Final Answer: （给用户的最终答案）

当你输出 Action 后，我会把 Observation: ... 追加给你，然后你继续推理。

Question: {question}
"""

def _strip_wrapping_quotes(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and ((t[0] == t[-1] == "\"") or (t[0] == t[-1] == "'")):
        return t[1:-1].strip()
    return t


def _extract_final_answer(text: str) -> str | None:
    """提取最终答案"""
    if "Final Answer:" not in text:
        return None
    return text.rsplit("Final Answer:", 1)[-1].strip() or None


def _extract_last_action(text: str) -> tuple[str, str] | None:
    """提取最后一个 Action 及其输入"""
    actions = re.findall(r"^Action:\s*(.+)\s*$", text, flags=re.MULTILINE)
    inputs = re.findall(r"^Action Input:\s*(.+)\s*$", text, flags=re.MULTILINE)
    if not actions or not inputs:
        return None
    return actions[-1].strip(), _strip_wrapping_quotes(inputs[-1])


def react_agent(question: str) -> str:
    prompt = REACT_PROMPT.format(question=question).rstrip() + "\n"
    logger.info(f"--- 开始解决问题: {question} ---")

    max_steps = 5
    for i in range(max_steps):
        logger.info(f"[Step {i + 1}] 正在思考...")
        response = llm_step.invoke(prompt).content.strip()

        prompt = prompt.rstrip() + "\n" + response.rstrip() + "\n"

        # 提取最终答案
        final_answer = _extract_final_answer(response)
        if final_answer:
            return final_answer

        # 提取最后一个 Action 及其输入
        parsed = _extract_last_action(response)
        if not parsed:
            prompt += "Observation: 解析失败，请严格按 ReAct 格式输出 Action/Action Input 或 Final Answer\n"
            continue

        action_name, action_input = parsed
        # 获取对应工具
        tool = tools.get(action_name)
        if not tool:
            prompt += f"Observation: 错误：找不到工具 {action_name}\n"
            continue

        logger.info(f"--> 执行工具: {action_name}, 输入: {action_input}")
        observation = tool(action_input)
        logger.info(f"--> 工具输出: {observation}")
        prompt += f"Observation: {observation}\n"

    return "达到最大步骤数，未能找到答案。"

if __name__ == "__main__":
    # 测试案例
    question = "北京现在的天气怎么样？如果我在那里买 6 件 99 元的T恤，一共要花多少钱？"
    answer = react_agent(question)
    logger.info(f"\n====== 最终答案 ======\n{answer}")
