# 代码重构计划：极简 ReAct 主循环架构

## 一、重构目标

将现有的多节点 LangGraph 工作流重构为**极简 ReAct 主循环架构**，实现：
- ✅ **0 修改扩展**：新增功能只需添加工具，无需修改图结构
- ✅ **极简状态**：状态只保留 `messages`，其他交给工具参数和 LLM Context
- ✅ **工具即功能**：记忆、路由、规划全部封装为工具
- ✅ **真正插拔**：MCP 工具热加载，即插即用

---

## 二、当前架构 vs 目标架构

### 当前架构（8 节点 + 10 状态字段）

```
┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌─────────────┐
│memory_retrie│ -> │  router  │ -> │ planner  │ -> │human_review │
└─────────────┘    └──────────┘    └──────────┘    └─────────────┘
                                                             │
       ┌─────────────────────────────────────────────────────┘
       ▼
┌─────────────┐    ┌─────────────┐    ┌───────────┐    ┌───────────┐
│  executor   │ -> │plan_summary │ -> │direct_ans │ -> │memory_save│
└─────────────┘    └─────────────┘    └───────────┘    └───────────┘

状态字段：question, plan, past_steps, response, route, messages, user_id, memories, approved, cancelled
```

### 目标架构（1 Agent + N 工具）

```
┌──────────────────────────────────────────────────────────────┐
│                    ReAct Agent (create_react_agent)          │
│                                                              │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│   │  Router  │    │  Memory  │    │ Executor │   ...       │
│   │  Tool   │    │  Tool    │    │  Tool    │             │
│   └──────────┘    └──────────┘    └──────────┘             │
│                                                              │
└──────────────────────────────────────────────────────────────┘

状态字段：messages (对话历史)
```

---

## 三、重构步骤（分 6 阶段）

### Phase 1：创建工具层（Tool Layer）

#### 1.1 创建路由工具 `tools/router_tool.py`

将路由器节点改造为工具：

```python
class RouterTool(BaseTool):
    """意图分类工具 - 判断用户意图"""
    name: str = "route_intent"
    description: str = """
    判断用户意图，返回下一步操作类型：
    - plan: 用户要求制定计划/规划行程
    - chat: 闲聊、问答、解释等
    - human_review: 需要用户确认计划
    """

    def _run(self, question: str, memories: List[str]) -> str:
        # 调用 LLM 进行意图分类
        # 返回 JSON: {"route": "plan" | "chat" | "human_review"}
```

#### 1.2 创建记忆工具 `tools/memory_tool.py`

将记忆节点改造为工具（合并检索和保存）：

```python
class MemoryTool(BaseTool):
    """长期记忆工具 - 检索和保存记忆"""
    name: str = "memory"
    description: str = """
    搜索用户的长期记忆，或保存对话到记忆库。
    用于了解用户的偏好、历史交互记录。
    """

    def _run(self, action: str, question: str, response: str = "") -> str:
        # action: "search" | "save"
        # search: 检索相关记忆
        # save: 保存对话到记忆
```

#### 1.3 创建规划工具 `tools/planner_tool.py`

将规划器节点改造为工具：

```python
class PlannerTool(BaseTool):
    """任务规划工具 - 生成执行计划"""
    name: str = "plan_task"
    description: str = """
    根据用户需求生成多步骤执行计划。
    返回计划列表，每个步骤描述一个具体任务。
    """

    def _run(self, question: str) -> str:
        # 调用 LLM 生成计划
        # 返回 JSON: {"steps": ["步骤1", "步骤2", ...]}
```

#### 1.4 创建人机交互工具 `tools/human_interaction_tool.py`

将人机交互节点改造为工具：

```python
class HumanInteractionTool(BaseTool):
    """人机交互工具 - 等待用户确认"""
    name: str = "human_interaction"
    description: str = """
    请求用户确认或审批。
    发送计划给用户，等待批准/修改/取消。
    """

    def _run(self, plan: List[str], thread_id: str) -> str:
        # 发送待审批计划到前端
        # 使用 interrupt() 等待用户响应
        # 返回用户决策
```

---

### Phase 2：创建主 Agent

#### 2.1 创建 `agents/travel_agent.py`

使用 `create_react_agent` 构建主 Agent：

```python
from langchain.agents import create_react_agent
from langgraph.prebuilt import create_react_agent

# 合并所有工具
all_tools = [
    # 记忆工具
    MemoryTool(),
    # 路由工具
    RouterTool(),
    # 规划工具
    PlannerTool(),
    # 人机交互工具
    HumanInteractionTool(),
    # MCP 工具（动态加载）
    *await get_mcp_tools()
]

# 系统提示词
system_prompt = """你是一个智能旅行助手。

## 工作流程
1. 首先使用 memory 工具搜索用户历史偏好
2. 使用 route_intent 工具判断用户意图
3. 如果需要规划，使用 plan_task 生成计划
4. 使用 human_interaction 等待用户确认
5. 使用 MCP 工具执行具体任务
6. 总结结果并回复用户

## 重要规则
- 每次工具调用后，根据结果决定下一步
- 如果需要用户确认，必须调用 human_interaction
- 完成任务后，使用 memory 工具保存对话
"""

# 创建 Agent
travel_agent = create_react_agent(
    llm,
    tools=all_tools,
    system_prompt=system_prompt,
    middleware=[log_tool_call]
)
```

---

