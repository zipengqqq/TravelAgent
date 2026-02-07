import os
import asyncio

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langgraph.graph import StateGraph, END, START
from typing import TypedDict

load_dotenv()

# ============ 全局变量 ============
mcp_client = None  # 全局 MCP 客户端


# ============ MCP 客户端类 ============
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


# ============ 状态定义 ============
class MCPState(TypedDict):
    """状态定义"""
    question: str  # 用户问题
    response: str  # 工具返回结果


# ============ LangGraph 节点 ============
async def mcp_tool_node(state: MCPState):
    """MCP 工具调用节点"""
    question = state["question"]

    # 简单判断用户意图（实际项目中可以用 LLM 判断）
    if "表" in question or "table" in question.lower():
        # 列出所有表
        result = await mcp_client.call_tool("list_tables", {})
    elif "结构" in question or "describe" in question.lower():
        # 描述表结构
        # 提取表名（简单处理）
        table_name = question.split()[-1]
        result = await mcp_client.call_tool("describe_table", {"table_name": table_name})
    else:
        # 执行 SQL
        result = await mcp_client.call_tool("execute_sql", {"query": question})

    # 提取工具返回的文本
    response = ""
    for content in result.content:
        if hasattr(content, 'text'):
            response += content.text + "\n"

    print(f"📊 查询结果: {response[:100]}...")

    return {"response": response}


# ============ LangGraph 工作流 ============
def create_mcp_workflow() -> StateGraph:
    """创建使用 MCP 的 LangGraph 工作流"""
    workflow = StateGraph(MCPState)

    # 添加节点
    workflow.add_node("mcp_tool", mcp_tool_node)

    # 定义边
    workflow.add_edge(START, "mcp_tool")
    workflow.add_edge("mcp_tool", END)

    return workflow


# ============ 运行 Demo ============
async def main():
    """主函数"""
    global mcp_client

    print("=" * 60)
    print("🎓 MCP + LangGraph 入门 Demo")
    print("=" * 60)

    # 1. 连接 MCP 服务器
    server_path = "pg_server.py"
    env = {"POSTGRES_URI": os.getenv("POSTGRES_URI", "")}

    mcp_client = MCPClient(server_path, env)
    await mcp_client.connect()


    # 2. 创建工作流
    workflow = create_mcp_workflow()
    app = workflow.compile()

    # 3. 运行一些测试查询
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

    # 4. 关闭连接
    await mcp_client.close()
    print("\n" + "=" * 60)
    print("🎉 Demo 完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
