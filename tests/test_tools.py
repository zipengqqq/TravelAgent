"""
检查 LLM 收到的函数定义
"""
import asyncio
import sys
import json
sys.path.insert(0, '/Users/penn/work/TravelAgent')

from langchain_core.utils.function_calling import convert_to_openai_function
from mcp_tools.tool_registry import get_mcp_tools


async def main():
    tools = await get_mcp_tools()
    print("工具列表:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")

    print("\n转换为函数定义:")
    functions = [convert_to_openai_function(tool) for tool in tools]
    for func in functions:
        print(f"\n{func['name']}:")
        print(json.dumps(func, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
