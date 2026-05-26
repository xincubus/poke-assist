"""
结果总结函数 - 将工具/计算结果汇总为自然语言回复
独立函数模式：传入 client/model 等参数，不依赖 LLMService 实例
"""
from typing import Optional

from .helpers import load_prompt, extra_params, build_messages_with_context


def _stream_summary(
    client, model: str, max_tokens: int,
    prompt_filename: str, placeholder: str,
    dynamic_content: str, user_message: str,
    context: list = None, temperature: float = 0,
    thinking: str = "auto",
    call_log: list = None, call_id: str = "3q", call_purpose: str = "结果总结",
    thinking_callback=None, thinking_step: int = 90,
) -> str:
    """通用流式总结：加载 prompt → 拆分 → 填充 → 流式生成"""
    _prompt_raw = load_prompt(prompt_filename)
    _split_idx = _prompt_raw.index(placeholder)
    _rules_prefix = _prompt_raw[:_split_idx]
    _rules_suffix = _prompt_raw[_split_idx + len(placeholder) + 1:]

    messages = [
        {"role": "system", "content": _rules_prefix, "cache_control": {"type": "ephemeral"}},
        {"role": "system", "content": dynamic_content},
        {"role": "system", "content": _rules_suffix},
    ]
    messages += build_messages_with_context(user_message, context)
    if call_log is not None:
        call_log.append({"call": call_id, "purpose": call_purpose, "messages": messages})

    stream = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
        stream=True,
        **extra_params(model, thinking=thinking),
    )
    text_parts = []
    reasoning_parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        r_delta = getattr(delta, "reasoning_content", None)
        if isinstance(r_delta, str) and r_delta:
            reasoning_parts.append(r_delta)
            if thinking_callback:
                try:
                    thinking_callback("整理回答", r_delta, thinking_step)
                except Exception:
                    pass
        c_delta = getattr(delta, "content", None)
        if isinstance(c_delta, str) and c_delta:
            text_parts.append(c_delta)
    text = "".join(text_parts)
    reasoning = "".join(reasoning_parts)
    has_reasoning = bool(reasoning.strip())
    if call_log is not None:
        call_log[-1]["reply"] = text
        if has_reasoning:
            call_log[-1]["reasoning"] = reasoning
    return text


def summarize_query_result(
    client, model: str, max_tokens: int,
    message: str, query_results_text: str,
    context: list = None, thinking: str = "enabled",
    call_log: list = None, thinking_callback=None,
) -> str:
    """查询结果总结：将精确查询结果汇总为自然语言回复"""
    return _stream_summary(
        client=client, model=model, max_tokens=max_tokens,
        prompt_filename="llm_query_summary.txt",
        placeholder="{query_results_text}",
        dynamic_content=query_results_text,
        user_message=message, context=context, temperature=0,
        thinking=thinking,
        call_log=call_log, call_id="3q", call_purpose="查询结果总结",
        thinking_callback=thinking_callback, thinking_step=90,
    )


def summarize_damage_result(
    client, model: str, max_tokens: int,
    user_message: str, calc_summary_text: str,
    context: list = None, thinking: str = "disabled",
    call_log: list = None, thinking_callback=None,
) -> str:
    """伤害计算结果总结：将计算结果汇总为自然语言回复"""
    return _stream_summary(
        client=client, model=model, max_tokens=max_tokens,
        prompt_filename="llm3_damage_summary.txt",
        placeholder="{calc_summary_text}",
        dynamic_content=calc_summary_text,
        user_message=user_message, context=context, temperature=0.3,
        thinking=thinking,
        call_log=call_log, call_id=3, call_purpose="结果总结",
        thinking_callback=thinking_callback, thinking_step=93,
    )


def summarize_threshold_result(
    client, model: str, max_tokens: int,
    user_message: str, calc_summary_text: str,
    context: list = None, thinking: str = "disabled",
    call_log: list = None, thinking_callback=None,
) -> str:
    """阈值搜索结果总结：将阈值结果汇总为自然语言回复"""
    return _stream_summary(
        client=client, model=model, max_tokens=max_tokens,
        prompt_filename="llm3_threshold_summary.txt",
        placeholder="{calc_summary_text}",
        dynamic_content=calc_summary_text,
        user_message=user_message, context=context, temperature=0.3,
        thinking=thinking,
        call_log=call_log, call_id="3t", call_purpose="阈值结果总结",
        thinking_callback=thinking_callback, thinking_step=93,
    )
