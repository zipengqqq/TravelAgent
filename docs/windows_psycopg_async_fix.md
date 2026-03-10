# Windows psycopg 异步连接问题解决记录

## 问题概述

在 Windows 系统上运行异步 LangGraph 应用时，使用 `psycopg_pool.AsyncConnectionPool` 进行 PostgreSQL 连接时出现以下错误：

```
error connecting in 'pool-1': Psycopg cannot use the 'ProactorEventLoop' to run in async mode. Please use a compatible event loop, for instance by setting 'asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())'
```

## 错误原因分析

### 1. Windows 默认事件循环
- Windows 上 Python 默认使用 `ProactorEventLoop`
- `psycopg` 的异步驱动需要 `SelectorEventLoop`
- 两者不兼容导致连接失败

### 2. 事件循环策略设置时机
- 事件循环策略必须在**任何异步代码运行之前**设置
- uvicorn 启动时会在模块导入后创建事件循环
- 如果在 `main.py` 中设置策略，时机可能太晚

### 3. 连接字符串格式问题
- SQLAlchemy 使用 `postgresql+psycopg://` 格式
- `AsyncConnectionPool` 只接受标准的 `postgresql://` 格式
- 使用错误格式会导致 "invalid connection option" 错误

## 解决方案

### 方案：创建专用启动脚本

创建 `run.py` 作为应用入口，在任何模块导入之前设置事件循环策略。

#### 最终文件结构

```
TravelAgent/
├── run.py                    # 新增：专用启动脚本
├── main.py                   # FastAPI 应用定义
├── .env                      # 环境变量配置
├── service/
│   └── assistant_service/
│       └── assistant_service.py
└── api/
    └── assistant_api.py
```

---

## 实施步骤

### 步骤 1：创建启动脚本 `run.py`

```python
"""
启动脚本 - 强制使用正确的事件循环策略
"""
import asyncio
import sys

# 在导入 uvicorn 之前设置策略
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main():
    import uvicorn.server

    # 直接使用 app 对象而不是字符串
    from main import app

    config = uvicorn.config.Config(app, host="0.0.0.0", port=8288)
    server = uvicorn.server.Server(config)

    # 使用 asyncio.run 确保 SelectorEventLoop
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
```

**关键点**：
- 在任何 `import` 之前就设置事件循环策略
- 使用 `asyncio.run()` 而不是直接调用 `uvicorn.run()`
- 直接导入 app 对象而不是使用字符串引用

---

### 步骤 2：修改 `.env` 配置

```bash
# 同步 PostgreSQL URI（用于其他模块）
POSTGRES_URI=postgresql://postgres:password@host:5432/postgres?sslmode=disable

# 异步 PostgreSQL URI（AsyncConnectionPool 使用）
# 注意：使用标准 postgresql:// 格式，不是 postgresql+psycopg://
ASYNC_POSTGRES_PS_URI=postgresql://postgres:password@host:5432/postgres?sslmode=disable

# SQLAlchemy asyncpg 驱动（用于 async_db_util.py）
ASYNC_POSTGRES_URI=postgresql+asyncpg://postgres:password@host:5432/postgres
```

**关键点**：
- `AsyncConnectionPool` 使用标准的 `postgresql://` 格式
- SQLAlchemy `create_async_engine` 使用 `postgresql+asyncpg://` 格式
- 不要混淆两种格式

---

### 步骤 3：修改 `main.py`

移除 `if __name__ == "__main__"` 代码块和事件循环设置（由 `run.py` 负责）：

```python
from typing import Optional, Generic
from typing import TypeVar

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
# ... 其他导入

T = TypeVar("T")

class GenericSchema(BaseModel, Generic[T]):
    # ... 模型定义

# 全局服务实例
assistant_service = AssistantService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("应用启动中...")
    yield
    logger.info("应用关闭中...")
    await assistant_service.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ... 异常处理器和路由配置

# 移除原来的 if __name__ == "__main__" 代码块
```

---

### 步骤 4：修改 `assistant_service.py`

确保正确初始化连接池：

