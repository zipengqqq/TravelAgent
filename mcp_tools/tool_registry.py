"""
MCP 工具注册中心

统一管理 MCP 工具的加载和转换
支持工具：
- 必应搜索 (bing_search)
- 高德地图：天气查询、路径规划、周边搜索
"""

import asyncio
from typing import List, Optional
from langchain_core.tools import BaseTool

# 导入已有的 MCP 客户端
from mcp_tools.bing_mcp_server import get_bing_mcp, close_bing_mcp
from mcp_tools.gaode_mcp_server import get_gaode_mcp, close_gaode_mcp
from mcp_tools.train12306_mcp_server import get_train_mcp, close_train_mcp


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


class GaodeGeocodeTool(BaseTool):
    """高德地图 - 地理编码（地址转经纬度）"""
    name: str = "maps_geo"
    description: str = "地理编码。将地址转换为经纬度坐标。输入地址和可选城市名，返回经纬度信息。"

    async def _arun(self, address: str, city: Optional[str] = None) -> str:
        client = await get_gaode_mcp()
        result = await client.geocode(address, city)
        return str(result)

    def _run(self, address: str, city: Optional[str] = None) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(address, city))


class GaodeRegeocodeTool(BaseTool):
    """高德地图 - 逆地理编码（经纬度转地址）"""
    name: str = "maps_regeocode"
    description: str = "逆地理编码。将经纬度坐标转换为地址信息。输入经纬度和可选参数，返回地址详情。"

    async def _arun(self, location: str, radius: str = "0", extensions: str = "base") -> str:
        client = await get_gaode_mcp()
        result = await client.regeocode(location, radius, extensions)
        return str(result)

    def _run(self, location: str, radius: str = "0", extensions: str = "base") -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(location, radius, extensions))


class GaodeDistanceTool(BaseTool):
    """高德地图 - 距离计算"""
    name: str = "maps_distance"
    description: str = "距离计算。输入起点和终点经纬度，返回两点之间的距离。type=0直线距离，type=1驾车距离，type=3步行距离。"

    async def _arun(self, origins: str, destination: str, type: str = "0") -> str:
        client = await get_gaode_mcp()
        result = await client.distance(origins, destination, type)
        return str(result)

    def _run(self, origins: str, destination: str, type: str = "0") -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(origins, destination, type))


# ========== 12306 火车票工具 ==========

class TrainCurrentDateTool(BaseTool):
    """12306 - 获取当前日期"""
    name: str = "train_current_date"
    description: str = "获取当前日期（以上海时区 UTC+8 为准）。用于解析用户提到的相对日期（如'明天'、'下周三'），返回格式为 yyyy-MM-dd。"

    async def _arun(self) -> str:
        client = await get_train_mcp()
        result = await client.get_current_date()
        return str(result)

    def _run(self) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun())


class TrainStationCodeTool(BaseTool):
    """12306 - 获取城市站点代码"""
    name: str = "train_station_code"
    description: str = "通过城市名获取12306站点代码。输入城市名称（如'北京'、'上海'），返回对应的火车站代码。用于为余票查询准备参数。"

    async def _arun(self, city: str) -> str:
        client = await get_train_mcp()
        result = await client.get_station_code_of_citys(city)
        return str(result)

    def _run(self, city: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(city))


class TrainStationCodeByNameTool(BaseTool):
    """12306 - 通过车站名获取代码"""
    name: str = "train_station_code_by_name"
    description: str = "通过具体车站名获取12306代码。输入车站名称（如'北京南'、'上海虹桥'），返回对应的车站代码。"

    async def _arun(self, station_name: str) -> str:
        client = await get_train_mcp()
        result = await client.get_station_code_by_names(station_name)
        return str(result)

    def _run(self, station_name: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(station_name))


class TrainStationsInCityTool(BaseTool):
    """12306 - 获取城市所有车站"""
    name: str = "train_stations_in_city"
    description: str = "查询城市所有火车站信息。输入城市名称，返回该城市所有火车站的名称和代码列表。"

    async def _arun(self, city: str) -> str:
        client = await get_train_mcp()
        result = await client.get_stations_code_in_city(city)
        return str(result)

    def _run(self, city: str) -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(city))


