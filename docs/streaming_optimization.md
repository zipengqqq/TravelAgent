# 回复助手流式输出性能优化方案

## 一、问题分析

### 1.1 当前性能瓶颈

用户反馈无论是简单问题还是复杂的旅游规划问题，都需要等待很久才能看到输出文字。经代码分析，主要瓶颈如下：

#### 问题 1：LLM 调用使用 `ainvoke` 而非 `astream`

**位置**: `graph/async_nodes.py`

```python
# 当前实现 - 等待完整响应
async def async_direct_answer_node(state: PlanExecuteState):
    raw = await async_llm.ainvoke(prompt)  # 阻塞等待完整响应
    return {"response": raw.content, ...}
```

**问题**:
- LLM 配置了 `streaming=True`，但所有节点都使用 `ainvoke()` 而非 `astream()`
- `ainvoke()` 会等待整个响应生成完毕才返回
- 用户必须等待 LLM 完全生成内容后才能看到任何输出

#### 问题 2：流式输出仅在节点级别

**位置**: `service/assistant_service.py:chat()`

```python
# 当前实现 - 节点级别流式输出
async for event in self._app.astream(state, config=config):
    for node_name, node_output in event.items():
        if node_name == "direct_answer":
            response = node_output.get("response", "")
            if response:
                yield {"type": "chunk", "data": {"response": response}}
```

**问题**:
- SSE 流式输出按节点发送事件
- 节点内部的 LLM 响应仍是整体返回
- 没有 token 级别的流式输出

#### 问题 3：搜索摘要生成也调用 LLM

**位置**: `graph/async_nodes.py:async_executor_node()` 和 `graph/async_function:async_abstract()`

```python
# 每次执行都需要调用 LLM 生成摘要
result_str = await async_abstract(result_str)
```

**问题**:
- 每个执行步骤都需要额外的 LLM 调用来生成摘要
- 对于多步骤规划问题，会累积多个 LLM 调用延迟

#### 问题 4：工作流顺序执行

**位置**: `graph/async_workflow.py`

当前工作流设计为顺序执行：
```
memory_retrieve → router → [planner → executor → reflect]*
```

**问题**:
- 没有利用并行化机会
- 例如：记忆检索可以与 LLM 调用并行

### 1.2 延迟构成

| 操作 | 预计延迟 | 次数 |
|------|---------|------|
| 记忆检索 | ~200ms | 1 |
| 路由 LLM 调用 | ~500ms | 1 |
| 直接回答 LLM 调用 | ~2-5s | 1 (简单问题) |
| 规划 LLM 调用 | ~1-2s | 1 |
| 执行循环（每步）: | | |
|  - 搜索关键词 LLM | ~500ms | N |
|  - Tavily 搜索 | ~1-2s | N |
|  - 摘要 LLM | ~1s | N |
|  - 反思 LLM | ~1s | N |
| 记忆保存 | ~200ms | 1 |

**简单问题总延迟**: ~3-6s
**复杂问题（3步）总延迟**: ~10-20s

---

## 二、优化方案

### 方案 1：实现 Token 级别流式输出（核心优化）

**优先级**: P0（必须实现）

#### 2.1.1 修改异步节点，使用 `astream`

流式节点文件 `graph/async_nodes.py`:

```python
import asyncio
from graph.async_config import async_llm
from utils.parse_llm_json_util import parse_llm_json
from utils.logger_util import logger

async def streaming_direct_answer_node(state: PlanExecuteState):
    """直接回答 - Token 级别流式输出"""
    logger.info("🚀直接回答中（流式）")
    question = state["question"]

    messages = "\n".join([f"{role}: {msg}" for role, msg in state["messages"]])

    prompt = direct_answer_prompt.format(
        user_request=question,
        messages=messages,
        memories=state.get("memories", [])
    )

    # 使用 astream 实现 token 级别流式
    chunks = []
    async for chunk in async_llm.astream(prompt):
        content = chunk.content
        if content:
            chunks.append(content)
            # 实时输出 chunk
            yield {"type": "token", "data": {"content": content}}

    full_response = "".join(chunks)
    return {
        "response": full_response,
        "messages": [("user", question), ("assistant", full_response)]
    }
```

**注意**: LangGraph 节点返回值必须是字典，不能直接 yield。需要使用 `Send` 机制或自定义回调。

#### 2.1.2 使用 LangGraph 的流式回调

创建 `graph/streaming_callback.py`:

