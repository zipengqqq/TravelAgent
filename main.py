from contextlib import asynccontextmanager
from typing import Optional, Generic
from typing import TypeVar

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api import assistant_api
from api.assistant_api import assistant_service
from utils.logger_util import logger

T = TypeVar("T")


class GenericSchema(BaseModel, Generic[T]):
    code: int = Field(10000, description="状态码")
    data: Optional[T] = Field(None, description="数据")
    message: str = Field("SUCCESS", description="信息")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("应用启动中...")
    yield
    # 关闭时清理
    logger.info("应用关闭中...")
    await assistant_service.close()


# FastAPI setup
app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exception: HTTPException):
    import traceback
    # 记录请求的 URL 和错误详情
    logger.error(f"发生异常的请求 URL: {request.url}")
    logger.error(f"异常详情: {exception.detail}")
    logger.error(f"堆栈跟踪:\n{''.join(traceback.format_tb(exception.__traceback__))}")

    return JSONResponse(
            status_code=exception.status_code,
            content={
                "code": exception.status_code,
                "message": str(exception.detail),
            },
        )

app.include_router(assistant_api.router, prefix="/api/v1", tags=['聊天助手'])