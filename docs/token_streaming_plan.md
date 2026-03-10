# Token 级别流式输出改造计划

## 目标

为 TravelAgent 项目实现 token 级别的 SSE 流式输出，前端可以实时看到每个 token 的生成。

## 现状分析

### 已有的文件
1. **learn/stream_nodes/main.py** - 完整的 SSE 流式输出示例（已验证可用）
2. **graph/stream_callback.py** - 回调处理器（存在问题）
3. **graph/nodes.py** - 部分节点已修改（不完整）
4. **graph/workflow.py** - 同步 workflow
5. **graph/config.py** - LLM 配置（已开启 streaming=True）

### 存在的问题
1. `stream_callback.py` 中 `on_llm_new_token` 是同步方法，直接调用 `queue.put()` 可能导致问题
2. 只有 `router_node` 使用了流式 LLM，其他节点仍是同步调用
3. workflow 尚未改造为异步运行
4. 缺少 API 层来提供 SSE 接口

---

## 改造步骤

### 第一步：修复 stream_callback.py

```python
# graph/stream_callback.py

import asyncio
import os

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI


class StreamCallback(BaseCallbackHandler):
    """监听 LLM 的 token 生成事件"""

    def __init__(self, queue: asyncio.Queue, node_name: str):
        self.queue = queue
        self.node_name = node_name

    def on_llm_new_token(self, token: str, **kwargs):
        """LLM 每生成一个 token 就会调用这个方法"""
        # 使用 call_soon_threadsafe 确保线程安全
        asyncio.get_event_loop().call_soon_threadsafe(
            self.queue.put_nowait, {
                "type": "token",
                "node": self.node_name,
                "data": {"content": token}
            }
        )
```

### 第二步：修改 PlanExecuteState，添加 queue 字段

```python
# graph/config.py

class PlanExecuteState(TypedDict):
    # ... 现有字段 ...
    queue: asyncio.Queue  # 添加队列字段
```

### 第三步：修改所有节点，支持流式 LLM

```python
# graph/nodes.py

def router_node(state: PlanExecuteState):
    """路由节点：判断意图"""
    queue = state["queue"]  # 从 state 中获取 queue
    # ... 其他代码不变 ...

def direct_answer_node(state: PlanExecuteState):
    """直接回答：需要工具"""
    queue = state["queue"]
    llm = create_streaming_llm("direct_answer", queue)
    # ... 使用流式 LLM ...

def planner_node(state: PlanExecuteState):
    """规划节点"""
    queue = state["queue"]
    llm = create_streaming_llm("planner", queue)
    # ... 使用流式 LLM ...

def executor_node(state: PlanExecuteState):
    """执行节点：这里主要是搜索，可以不流式"""
    # 搜索不需要流式输出，保持不变
    # ...

def reflect_node(state: PlanExecuteState):
    """反思节点"""
    queue = state["queue"]
    llm = create_streaming_llm("reflect", queue)
    # ... 使用流式 LLM ...
```

### 第四步：改造 workflow 为异步版本

```python
# graph/workflow_async.py

import asyncio
from langgraph.graph import END, StateGraph, START

# 可以复用现有的 config 和 nodes
from graph.config import PlanExecuteState
from graph.nodes import router_node, planner_node, executor_node, direct_answer_node, reflect_node

workflow = StateGraph(PlanExecuteState)

# 添加节点（使用异步包装）
workflow.add_node("router", router_node)
workflow.add_node("planner", planner_node)
workflow.add_node("executor", executor_node)
workflow.add_node("direct_answer", direct_answer_node)
workflow.add_node("reflect", reflect_node)
# ... 其他边配置不变 ...

# 编译 workflow
app = workflow.compile()
```

### 第五步：创建 API 层 SSE 接口

```python
# api/stream.py

import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from graph.workflow_async import app
from graph.config import PlanExecuteState

router = APIRouter()


async def stream_chat(question: str, user_id: int = 1):
    queue = asyncio.Queue()
    workflow_done = False

    # 初始状态
    initial_state: PlanExecuteState = {
        "question": question,
        "user_id": user_id,
        "plan": [],
        "past_steps": [],
        "response": "",
        "route": "",
        "messages": [],
        "memories": [],
        "queue": queue
    }

    async def run_workflow():
        nonlocal workflow_done
        try:
            async for chunk in app.astream(initial_state):
                # 处理每个 chunk，提取 token
                # ...
                pass
        except Exception as e:
            await queue.put({"type": "error", "data": {"message": str(e)}})
        finally:
            await queue.put({"type": "workflow_end"})
            workflow_done = True

    # 生成器函数，参考 learn/stream_nodes/main.py 的实现
    async def event_generator():
        # ... 参考已有实现 ...
        pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 第六步：启动服务

```bash
# 修改 async_run.py 或新建入口
python -m uvicorn api.stream:app --reload
```

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `graph/stream_callback.py` | 修复 `on_llm_new_token` 使用 `call_soon_threadsafe` |
| `graph/config.py` | `PlanExecuteState` 添加 `queue` 字段 |
| `graph/nodes.py` | 所有 LLM 调用节点添加 queue 支持 |
| `graph/workflow_async.py` | 新建异步 workflow（可复用现有 workflow） |
| `api/stream.py` | 新建 SSE API 接口 |
| `main.py` 或 `async_run.py` | 添加路由，启动服务 |

---

## 注意事项

1. **渐进式改造**：可以先只改造 `direct_answer_node`，测试流式输出是否正常
2. **性能考虑**：`on_llm_new_token` 中不要做耗时操作
3. **错误处理**：确保 queue 相关操作有异常处理
4. **前端配合**：需要改造前端 SSE 接收逻辑

---

## 验证方法

1. 启动服务后访问 `/stream?question=xxx`
2. 观察返回的 SSE 事件中是否包含 token 事件
3. 验证每个 token 是否正确推送

---

## 参考资料

- `learn/stream_nodes/main.py` - 完整的 SSE 示例
- `learn/stream_nodes/workflow.py` - 工作流实现
