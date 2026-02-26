# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TravelAgent 是一个基于 Python 的 AI 旅行规划智能体，使用 LangGraph 和 LLM 技术构建。项目展示了先进的 AI 智能体模式，包括规划-执行、多智能体系统、记忆管理、MCP 集成、人机交互以及 Token 级别的流式输出。

## 环境设置

项目使用 conda 环境 `travel-agent`。**所有 Python 命令都必须在此环境中运行**。

激活环境：
```bash
conda activate travel-agent
```

或者在 Git Bash 中：
```bash
source "C:/Users/apeng/anaconda3/etc/profile.d/conda.sh" && conda activate travel-agent
```

## 运行应用

```bash
# FastAPI 主应用（生产环境推荐）
python main.py

# 主旅行规划智能体（同步版本）
python graph/sync_run.py

# 后端服务（异步版本，支持 SSE 流式输出）
python async_run.py

# MCP 示例（MCP + LangGraph 集成）
cd learn/mcp/local
python mcp_agent_demo.py

# ReAct 模式示例
cd learn/react
python main.py

# 持久化示例（各种状态管理模式）
cd learn/persistence
python 01_load_to_db.py   # 基础 SQLite 持久化
python 02_interupt.py     # 处理中断
python 03_go_on.py        # 继续工作流
python 04_time_back.py    # 时间旅行（状态版本控制）
python 05_long_memory.py  # 长期记忆

# 流式输出示例
cd learn/stream_nodes
python main.py

# 人机交互示例
cd learn/human_in_loop
python server.py
```

## 架构设计

项目实现了 **规划-执行（Plan-and-Execute）** 多智能体系统，工作流程如下：

```
记忆检索 → 路由器 → 规划器 → 执行器 → 计划总结 → 记忆保存 → (循环回执行器或结束)
                        ↓
                   直接回答（针对非规划查询）
```

### 核心组件

**同步版本：**

**graph/workflow.py** - 同步 LangGraph 工作流定义，包含 5 个节点

**graph/nodes.py** - 同步节点实现：
- `router_node`: 使用 LLM 进行意图分类
- `planner_node`: 创建结构化 Plan（步骤数组）
- `executor_node`: 使用 Tavily Search API 执行任务
- `reflect_node`: 评估完成度，生成 Response
- `direct_answer_node`: 处理非规划查询
- `profile_node`: 更新长期用户画像

**graph/config.py** - 同步配置和状态定义：
- `PlanExecuteState`: TypedDict，包含 `question`、`plan`、`past_steps`、`response`、`route`、`messages`、`user_id`、`memories`
- LLM: DeepSeek Chat API（`deepseek-chat` 模型）
- 工具: TavilySearch（`max_results=5`）
- Pydantic 模型: `Plan`、`Response`

**异步版本（生产环境使用）：**

**graph/async_workflow.py** - 异步 LangGraph 工作流定义，包含 8 个节点：
- `memory_retrieve`: 长期记忆检索
- `router`: 意图分类
- `planner`: 生成规划
- `human_review`: 人机交互节点（等待用户确认规划）
- `executor`: 执行搜索
- `plan_summary`: 计划总结（反思评估）
- `direct_answer`: 直接回答
- `memory_save`: 记忆保存

**graph/async_nodes.py** - 异步节点实现（所有节点都是 async def）

**graph/async_config.py** - 异步配置：
- `async_llm`: 异步 LLM 配置，支持流式输出
- `AsyncTavilySearch`: 异步 Tavily Search 包装器（使用 httpx）
- `PlanExecuteState`: 异步状态定义，增加了 `memories` 字段

**graph/stream_callback.py** - Token 级别流式输出：
- `StreamCallback`: 自定义回调，捕获每个 token 并推送到队列
- `set_stream_queue()` / `get_stream_queue()`: 使用 ContextVar 存储队列
- `create_streaming_llm()`: 创建支持流式的 LLM

**graph/async_memory_rag.py** - 异步长期记忆 RAG：
- 使用本地模型 BAAI/bge-m3 进行向量嵌入
- 支持 macOS MPS 加速和 CUDA 加速
- 异步数据库读写操作

