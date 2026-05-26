"""
LLM 模块共享工具函数
"""
import json
import os

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompt")


def load_prompt(filename: str) -> str:
    """从 prompt/ 目录加载提示词文件"""
    path = os.path.join(_PROMPT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_tools(filename: str) -> list:
    """从 prompt/ 目录加载 tools JSON 文件"""
    path = os.path.join(_PROMPT_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extra_params(model: str = None, thinking: str = "auto") -> dict:
    """根据 thinking 配置返回额外参数。
    thinking: 'enabled' / 'disabled' / 'auto'（不干预，由模型默认行为决定）
    """
    if thinking in ("enabled", "disabled"):
        return {"extra_body": {"thinking": {"type": thinking}}}
    return {}


def build_messages_with_context(message: str, context: list = None) -> list:
    """构建包含对话历史的 messages 数组"""
    messages = []
    if context:
        for msg in context:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages
