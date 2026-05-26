"""
别名解析服务 - 基于 battle_terms 表 + rapidfuzz 模糊匹配 + 拼音匹配
替代静态 pokemon_aliases.json，提供程序化别名查找
"""
import sqlite3
from typing import Optional, Dict, List
from rapidfuzz import fuzz, process
from pypinyin import pinyin, Style


# _translate() 的 category 参数 → battle_terms 的 category 值
CATEGORY_MAP = {
    "pokemon": "pokemon_alias",
    "item": "item_alias",
}

# _translate() 的 category 参数 → 数据库表名和列名
TABLE_MAP = {
    "pokemon": ("pokemons", "name_zh", "name_en"),
    "move": ("moves", "name_zh", "name_en"),
    "item": ("items", "name_zh", "name_en"),
    "ability": ("abilities", "name_zh", "name_en"),
    "nature": ("natures", "name_zh", "name_en"),
    "weather": ("status", "name_zh", "name_en"),
    "terrain": ("status", "name_zh", "name_en"),
    "type": ("types", "name_zh", "name_en"),
    "status": ("status", "name_zh", "name_en"),
}

FUZZY_SCORE_CUTOFF = 75


def _to_pinyin(text: str) -> str:
    """将中文文本转为无声调拼音字符串（空格分隔），与 add_pinyin.py 格式一致"""
    if not text:
        return ""
    result = pinyin(text, style=Style.NORMAL, errors='default')
    return " ".join([item[0] for item in result])


