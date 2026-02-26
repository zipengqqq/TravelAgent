"""
LangGraph create_agent + MCP 集成示例

演示如何使用 langchain_mcp_adapters 加载 MCP 工具，
并手动实现 ReAct 循环来调用 MCP 工具。

依赖:
    pip install langchain-mcp-adapters langgraph

运行:
    cd learn/langgraph_react_mcp
    python mcp_agent_demo.py

注意: DeepSeek 模型可能不支持 function_calling，导致工具无法被自动调用。
如果遇到这种情况，可以考虑使用 OpenAI GPT 模型或其他支持 function_calling 的模型。
"""

import asyncio
import json
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import load_mcp_tools
from langchain_mcp_adapters.sessions import StdioConnection
from langchain_core.messages import HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_function

load_dotenv()


# 创建 DeepSeek LLM
# 注意: 如果 DeepSeek 不支持 function calling，可以改用 OpenAI
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL'),
    temperature=0.7,
)


async def run_react_agent(llm, tools, question: str, max_iterations: int = 5):
    """手动实现 ReAct 循环"""

    # 将工具转换为 OpenAI 函数格式
    functions = [convert_to_openai_function(tool) for tool in tools]

    # 绑定函数到 LLM
    llm_with_tools = llm.bind(functions=functions)

    messages = [HumanMessage(content=question)]

    for i in range(max_iterations):
        print(f"\n--- 迭代 {i+1} ---")

        # 调用 LLM
        response = await llm_with_tools.ainvoke(messages)

        # 打印响应详情（调试用）
        print(f"响应类型: {type(response)}")
        print(f"响应内容: {str(response)[:200]}...")
        if hasattr(response, 'additional_kwargs'):
            print(f"额外参数: {response.additional_kwargs}")

        # 检查是否有函数调用 - 支持两种格式
        # 1. OpenAI tool_calls 格式 (response.additional_kwargs['function_call'])
        # 2. LangChain tool_calls 属性
        func_call = None

        if hasattr(response, 'additional_kwargs') and response.additional_kwargs.get('function_call'):
            func_call = response.additional_kwargs['function_call']
        elif hasattr(response, 'tool_calls') and response.tool_calls:
            func_call = response.tool_calls[0]

        if func_call:
            # 处理两种格式
            if isinstance(func_call, dict):
                func_name = func_call['name']
                func_args = json.loads(func_call['arguments'])
            else:
                func_name = func_call['name']
                func_args = func_call.get('args', {})

            print(f"调用工具: {func_name}")
            print(f"参数: {func_args}")

            # 查找并调用工具
            tool = next((t for t in tools if t.name == func_name), None)
            if tool:
                result = await tool.ainvoke(func_args)
                print(f"工具返回结果: {str(result)[:200]}...")

                # 将结果添加到消息历史
                messages.append(response)
                messages.append(HumanMessage(
                    content=f"工具 {func_name} 返回结果: {result}"
                ))
            else:
                print(f"未找到工具: {func_name}")
                messages.append(response)
                break
        else:
            # 没有函数调用，返回最终答案
            messages.append(response)
            return response.content

    return "达到最大迭代次数"


async def main():
    """主函数：加载 MCP 工具并创建 ReAct Agent"""

    # 加载 Bing MCP 工具
    bing_connection = StdioConnection(
        transport="stdio",
        command="npx",
        args=["-y", "bing-cn-mcp"],
    )
    bing_tools = await load_mcp_tools(
        None,  # session 参数
        connection=bing_connection,
        server_name="bing"
    )

    print(f"已加载 {len(bing_tools)} 个 MCP 工具:")
    for tool in bing_tools:
        print(f"  - {tool.name}: {tool.description[:50]}...")

    # 测试问答
    test_questions = [
        "985大学有哪些",
    ]

    for question in test_questions:
        print(f"\n{'='*50}")
        print(f"用户问题: {question}")
        print(f"{'='*50}")

        # 运行 ReAct 循环
        answer = await run_react_agent(llm, bing_tools, question)
        print(f"\n助手回答: {answer}")


if __name__ == "__main__":
    asyncio.run(main())