```python
from langchain_core.callbacks import BaseCallbackHandler
from typing import Any, Dict, List

class TokenStreamCallback(BaseCallbackHandler):
    """Token 流式输出回调"""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def on_llm_new_token(self, token: str, **kwargs):
        """每当生成新 token 时调用"""
        await self.queue.put({
            "type": "token",
            "data": {"content": token}
        })

    async def on_llm_end(self, response: Any, **kwargs):
        """LLM 完成时调用"""
        await self.queue.put({"type": "llm_end"})
```

#### 2.1.3 修改 Service 层

```python
async def chat(self, request: ChatRequest):
    """流式 chat 实现 - Token 级别"""
    await self._ensure_initialized()

    question = request.question
    thread_id = request.thread_id
    user_id = request.user_id

    state = {
        "question": question,
        "plan": [],
        "past_steps": [],
        "response": "",
        "route": "",
        "messages": [],
        "user_id": user_id,
        "memories": [],
    }

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [TokenStreamCallback(self._queue)]  # 添加流式回调
    }

    # 创建事件队列用于收集流式输出
    self._queue = asyncio.Queue()

    # 启动工作流任务
    workflow_task = asyncio.create_task(self._app.ainvoke(state, config=config))

    # 持续输出队列中的事件
    while True:
        # 从队列获取事件（带超时）
        try:
            event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            yield event
        except asyncio.TimeoutError:
            # 检查工作流是否完成
            if workflow_task.done():
                # 获取最终状态并输出
                final_state = workflow_task.result()
                yield {
                    "type": "end",
                    "data": {
                        "thread_id": thread_id,
                        "response": final_state.get("response", ""),
                    }
                }
                break
```

**预期效果**:
- 简单问题：用户立即看到第一个 token，不再等待 2-5 秒
- 用户体验提升：打字机效果，实时反馈

---

### 方案 2：优化搜索摘要生成

**优先级**: P1（建议实现）

#### 2.2.1 减少 LLM 调用

**当前问题**: 每个执行步骤都需要调用 LLM 生成摘要

**优化方案 A**: 直接使用搜索结果
```python
async def async_executor_node(state: PlanExecuteState):
    # ... 搜索代码 ...

    # 不再调用 async_abstract，直接使用 JSON 结果
    # 或者只提取关键信息
    simple_result = {
        "task": task,
        "results_count": len(search_result.get("results", [])),
        # 只提取前几个结果的标题和摘要
        "top_results": search_result.get("results", [])[:3]
    }

    return {
        "past_steps": [(task, json.dumps(simple_result, ensure_ascii=False))],
        "plan": plan[1:]
    }
```

**优化方案 B**: 批量摘要
- 收集所有步骤的搜索结果
- 最后一次性生成摘要

**预期效果**:
- 每个执行步骤减少 ~1s 延迟
- 3 步规划可减少 ~3s 总延迟

---

### 方案 3：并行化独立操作

**优先级**: P2（可选实现）

#### 2.3.1 记忆检索与路由并行

```python
# 在工作流中添加并行边
from langgraph.graph import END, StateGraph, START

# 修改工作流结构
workflow.add_edge(START, "parallel_start")

# 并行执行记忆检索和用户意图预判（如果可以预先判断）
```

**注意**: 当前记忆检索是路由的前置条件，可能需要调整逻辑

#### 2.3.2 多个搜索查询并行

对于复杂的规划问题，可以将多个独立的搜索查询并行执行：

```python
async def parallel_executor_node(state: PlanExecuteState):
    plan = state['plan']

    # 收集所有搜索任务
    search_tasks = []
    for task in plan:
        # 生成搜索关键词
        keywords = await async_llm.ainvoke(search_query_prompt.format(task=task))
        search_tasks.append(async_tavily_tool.ainvoke(keywords.content.strip()))

    # 并行执行所有搜索
    results = await asyncio.gather(*search_tasks)

    return {"past_steps": list(zip(plan, results)), "plan": []}
```

**预期效果**:
- N 个搜索步骤并行执行，延迟从 N × 时间 减少到 1 × 时间
- 3 步搜索可从 ~6-9s 减少到 ~2-3s

---

### 方案 4：缓存优化

**优先级**: P2（可选实现）

#### 2.4.1 向量检索结果缓存

对于相同或相似的用户问题，缓存记忆检索结果：

```python
import hashlib
from functools import lru_cache

@lru_cache(maxsize=100)
def get_memory_cache_key(question: str, user_id: int) -> str:
    return hashlib.md5(f"{user_id}:{question}".encode()).hexdigest()

async def async_memory_retrieve_node(state: PlanExecuteState):
    user_id = state["user_id"]
    question = state["question"]

    cache_key = get_memory_cache_key(question, user_id)
    # 检查缓存...
```

#### 2.4.2 LLM 响应缓存

