# 图片对话 - 通义千问视觉模型技术方案

## 1. 概述

图片对话功能允许用户上传图片，AI 模型理解图片内容并回答问题，实现多模态交互。

## 2. 技术选型

### 2.1 视觉模型

| 模型 | 说明 | 推荐场景 |
|------|------|----------|
| qwen-vl-plus | 通用视觉理解 | 日常使用 |
| qwen-vl-max | 增强版视觉理解 | 复杂场景 |

**选择理由**：性价比高，国内可直接调用

### 2.2 API 接入

- **平台**：阿里云 DashScope
- **接入方式**：OpenAI 兼容接口
- **调用地址**：`https://dashscope.aliyuncs.com/compatible-mode/v1`

## 3. 核心实现

### 3.1 消息格式

```python
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,xxx"}},
            {"type": "text", "text": "问题内容"}
        ]
    }
]
```

**关键点**：
- `content` 是数组，包含图片和文本
- 每个元素必须指定 `type`
- 图片使用 base64 编码，格式为 `data:image/jpeg;base64,{数据}`

### 3.2 图片处理

```python
import base64

def encode_image(image_path: str) -> str:
    """图片转 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
```

### 3.3 LLM 配置

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen-vl-plus",
    api_key="sk-xxx",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.7,
)
```

## 4. 功能列表

### 4.1 同步版本

```python
# 单图对话
response = chat_with_image("test.jpg", "描述这张图片")

# 接收 base64
response = chat_with_image_base64(image_base64, "图片里有什么？")

# 多图对话
response = chat_with_multiple_images(["img1.jpg", "img2.jpg"], "这两张图有什么区别？")
```

### 4.2 异步版本

```python
import asyncio

response = await async_chat_with_image("test.jpg", "描述这张图片")
response = await async_chat_with_image_base64(image_base64, "图片里有什么？")
```

### 4.3 流式版本

```python
# 同步流式
for chunk in chat_with_image_stream("test.jpg", "描述这张图片"):
    print(chunk, end="", flush=True)

# 异步流式
async for chunk in async_chat_with_image_stream(image_base64, "描述这张图片"):
    print(chunk, end="")
```

### 4.4 图片压缩

```python
# 压缩图片
base64_compressed = compress_image("test.jpg", max_size=1024, quality=85)
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| max_size | 最大边长(像素) | 1024 |
| quality | JPEG 质量 | 85 |

## 5. API 接口格式

### 请求格式

```json
{
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,..."
                    }
                },
                {
                    "type": "text",
                    "text": "描述这张图片"
                }
            ]
        }
    ]
}
```

### 响应格式

```json
{
    "id": "chatcmpl-xxx",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "这张图片显示..."
            }
        }
    ]
}
```

## 6. 集成到主工作流

### 6.1 扩展状态定义

```python
class PlanExecuteState(TypedDict):
    # ... 现有字段
    images: Optional[List[str]]  # 用户上传的图片 (base64)
```

### 6.2 添加图片处理节点

```python
def vision_node(state: PlanExecuteState):
    """图片理解节点"""
    images = state.get("images", [])
    question = state["question"]

    if not images:
        return {}

    # 处理第一张图片
    response = chat_with_image_base64(images[0], question)
    return {"response": response}
```

## 7. 图片处理优化

### 7.1 压缩策略

```python
def optimize_image(image_path: str) -> dict:
    """生成多种规格"""
    original = compress_image(image_path, max_size=2048, quality=90)
    thumbnail = compress_image(image_path, max_size=256, quality=70)
    preview = compress_image(image_path, max_size=512, quality=80)

    return {
        "original": original,
        "thumbnail": thumbnail,
        "preview": preview
    }
```

### 7.2 Token 优化

| 策略 | 说明 | 节省比例 |
|------|------|----------|
| 尺寸限制 | 最大 2048x2048 | 50-70% |
| 质量压缩 | quality=85 | 30-50% |
| 格式选择 | 优先 JPEG | 20-30% |

## 8. 错误处理

| 错误码 | 说明 | 处理方式 |
|--------|------|----------|
| 4001 | 图片格式不支持 | 返回支持的格式列表 |
| 4002 | 图片过大 | 提示压缩或裁剪 |
| 5001 | 模型调用失败 | 重试 |
| 5002 | 超时 | 增加超时时间 |

## 9. 环境变量

```bash
# 必需
DASHSCOPE_API_KEY=sk-xxx
```

获取 API Key: [阿里云 DashScope](https://dashscope.console.aliyun.com/)

## 10. 参考资料

- [通义千问视觉模型文档](https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope)
- [DashScope 控制台](https://dashscope.console.aliyun.com/)
