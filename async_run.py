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
