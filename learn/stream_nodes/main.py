"""
FastAPI 后端服务 - SSE 流式输出
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json

from workflow import run_workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="LangGraph 流式输出示例",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return StreamingResponse(
            iter([f.read()]),
            media_type="text/html"
        )


@app.get("/health")
async def health_check():
    return {"status": "ok"}


async def event_generator(request: Request):
    queue = asyncio.Queue()
    workflow_done = asyncio.Event()

    async def run():
        try:
            await run_workflow(queue)
        except Exception as e:
            await queue.put({"type": "error", "data": {"message": str(e)}})
        finally:
            await queue.put({"type": "workflow_end"})
            workflow_done.set()

    task = asyncio.create_task(run())

    try:
        while True:
            if await request.is_disconnected():
                task.cancel()
                break

            if workflow_done.is_set():
                try:
                    event = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            else:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
                    continue

            if event.get("type") == "token":
                data = json.dumps({
                    "node": event.get("node"),
                    "token": event.get("data", {}).get("content", ""),
                    "event": "token"
                })
                yield f"data: {data}\n\n"

            elif event.get("type") == "node_start":
                data = json.dumps({
                    "node": event.get("node"),
                    "message": event.get("data", {}).get("message", ""),
                    "event": "node_start"
                })
                yield f"data: {data}\n\n"

            elif event.get("type") == "node_end":
                data = json.dumps({
                    "node": event.get("node"),
                    "event": "node_end"
                })
                yield f"data: {data}\n\n"

            elif event.get("type") == "error":
                data = json.dumps({
                    "message": event.get("data", {}).get("message", ""),
                    "event": "error"
                })
                yield f"data: {data}\n\n"

            elif event.get("type") == "workflow_end":
                data = json.dumps({"event": "workflow_end"})
                yield f"data: {data}\n\n"
                break

    except asyncio.CancelledError:
        task.cancel()
    finally:
        if not task.done():
            task.cancel()


@app.get("/stream")
async def stream(request: Request):
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