class TrainTicketsTool(BaseTool):
    """12306 - 查询余票信息"""
    name: str = "train_tickets"
    description: str = "查询12306火车票余票信息。输入日期、出发地代码、到达地代码，可选筛选条件（车次类型如G/D/Z/T/K、出发时间范围、排序方式）。返回余票详情。"

    async def _arun(
        self,
        date: str,
        from_station: str,
        to_station: str,
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        sort_flag: str = "",
        format: str = "text"
    ) -> str:
        client = await get_train_mcp()
        result = await client.get_tickets(
            date=date,
            from_station=from_station,
            to_station=to_station,
            train_filter_flags=train_filter_flags,
            earliest_start_time=earliest_start_time,
            latest_start_time=latest_start_time,
            sort_flag=sort_flag,
            format=format
        )
        return str(result)

    def _run(
        self,
        date: str,
        from_station: str,
        to_station: str,
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        sort_flag: str = "",
        format: str = "text"
    ) -> str:
        return asyncio.get_event_loop().run_until_complete(
            self._arun(date, from_station, to_station, train_filter_flags,
                      earliest_start_time, latest_start_time, sort_flag, format)
        )


class TrainInterlineTool(BaseTool):
    """12306 - 查询中转票"""
    name: str = "train_interline"
    description: str = "查询12306中转换乘方案。当没有直达列车时，输入日期、出发地、到达地，可选指定中转站，返回中转余票信息。"

    async def _arun(
        self,
        date: str,
        from_station: str,
        to_station: str,
        middle_station: str = "",
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        format: str = "text"
    ) -> str:
        client = await get_train_mcp()
        result = await client.get_interline_tickets(
            date=date,
            from_station=from_station,
            to_station=to_station,
            middle_station=middle_station,
            train_filter_flags=train_filter_flags,
            earliest_start_time=earliest_start_time,
            latest_start_time=latest_start_time,
            format=format
        )
        return str(result)

    def _run(
        self,
        date: str,
        from_station: str,
        to_station: str,
        middle_station: str = "",
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        format: str = "text"
    ) -> str:
        return asyncio.get_event_loop().run_until_complete(
            self._arun(date, from_station, to_station, middle_station,
                      train_filter_flags, earliest_start_time, latest_start_time, format)
        )


class TrainRouteStationsTool(BaseTool):
    """12306 - 查询列车途径车站"""
    name: str = "train_route_stations"
    description: str = "查询特定列车车次的途径车站信息。输入车次（如G1033）和日期，返回该车次在指定日期的详细停靠站信息（到站时间、出发时间、停留时间）。"

    async def _arun(self, train_code: str, date: str, format: str = "text") -> str:
        client = await get_train_mcp()
        result = await client.get_train_route_stations(train_code, date, format)
        return str(result)

    def _run(self, train_code: str, date: str, format: str = "text") -> str:
        return asyncio.get_event_loop().run_until_complete(self._arun(train_code, date, format))


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
            GaodeGeocodeTool(),
            GaodeRegeocodeTool(),
            GaodeDistanceTool(),
            # 12306 火车票工具
            TrainCurrentDateTool(),
            TrainStationCodeTool(),
            TrainStationCodeByNameTool(),
            TrainStationsInCityTool(),
            TrainTicketsTool(),
            TrainInterlineTool(),
            TrainRouteStationsTool(),
        ]
        from utils.logger_util import logger
        logger.info(f"已加载 {len(_mcp_tools)} 个 MCP 工具: {[t.name for t in _mcp_tools]}")
    return _mcp_tools


async def get_mcp_tools() -> List[BaseTool]:
    """获取已加载的 MCP 工具"""
    return await load_mcp_tools()


async def close_all_mcp():
    """关闭所有 MCP 连接"""
    await close_bing_mcp()
    await close_gaode_mcp()
    await close_train_mcp()
