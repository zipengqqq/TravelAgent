"""
MCP + LangGraph 入门 Demo
演示如何在 LangGraph 中使用 MCP 连接 PostgreSQL

学习目标：
1. 理解 MCP 是什么
2. 如何在 Python 中调用 MCP 工具
3. 如何将 MCP 集成到 LangGraph
"""

import os
import json
from imp import load_dynamic
from plistlib import load
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ============ 第一步：理解 MCP ============
# MCP (Model Context Protocol) 是一个协议，让 LLM 能标准化地调用各种工具
# 就像"USB 接口"一样，任何支持 MCP 的工具都可以被 LLM 调用

load_dotenv()

# ============ 第二步：创建 MCP 客户端 ============
class MCPClient:
    """MCP 客户端：连接到 MCP 服务器并调用工具"""

    def __init__(self, server_path: str, env: dict = None):
        self.server_path = server_path
        self.env = env or {}
        self.session = None

    async def connect(self):
        """连接到 MCP 服务器"""
        server_params = StdioServerParameters(
            command="python",
            args=[self.server_path],
            env=self.env,
        )
        self.stdio_context = stdio_client(server_params)
        self.stdio, self.write = await self.stdio_context.__aenter__()
        self.session = ClientSession(self.stdio, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        print(f"✅ MCP 客户端已连接")

    async def list_tools(self):
        """列出所有可用工具"""
        tools = await self.session.list_tools()
        print(f"📦 可用工具: {[tool.name for tool in tools.tools]}")
        return tools.tools

    async def call_tool(self, tool_name: str, arguments: dict):
        """调用指定工具"""
        print(f"🔧 调用工具: {tool_name}，参数: {arguments}")
        result = await self.session.call_tool(tool_name, arguments)
        return result

    async def close(self):
        """关闭连接"""
        if hasattr(self, 'session') and self.session:
            await self.session.__aexit__(None, None, None)
        if hasattr(self, 'stdio_context'):
            await self.stdio_context.__aexit__(None, None, None)


# ============ 第三步：创建 LangGraph 工具节点 ============
class MCPToolNode:
    """LangGraph 节点：调用 MCP 工具"""

    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client

    async def __call__(self, state: dict):
        """节点执行函数"""
        question = state["question"]

        # 简单判断用户意图（实际项目中可以用 LLM 判断）
        if "表" in question or "table" in question.lower():
            # 列出所有表
            result = await self.mcp_client.call_tool("list_tables", {})
        elif "结构" in question or "describe" in question.lower():
            # 描述表结构
            # 提取表名（简单处理）
            table_name = question.split()[-1]
            result = await self.mcp_client.call_tool("describe_table", {"table_name": table_name})
        else:
            # 执行 SQL
            result = await self.mcp_client.call_tool("execute_sql", {"query": question})

        # 提取工具返回的文本
        response = ""
        for content in result.content:
            if hasattr(content, 'text'):
                response += content.text + "\n"

        print(f"📊 查询结果: {response[:100]}...")

        return {"response": response, "past_steps": [(question, response)]}


# ============ 第四步：简单 LangGraph 工作流 ============
import asyncio
from langgraph.graph import StateGraph, END, START
from typing import TypedDict, List, Tuple, Annotated
import operator


class MCPState(TypedDict):
    """状态定义"""
    question: str  # 用户问题
    response: str  # 工具返回结果
    past_steps: Annotated[List[Tuple], operator.add]  # 历史步骤


def create_mcp_workflow(mcp_client: MCPClient) -> StateGraph:
    """创建使用 MCP 的 LangGraph 工作流"""

    workflow = StateGraph(MCPState)

    # 创建工具节点
    tool_node = MCPToolNode(mcp_client)

    # 添加节点
    workflow.add_node("mcp_tool", tool_node)

    # 定义边
    workflow.add_edge(START, "mcp_tool")
    workflow.add_edge("mcp_tool", END)

    return workflow


# ============ 第五步：运行 Demo ============
async def main():
    """主函数"""
    print("=" * 60)
    print("🎓 MCP + LangGraph 入门 Demo")
    print("=" * 60)

    # 1. 连接 MCP 服务器
    server_path = "C:/Users/apeng/PycharmProjects/TravelAgent/learn/mcp/pg_server.py"
    env = {"POSTGRES_URI": os.getenv("POSTGRES_URI", "")}

    mcp_client = MCPClient(server_path, env)
    await mcp_client.connect()

    # 2. 列出可用工具
    tools = await mcp_client.list_tools()

    # 3. 创建工作流
    workflow = create_mcp_workflow(mcp_client)
    app = workflow.compile()

    # 4. 运行一些测试查询
    test_questions = [
        "列出所有表",
        "SELECT version();",
    ]

    for question in test_questions:
        print(f"\n{'=' * 40}")
        print(f"❓ 用户问题: {question}")
        print(f"{'=' * 40}")

        result = await app.ainvoke({"question": question})
        print(f"✅ 回答: {result['response'][:200]}")

    # 5. 关闭连接
    await mcp_client.close()
    print("\n" + "=" * 60)
    print("🎉 Demo 完成！")
    print("=" * 60)


# ============ 第六步：更高级的用法 ============
"""
在实际项目中，你可能会这样使用：

1. 在 config.py 中初始化 MCP 客户端
2. 在 nodes.py 中创建使用 MCP 工具的节点
3. 在 workflow.py 中添加这些节点到工作流

示例节点写法：

async def postgres_query_node(state: PlanExecuteState):
    # 调用 MCP 工具执行查询
    result = await mcp_client.call_tool("execute_sql", {
        "query": state["sql_query"]
    })
    return {"query_result": result}

# 在主项目中使用高德地图 MCP 时，也是类似的模式：
# 1. 连接到高德地图 MCP 服务器
# 2. 调用地图查询工具
# 3. 将结果返回给 LLM 处理
"""

if __name__ == "__main__":
    asyncio.run(main())
