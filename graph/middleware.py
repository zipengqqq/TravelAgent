"""
工具调用日志中间件

用于记录 create_agent 调用的工具
"""
from langchain.agents.middleware import wrap_tool_call

from utils.logger_util import logger


@wrap_tool_call
async def log_tool_call(request, handler):
    """记录工具调用"""
    # tool_call 是字典，有 'name' 和 'args' 键
    tool_call = request.tool_call
    if isinstance(tool_call, dict):
        tool_name = tool_call.get('name', 'unknown')
        tool_input = tool_call.get('args', {})
    else:
        tool_name = 'unknown'
        tool_input = {}

    logger.info(f"[Tool] {tool_name} | 输入: {tool_input}")

    # 调用原始工具
    return await handler(request)