**流式输出工作流（learn/stream_nodes/）：**

**learn/stream_nodes/workflow.py** - 节点级流式输出示例：
- 使用 asyncio.Queue 在节点间传递 token
- StreamCallback 捕获 LLM 生成的每个 token

**learn/stream_nodes/main.py** - SSE 接口实现

**graph/prompts.py** - 所有系统提示词

**graph/function.py** / **graph/async_function.py** - 辅助函数

**graph/memory_rag.py** - 同步版本长期记忆

### 工具类

**utils/db_util.py** - 同步数据库会话管理：
- `DatabaseManager` 类管理 SQLAlchemy 引擎和会话
- `get_session()` 上下文管理器提供自动事务处理

**utils/async_db_util.py** - 异步数据库会话管理：
- 使用 SQLAlchemy 2.0 的 AsyncSession 和 asyncpg 驱动
- `AsyncDatabaseManager` 类
- `create_async_session()` 异步上下文管理器

**utils/logger_util.py** - Loguru 日志配置

**utils/id_util.py** - ID 生成器工具

**utils/parse_llm_json_util.py** - LLM JSON 响应解析工具

**utils/api_response_uti.py** - 统一响应封装

## 状态管理

### 短期记忆（检查点持久化）
- PostgreSQL 检查点，使用 `PostgresSaver`（同步）或 `AsyncPostgresSaver`（异步）
- 对话历史按 `thread_id` 持久化
- 允许跨会话恢复对话
- 表: `checkpoints`、`checkpoint_writes`、`checkpoint_blobs`、`checkpoint_migrations`

### 长期记忆
- 用户画像存储在 PostgreSQL（JSONB 列）
- 基于向量嵌入的 RAG 语义记忆存储在 `memory` 表
- 使用 pgvector 进行相似性搜索
- 支持本地嵌入模型 BAAI/bge-m3（首次使用自动下载约 2.2GB）

## API 接口

使用 FastAPI 构建的 REST API，前端通过 SSE 接收流式输出。

**api/assistant_api.py** - 路由层：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat` | POST | SSE 流式聊天接口 |
| `/api/v1/approve` | POST | 审批规划（批准/修改/取消） |
| `/api/v1/conversation/add` | POST | 新增对话 |
| `/api/v1/conversation/list` | POST | 查询对话列表 |
| `/api/v1/conversation/select` | POST | 查看对话内容 |
| `/api/v1/conversation/delete` | POST | 删除对话 |

**pojo/request/** - 请求参数定义：
- `ChatRequest`: 聊天请求（question, thread_id, user_id）
- `ApproveRequest`: 审批请求（approved, plan, cancelled）
- `ConversationAddRequest`: 新增对话请求
- `ConversationListRequest`: 对话列表请求
- `ConversationSelectRequest`: 查看对话请求
- `ConversationDeleteRequest`: 删除对话请求

**pojo/entity/** - 数据库实体：
- `Conversation`: 对话记录实体
- `Memory`: 记忆实体
- `UserProfile`: 用户画像实体

**service/assistant_service.py** - 业务层：
- `chat()`: 流式聊天实现，使用队列 + 后台任务
- `approve()`: 处理用户审批（批准/修改/取消）
- `add_conversation()`: 新增对话
- `list_conversations()`: 查询对话列表
- `select_conversation()`: 查看对话内容
- `delete_conversation()`: 删除对话

## 目录结构

```
graph/                    # 主智能体工作流
├── workflow.py           # 同步工作流定义
├── async_workflow.py     # 异步工作流定义
├── nodes.py              # 同步节点实现
├── async_nodes.py        # 异步节点实现
├── config.py             # 同步配置
├── async_config.py       # 异步配置
├── prompts.py            # 系统提示词
├── function.py           # 同步辅助函数
├── async_function.py     # 异步辅助函数
├── memory_rag.py         # 同步长期记忆
├── async_memory_rag.py   # 异步长期记忆
├── stream_callback.py    # 流式回调
├── sync_run.py           # 同步运行入口
└── async_run.py          # 异步运行入口

