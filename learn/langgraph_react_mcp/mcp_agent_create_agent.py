"""
LangGraph create_agent + MCP 集成示例

使用 langchain.agents.create_agent + MCP 工具
通过工具结果字符串转换解决 DeepSeek 兼容性问题

依赖:
    pip install langchain-mcp-adapters langgraph

运行:
    cd learn/langgraph_react_mcp
    python mcp_agent_create_agent.py
"""

import asyncio
import json
import os
from functools import wraps
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import load_mcp_tools
from langchain_mcp_adapters.sessions import StdioConnection
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool

load_dotenv()


def create_stringify_tool(tool: StructuredTool) -> StructuredTool:
    """创建一个包装后的工具，确保返回字符串

    解决 DeepSeek 模型对复杂数据结构兼容性问题
    """

    original_func = tool.coroutine

    @wraps(original_func)
    async def wrapped_func(*args, **kwargs):
        result = await original_func(*args, **kwargs)
        # 转换为字符串
        if isinstance(result, (list, dict)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)

    # 创建新工具
    new_tool = StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=wrapped_func,
        func=None,
    )
    return new_tool


# 创建 DeepSeek LLM
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
)


async def main():
    """主函数：加载 MCP 工具并创建 ReAct Agent"""

    # 加载 Bing MCP 工具
    bing_connection = StdioConnection(
        transport="stdio",
        command="npx",
        args=["-y", "bing-cn-mcp"],
    )
    bing_tools = await load_mcp_tools(
        None,
        connection=bing_connection,
        server_name="bing"
    )

    # 转换为确保返回字符串的工具
    stringified_tools = [create_stringify_tool(t) for t in bing_tools]

    print(f"已加载 {len(stringified_tools)} 个 MCP 工具 (已转换为字符串输出):")
    for tool in stringified_tools:
        print(f"  - {tool.name}")

    # 创建 ReAct Agent (使用 create_agent)
    agent = create_agent(llm, stringified_tools)

    # 测试问答
    questions = [
        "985大学有哪些",
    ]

    for question in questions:
        print(f"\n{'='*50}")
        print(f"用户问题: {question}")
        print(f"{'='*50}")

        response = await agent.ainvoke(
            {"messages": [("user", question)]},
            {"stream_mode": "values"}
        )

        print(f"\n助手回答: {response['messages'][-1].content}")


if __name__ == "__main__":
    asyncio.run(main())
