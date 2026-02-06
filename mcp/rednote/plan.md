# 小红书 MCP 集成计划

## 目标
在 TravelAgent 应用中集成小红书 MCP，添加小红书内容搜索功能。

## MCP 配置信息
```json
{
  "mcpServers": {
    "xiaohongshu-automation": {
      "args": ["xhs-mcp"],
      "command": "uvx --from xiaohongshu-automation",
      "disabled": false,
      "timeout": 60,
      "transportType": "stdio"
    }
  }
}
```

## 实施步骤

### 第一步：准备环境
1. 确保 `uv` 工具已安装（Python 包管理器）
2. 测试 MCP 服务器连接：
   ```bash
   uvx --from xiaohongshu-automation xhs-mcp
   ```
3. 了解小红书 MCP 提供的工具列表

### 第二步：创建小红书 MCP 客户端模块
在 `mcp/rednote/` 目录下创建 `xhs_mcp_client.py`：
```python
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class XHSMCPClient:
    def __init__(self):
        self.session = None

    async def connect(self):
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

    async def call_tool(self, tool_name: str, arguments: dict):
        result = await self.session.call_tool(tool_name, arguments)
        return result

    async def close(self):
        if hasattr(self, 'session') and self.session:
            await self.session.__aexit__(None, None, None)
        if hasattr(self, 'stdio_context'):
            await self.stdio_context.__aexit__(None, None, None)
```

### 第三步：在 config.py 中添加全局客户端引用
```python
# 全局小红书 MCP 客户端（在 mcp/rednote/xhs_mcp_client.py 中定义）
xhs_mcp_client = None

async def init_xhs_mcp():
    global xhs_mcp_client
    from mcp.rednote.xhs_mcp_client import XHSMCPClient
    xhs_mcp_client = XHSMCPClient()
    await xhs_mcp_client.connect()
```

### 第四步：在 nodes.py 中创建搜索节点
```python
async def xhs_search_node(state: PlanExecuteState):
    """小红书搜索节点"""
    from graph.config import xhs_mcp_client

    keyword = state["question"]

    result = await xhs_mcp_client.call_tool(
        "search",  # 假设工具名是 search
        {"keyword": keyword}
    )

    # 提取搜索结果
    response = extract_response(result)
    return {"response": response}
```

### 第五步：更新 workflow.py
将 `xhs_search_node` 添加到工作流中，可以：
1. 作为新增节点，在 executor 中增加小红书搜索选项
2. 或替换/补充现有的 Tavily 搜索

### 第六步：修改路由器逻辑
在 `router_node` 或 `executor_node` 中添加判断：
- 如果用户问题与旅游攻略、景点推荐相关 → 调用小红书搜索
- 如果需要实时信息 → 调用 Tavily 搜索

### 第七步：测试与优化
1. 测试小红书搜索功能
2. 优化搜索结果展示
3. 处理错误和异常情况

## 目录结构
```
mcp/rednote/
├── plan.md              # 本计划文档
├── xhs_mcp_client.py    # 小红书 MCP 客户端（新建）
└── demo.py              # 小红书搜索演示（新建）

graph/
├── config.py           # 添加 xhs_mcp_client 引用（修改）
├── nodes.py             # 添加 xhs_search_node（修改）
└── workflow.py         # 集成搜索节点（修改）
```

## 注意事项
1. 小红书 MCP 的具体工具名称和参数需要先测试确认
2. 搜索结果需要与 Tavily 搜索结果统一格式处理
3. 考虑搜索结果缓存，避免重复请求
4. 添加错误处理，防止 MCP 服务不可用时影响整体流程
5. 客户端代码都在 `mcp/rednote/` 目录下，便于维护
