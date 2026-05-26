"""
LLM 模块 - 拆分为独立函数
- param_extractors: 参数提取（伤害计算 / 阈值搜索）
- summarizers: 结果总结（查询 / 伤害 / 阈值）
- rejection: 内容安全拒绝检测
"""
from .rejection import is_rejection, REJECTION_RETRY_NOTE
from .param_extractors import extract_damage_calc_params, extract_threshold_params
from .summarizers import summarize_query_result, summarize_damage_result, summarize_threshold_result