对于简单的直接回答问题，可以缓存响应（需要考虑时效性）。

---

### 方案 5：智能降级

**优先级**: P1（建议实现）

#### 2.5.1 路由节点快速预判

在路由节点中，对于明显简单的问候类问题，可以直接跳过记忆检索：

```python
async def async_router_node(state: PlanExecuteState):
    # 添加快速预判逻辑
    simple_patterns = ["你好", "hello", "在吗", "thanks", "谢谢"]
    question = state["question"].lower()

    if any(p in question for p in simple_patterns):
        return {"route": "direct_answer"}

    # 正常路由逻辑...
```

#### 2.5.2 限制搜索深度

根据问题复杂度调整搜索参数：
- 简单问题：`max_results=2`, `search_depth="basic"`
- 复杂问题：`max_results=5`, `search_depth="advanced"`

---

## 三、实施路线图

### 阶段 1：核心流式输出（1-2 天）
- [ ] 创建 `graph/streaming_callback.py`
- [ ] 修改 `service/assistant_service.py` 实现队列机制
- [ ] 修改前端代码处理 token 流式事件
- [ ] 测试验证

**预期收益**: 解决用户最痛心的等待问题，简单问题响应延迟从 3-6s 降低到立即显示

### 阶段 2：搜索摘要优化（1 天）
- [ ] 修改 `graph/async_nodes.py:async_executor_node`
- [ ] 测试搜索结果质量
- [ ] 调整提示词

**预期收益**: 每步骤减少 ~1s 延迟

### 阶段 3：并行化优化（1-2 天）
- [ ] 实现搜索并行执行
- [ ] 测试并发控制
- [ ] 监控 API 速率限制

**预期收益**: 多步骤问题延迟显著降低

### 阶段 4：缓存和智能降级（1 天）
- [ ] 实现记忆检索缓存
- [ ] 添加路由快速预判
- [ ] A/B 测试效果

**预期收益**: 常见问题响应更快

---

## 四、前端适配要求

### 4.1 SSE 事件处理更新

```javascript
// 前端代码需要处理新的 token 事件类型
const eventSource = new EventSource('/api/v1/chat');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'token':
            // 追加 token 到当前响应
            appendToken(data.data.content);
            break;
        case 'chunk':
            // 兼容旧版 - 完整内容块
            appendFullResponse(data.data.response);
            break;
        case 'node':
            // 节点进度通知
            showProgress(data.node, data.data);
            break;
        case 'end':
            // 对话结束
            eventSource.close();
            break;
        case 'error':
            // 错误处理
            handleError(data.data.message);
            break;
    }
};

function appendToken(token) {
    // 实现打字机效果
    currentResponseElement.textContent += token;
    // 自动滚动到底部
    scrollToBottom();
}
```

### 4.2 UI 改进建议

1. **打字机动画**: 使用 CSS 动画增强视觉效果
2. **进度指示器**: 显示当前执行节点
   ```
   [记忆检索] → [路由分析] → [回答生成]...
   ```
3. **中断功能**: 允许用户取消长时间运行的任务

---

## 五、性能预期

### 优化前后对比

| 场景 | 优化前 | 优化后（方案1+2） | 优化后（全方案） |
|------|--------|------------------|-----------------|
| 简单问候 | 3-5s | ~0.5s（首token立即） | ~0.3s |
| 直接回答问题 | 3-6s | ~1s（流式开始） | ~0.8s |
| 单步搜索规划 | 5-8s | ~3s | ~2s |
| 三步搜索规划 | 10-20s | ~6s | ~3s |

### 用户体验提升

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 首次可见时间 | 3-6s | <0.5s |
| 流畅度 | 卡顿感强 | 打字机效果 |
| 可控性 | 无法取消 | 可中断 |

---

## 六、技术风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Token 流式处理增加复杂度 | 中 | 充分测试，做好错误处理 |
| 并发搜索可能触发 API 限流 | 中 | 实现速率限制，优雅降级 |
| 缓存导致数据过时 | 低 | 设置合理的 TTL |
| 前端适配工作量 | 中 | 保持兼容性，渐进式增强 |

---

## 七、总结

当前系统的主要性能瓶颈在于：

1. **LLM 调用未使用流式输出** - 这是用户体验最核心的问题
2. **搜索摘要额外调用 LLM** - 增加不必要的延迟
3. **顺序执行未利用并行化** - 多步骤问题延迟累积

**建议优先实施**:
1. 方案 1（Token 级别流式输出）- 解决用户最痛心的问题
2. 方案 2（搜索摘要优化）- 显著减少多步骤延迟

这两项优化可以解决 80% 的用户体验问题，且实施风险可控。
