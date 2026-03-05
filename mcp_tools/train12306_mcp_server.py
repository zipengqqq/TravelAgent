"""
12306 火车票 MCP 配置

用于旅行规划智能体调用 12306 火车票相关功能：
- 获取当前日期 (get-current-date)
- 城市站点代码查询 (get-station-code-of-citys, get-station-code-by-names)
- 余票查询 (get-tickets)
- 中转查询 (get-interline-tickets)
- 列车途径车站查询 (get-train-route-stations)

配置来源: https://www.modelscope.cn/mcp/servers/@Joooook/12306-mcp

工具名对照:
- 日期: get-current-date
- 城市代码: get-station-code-of-citys
- 车站代码: get-station-code-by-names
- 余票: get-tickets
- 中转: get-interline-tickets
- 过站: get-train-route-stations

用法示例:

    # 方式1: 上下文管理器（短时使用）
    async with Train12306MCP() as client:
        result = await client.get_station_code("北京")

    # 方式2: 全局单例（ReAct agent 推荐）
    client = await get_train_mcp()
    result = await client.get_station_code("北京")
    # 使用完毕后关闭
    await close_train_mcp()
"""

import asyncio
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# MCP 服务器配置
server_params = StdioServerParameters(
    command="npx",
    args=["-y", "12306-mcp"],
)


class Train12306MCP:
    """12306 火车票 MCP 客户端 - 用于 ReAct agent 调用"""

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

    # ========== 日期获取 ==========
    async def get_current_date(self) -> Any:
        """获取当前日期（以上海时区为准）"""
        return await self.call_tool("get-current-date", {})

    # ========== 站点代码查询 ==========
    async def get_stations_code_in_city(self, city: str) -> Any:
        """通过城市名获取该城市所有火车站信息"""
        return await self.call_tool("get-stations-code-in-city", {"city": city})

    async def get_station_code_of_citys(self, citys: str) -> Any:
        """通过城市名获取代表该城市的 station_code（城市代码）

        Args:
            citys: 城市名，多个用 | 分隔，如 "北京|上海"
        """
        return await self.call_tool("get-station-code-of-citys", {"citys": citys})

    async def get_station_code_by_names(self, station_names: str) -> Any:
        """通过车站名获取 station_code

        Args:
            station_names: 车站名，多个用 | 分隔，如 "北京南|上海虹桥"
        """
        return await self.call_tool("get-station-code-by-names", {"stationNames": station_names})

    async def get_station_by_telecode(self, telecode: str) -> Any:
        """通过 telecode 获取车站详情

        Args:
            telecode: 车站的 3 位字母编码
        """
        return await self.call_tool("get-station-by-telecode", {"stationTelecode": telecode})

    # ========== 余票查询 ==========
    async def get_tickets(
        self,
        date: str,
        from_station: str,
        to_station: str,
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        sort_flag: str = "",
        sort_reverse: bool = False,
        limited_num: int = 0,
        format: str = "text"
    ) -> Any:
        """查询 12306 余票信息

        Args:
            date: 查询日期，格式 "yyyy-MM-dd"
            from_station: 出发地 station_code
            to_station: 到达地 station_code
            train_filter_flags: 车次筛选标志，如 "G" 只查高铁
            earliest_start_time: 最早出发时间 (0-24)
            latest_start_time: 最迟出发时间 (0-24)
            sort_flag: 排序方式 (startTime/arriveTime/duration)
            sort_reverse: 是否逆向排序
            limited_num: 返回数量限制
            format: 返回格式 (text/csv/json)
        """
        return await self.call_tool("get-tickets", {
            "date": date,
            "fromStation": from_station,
            "toStation": to_station,
            "trainFilterFlags": train_filter_flags,
            "earliestStartTime": earliest_start_time,
            "latestStartTime": latest_start_time,
            "sortFlag": sort_flag,
            "sortReverse": sort_reverse,
            "limitedNum": limited_num,
            "format": format
        })

    # ========== 中转查询 ==========
    async def get_interline_tickets(
        self,
        date: str,
        from_station: str,
        to_station: str,
        middle_station: str = "",
        show_wz: bool = False,
        train_filter_flags: str = "",
        earliest_start_time: int = 0,
        latest_start_time: int = 24,
        sort_flag: str = "",
        sort_reverse: bool = False,
        limited_num: int = 10,
        format: str = "text"
    ) -> Any:
        """查询 12306 中转余票信息

        Args:
            date: 查询日期，格式 "yyyy-MM-dd"
            from_station: 出发地 station_code
            to_station: 到达地 station_code
            middle_station: 中转地 station_code（可选）
            show_wz: 是否显示无座
            train_filter_flags: 车次筛选标志
            earliest_start_time: 最早出发时间
            latest_start_time: 最迟出发时间
            sort_flag: 排序方式
            sort_reverse: 是否逆向排序
            limited_num: 返回数量限制，默认10
            format: 返回格式 (text/json)
        """
        return await self.call_tool("get-interline-tickets", {
            "date": date,
            "fromStation": from_station,
            "toStation": to_station,
            "middleStation": middle_station,
            "showWZ": show_wz,
            "trainFilterFlags": train_filter_flags,
            "earliestStartTime": earliest_start_time,
            "latestStartTime": latest_start_time,
            "sortFlag": sort_flag,
            "sortReverse": sort_reverse,
            "limitedNum": limited_num,
            "format": format
        })

    # ========== 列车过站查询 ==========
    async def get_train_route_stations(
        self,
        train_code: str,
        depart_date: str,
        format: str = "text"
    ) -> Any:
        """查询特定列车车次在指定区间内的途径车站信息

        Args:
            train_code: 车次，如 "G1033"
            depart_date: 出发日期，格式 "yyyy-MM-dd"
            format: 返回格式 (text/json)
        """
        return await self.call_tool("get-train-route-stations", {
            "trainCode": train_code,
            "departDate": depart_date,
            "format": format
        })

    # ========== 便捷方法 ==========
    async def get_station_code(self, location: str) -> str:
        """获取站点代码（智能判断是城市还是车站名）

        Args:
            location: 城市名或车站名，如 "北京" 或 "北京南"

        Returns:
            station_code 字符串
        """
        # 先尝试作为车站名查询
        result = await self.get_station_code_by_names(location)
        result_str = str(result)

        # 如果没有找到，尝试作为城市名查询
        if "未找到" in result_str or "null" in result_str or not result_str.strip():
            result = await self.get_station_code_of_citys(location)

        return str(result)


