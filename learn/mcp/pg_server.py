import os
from typing import Any
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import psycopg2
from psycopg2.extras import RealDictCursor

# 从环境变量读取数据库配置
DB_URI = os.getenv("POSTGRES_URI")

# 创建 MCP 服务器实例
server = Server("postgres-server")

"""PostgreSQL MCP 服务器，允许通过 MCP 协议查询 PostgreSQL 数据库"""
async def execute_query(query: str) -> list[dict[str, Any]]:
    """执行 PostgreSQL 查询"""
    if not DB_URI:
        raise ValueError("POSTGRES_URI 环境变量未设置")

    conn = None
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query)
        results = cursor.fetchall()
        return [dict(row) for row in results]
    except Exception as e:
        raise Exception(f"查询执行失败: {str(e)}")
    finally:
        if conn:
            conn.close()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用的工具"""
    return [
        Tool(
            name="execute_sql",
            description="执行 PostgreSQL SQL 查询语句",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL 查询语句 (SELECT, INSERT, UPDATE, DELETE 等)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="list_tables",
            description="列出数据库中的所有表",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="describe_table",
            description="获取表的结构信息（列名、类型等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名",
                    },
                },
                "required": ["table_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用"""
    try:
        if name == "execute_sql":
            query = arguments.get("query", "")
            results = await execute_query(query)
            return [TextContent(type="text", text=str(results))]

        elif name == "list_tables":
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """
            results = await execute_query(query)
            return [TextContent(type="text", text=str(results))]

        elif name == "describe_table":
            table_name = arguments.get("table_name", "")
            query = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                AND table_schema = 'public'
                ORDER BY ordinal_position;
            """
            results = await execute_query(query)
            return [TextContent(type="text", text=str(results))]

        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"错误: {str(e)}")]


async def main():
    """启动 MCP 服务器"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
