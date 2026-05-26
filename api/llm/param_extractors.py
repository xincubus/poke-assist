"""
参数提取函数 - 从用户消息中提取伤害计算/阈值搜索参数
独立函数模式：传入 client/model 等参数，不依赖 LLMService 实例
"""
import json
from typing import Dict, Any, Optional

from .helpers import load_tools, load_prompt, extra_params, build_messages_with_context


def extract_damage_calc_params(
    client, model: str, max_tokens: int,
    message: str, search_results_text: str,
    context: list = None, thinking: str = "auto",
    call_log: list = None,
) -> Dict[str, Any]:
    """
    从用户消息中提取伤害计算参数（Tool Use）

    参数：
      client: OpenAI client 实例
      model: 模型名
      max_tokens: 最大 token 数
      message: 用户消息
      search_results_text: 检索结果文本
      context: 对话历史
      thinking: 思考模式
      call_log: 调试日志
    """
    tools = load_tools("llm2_damage_calculator_tool.json")

    _prompt_raw = load_prompt("llm2_damage_params.txt")
    _split_idx = _prompt_raw.index("{search_results_text}")
    _rules_prefix = _prompt_raw[:_split_idx]
    _rules_suffix = _prompt_raw[_split_idx + len("{search_results_text}") + 1:]

    tools_openai = [{
        "type": "function",
        "function": {
            "name": tools[0]["name"],
            "description": tools[0]["description"],
            "parameters": tools[0]["input_schema"],
        }
    }]

    try:
        messages = [
            {"role": "system", "content": _rules_prefix, "cache_control": {"type": "ephemeral"}},
            {"role": "system", "content": search_results_text},
            {"role": "system", "content": _rules_suffix},
        ]
        messages += build_messages_with_context(message, context)
        if call_log is not None:
            call_log.append({"call": 2, "purpose": "参数提取", "messages": messages})
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            tools=tools_openai,
            tool_choice={"type": "function", "function": {"name": "damage_calculator"}},
            messages=messages,
            **extra_params(model, thinking=thinking),
        )
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            reply = tool_calls[0].function.arguments
            if call_log is not None:
                call_log[-1]["reply"] = reply
            if not reply:
                return {}
            return json.loads(reply)
        return {}

    except Exception as e:
        print(f"LLM Call #2 参数提取失败: {e}")
        return {}


def extract_threshold_params(
    client, model: str, max_tokens: int,
    message: str, search_results_text: str,
    context: list = None, thinking: str = "auto",
    call_log: list = None,
) -> Dict[str, Any]:
    """
    从用户消息中提取阈值搜索参数（Tool Use）

    参数：
      client: OpenAI client 实例
      model: 模型名
      max_tokens: 最大 token 数
      message: 用户消息
      search_results_text: 检索结果文本
      context: 对话历史
      thinking: 思考模式
      call_log: 调试日志
    """
    tools = load_tools("llm2_threshold_tool.json")

    _prompt_raw = load_prompt("llm2_threshold_params.txt")
    _split_idx = _prompt_raw.index("{search_results_text}")
    _rules_prefix = _prompt_raw[:_split_idx]
    _rules_suffix = _prompt_raw[_split_idx + len("{search_results_text}") + 1:]

    tools_openai = [{
        "type": "function",
        "function": {
            "name": tools[0]["name"],
            "description": tools[0]["description"],
            "parameters": tools[0]["input_schema"],
        }
    }]

    try:
        messages = [
            {"role": "system", "content": _rules_prefix, "cache_control": {"type": "ephemeral"}},
            {"role": "system", "content": search_results_text},
            {"role": "system", "content": _rules_suffix},
        ]
        messages += build_messages_with_context(message, context)
        if call_log is not None:
            call_log.append({"call": "2t", "purpose": "阈值参数提取", "messages": messages})
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            tools=tools_openai,
            tool_choice={"type": "function", "function": {"name": "ev_threshold_calculator"}},
            messages=messages,
            **extra_params(model, thinking=thinking),
        )
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            reply = tool_calls[0].function.arguments
            if call_log is not None:
                call_log[-1]["reply"] = reply
            if not reply:
                return {}
            return json.loads(reply)
        return {}

    except Exception as e:
        print(f"LLM Call #2t 阈值参数提取失败: {e}")
        return {}
