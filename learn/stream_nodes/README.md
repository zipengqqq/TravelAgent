# LangGraph 节点级流式输出实现指南

## 概述

本文档解释如何实现 LangGraph 节点的**流式 Token 输出**，即在 LLM 生成答案时，一个字一个字地实时显示到前端，而不是等待完整答案生成完毕再一次性返回。

## 核心概念

### 1. 为什么需要流式输出？

传统模式：用户提问 → 等待 LLM 生成完整答案 → 一次性返回

流式模式：用户提问 → LLM 开始生成 → **实时推送每个字** → 前端逐字显示

用户体验：流式输出让用户感觉"AI正在思考"，响应更快，体验更好。

### 2. 技术栈

| 技术 | 作用 |
|------|------|
| LangChain Callback | 捕获 LLM 生成的每个 token |
| asyncio.Queue | 线程安全的队列，在节点间传递数据 |
| SSE (Server-Sent Events) | 服务器向浏览器单向推送消息的技术 |
| EventSource (前端) | 浏览器接收 SSE 消息的 API |

---

## 实现步骤

### 第一步：创建 Token 捕获回调

```python
class StreamCallback(BaseCallbackHandler):
    """监听 LLM 的 token 生成事件"""

    def __init__(self, queue: asyncio.Queue, node_name: str):
        self.queue = queue          # 用于存放 token 的队列
        self.node_name = node_name  # 当前节点名称

    def on_llm_new_token(self, token: str, **kwargs):
        """LLM 每生成一个 token 就会调用这个方法"""
        # 将 token 放入队列
        self.queue.put({
            "type": "token",
            "node": self.node_name,
            "data": {"content": token}
        })
```

**原理**：LangChain 提供的回调机制就像一个"监听器"，LLM 生成每个字时会通知我们。

### 第二步：创建带流式支持的 LLM

```python
def create_streaming_llm(node_name: str, queue: asyncio.Queue):
    return ChatOpenAI(
        model="deepseek-chat",
        streaming=True,  # 关键：启用流式输出
        callbacks=[StreamCallback(queue, node_name)]  # 绑定回调
    )
```

**原理**：`streaming=True` 告诉 LLM "不要等全部生成完，一有结果就告诉我"。

### 第三步：定义节点，使用 LLM

```python
async def node_b(state: GraphState):
    # 通知前端：节点开始
    await _stream_queue.put({
        "type": "node_start",
        "node": "node_b"
    })

    # 创建带流式的 LLM 并调用
    llm = create_streaming_llm("node_b", _stream_queue)
    response = await llm.ainvoke([HumanMessage(content="请介绍旅游")])

    # 通知前端：节点结束
    await _stream_queue.put({
        "type": "node_end",
        "node": "node_b"
    })

    return {"node_outputs": {"node_b": response.content}}
```

**原理**：调用 LLM 时，回调会自动把每个 token 放入队列，我们无需关心具体实现。

### 第四步：构建 LangGraph 工作流

```python
def create_workflow():
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("node_a", node_a)  # 简单节点
    workflow.add_node("node_b", node_b)  # LLM 节点
    workflow.add_node("node_c", node_c)  # LLM 节点

    # 设置流程
    workflow.set_entry_point("node_a")
    workflow.add_edge("node_a", "node_b")
    workflow.add_edge("node_b", "node_c")
    workflow.add_edge("node_c", END)

    return workflow.compile()
```

### 第五步：SSE 后端接口

```python
@app.get("/stream")
async def stream(request: Request):
    """SSE 流式接口"""

    async def event_generator():
        queue = asyncio.Queue()
        set_queue(queue)  # 设置全局队列

        # 启动工作流（异步执行）
        workflow_task = asyncio.create_task(run_workflow(queue))

        # 持续从队列读取数据，推送给前端
        while True:
            event = await queue.get()

            if event["type"] == "token":
                # 推送 token
                yield f"data: {json.dumps(event)}\n\n"

            elif event["type"] == "workflow_end":
                yield f"data: {json.dumps({'event': 'workflow_end'})}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**原理**：SSE 是一种服务器主动推送数据的技术，浏览器通过 `EventSource` 接收。

### 第六步：前端接收流式数据

```javascript
// 连接到 SSE
const eventSource = new EventSource('http://127.0.0.1:8000/stream');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);

    if (data.type === "token") {
        // 追加 token 到页面
        document.getElementById('content').innerHTML += data.data.content;
    }
};
```

---

## 数据流向图

```
┌─────────────────────────────────────────────────────────────────┐
│                         工作流执行                                │
│                                                                 │
│   node_a ──→ node_b ──→ node_c                                 │
│              ↓              ↓                                  │
│         [LLM 调用]      [LLM 调用]                              │
│              ↓              ↓                                  │
│         StreamCallback   StreamCallback                        │
│              ↓              ↓                                  │
│         Token 入队      Token 入队                             │
│              └─────────────┼─────────────┐                      │
│                            ↓            │                      │
│                     asyncio.Queue ◄──────┘                      │
│                            ↓                                    │
│                    SSE event_generator                          │
│                            ↓                                    │
│                      前端浏览器                                  │
│                   EventSource 接收                              │
│                            ↓                                    │
│                 实时显示到页面 HTML                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 关键代码位置

| 文件 | 说明 |
|------|------|
| `workflow.py:28-57` | StreamCallback 回调实现 |
| `workflow.py:61-70` | 创建流式 LLM |
| `workflow.py:99-125` | 节点 B 使用流式 LLM |
| `main.py:66-140` | SSE 接口实现 |

---

## 如何集成到现有项目

1. **复制 StreamCallback 类**到你的项目中
2. **在调用 LLM 的节点**中使用 `streaming=True` + 回调
3. **通过队列 + SSE** 推送到前端

---

## 常见问题

### Q: 为什么用全局队列而不是状态传递？

A: LangGraph 的状态需要可序列化，Queue 对象无法放入状态。使用全局变量更简单。

### Q: 如何区分不同节点的 token？

A: 在回调中传入 `node_name`，前端根据 `node` 字段判断。

### Q: SSE 和 WebSocket 有什么区别？

A: SSE 是单向的（服务器→浏览器），更简单；WebSocket 是双向的。流式输出用 SSE 就够了。
