"""
MCP 工具注册中心

统一管理 MCP 工具的加载和转换
支持工具：
- 必应搜索 (bing_search)
- 高德地图：天气查询、路径规划、周边搜索
"""

import asyncio
from typing import List
from langchain_core.tools import BaseTool

# 导入已有的 MCP 客户端
from mcp_tools.bing_mcp_server import get_bing_mcp, close_bing_mcp
from mcp_tools.gaode_mcp_server import get_gaode_mcp, close_gaode_mcp


class BingSearchTool(BaseTool):
    """必应搜索工具"""
    name: str = "bing_search"
    description: str = "使用必应中文搜索引擎搜索信息。输入搜索关键词，返回搜索结果列表。"

    async def _arun(self, query: str) -> str:
        client = await get_bing_mcp()
        result = await client.search(query)
        return str(result)

    def _run(self, query: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(query))


class GaodeWeatherTool(BaseTool):
    """高德地图 - 天气查询"""
    name: str = "maps_weather"
    description: str = "查询城市天气信息。输入城市名称，返回天气数据。"

    async def _arun(self, city: str) -> str:
        client = await get_gaode_mcp()
        result = await client.weather(city)
        return str(result)

    def _run(self, city: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(city))


class GaodeDrivingTool(BaseTool):
    """高德地图 - 驾车路径规划"""
    name: str = "maps_direction_driving"
    description: str = "驾车路径规划。输入起点和终点经纬度，返回驾车路线。"

    async def _arun(self, origin: str, destination: str) -> str:
        client = await get_gaode_mcp()
        result = await client.direction_driving(origin, destination)
        return str(result)

    def _run(self, origin: str, destination: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(origin, destination))


class GaodeTransitTool(BaseTool):
    """高德地图 - 公交路径规划"""
    name: str = "maps_direction_transit"
    description: str = "公交路径规划。输入起点、终点和城市名，返回公交路线。"

    async def _arun(self, origin: str, destination: str, city: str, cityd: str) -> str:
        client = await get_gaode_mcp()
        result = await client.direction_transit(origin, destination, city, cityd)
        return str(result)

    def _run(self, origin: str, destination: str, city: str, cityd: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(origin, destination, city, cityd))


class GaodeAroundSearchTool(BaseTool):
    """高德地图 - 周边搜索"""
    name: str = "maps_around_search"
    description: str = "周边搜索。输入位置经纬度、关键词，返回周边 POI 列表。"

    async def _arun(self, location: str, keywords: str, radius: str = "3000") -> str:
        client = await get_gaode_mcp()
        result = await client.around_search(location, keywords, radius)
        return str(result)

    def _run(self, location: str, keywords: str, radius: str = "3000") -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(location, keywords, radius))


# 工具缓存
_mcp_tools: List[BaseTool] = []


async def load_mcp_tools() -> List[BaseTool]:
    """加载所有 MCP 工具"""
    global _mcp_tools
    if not _mcp_tools:
        _mcp_tools = [
            BingSearchTool(),
            GaodeWeatherTool(),
            GaodeDrivingTool(),
            GaodeTransitTool(),
            GaodeAroundSearchTool(),
        ]
    return _mcp_tools


async def get_mcp_tools() -> List[BaseTool]:
    """获取已加载的 MCP 工具"""
    return await load_mcp_tools()


async def close_all_mcp():
    """关闭所有 MCP 连接"""
    await close_bing_mcp()
    await close_gaode_mcp()
