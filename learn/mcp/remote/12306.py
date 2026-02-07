import asyncio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "12306-mcp"],
)


async def run():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("工具列表:", tools)

            result = await session.call_tool("get-stations-code-in-city", arguments={"city": "郑州"})
            print(f"调用结果:{result}")


if __name__ == "__main__":
    asyncio.run(run())
