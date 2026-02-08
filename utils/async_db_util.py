"""
异步数据库会话管理工具

使用 SQLAlchemy 2.0 的 AsyncSession 和 asyncpg 驱动
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from utils.logger_util import logger

load_dotenv()

# 异步数据库 URI
ASYNC_DATABASE_URI = os.getenv("ASYNC_POSTGRES_URI")

# 异步引擎配置
async_engine = create_async_engine(
    ASYNC_DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 基类（保持与同步版本一致）
Base = declarative_base()


class AsyncDatabaseManager:
    """异步数据库管理器"""

    def __init__(self):
        self.engine = async_engine
        self.AsyncSessionLocal = AsyncSessionLocal

    @asynccontextmanager
    async def get_async_session(self):
        """获取异步数据库会话的上下文管理器"""
        async with self.AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Async database error: {e}")
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Unexpected async error: {e}")
                raise


# 全局异步数据库管理器实例
async_db_manager = AsyncDatabaseManager()


def create_async_session():
    """创建异步会话上下文管理器的便捷函数"""
    return async_db_manager.get_async_session()
