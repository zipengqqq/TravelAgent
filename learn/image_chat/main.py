"""
图片对话 - 通义千问视觉模型
"""

import base64
import os

from langchain_openai import ChatOpenAI

# API 配置
API_KEY = 'sk-c731b0bcdec6419fb338717e2717ae63'
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def get_vision_llm():
    """获取通义千问视觉模型"""
    return ChatOpenAI(
        model="qwen-vl-plus",
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.7,
    )


def encode_image(image_path: str) -> str:
    """图片文件转 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def chat_with_image(image_path: str, question: str) -> str:
    """
    单图对话

    Args:
        image_path: 图片路径
        question: 问题

    Returns:
        模型回答
    """
    # 图片转 base64
    image_base64 = encode_image(image_path)

    # 构建消息
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": question}
            ]
        }
    ]

    llm = get_vision_llm()
    return llm.invoke(messages).content


if __name__ == "__main__":
    image_path = "test.jpg"

    if not os.path.exists(image_path):
        print(f"请提供一张图片文件，命名为: {image_path}")
    else:
        response = chat_with_image(image_path, "描述这张图片")
        print("单图对话:")
        print(response)