### Phase 3：简化状态管理

#### 3.1 极简状态定义

```python
class AgentState(TypedDict):
    """极简状态 - 只有对话历史"""
    messages: Annotated[List[BaseMessage], add_messages]
```

#### 3.2 移除冗余字段

删除以下状态字段：
- ❌ `question` → 通过 `messages` 获取最后一条用户消息
- ❌ `plan` → 通过工具参数传递
- ❌ `past_steps` → 通过工具参数传递
- ❌ `response` → 通过 `messages` 获取
- ❌ `route` → 通过路由工具返回
- ❌ `memories` → 通过记忆工具返回
- ❌ `approved` / `cancelled` → 通过人机交互工具返回
- ✅ 保留 `user_id` → 放在 config 中，不进入 state

---

### Phase 4：改造服务层

#### 4.1 重构 `AssistantService.chat()`

```python
async def chat(self, request: ChatRequest):
    """极简 Agent 对话"""
    await self._ensure_initialized()

    # 构建初始消息
    messages = [HumanMessage(content=request.question)]

    # 配置
    config = {
        "configurable": {
            "thread_id": request.thread_id,
            "user_id": request.user_id
        }
    }

    # 执行 Agent
    async for event in self._app.astream(
        {"messages": messages},
        config=config
    ):
        # 流式输出
        yield event
```

#### 4.2 改造审批流程

人机交互工具内部使用 `interrupt()` 暂停，审批 API 直接更新状态并继续：

```python
async def approve(self, request: ApproveRequest):
    """用户审批"""
    # 更新状态
    await self._app.aupdate_state(
        config,
        {"user_decision": request.dict()}
    )
    # 继续执行
    async for event in self._app.astream(None, config=config):
        yield event
```

---

### Phase 5：目录结构重构

```
graph/
├── __init__.py
├── config.py              # LLM 配置
├── state.py               # 极简状态定义
├── prompts.py             # 系统提示词
│
├── tools/                 # 工具层（新增）
│   ├── __init__.py
│   ├── router_tool.py    # 路由工具
│   ├── memory_tool.py    # 记忆工具
│   ├── planner_tool.py   # 规划工具
│   ├── human_tool.py     # 人机交互工具
│   └── tool_builder.py   # 工具构建器（合并所有工具）
│
├── agents/                # Agent 层（新增）
│   ├── __init__.py
│   └── travel_agent.py   # 主 Agent
│
├── workflow.py           # 简化后的工作流（可选，或直接使用 Agent）
└── run.py                # 运行入口
```

---

### Phase 6：渐进式迁移策略

#### 6.1 策略：双轨并行

为了不影响现有功能，采用双轨并行策略：

1. **保留现有工作流**（不做修改）
2. **新建 ReAct 架构**（作为新版本）
3. **通过配置切换**

```python
# config.py
AGENT_TYPE = "react"  # 或 "legacy"
```

#### 6.2 迁移顺序

| 步骤 | 内容 | 影响 |
|------|------|------|
| 1 | 创建 `graph/tools/` 工具层 | 低 |
| 2 | 创建 `graph/agents/` Agent 层 | 低 |
| 3 | 改造 `AssistantService` 支持双模式 | 中 |
| 4 | 切换生产环境到 ReAct 模式 | 高 |
| 5 | 删除旧代码（旧节点、状态字段） | 高 |

---

## 四、重构后的优势

### 4.1 扩展性对比

| 场景 | 重构前 | 重构后 |
|------|--------|--------|
| 新增 MCP 工具 | 修改 tool_registry + 可能改图 | 只在 tool_registry 添加 |
| 新增记忆类型 | 新增记忆节点 + 修改图 | 新增工具方法 |
| 新增路由规则 | 修改路由器节点 + 改条件边 | 修改路由工具 prompt |
| 新增人机交互 | 新增节点 + 改图结构 | 新增/修改人机交互工具 |

### 4.2 状态复杂度对比

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| 状态字段数 | 10 | 1 (messages) |
| 节点数 | 8 | 0 (由 Agent 内部管理) |
| 条件边数 | 4 | 0 |
| 代码行数（工作流） | ~80 | ~10 |

---

## 五、风险与注意事项

### 5.1 潜在风险

1. **LLM 不稳定**：完全依赖 LLM 进行路由/规划，可能出现意外行为
   - ✅ 缓解：工具 description 详细描述，system prompt 明确引导

2. **工具调用循环**：LLM 可能反复调用同一工具
   - ✅ 缓解：添加 max_iterations 限制，工具返回时包含上下文

3. **调试困难**：黑盒 Agent 难以追踪问题
   - ✅ 缓解：使用 middleware 记录完整调用链

### 5.2 兼容性考虑

- 保留旧版工作流，通过配置切换
- 审批 API 兼容现有前端
- 对话历史兼容（messages 格式一致）

---

## 六、总结

| 项目 | 重构前 | 重构后 |
|------|--------|--------|
| 架构模式 | 多节点 StateGraph | create_react_agent |
| 状态管理 | 10 字段臃肿 State | 1 字段极简 State |
| 功能扩展 | 修改图结构 + 改代码 | 添加工具即可 |
| 人机交互 | 独立节点 + 条件边 | 工具内部 interrupt() |
| 记忆功能 | 独立节点 | 工具封装 |

**核心理念**：将控制权交给大模型，代码只负责提供工具和环境。
