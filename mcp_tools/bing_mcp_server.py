"""
必应搜索 MCP 配置

用于旅行规划智能体调用必应搜索功能：
- 网页搜索 (bing_search)

配置来源: https://github.com/BingChatLLM/bing-cn-mcp

用法示例:

    # 方式1: 上下文管理器（短时使用）
    async with BingMCP() as client:
        result = await client.search("日本旅游攻略")

    # 方式2: 全局单例（ReAct agent 推荐）
    client = await get_bing_mcp()
    result = await client.search("日本旅游攻略")
    # 使用完毕后关闭
    await close_bing_mcp()
"""

import asyncio
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# MCP 服务器配置
server_params = StdioServerParameters(
    command="npx",
    args=["-y", "bing-cn-mcp"],
)


class BingMCP:
    """必应搜索 MCP 客户端 - 用于 ReAct agent 调用"""

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self._read = None
        self._write = None
        self._stdio_ctx = None
        self._session_ctx = None

    async def __aenter__(self):
        """进入上下文"""
        self._stdio_ctx = stdio_client(server_params)
        self._read, self._write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(self._read, self._write)
        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self._session_ctx:
            await self._session_ctx.__aexit__(exc_type, exc_val, exc_tb)
        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(exc_type, exc_val, exc_tb)

    async def list_tools(self) -> list:
        """列出所有可用工具"""
        tools = await self.session.list_tools()
        return tools.tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用指定工具"""
        return await self.session.call_tool(tool_name, arguments)

    async def search(self, query: str) -> Any:
        """搜索网页"""
        return await self.call_tool("bing_search", {"query": query})


# 全局客户端实例 (用于 ReAct agent)
_client: Optional[BingMCP] = None


async def get_bing_mcp() -> BingMCP:
    """获取全局 MCP 客户端"""
    global _client
    if _client is None:
        _client = BingMCP()
        await _client.__aenter__()
    return _client


async def close_bing_mcp():
    """关闭全局 MCP 客户端"""
    global _client
    if _client:
        await _client.__aexit__(None, None, None)
        _client = None


async def test():
    """测试搜索功能"""
    async with BingMCP() as client:
        # 列出所有工具
        print("=" * 50)
        print("1. 列出所有工具:")
        print("=" * 50)
        tools = await client.list_tools()
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")

        # 测试搜索
        print("\n" + "=" * 50)
        print("2. 测试搜索:")
        print("=" * 50)
        result = await client.search("日本旅游攻略")
        print(result)


if __name__ == "__main__":
    asyncio.run(test())
