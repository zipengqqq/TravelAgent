# 反思节点最终回复流式输出技术方案

## 一、问题分析

### 1.1 当前问题

在 `async_reflect_node` 反思节点中，当判断任务完成时，直接返回完整的 response 字符串：

```python
# graph/async_nodes.py:async_reflect_node (当前实现)
if result.response and result.response.strip() != "":
    logger.info("任务完成，生成最终回答。")
    return {
        "response": result.response,  # 完整字符串，无流式输出
        "plan": [],
        "messages": [("user", state['question']), ("assistant", result.response)]
    }
```

**问题**：
- 最终回复是一个完整的字符串，没有流式输出
- 用户需要等待整个反思节点执行完毕才能看到回复
- 影响了用户体验，特别是长回复场景

### 1.2 期望效果

当反思节点判断任务完成时，最终回复应该流式输出到前端，实现打字机效果。

---

## 二、方案设计

### 方案：复用现有 StreamCallback 机制

#### 2.1 核心思路

利用已有的 `StreamCallback` 回调机制，在反思节点生成最终回复时：
1. 调用 LLM 时启用流式输出（`streaming=True`）
2. 通过回调将每个 token 推送到队列
3. 前端实时消费队列中的 token

#### 2.2 实现步骤

**Step 1：修改反思节点，添加最终回复流式输出逻辑**

```python
# graph/async_nodes.py

async def async_reflect_node(state: PlanExecuteState):
    """重新规划器：根据执行结果，判断是否需要重新规划"""
    logger.info(f"🚀反思节点正在判断是否需要重新规划")
    # ... 现有代码 ...

    # 使用流式 LLM
    if queue:
        streaming_llm = create_streaming_llm("reflect")
        raw = await streaming_llm.ainvoke(prompt)
    else:
        raw = await async_llm.ainvoke(prompt)

    try:
        data = parse_llm_json(raw.content)
        logger.info(f"大模型结果为：{data}")
        # 改为字典访问
        response_text = data.get("response", "")
        next_plan = data.get("next_plan", [])
    except Exception as e:
        logger.error(f"反思节点解析失败：{e}")
        response_text = ""
        next_plan = []

    # 如果有最终回复，判断是否需要流式输出
    if response_text and response_text.strip() != "":
        logger.info("任务完成，生成最终回答。")

        # 如果有流式队列，使用流式输出最终回复
        if queue:
            # 最终回复已在上面 LLM 调用时流式输出了
            # 这里直接返回完整回复
            return {
                "response": response_text,
                "plan": [],
                "messages": [("user", state['question']), ("assistant", response_text)]
            }
        else:
            return {
                "response": response_text,
                "plan": [],
                "messages": [("user", state['question']), ("assistant", response_text)]
            }
    else:
        logger.info(f"反思节点决策：继续执行，剩余计划：{len(next_plan)}个步骤")
        logger.info(f"剩余计划：{next_plan}")
        return {"plan": next_plan}
```

**关键点**：当使用 `streaming_llm`（带 `streaming=True`）调用 LLM 时，`StreamCallback` 会自动捕获每个 token 并推送到队列。前端已经可以消费这些 token。

#### 2.3 验证现有机制

现有 `stream_callback.py` 中的 `StreamCallback` 已经可以处理反思节点的流式输出：

```python
# graph/stream_callback.py

class StreamCallback(BaseCallbackHandler):
    """自定义回调，用于捕获每个 token 并推送到队列"""

    def __init__(self, node_name: str):
        self.node_name = node_name

    def on_llm_new_token(self, token: str, **kwargs):
        """LLM 生成新 token 时调用"""
        if token:
            queue = get_stream_queue()
            if queue:
                queue.put_nowait({
                    "type": "token",
                    "node": self.node_name,
                    "data": {"content": token}
                })
```

当 `async_reflect_node` 使用 `create_streaming_llm("reflect")` 时：
- LLM 的每个 token 都会触发 `on_llm_new_token`
- token 会被推送到队列
- 前端通过 SSE 消费队列

---

## 三、简化方案（推荐）

实际上，当前代码已经支持流式输出！只需确保：

1. **确认队列存在**：当用户通过 SSE 连接时，`queue` 不为空
2. **使用 streaming_llm**：当前代码已经这样做了

只需将解析方式改为字典访问即可：

```python
# 修改后的 async_reflect_node 关键部分

try:
    data = parse_llm_json(raw.content)
    logger.info(f"大模型结果为：{data}")
    # 使用字典访问，避免 Pydantic 版本问题
    response_text = data.get("response", "")
    next_plan = data.get("next_plan", [])
except Exception as e:
    logger.error(f"反思节点解析失败：{e}")
    response_text = ""
    next_plan = []

if response_text and response_text.strip() != "":
    logger.info("任务完成，生成最终回答。")
    return {
        "response": response_text,
        "plan": [],
        "messages": [("user", state['question']), ("assistant", response_text)]
    }
else:
    logger.info(f"反思节点决策：继续执行，剩余计划：{len(next_plan)}个步骤")
    return {"plan": next_plan}
```

---

## 四、测试验证

### 4.1 测试步骤

1. 启动后端服务
2. 打开前端页面
3. 发送一个问题，如"我想去北京玩一天"
4. 观察最终回复是否流式输出

### 4.2 预期行为

- 反思节点调用 LLM 时，每个 token 会实时推送到队列
- 前端收到 SSE 事件，打字机效果显示回复
- 日志中可以看到 `StreamCallback` 捕获的 token

### 4.3 调试方法

在 `stream_callback.py` 中添加调试日志：

```python
def on_llm_new_token(self, token: str, **kwargs):
    """LLM 生成新 token 时调用"""
    if token:
        logger.info(f"[StreamCallback] 捕获 token: {token[:20]}...")
        queue = get_stream_queue()
        if queue:
            queue.put_nowait({
                "type": "token",
                "node": self.node_name,
                "data": {"content": token}
            })
```

---

## 五、进阶方案（可选）

如果需要更精细的控制（如区分不同阶段的流式输出），可以考虑：

### 5.1 分阶段流式输出

```python
async def async_reflect_node_with_stages(state: PlanExecuteState):
    """分阶段的反思节点"""

    # 阶段 1：判断是否需要继续执行
    queue = get_stream_queue()

    # 通知前端进入反思阶段
    if queue:
                   "type": "stage",
            "node": "reflect",
            "data": {"stage": "thinking"}
 await queue.put({
        })

    # ... 执行判断逻辑 ...

    # 阶段 2：生成最终回复（流式）
    if needs_final_response:
        # 通知前端进入回复阶段
        if queue:
            await queue.put({
                "type": "stage",
                "node": "reflect",
                "data": {"stage": "responding"}
            })

        # 流式生成回复
        streaming_llm = create_streaming_llm("reflect_final")
        # ... 流式输出 ...
```

### 5.2 消息类型扩展

扩展 SSE 消息类型：

| 类型 | 说明 |
|------|------|
| `token` | 单个 token |
| `stage` | 阶段切换通知 |
| `thinking` | 思考中（不显示） |
| `responding` | 生成回复中（流式输出） |

---

## 六、总结

**推荐方案**：最小改动，复用现有机制

1. 将 `Response.model_validate(data)` 改为字典访问 `data.get("response", "")`
2. 确保使用 `streaming_llm` 时回调正常工作
3. 测试验证流式输出效果

这样可以快速实现需求，无需引入新的复杂性。
