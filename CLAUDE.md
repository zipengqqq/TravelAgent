# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TravelAgent 是一个基于 Python 的 AI 旅行规划智能体，使用 LangGraph 和 LLM 技术构建。项目展示了先进的 AI 智能体模式，包括规划-执行、多智能体系统、记忆管理和 MCP（模型上下文协议）集成。

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
# 主旅行规划智能体
python graph/run.py

# MCP 示例（MCP + LangGraph 集成）
cd learn/mcps
python mcp_agent_demo.py

# ReAct 模式示例
cd learn/react
python map.py

# 持久化示例（各种状态管理模式）
cd learn/persistence
python 01_load_to_db.py   # 基础 SQLite 持久化
python 02_interupt.py     # 处理中断
python 03_go_on.py        # 继续工作流
python 04_time_back.py    # 时间旅行（状态版本控制）
python 05_long_memory.py  # 长期记忆
```

## 架构设计

项目实现了一个 **规划-执行（Plan-and-Execute）** 多智能体系统，工作流程如下：

```
路由器 → 规划器 → 执行器 → 反思器 → (循环回执行器或结束)
         ↓
    直接回答（针对非规划查询）
```

### 核心组件

**graph/run.py** - 主运行入口，启动旅行规划智能体

**graph/workflow.py** - 主 LangGraph 工作流定义，包含 5 个节点：
- `router`: 分类用户意图（规划 vs 直接回答）
- `planner`: 生成多步骤规划（使用结构化输出）
- `executor`: 使用 Tavily 搜索执行规划步骤
- `reflect`: 评估结果，决定继续或结束
- `direct_answer`: 处理非规划查询

**graph/nodes.py** - 节点实现：
- `router_node`: 使用 LLM 进行意图分类
- `planner_node`: 创建结构化 Plan（步骤数组）
- `executor_node`: 使用 Tavily Search API 执行任务
- `reflect_node`: 评估完成度，生成 Response（最终回答 + 剩余步骤）
- `profile_node`: 更新长期用户画像（已定义但未集成）

**graph/config.py** - 配置和状态定义：
- `PlanExecuteState`: TypedDict，包含 `question`、`plan`、`past_steps`、`response`、`route`、`messages`、`user_id`
- LLM: DeepSeek Chat API（`deepseek-chat` 模型）
- 工具: TavilySearch（`max_results=5`）
- Pydantic 模型: `Plan`、`Response`

**graph/prompts.py** - 所有系统提示词：
- 意图路由、直接对话、旅行规划、搜索查询生成、反思、摘要、用户画像

**graph/function.py** - 辅助函数：
- `route_by_intent()`: 基于 state.route 的条件路由
- `should_end()`: 工作流终止逻辑
- `abstract()`: 搜索结果摘要

**graph/memory_rag.py** - 基于 RAG 的长期记忆：
- `MemoryRAG` 类用于语义记忆存储/检索
- 使用 OpenAI embeddings（`text-embedding-3-small`）
- PostgreSQL + pgvector 进行相似性搜索
- 方法: `add_memory()`、`search_memories()`

### 工具类

**utils/db_util.py** - 数据库会话管理：
- `DatabaseManager` 类管理 SQLAlchemy 引擎和会话
- `get_session()` 上下文管理器提供自动事务处理

**utils/logger_util.py** - Loguru 日志配置

**utils/id_util.py** - ID 生成器工具

**utils/parse_llm_json_util.py** - LLM JSON 响应解析工具

## 状态管理

### 短期记忆
- PostgreSQL 检查点，使用 `PostgresSaver`
- 对话历史按 `thread_id` 持久化
- 允许跨会话恢复对话
- 表: `checkpoints`、`checkpoint_writes`、`checkpoint_blobs`、`checkpoint_migrations`（由 LangGraph 自动创建）

### 长期记忆
- 用户画像存储在 PostgreSQL（JSONB 列）
- 基于向量嵌入的 RAG 语义记忆存储在 `memory` 表
- `entity/user_profiles_entity.py` 定义用户画像表结构
- `entity/memory_entity.py` 定义记忆表结构

## 目录结构

```
graph/          # 主智能体工作流（workflow.py, nodes.py, config.py, prompts.py, memory_rag.py, run.py, function.py）
entity/         # 数据库模型（SQLAlchemy）
utils/          # 数据库会话、日志、ID 生成器、JSON 解析器
learn/          # 学习示例（MCP、持久化、ReAct）
tests/          # 测试文件（test_memory_rag.py）
assets/         # 静态资源（流程图）
logs/           # 应用日志（由 loguru 生成）
api/            # 路由层
service/        # 业务层
ahead/          # 前端页面，包括html、css、javascript等
```

## 关键技术

- **LangGraph** (~1.0.7): 工作流编排
- **DeepSeek API**: LLM 提供商（`deepseek-chat` 模型）
- **Tavily Search**: 用于旅行信息的网络搜索
- **PostgreSQL**: 状态持久化和向量存储（pgvector）
- **MCP 协议**: 标准化工具调用（通过 PostgreSQL 服务器演示）
- **Loguru**: 结构化日志（10MB 轮换，7 天保留）

## MCP 集成

`learn/mcp/` 目录包含完整的 MCP 学习指南和 PostgreSQL MCP 服务器实现。查看 `learn/mcp/LEARNING_GUIDE.md` 了解：
- 理解 MCP 协议及其相对于传统 API 调用的优势
- 设置和运行 MCP 服务器
- 将 MCP 与 LangGraph 工作流集成
- 扩展到自定义工具（如地图 API）

关键文件：
- `learn/mcp/pg_server.py`: PostgreSQL MCP 服务器，带 SQL 执行工具
- `learn/mcp/mcp_agent_demo.py`: MCP + LangGraph 集成演示，包含 `MCPClient` 和 `MCPToolNode` 类

## 环境变量

`.env` 中必需：
```
POSTGRES_URI=postgresql://postgres:password@host:5432/postgres
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
TAVILY_API_KEY=tvly-xxx
```

## 重要模式

### LLM 响应的 JSON 解析
使用 `utils/parse_llm_json_util.py` 进行 LLM JSON 响应的健壮解析。它处理：
- Markdown 代码块（```json ... ```）
- "json:" 前缀
- 格式错误的响应

### 日志记录
`utils/logger_util.py` 中配置的 Loguru 日志器。日志输出到控制台和 `logs/app/` 目录，支持轮换。

### 状态更新
`messages` 字段使用 `Annotated[List[Tuple], operator.add]` 来累积对话历史。

### 数据库会话管理
使用 `utils/db_util.py` 的 `create_session()` 上下文管理器进行所有数据库操作，自动处理事务提交和回滚：

```python
from utils.db_util import create_session
from entity.user_profiles_entity import UserProfile

# 新增记录
with create_session() as session:
    record = UserProfile(
        user_id=user_id,
        profiles=data,
    )
    session.add(record)

# 更新记录
with create_session() as session:
    session.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).update({"profiles": data})

# 查询记录
with create_session() as session:
    profile = session.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()
```

### 测试
`tests/test_memory_rag.py` 包含 RAG 长期记忆的测试用例。