learn/
├── stream_nodes/         # Token 级别流式输出示例
│   ├── main.py           # SSE 流式服务
│   └── workflow.py       # 节点级流式工作流
├── human_in_loop/        # 人机交互示例
│   ├── workflow.py       # 人机交互工作流定义
│   ├── server.py         # FastAPI 服务
│   └── index.html        # 演示前端页面
├── persistence/          # 持久化示例
│   ├── 01_load_to_db.py  # SQLite 持久化
│   ├── 02_interupt.py    # 处理中断
│   ├── 03_go_on.py       # 继续工作流
│   ├── 04_time_back.py   # 时间旅行
│   └── 05_long_memory.py # 长期记忆
├── react/                # ReAct 模式示例
│   └── main.py           # ReAct 智能体实现
└── mcp/                  # MCP 协议集成
    ├── local/             # 本地 MCP 服务器
    │   ├── mcp_agent_demo.py
    │   └── pg_server.py
    ├── remote/            # 远程 MCP 工具
    │   ├── bing.py
    │   ├── map.py
    │   └── 12306.py
    └── rednote/           # 小红书 MCP

main.py                   # FastAPI 主应用入口
async_run.py              # 异步运行脚本（带 Windows 兼容）

api/                      # 路由层
service/                  # 业务层
pojo/                     # 实体类层
├── entity/               # 数据库实体
└── request/              # 请求参数
utils/                    # 工具类
tests/                    # 测试文件
docs/                     # 技术文档
ahead/                    # 前端页面
│   ├── index.html        # 聊天界面
│   ├── js/
│   │   ├── app.js        # 前端逻辑
│   │   └── api.js        # API 调用封装
│   └── css/
│       └── style.css     # 样式文件
logs/                     # 应用日志
```

## 关键技术

- **LangGraph** (~1.0.7): 工作流编排
- **DeepSeek API**: LLM 提供商（`deepseek-chat` 模型）
- **Tavily Search**: 用于旅行信息的网络搜索
- **PostgreSQL + pgvector**: 状态持久化和向量存储
- **FastAPI**: 异步 Web 框架，支持 SSE 流式输出
- **asyncpg**: 异步 PostgreSQL 驱动
- **SQLAlchemy 2.0**: 异步 ORM
- **HuggingFace Embeddings**: 本地向量嵌入（BAAI/bge-m3）
- **MCP 协议**: 标准化工具调用
- **Loguru**: 结构化日志
- **httpx**: 异步 HTTP 客户端
- **ContextVar**: 线程安全的上下文变量（用于流式输出）

## 前端实现

`ahead/` 目录包含完整的聊天界面：

| 文件 | 说明 |
|------|------|
| `index.html` | 主聊天界面（TravelAssistant 智能旅行助手） |
| `js/app.js` | 前端逻辑（消息处理、事件监听） |
| `js/api.js` | API 调用封装（SSE 连接管理） |
| `css/style.css` | 样式文件 |

**前端特性：**
- 左侧边栏（历史对话列表）
- 欢迎页面（功能介绍）
- SSE 流式接收消息
- Shift+Enter 换行发送

## 流式输出实现

项目实现了两种流式输出模式：

### 1. 节点级流式输出（learn/stream_nodes/）
- 使用 LangChain Callback 捕获 LLM token
- 通过 asyncio.Queue 在节点间传递数据
- SSE 推送到前端

### 2. Token 级别流式输出（生产环境）
- 使用 ContextVar 存储队列（避免序列化问题）
- StreamCallback 捕获每个 token
- 后台任务执行工作流，主任务消费队列
- 支持心跳保持连接

详细实现见 `docs/streaming_optimization.md` 和 `learn/stream_nodes/README.md`

## MCP 集成

`learn/mcp/` 目录包含完整的 MCP 学习指南和实现：

**本地 MCP (`learn/mcp/local/`):**
- `mcp_agent_demo.py`: MCP + LangGraph 入门示例
- `pg_server.py`: PostgreSQL MCP 服务器实现

**远程 MCP (`learn/mcp/remote/`):**
- `bing.py`: 必应搜索 MCP 客户端（使用 npx bing-cn-mcp）
- `map.py`: 地图 MCP 工具
- `12306.py`: 12306 火车票 MCP 工具

**小红书 MCP (`learn/mcp/rednote/`):**
- 集成小红书内容搜索功能
- 使用 `uvx --from xiaohongshu-automation xhs-mcp` 调用

## 人机交互（Human-in-the-Loop）

项目实现了基于 LangGraph `interrupt()` 的人机交互功能，允许用户在关键节点介入决策。

### 核心实现

**工作流节点 (`graph/async_nodes.py`):**
- `async_human_review_node`: 人机交互节点，使用 `interrupt()` 实现真正的节点内部中断
- 支持三种操作：批准执行、修改计划、取消任务
- 中断时会向前端发送 `waiting_for_approval` 类型的消息

**前端交互 (`ahead/js/app.js`):**
- 监听 `waiting_for_approval` 事件
- 显示审批弹窗，包含计划详情
- 支持「批准执行」「修改计划」「取消任务」三个按钮

**API 接口:**
- `POST /api/v1/approve`: 审批规划
  - `approved`: 是否批准
  - `plan`: 修改后的计划（可选）
  - `cancelled`: 是否取消

### 人机交互工作流

```
用户输入 → 记忆检索 → 路由器 → 规划器 → [人机交互: 等待用户确认]
                                                      ↓
                                              用户批准/修改/取消
                                                      ↓