```python
class AssistantService:
    def __init__(self):
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._app = None
        self._pool = None
        self._checkpointer = None

    async def _ensure_initialized(self):
        """初始化工作流"""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            db_uri = os.getenv("ASYNC_POSTGRES_PS_URI")

            if db_uri:
                try:
                    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                    from psycopg_pool import AsyncConnectionPool

                    # 创建连接池
                    self._pool = AsyncConnectionPool(
                        db_uri,
                        kwargs={"autocommit": True},
                        min_size=2,
                        max_size=10
                    )
                    # 关键：必须显式调用 open()
                    await self._pool.open()
                    self._checkpointer = AsyncPostgresSaver(self._pool)

                    # 设置 checkpointer
                    setup = getattr(self._checkpointer, "setup", None)
                    if setup is not None:
                        maybe_awaitable = setup()
                        if inspect.isawaitable(maybe_awaitable):
                            await maybe_awaitable

                    self._app = async_workflow.compile(checkpointer=self._checkpointer)
                    logger.info("AssistantService 初始化完成（启用 Postgres checkpointer）")
                except Exception as e:
                    logger.warning(f"AssistantService 初始化 checkpointer 失败，将使用无持久化工作流: {e}")
                    self._app = compiled_async_workflow
            else:
                self._app = compiled_async_workflow
                logger.info("AssistantService 初始化完成（未配置 POSTGRES_URI，使用无持久化工作流）")

            self._initialized = True

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("AssistantService 连接池已关闭")
```

**关键点**：
- 创建 `AsyncConnectionPool` 后必须调用 `await self._pool.open()`
- 添加 `close()` 方法正确清理资源
- 在 lifespan 中调用 `close()` 确保连接池正确关闭

---

## 最终验证

### 启动应用

```bash
conda activate travel-agent
python async_run.py
```

### 预期输出（无错误）

```
2026-02-08 14:43:24 | INFO     | graph.async_memory_rag:__init__:27 - 初始化 AsyncMemoryRAG，使用 BAAI/bge-m3 嵌入模型 (GPU)
INFO:     Started server process [xxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8288 (Press CTRL+C to quit)
2026-02-08 14:43:32 | INFO     | main:lifespan:33 - 应用启动中...
2026-02-08 14:43:32 | INFO     | service.assistant_service.assistant_service:_ensure_initialized:xx - AssistantService 初始化完成（启用 Postgres checkpointer）
```

**关键指标**：
- ❌ 不再出现 `Psycopg cannot use the 'ProactorEventLoop'` 错误
- ❌ 不再出现 `invalid connection option` 错误
- ✅ 连接池成功初始化
- ✅ checkpointer 正常工作

---

## 经验总结

### 1. 事件循环策略是全局的
- 一旦设置，会影响所有后续异步操作
- 必须在应用启动的最早期设置

### 2. uvicorn 的启动方式很重要
- `uvicorn.run()` 可能会创建自己的事件循环
- 使用 `asyncio.run()` + 手动创建 Server 更可控

### 3. 不同库使用不同的连接字符串格式
- `AsyncConnectionPool` (psycopg): `postgresql://`
- `create_async_engine` (SQLAlchemy): `postgresql+asyncpg://`
- 不要混淆

### 4. 资源清理很重要
- 添加 `close()` 方法
- 在 lifespan 中调用
- 避免连接泄漏

### 5. 错误信息的解读
- `ProactorEventLoop` 错误 → 事件循环策略问题
- `invalid connection option` → 连接字符串格式问题
- `opening the async pool in the constructor is deprecated` → 需要调用 `await pool.open()`

---

## 相关文件

| 文件 | 修改内容 |
|------|---------|
| `run.py` | 新建：专用启动脚本，设置事件循环策略 |
| `.env` | 新增 `ASYNC_POSTGRES_PS_URI` 变量 |
| `main.py` | 移除 `if __name__ == "__main__"` 代码块和事件循环设置 |
| `assistant_service.py` | 使用 `ASYNC_POSTGRES_PS_URI`，添加 `close()` 方法 |

---

## 参考资料

- [psycopg 文档 - AsyncConnectionPool](https://www.psycopg.org/psycopg3/docs/api/pool/#psycopg_pool.AsyncConnectionPool)
- [uvicorn 文档 - Event Loop Policy](https://www.uvicorn.org/deployment/#event-loop-policy)
- [Python asyncio - Event Loop Policies](https://docs.python.org/3/library/asyncio-eventloop.html#event-loop-policies)