# 全局客户端实例 (用于 ReAct agent)
_client: Optional[Train12306MCP] = None


async def get_train_mcp() -> Train12306MCP:
    """获取全局 MCP 客户端"""
    global _client
    if _client is None:
        _client = Train12306MCP()
        await _client.__aenter__()
    return _client


async def close_train_mcp():
    """关闭全局 MCP 客户端"""
    global _client
    if _client:
        await _client.__aexit__(None, None, None)
        _client = None


async def test():
    """测试所有功能"""
    async with Train12306MCP() as client:
        # ========== 获取当前日期 ==========
        print("=" * 50)
        print("1. 测试获取当前日期:")
        print("=" * 50)
        result = await client.get_current_date()
        print(result)

        # ========== 站点代码查询 ==========
        print("\n" + "=" * 50)
        print("2. 测试站点代码查询:")
        print("=" * 50)

        # 通过城市获取代码
        print("\n[城市代码] 北京:")
        result = await client.get_station_code_of_citys("北京")
        print(result)

        # 通过车站名获取代码
        print("\n[车站代码] 北京南:")
        result = await client.get_station_code_by_names("北京南")
        print(result)

        # 获取城市所有车站
        print("\n[城市所有车站] 上海:")
        result = await client.get_stations_code_in_city("上海")
        print(result)

        # ========== 余票查询 ==========
        print("\n" + "=" * 50)
        print("3. 测试余票查询:")
        print("=" * 50)

        # 获取当前日期
        current_date = await client.get_current_date()
        print(f"\n当前日期: {current_date}")

        # 获取北京和上海的 station_code
        from_code = await client.get_station_code_of_citys("北京")
        to_code = await client.get_station_code_of_citys("上海")
        print(f"北京代码: {from_code}")
        print(f"上海代码: {to_code}")

        # 查询余票（使用文本中的日期）
        # 解析日期（实际使用时需要处理相对日期）
        print("\n[余票查询] 北京 -> 上海:")
        # 注意：这里需要传入实际的日期格式
        result = await client.get_tickets(
            date="2026-03-10",
            from_station="BJP",
            to_station="SHH",
            train_filter_flags="G",
            earliest_start_time=6,
            latest_start_time=22,
            sort_flag="duration",
            format="text"
        )
        print(result)

        # ========== 列车过站查询 ==========
        print("\n" + "=" * 50)
        print("4. 测试列车过站查询:")
        print("=" * 50)

        print("\n[过站查询] G1033:")
        result = await client.get_train_route_stations("G1033", "2026-03-10")
        print(result)


if __name__ == "__main__":
    asyncio.run(test())
