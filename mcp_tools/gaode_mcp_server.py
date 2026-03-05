"""
高德地图 MCP 配置

用于旅行规划智能体调用高德地图相关功能：
- 天气查询 (maps_weather)
- 路径规划 (maps_direction_driving, maps_direction_walking, maps_direction_transit_integrated)
- 周边搜索 (maps_around_search, maps_text_search)

配置来源: https://www.modelscope.cn/mcp/servers/@amap/amap-maps

工具名对照:
- 天气: maps_weather
- 驾车: maps_direction_driving
- 步行: maps_direction_walking
- 公交: maps_direction_transit_integrated
- 周边: maps_around_search
- 关键字: maps_text_search

用法示例:

    # 方式1: 上下文管理器（短时使用）
    async with GaodeMCP() as client:
        result = await client.weather("郑州")

    # 方式2: 全局单例（ReAct agent 推荐）
    client = await get_gaode_mcp()
    result = await client.weather("郑州")
    # 使用完毕后关闭
    await close_gaode_mcp()
"""

import asyncio
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# MCP 服务器配置
AMAP_MAPS_API_KEY = "667fcf8b411625e20413e497b8c7746d"

server_params = StdioServerParameters(
    command="npx",
    args=["-y", "@amap/amap-maps-mcp-server"],
    env={"AMAP_MAPS_API_KEY": AMAP_MAPS_API_KEY}
)


class GaodeMCP:
    """高德地图 MCP 客户端 - 用于 ReAct agent 调用"""

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

    # ========== 天气查询 ==========
    async def weather(self, city: str) -> Any:
        """查询城市天气"""
        return await self.call_tool("maps_weather", {"city": city})

    # ========== 路径规划 ==========
    async def direction_driving(self, origin: str, destination: str) -> Any:
        """驾车路径规划 (origin/destination: 经度,纬度)"""
        return await self.call_tool("maps_direction_driving", {
            "origin": origin,
            "destination": destination
        })

    async def direction_walking(self, origin: str, destination: str) -> Any:
        """步行路径规划 (origin/destination: 经度,纬度)"""
        return await self.call_tool("maps_direction_walking", {
            "origin": origin,
            "destination": destination
        })

    async def direction_transit(self, origin: str, destination: str, city: str, cityd: str) -> Any:
        """公交路径规划"""
        return await self.call_tool("maps_direction_transit_integrated", {
            "origin": origin,
            "destination": destination,
            "city": city,
            "cityd": cityd
        })

    # ========== 周边搜索 ==========
    async def around_search(self, location: str, keywords: str, radius: str = "3000") -> Any:
        """周边搜索 (location: 经度,纬度)"""
        return await self.call_tool("maps_around_search", {
            "location": location,
            "keywords": keywords,
            "radius": radius
        })

    async def text_search(self, keywords: str, city: Optional[str] = None, types: Optional[str] = None) -> Any:
        """关键字搜索"""
        args = {"keywords": keywords}
        if city:
            args["city"] = city
        if types:
            args["types"] = types
        return await self.call_tool("maps_text_search", args)

    # ========== 地理编码 ==========
    async def geocode(self, address: str, city: Optional[str] = None) -> Any:
        """地理编码 - 地址转换为经纬度

        Args:
            address: 地址字符串，如 "北京市朝阳区望京SOHO"
            city: 可选，城市名，用于提高精度，如 "北京"
        """
        args = {"address": address}
        if city:
            args["city"] = city
        return await self.call_tool("maps_geo", args)

    async def regeocode(self, location: str, radius: str = "0", extensions: str = "base") -> Any:
        """逆地理编码 - 经纬度转换为地址

        Args:
            location: 经纬度坐标，格式 "经度,纬度"，如 "116.397428,39.90923"
            radius: 搜索半径，默认0（精确匹配），范围0-1000米
            extensions: 返回结果类型，base=基本信息，all=全部信息
        """
        return await self.call_tool("maps_regeocode", {
            "location": location,
            "radius": radius,
            "extensions": extensions
        })

    # ========== 距离计算 ==========
    async def distance(self, origins: str, destination: str, type: str = "0") -> Any:
        """距离计算 - 计算两点之间的距离

        Args:
            origins: 起点经纬度，格式 "经度,纬度"，如 "116.397428,39.90923"，多个坐标用竖线分隔
            destination: 终点经纬度，格式 "经度,纬度"，如 "116.397428,39.90923"
            type: 距离测量类型，0=直线距离，1=驾车距离，3=步行距离，默认0
        """
        return await self.call_tool("maps_distance", {
            "origins": origins,
            "destination": destination,
            "type": type
        })


# 全局客户端实例 (用于 ReAct agent)
_client: Optional[GaodeMCP] = None


async def get_gaode_mcp() -> GaodeMCP:
    """获取全局 MCP 客户端"""
    global _client
    if _client is None:
        _client = GaodeMCP()
        await _client.__aenter__()
    return _client


async def close_gaode_mcp():
    """关闭全局 MCP 客户端"""
    global _client
    if _client:
        await _client.__aexit__(None, None, None)
        _client = None


async def test():
    """测试所有功能"""
    async with GaodeMCP() as client:
        # ========== 天气查询 ==========
        print("=" * 50)
        print("1. 测试天气查询:")
        print("=" * 50)
        result = await client.weather("郑州")
        print(result)

        # ========== 路径规划 ==========
        print("\n" + "=" * 50)
        print("2. 测试路径规划:")
        print("=" * 50)

        # 驾车
        print("\n[驾车] 郑州站 -> 二七广场:")
        result = await client.direction_driving("113.649,34.747", "113.625,34.755")
        print(result)

        # 步行
        print("\n[步行] 郑州站 -> 二七广场:")
        result = await client.direction_walking("113.649,34.747", "113.625,34.755")
        print(result)

        # 公交
        print("\n[公交] 郑州站 -> 二七广场:")
        result = await client.direction_transit(
            "113.649,34.747",
            "113.625,34.755",
            "郑州",
            "郑州"
        )
        print(result)

        # ========== 周边搜索 ==========
        print("\n" + "=" * 50)
        print("3. 测试周边搜索:")
        print("=" * 50)

        # 周边搜索
        print("\n[周边搜索] 郑州站附近美食:")
        result = await client.around_search("113.649,34.747", "美食")
        print(result)

        # 关键字搜索
        print("\n[关键字搜索] 郑州酒店:")
        result = await client.text_search("酒店", "郑州")
        print(result)

        # ========== 地理编码 ==========
        print("\n" + "=" * 50)
        print("4. 测试地理编码:")
        print("=" * 50)

        # 地理编码
        print("\n[地理编码] 北京市朝阳区望京SOHO:")
        result = await client.geocode("北京市朝阳区望京SOHO", "北京")
        print(result)

        # 逆地理编码
        print("\n[逆地理编码] 北京天安门经纬度:")
        result = await client.regeocode("116.397428,39.90923")
        print(result)

        # 距离计算
        print("\n[距离计算] 天安门到故宫:")
        result = await client.distance("116.397428,39.90923", "116.4100,39.9163")
        print(result)


if __name__ == "__main__":
    asyncio.run(test())
