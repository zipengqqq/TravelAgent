# MCP 学习指南

## 什么是 MCP？

**MCP (Model Context Protocol)** 是一个协议标准，让 LLM（大语言模型）能够**标准化地调用各种工具和服务**。

### 形象理解

想象 MCP 就像 **USB 接口**：
- 各种设备（鼠标、键盘、U盘）都可以用 USB 接口连接电脑
- 同样的，各种服务（数据库、地图API、文件系统）都可以用 MCP 协议连接 LLM

### MCP 的组成

```
┌─────────────┐         MCP 协议          ┌──────────────┐
│  LLM (Claude) │  ────────────────────────▶  │  MCP 服务器  │
└─────────────┘                          └──────────────┘
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │  底层服务       │
                                       │ (数据库/API等)  │
                                       └────────────────┘
```

## 项目结构

```
learn/mcp/
├── pg_server.py          # PostgreSQL MCP 服务器
├── mcp_agent_demo.py     # LangGraph + MCP Demo（入门）
├── requirements.txt      # Python 依赖
└── LEARNING_GUIDE.md     # 本文档
```

## 学习步骤

### 第一步：理解 MCP 服务器 (pg_server.py)

打开 `pg_server.py`，看到三个核心函数：

```python
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    # LLM 调用工具时，这个函数会被执行
    if name == "execute_sql":
        # 执行 SQL
    elif name == "list_tables":
        # 列出所有表
    elif name == "describe_table":
        # 描述表结构
```

**关键点：**
- MCP 服务器通过 `call_tool` 暴露工具给 LLM
- 每个工具有 `name` 和 `inputSchema`（参数格式）
- 工具返回的是 `TextContent`（文本内容）

### 第二步：运行 Demo

```bash
# 1. 安装依赖
pip install -r learn/mcp/requirements.txt

# 2. 运行 demo
cd learn/mcp
python mcp_agent_demo.py
```

### 第三步：理解 Demo 代码

打开 `mcp_agent_demo.py`，逐步理解：

#### 1. MCPClient - 连接 MCP 服务器

```python
class MCPClient:
    async def connect(self):
        # 启动 pg_server.py，建立通信

    async def call_tool(self, tool_name, arguments):
        # 调用 MCP 工具，比如 execute_sql
```

#### 2. MCPToolNode - LangGraph 节点

```python
class MCPToolNode:
    async def __call__(self, state):
        # 从 state 获取问题
        # 调用 MCP 工具
        # 将结果返回
```

#### 3. 工作流定义

```python
workflow = StateGraph(MCPState)
workflow.add_node("mcp_tool", tool_node)
workflow.add_edge(START, "mcp_tool")
workflow.add_edge("mcp_tool", END)
```

### 第四步：应用到你的 TravelAgent 项目

在你的项目中集成高德地图 MCP 时，步骤类似：

#### 1. 创建高德地图 MCP 服务器

```python
# learn/mcp/amap_server.py
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_location":
        # 调用高德地图 API 搜索地点
    elif name == "get_route":
        # 调用高德地图 API 获取路线
```

#### 2. 在 config.py 中初始化 MCP 客户端

```python
# graph/config.py
from learn.mcp.mcp_client import MCPClient

# 初始化高德地图 MCP 客户端
amap_client = MCPClient("learn/mcp/amap_server.py", {...})
```

#### 3. 创建使用 MCP 的节点

```python
# graph/nodes.py
async def amap_search_node(state: PlanExecuteState):
    location = state["location"]
    result = await amap_client.call_tool("search_location", {"query": location})
    return {"location_data": result}
```

#### 4. 在 workflow.py 中添加节点

```python
# graph/workflow.py
workflow.add_node("amap_search", amap_search_node)
workflow.add_conditional_edges("planner", should_use_amap, {"use": "amap_search", ...})
```

## MCP vs 传统方式对比

### 传统方式（直接调用 API）

```python
# 不使用 MCP
import requests

def search_location(query):
    url = f"https://restapi.amap.com/v3/geocode/geo?key={API_KEY}&address={query}"
    return requests.get(url).json()
```

### MCP 方式

```python
# 使用 MCP - 更标准化、更安全、更易扩展
result = await mcp_client.call_tool("search_location", {"query": query})
```

**MCP 的优势：**
1. **标准化** - 统一的协议，所有工具调用方式一样
2. **安全性** - MCP 服务器和 LLM 隔离，工具权限可控
3. **可扩展** - 添加新工具只需写新的 MCP 服务器
4. **跨平台** - 任何支持 MCP 的工具都可以用

## 常见问题

### Q1: MCP 和 LangChain Tool 有什么区别？

| MCP | LangChain Tool |
|-----|----------------|
| 标准协议（行业通用） | LangChain 特有 |
| 支持任何 LLM | 主要用于 LangChain 生态 |
| 工具运行在独立进程 | 工具在同一个进程 |
| 更安全、更灵活 | 更简单、更直接 |

**结论：** MCP 更适合复杂场景和长期项目。

### Q2: 如何调试 MCP？

```python
# 在 call_tool 函数中添加日志
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    print(f"[MCP DEBUG] 调用工具: {name}, 参数: {arguments}")  # 调试信息
    # ... 原有代码
```

### Q3: MCP 工具返回什么？

MCP 工具返回 `list[TextContent]`，每个 TextContent 有 `text` 属性：

```python
result = await mcp_client.call_tool("execute_sql", {"query": "SELECT * FROM users"})
# result.content[0].text 就是查询结果的 JSON 字符串
```

## 推荐学习顺序

1. ✅ 运行 `mcp_agent_demo.py`，理解基本流程
2. ✅ 修改 `pg_server.py`，添加新的工具（比如 `count_rows`）
3. ✅ 修改 `mcp_agent_demo.py`，让 LLM 自动选择工具
4. ✅ 创建高德地图 MCP 服务器（`amap_server.py`）
5. ✅ 将 MCP 集成到你的 TravelAgent 项目

## 参考资料

- [MCP 官方文档](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
