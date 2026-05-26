"""
文本处理 Mixin：jieba 切词、拼音匹配、形态名 normalize、中英互译
"""
import re
import sqlite3
from typing import Dict, List, Optional

import jieba
from pypinyin import pinyin, Style


class TextProcessorMixin:
    """文本处理相关方法"""

    # 停用词（切词后过滤掉的无意义词）
    _STOP_WORDS = {
        "的", "了", "吗", "呢", "吧", "啊", "哦", "是", "在", "和", "与",
        "能", "会", "可以", "什么", "哪些", "哪个", "怎么", "如何", "多少",
        "查询", "查", "看看", "告诉", "帮我", "请问", "想知道",
    }

    # mega/primal 前缀 → 中文后缀映射
    _FORME_PREFIXES = {
        "mega": "（超级进化）",
        "超级": "（超级进化）",
        "primal": "（原始回归）",
        "原始": "（原始回归）",
    }
    _FORME_PREFIX_PATTERN = re.compile(
        r'(?i)\b(mega|primal)\s*',
    )

    def _init_jieba(self):
        """将所有实体中文名和拼音注册为 jieba 自定义词，提高切词准确率"""
        try:
            count = 0
            pinyin_count = 0
            for _category, mapping in self._en2zh_cache.items():
                for zh_name in mapping.values():
                    if zh_name and len(zh_name) >= 2:
                        jieba.add_word(zh_name, freq=50000)
                        count += 1
            # 注册拼音（无空格版）为自定义词，让 jieba 能识别拼音输入
            for py_no_space in self._pinyin_to_zh:
                if len(py_no_space) >= 4:  # 拼音至少4字符才有意义（如 "miao"）
                    jieba.add_word(py_no_space, freq=40000)
                    pinyin_count += 1
            print(f"jieba: 注册 {count} 个中文词 + {pinyin_count} 个拼音词")
        except Exception as e:
            print(f"jieba 初始化失败: {e}")

    def _normalize_forme_prefixes(self, message: str) -> str:
        """将 'mega 大食花' → '大食花（超级进化）', 'primal 盖欧卡' → '盖欧卡（原始回归）'"""
        pokemon_names = set(self._en2zh_cache.get("pokemon", {}).values()) - {None, ""}

        def _replace(m):
            prefix = m.group(1).lower()
            suffix_zh = self._FORME_PREFIXES.get(prefix, "")
            # 取 prefix 后面的文本，尝试匹配宝可梦名
            rest = message[m.end():]
            for name in sorted(pokemon_names, key=len, reverse=True):
                if rest.startswith(name):
                    forme_name = name + suffix_zh
                    # 确认 forme 存在于数据库
                    if forme_name in pokemon_names:
                        return forme_name + rest[len(name):]
            return m.group(0)

        # 逐个替换（不能用 re.sub 因为需要检查后续文本）
        result = message
        for prefix_word, suffix_zh in self._FORME_PREFIXES.items():
            pattern = re.compile(re.escape(prefix_word) + r'\s*', re.IGNORECASE)
            offset = 0
            for m in pattern.finditer(message):
                rest = message[m.end():]
                for name in sorted(pokemon_names, key=len, reverse=True):
                    if rest.startswith(name):
                        forme_name = name + suffix_zh
                        if forme_name in pokemon_names:
                            start = m.start() + offset
                            end = m.end() + len(name) + offset
                            result = result[:start] + forme_name + result[end:]
                            offset += len(forme_name) - (m.end() + len(name) - m.start())
                            break
        return result

    def _normalize_forme_keywords(self, keywords: List[str]) -> List[str]:
        """
        将关键词中的 mega/primal 前缀展开为数据库中的形态名。
        处理两种情况：
        1. 合在一起：["mega喷火龙Y"] → ["喷火龙（超级进化Y）"]
        2. 分开的：["mega", "喷火龙"] → ["喷火龙（超级进化）"]
        """
        pokemon_names = set(self._en2zh_cache.get("pokemon", {}).values()) - {None, ""}
        # 按长度降序排列，优先匹配长名称
        sorted_names = sorted(pokemon_names, key=len, reverse=True)

        # 前缀 → (超级进化/原始回归, X/Y 后缀模式)
        # mega 常见手误：mage, maga, mege
        mega_typos = ("mega", "mage", "maga", "mege")
        prefix_map = {
            **{t: "超级进化" for t in mega_typos},
            "超级": "超级进化",
            "primal": "原始回归",
            "原始": "原始回归",
        }
        # 匹配 "mega喷火龙Y" 或 "mage喷火龙Y" 等混合写法
        mega_alts = "|".join(mega_typos)
        forme_re = re.compile(
            rf'^({mega_alts}|primal|超级|原始)\s*(.+?)(?:\s*([xyzXYZ]))?$',
            re.IGNORECASE,
        )

        result = []
        skip_next = False
        for i, word in enumerate(keywords):
            if skip_next:
                skip_next = False
                continue

            low = word.lower().strip()

            # Case 1: 关键词本身包含前缀 + 宝可梦名（如 "mega喷火龙Y"）
            m = forme_re.match(word)
            if m:
                prefix_key = m.group(1).lower()
                if prefix_key in ("超级",):
                    prefix_key = "超级"
                elif prefix_key in ("原始",):
                    prefix_key = "原始"
                forme_type = prefix_map.get(prefix_key, prefix_map.get(m.group(1).lower()))
                base_text = m.group(2).strip()
                xy_suffix = m.group(3).upper() if m.group(3) else ""

                # 用 alias_service 解析 base_text 为标准中文名
                resolved_base = base_text
                if self.rag_service and self.rag_service.alias_service:
                    r = self.rag_service.alias_service.resolve(base_text, "pokemon")
                    if r:
                        resolved_base = r

                # 构造形态名并检查是否存在
                if xy_suffix:
                    forme_name = f"{resolved_base}（{forme_type}{xy_suffix}）"
                else:
                    forme_name = f"{resolved_base}（{forme_type}）"

                if forme_name in pokemon_names:
                    result.append(forme_name)
                    continue
                # 没有 X/Y 后缀的也试试
                if xy_suffix:
                    forme_name_no_xy = f"{resolved_base}（{forme_type}）"
                    if forme_name_no_xy in pokemon_names:
                        result.append(forme_name_no_xy)
                        continue

            # Case 2: 关键词是单独的前缀（如 "mega"），下一个词是宝可梦名
            suffix_zh_type = prefix_map.get(low)
            if suffix_zh_type and i + 1 < len(keywords):
                next_word = keywords[i + 1].strip()
                # 检查下一个词是否带 X/Y 后缀
                xy_match = re.match(r'^(.+?)([xyzXYZ])$', next_word)
                if xy_match:
                    base_next = xy_match.group(1)
                    xy = xy_match.group(2).upper()
                else:
                    base_next = next_word
                    xy = ""

                resolved_next = base_next
                if self.rag_service and self.rag_service.alias_service:
                    r = self.rag_service.alias_service.resolve(base_next, "pokemon")
                    if r:
                        resolved_next = r

                if xy:
                    forme_name = f"{resolved_next}（{suffix_zh_type}{xy}）"
                else:
                    forme_name = f"{resolved_next}（{suffix_zh_type}）"

                if forme_name in pokemon_names:
                    result.append(forme_name)
                    skip_next = True
                    continue

            result.append(word)
        return result

    def _tokenize(self, message: str) -> List[str]:
        """jieba 切词 + 过滤停用词 + 拼音转中文，返回有意义的词列表"""
        words = jieba.cut(message, cut_all=False)
        result = []
        for w in words:
            w = w.strip()
            if not w or len(w) < 2 or w in self._STOP_WORDS:
                continue
            # 尝试将词转拼音后查找对应中文名（支持谐音输入）
            zh = self._try_pinyin_resolve(w)
            result.append(zh if zh else w)
        return result

    def _try_pinyin_resolve(self, word: str) -> Optional[str]:
        """尝试将词（中文谐音或纯拼音）通过拼音匹配到实体中文名"""
        # 1. 检查是否已经是已知中文名
        for mapping in self._en2zh_cache.values():
            if word in mapping.values():
                return None  # 已经是正确的中文名，不需要转换

        # 2. 纯拼音输入：直接查缓存（无空格拼音 → 中文名）
        if word in self._pinyin_to_zh:
            return self._pinyin_to_zh[word]

        # 3. 中文谐音输入：转拼音后查缓存
        word_pinyin = "".join([p[0] for p in pinyin(word, style=Style.NORMAL, errors='default')])
        if word_pinyin != word and word_pinyin in self._pinyin_to_zh:
            return self._pinyin_to_zh[word_pinyin]

        return None

    def _en2zh(self, en_name: str, category: str) -> str:
        """英文名 → 中文名，查不到则原样返回"""
        mapping = self._en2zh_cache.get(category, {})
        # 先精确匹配，再试小写匹配
        if en_name in mapping:
            return mapping[en_name]
        lower = en_name.lower()
        if lower in mapping:
            return mapping[lower]
        # 尝试 Title Case（计算器返回的格式，如 Choice Specs）
        title = en_name.replace("-", " ").title()
        if title in mapping:
            return mapping[title]
        return en_name

    def _zh2en(self, zh_name: str, category: str) -> Optional[str]:
        """中文名 → 英文名"""
        mapping = self._en2zh_cache.get(category, {})
        for en, zh in mapping.items():
            if zh == zh_name:
                return en
        return None

    def _is_physical_move(self, move_name: str) -> bool:
        """判断招式是否为物理招式，支持中文名、kebab-case、Title Case"""
        try:
            from ..chat_service import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            kebab = move_name.lower().replace(" ", "-")
            cursor = conn.execute(
                "SELECT damage_class FROM moves WHERE name_zh = ? OR name_en = ?",
                (move_name, kebab)
            )
            row = cursor.fetchone()
            conn.close()
            return bool(row and row[0] == "physical")
        except Exception:
            return False

    def _parse_intent_fallback(self, message: str) -> tuple[str, Dict]:
        """
        降级方案：基于规则的意图识别（无 LLM 时使用）
        """
        if any(kw in message for kw in ["伤害", "打", "攻击", "使用", "能秒", "能杀", "能ko"]):
            return "damage_calc", {"error": "需要配置 LLM 服务才能使用智能参数提取"}
        elif any(kw in message for kw in ["查询", "查", "种族值", "属性", "特性", "招式", "克制"]):
            return "query", {"query": message}
        else:
            return "chat", {"message": message}