执行器 → 计划总结 → 记忆保存 → 结束
```

### 独立示例

`learn/human_in_loop/` 目录包含完整的人机交互演示：
- `workflow.py`: 基础人机交互工作流（可直接运行测试）
- `server.py`: FastAPI 服务（带前端页面）
- `index.html`: 演示用前端页面

详细实现见 `docs/mcp_react_human_integration.md`

## 环境变量

`.env` 中必需：
```
POSTGRES_URI=postgresql://postgres:password@host:5432/postgres
ASYNC_POSTGRES_URI=postgresql+asyncpg://postgres:password@host:5432/postgres
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
TAVILY_API_KEY=tvly-xxx
```

## API 设计规范

### HTTP 方法选择

**优先使用 POST 方法进行所有 API 调用**，包括查询、新增、更新、删除操作。

### 请求参数定义

所有 POST 请求必须使用 Pydantic BaseModel 定义请求参数类，存放于 `pojo/request/` 目录。

### 响应格式

使用 `utils/api_response_uti.py` 中的 `build_response()` 函数统一封装响应。

## 重要模式

### LLM 响应的 JSON 解析
使用 `utils/parse_llm_json_util.py` 进行 LLM JSON 响应的健壮解析。

### 日志记录
`utils/logger_util.py` 中配置的 Loguru 日志器。

### 数据库会话管理

同步版本：
```python
from utils.db_util import create_session

with create_session() as session:
    # 数据库操作
```

异步版本：
```python
from utils.async_db_util import create_async_session

async with create_async_session() as session:
    # 异步数据库操作
```

### 状态更新
`messages` 字段使用 `Annotated[List[Tuple], operator.add]` 来累积对话历史。

## 测试

```bash
# 运行所有测试
pytest tests/

# 单独运行特定测试
pytest tests/test_memory_rag.py
pytest tests/test_async_layer.py
pytest tests/test_long_memory_integration.py
```

## 文档

项目包含丰富的技术文档，位于 `docs/` 目录：

- `long_memory_implementation.md`: 长期记忆实现详解（11步实施计划）
- `conversation_interface.md`: 对话接口设计说明
- `mcp_react_human_integration.md`: MCP、ReAct 与人机交互集成方案
- `executor_react_migration.md`: 执行器 ReAct 化改造方案

## 主应用入口

**main.py** - FastAPI 主应用入口，集成了对话 API 和生命周期管理：

- 自动管理应用启动和关闭事件
- 集成所有路由层和服务层
- 支持 SSE 流式输出
