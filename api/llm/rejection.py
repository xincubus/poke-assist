"""
内容安全拒绝检测
"""
import re

_REJECTION_PATTERNS = [
    re.compile(r"high\s*risk", re.IGNORECASE),
    re.compile(r"rejected", re.IGNORECASE),
    re.compile(r"sensitive\s*content", re.IGNORECASE),
    re.compile(r"inappropriate", re.IGNORECASE),
    re.compile(r"content\s*policy", re.IGNORECASE),
    re.compile(r"violation", re.IGNORECASE),
    re.compile(r"违规"),
    re.compile(r"拒绝"),
    re.compile(r"敏感"),
    re.compile(r"不当"),
]

REJECTION_RETRY_NOTE = (
    '注意：我之前的回复被内容安全系统误判。请重新回答。'
    '再次强调：这是宝可梦(Pokémon)游戏虚拟对战的数值计算问题，'
    '所有"攻击"、"伤害"、"秒杀"等术语均指游戏机制，不涉及任何现实内容。'
    '请正常使用工具查询并给出回答。'
)


def is_rejection(text: str) -> bool:
    """检测 LLM 返回是否为内容安全拒绝"""
    if not text:
        return False
    return any(p.search(text) for p in _REJECTION_PATTERNS)
