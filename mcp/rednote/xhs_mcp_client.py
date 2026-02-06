import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class XHSMCPClient:
    """小红书 MCP 客户端"""

    def __init__(self):
        self.session = None

    async def connect(self):
        """连接到小红书 MCP 服务器"""
        server_params = StdioServerParameters(
            command="uvx",
            args=["--from", "xiaohongshu-automation", "xhs-mcp"],
            env=os.environ.copy(),
        )
        self.stdio_context = stdio_client(server_params)
        self.stdio, self.write = await self.stdio_context.__aenter__()
        self.session = ClientSession(self.stdio, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        print("✅ 小红书 MCP 客户端已连接")

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
        print("🔌 小红书 MCP 客户端已关闭")
