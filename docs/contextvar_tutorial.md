# ContextVar 详解

## 什么是 ContextVar？

`ContextVar` 是 Python 3.7+ 标准库 `contextvars` 模块提供的**上下文局部变量**，专为 asyncio 异步编程设计。

它解决的问题：**在异步环境中，每个请求需要独立的数据，而普通全局变量会被所有请求共享。**

---

## 为什么不用其他方案？

| 方案 | 问题 |
|------|------|
| 普通全局变量 | 所有请求共享，会冲突 |
| 线程本地变量 (threading.local) | asyncio 是单线程，不适用 |
| 放在 state 字典里 | LangGraph 会序列化，无法保存 Queue 等对象 |
| **ContextVar** | ✅ 每个异步任务独立，互不干扰 |

---

## 基本用法

### 1. 定义和设置

```python
from contextvars import ContextVar
from typing import Optional
import asyncio

# 定义 ContextVar，default 为默认值
_stream_queue: ContextVar[Optional[asyncio.Queue]] = ContextVar('stream_queue', default=None)

# 设置值（当前异步任务）
queue = asyncio.Queue()
_stream_queue.set(queue)

# 获取值（当前异步任务）
queue = _stream_queue.get()
```

### 2. 在函数中使用

```python
from contextvars import ContextVar

# 定义
current_user: ContextVar[str] = ContextVar('current_user', default='guest')

# 中间件设置
def set_current_user(user_id: str):
    current_user.set(user_id)

# 业务代码获取
def get_current_user() -> str:
    return current_user.get()
```

---

## 实际应用场景

### 场景：异步请求的日志追踪

```python
import asyncio
from contextvars import ContextVar
from uuid import uuid4

# 定义 trace_id
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')

def set_trace_id():
    """在请求入口设置 trace_id"""
    trace_id_var.set(str(uuid4()))

def get_trace_id() -> str:
    """在任意位置获取 trace_id"""
    return trace_id_var.get()

async def handle_request():
    set_trace_id()  # 设置
    await process_order()  # 调用链都能获取到同一个 trace_id

async def process_order():
    tid = get_trace_id()  # 获取到同一个 ID
    print(f"Processing order: {tid}")
```

### 场景：Token 级别流式输出

```python
from contextvars import ContextVar
import asyncio
from typing import Optional

# 定义
_stream_queue: ContextVar[Optional[asyncio.Queue]] = ContextVar('stream_queue', default=None)

# 设置 queue
def set_stream_queue(queue: asyncio.Queue):
    _stream_queue.set(queue)

# 获取 queue
def get_stream_queue() -> Optional[asyncio.Queue]:
    return _stream_queue.get()

# 回调中使用
class StreamCallback(BaseCallbackHandler):
    def on_llm_new_token(self, token: str, **kwargs):
        queue = get_stream_queue()  # 获取当前请求的 queue
        if queue:
            queue.put_nowait(token)
```

---

## 核心原理

```
┌─────────────────────────────────────────────────────────┐
│                    Context                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Task A (请求1)                                  │   │
│  │   _stream_queue → queue_a                       │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Task B (请求2)                                  │   │
│  │   _stream_queue → queue_b                       │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

同一个 ContextVar 变量，不同任务看到的是不同的值
```

---

## 与 threading.local 对比

```python
# threading.local - 线程级别
import threading

local = threading.local()
local.value = "hello"

# 在同一线程内共享，不同线程独立

# ContextVar - 异步任务级别
from contextvars import ContextVar

var = ContextVar('var', default='default')
var.set('hello')

# 在同一异步任务内共享，不同任务独立
```

---

## 注意事项

1. **不需要 `nonlocal`**: ContextVar 是存储在独立的上下文中，不需要像闭包那样用 `nonlocal`

2. **必须设置才能获取**: 如果未设置且无默认值，会抛出 `LookupError`

```python
var = ContextVar('var')  # 无默认值
var.get()  # ❌ 抛出 LookupError

var = ContextVar('var', default='default')
var.get()  # ✅ 返回 'default'
```

3. **线程安全**: ContextVar 本身就是线程安全的

---

## 总结

- ContextVar = **异步任务级别的"全局变量"**
- 每个 `await` 的任务有自己独立的值，互不影响
- 常用于：请求追踪、用户上下文、流式输出队列等场景
- 解决：asyncio 环境下需要"每个请求独立数据"的问题