class AliasService:
    """别名解析服务"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # term/alias → 标准中文名，按 category 分组
        self._term_index: Dict[str, Dict[str, str]] = {}
        # 各表所有 name_zh 列表，用于模糊 fallback
        self._name_zh_lists: Dict[str, List[str]] = {}
        # 拼音 → 标准中文名，按 category 分组
        self._pinyin_to_zh: Dict[str, Dict[str, str]] = {}
        # 各表所有拼音列表，用于拼音模糊 fallback
        self._pinyin_lists: Dict[str, List[str]] = {}

        self._load(db_path)

    def _load(self, db_path: str):
        conn = sqlite3.connect(db_path)

        # 1. 加载各表 name_en → name_zh 反向映射 + 拼音数据
        en_to_zh: Dict[str, Dict[str, str]] = {}
        for category, (table, zh_col, en_col) in TABLE_MAP.items():
            try:
                # 检查表是否有 name_pinyin 列
                cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                has_pinyin = "name_pinyin" in cols

                if has_pinyin:
                    rows = conn.execute(
                        f"SELECT {zh_col}, {en_col}, name_pinyin FROM {table} "
                        f"WHERE {zh_col} IS NOT NULL AND {en_col} IS NOT NULL"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT {zh_col}, {en_col} FROM {table} "
                        f"WHERE {zh_col} IS NOT NULL AND {en_col} IS NOT NULL"
                    ).fetchall()

                en_to_zh[category] = {row[1]: row[0] for row in rows}
                self._name_zh_lists[category] = [row[0] for row in rows]

                # 构建拼音索引
                if has_pinyin:
                    py_to_zh = {}
                    py_list = []
                    for row in rows:
                        name_zh, _name_en, name_py = row[0], row[1], row[2]
                        if name_py:
                            py_to_zh[name_py] = name_zh
                            py_list.append(name_py)
                    self._pinyin_to_zh[category] = py_to_zh
                    self._pinyin_lists[category] = py_list
            except Exception:
                en_to_zh[category] = {}
                self._name_zh_lists[category] = []

        # 2. 加载 battle_terms 构建精确索引
        bt_rows = conn.execute(
            "SELECT term, aliases, category, related_value FROM battle_terms WHERE language = 'zh'"
        ).fetchall()

        for term, aliases_str, bt_category, related_value in bt_rows:
            # 确定对应的 translate category
            translate_cat = None
            for cat, bt_cat in CATEGORY_MAP.items():
                if bt_cat == bt_category:
                    translate_cat = cat
                    break
            if translate_cat is None:
                continue

            # 从 related_value（英文）反查标准中文名
            canonical_zh = self._resolve_canonical_zh(
                related_value, translate_cat, en_to_zh
            )
            if not canonical_zh:
                continue

            # 建索引
            if translate_cat not in self._term_index:
                self._term_index[translate_cat] = {}

            idx = self._term_index[translate_cat]
            idx[term] = canonical_zh

            if aliases_str:
                for alias in aliases_str.split(","):
                    alias = alias.strip()
                    if alias:
                        idx[alias] = canonical_zh

        conn.close()

        count = sum(len(v) for v in self._term_index.values())
        pinyin_count = sum(len(v) for v in self._pinyin_to_zh.values())
        print(f"别名服务加载完成：{count} 条精确映射，{pinyin_count} 条拼音映射，"
              f"模糊候选 pokemon={len(self._name_zh_lists.get('pokemon', []))} "
              f"item={len(self._name_zh_lists.get('item', []))}")

    @staticmethod
    def _resolve_canonical_zh(
        related_value: str,
        category: str,
        en_to_zh: Dict[str, Dict[str, str]],
    ) -> Optional[str]:
        """将 related_value（英文，可能逗号分隔）转为标准中文名"""
        if not related_value:
            return None
        mapping = en_to_zh.get(category, {})
        # related_value 可能是 "zacian,zacian-crowned"，取第一个能匹配的
        for en_name in related_value.split(","):
            en_name = en_name.strip()
            zh = mapping.get(en_name)
            if zh:
                return zh
        return None

    def resolve_top(self, text: str, category: str, top_k: int = 5) -> List[str]:
        """
        返回最多 top_k 个候选标准中文名：先取 >=75 分的，不足则补低分条目。
        精确匹配排在最前面。支持拼音匹配（谐音/拼音输入）。
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        seen = []

        # 1. battle_terms 精确匹配（最高优先）
        idx = self._term_index.get(category, {})
        if text in idx:
            seen.append(idx[text])

        # 2. 模糊匹配，取所有候选排序
        candidates = self._name_zh_lists.get(category, [])
        if candidates:
            # 取足够多的候选（至少 top_k * 2）以便补位
            all_results = process.extract(
                text,
                candidates,
                scorer=fuzz.partial_ratio,
                limit=max(top_k * 2, 20),
            )
            # 先收集 >=75 的
            high = [r[0] for r in all_results if r[1] >= FUZZY_SCORE_CUTOFF and r[0] not in seen]
            # 再收集 <75 的作为补位
            low = [r[0] for r in all_results if r[1] < FUZZY_SCORE_CUTOFF and r[0] not in seen]

            seen.extend(high)
            # 补位到 top_k
            for name in low:
                if len(seen) >= top_k:
                    break
                seen.append(name)

        # 3. 拼音匹配（将输入转拼音，与数据库拼音做匹配）
        if len(seen) < top_k:
            pinyin_results = self._resolve_by_pinyin(text, category, top_k)
            for name in pinyin_results:
                if name not in seen:
                    seen.append(name)
                    if len(seen) >= top_k:
                        break

        return seen[:top_k]

    def resolve(self, text: str, category: str) -> Optional[str]:
        """
        解析别名，返回标准中文名。支持拼音匹配。

        Args:
            text: 用户输入的名称
            category: 类别（pokemon/item/move/ability/nature 等）

        Returns:
            标准中文名，或 None（未找到）
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # 1. battle_terms 精确匹配
        idx = self._term_index.get(category, {})
        if text in idx:
            return idx[text]

        # 2. 模糊匹配（对 name_zh 列表）
        candidates = self._name_zh_lists.get(category, [])
        if candidates:
            result = process.extractOne(
                text,
                candidates,
                scorer=fuzz.partial_ratio,
                score_cutoff=FUZZY_SCORE_CUTOFF,
            )
            if result:
                return result[0]

        # 3. 拼音匹配
        pinyin_results = self._resolve_by_pinyin(text, category, top_k=1)
        if pinyin_results:
            return pinyin_results[0]

        return None

    def _resolve_by_pinyin(self, text: str, category: str, top_k: int = 5) -> List[str]:
        """
        将输入文本转为拼音，与数据库中的拼音做精确/模糊匹配，返回对应的中文名列表。
        支持：
        - 中文谐音输入（"太热巴格师" → pinyin → fuzzy match → "太乐巴戈斯"）
        - 纯拼音输入（"penhuolong" → match → "喷火龙"）
        - 拼音缩写（已在 SQL 层支持，这里不重复处理）
        """
        py_to_zh = self._pinyin_to_zh.get(category, {})
        py_list = self._pinyin_lists.get(category, [])
        if not py_to_zh or not py_list:
            return []

        # 将输入转为拼音（中文 → 无声调拼音）
        input_pinyin = _to_pinyin(text)
        if not input_pinyin:
            return []

        results = []

        # 精确匹配拼音
        if input_pinyin in py_to_zh:
            results.append(py_to_zh[input_pinyin])

        # 也尝试无空格版本匹配（用户可能输入 "penhuolong" 而非 "pen huo long"）
        input_no_space = input_pinyin.replace(" ", "")
        for py, zh in py_to_zh.items():
            if py.replace(" ", "") == input_no_space and zh not in results:
                results.append(zh)
                break

        if len(results) >= top_k:
            return results[:top_k]

        # 模糊匹配拼音
        all_results = process.extract(
            input_pinyin,
            py_list,
            scorer=fuzz.ratio,
            limit=max(top_k * 2, 10),
        )
        for matched_py, score, _ in all_results:
            if score >= FUZZY_SCORE_CUTOFF:
                zh = py_to_zh.get(matched_py)
                if zh and zh not in results:
                    results.append(zh)
                    if len(results) >= top_k:
                        break

        return results[:top_k]


if __name__ == "__main__":
    import os
    db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pokemon_data", "pokemonData.db")
    svc = AliasService(db)

    tests = [
        ("原始盖欧卡", "pokemon"),
        ("黑马蕾冠王", "pokemon"),
        ("围巾", "item"),
        ("眼镜", "item"),
        ("盖欧卡", "pokemon"),
        ("密勒顿", "pokemon"),
        # 拼音/谐音测试
        ("太热巴格师", "pokemon"),
        ("泰勒巴哥司", "pokemon"),
        ("喷火龙", "pokemon"),
    ]
    for text, cat in tests:
        print(f"  resolve({text!r}, {cat!r}) = {svc.resolve(text, cat)!r}")
