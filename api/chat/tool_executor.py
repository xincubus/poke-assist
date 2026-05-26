"""
工具执行 Mixin：单工具执行分发 + 能力值计算
"""
import math
from typing import Dict, Any, List

from ..rag_service import RAGService


class ToolExecutorMixin:
    """工具执行分发 + 能力值计算"""

    def _execute_single_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        """执行单个工具调用，返回格式化结果文本。作为 agent_loop 的 tool_executor 回调。"""
        try:
            # Wiki 工具（委托给 WikiToolsMixin）
            if tool_name == "fetch_wiki_page":
                return self._fetch_wiki_page(params.get("title", ""))

            if tool_name == "search_wiki":
                return self._search_wiki(params.get("keywords", []))

            if tool_name == "execute_sql":
                sql = params.get("sql", "")
                try:
                    rows = self.query_service.execute_sql(sql)
                    if rows:
                        header = "SQL查询结果："
                        keys = list(rows[0].keys())
                        lines = [" | ".join(keys)]
                        lines.append("-" * len(lines[0]))
                        for row in rows:
                            lines.append(" | ".join(str(row.get(k, "")) for k in keys))
                        return header + "\n" + "\n".join(lines)
                    return "查询结果为空"
                except ValueError as e:
                    return f"SQL 执行被拒绝: {e}"

            if tool_name == "semantic_search":
                query = params.get("query", "")
                top_k = min(params.get("top_k", 10), 20)
                search_results = self.rag_service.search(query, top_k=top_k) if self.rag_service else []
                if search_results:
                    texts = [doc["text"] for doc in search_results]
                    return f"语义搜索「{query}」结果：\n\n" + "\n\n---\n\n".join(texts)
                return f"语义搜索「{query}」无结果"

            if tool_name == "get_type_effectiveness":
                attacker_type = params.get("attacker_type", "")
                defender_type = params.get("defender_type", "")
                if not attacker_type and defender_type:
                    rows = self.query_service.get_type_effectiveness_by_defender(defender_type)
                    if rows:
                        return self._format_type_effectiveness_by_defender(defender_type, rows)
                else:
                    rows = self.query_service.get_type_effectiveness(attacker_type, defender_type or None)
                    if rows:
                        return self._format_type_effectiveness(attacker_type, rows)
                return "未找到属性克制关系"

            if tool_name == "get_dual_type_effectiveness":
                type1 = params.get("type1", "")
                type2 = params.get("type2")
                rows = self.query_service.get_dual_type_effectiveness(type1, type2)
                if rows:
                    return self._format_dual_type_effectiveness(type1, type2, rows)
                return "未找到双属性克制关系"

            if tool_name == "stat_calculator":
                return self._execute_stat_calculator(params)

            # HOME 使用率工具（委托给 HomeQueryMixin）
            if tool_name == "get_home_rankings":
                return self._query_home_rankings(params)
            if tool_name == "get_pokemon_home_usage":
                return self._query_pokemon_home_usage(params)
            if tool_name == "get_home_teams":
                return self._query_home_teams(params)

            # 通用工具映射
            _SINGLE_ENTITY_TOOLS = {
                "search_pokemon", "search_moves", "search_abilities", "search_items",
                "search_stat", "search_status", "search_type", "search_nature",
            }
            _SINGLE_ENTITY_CATEGORY = {
                "search_pokemon": "pokemon",
                "search_moves": "move",
                "search_abilities": "ability",
                "search_items": "item",
                "search_stat": "stat",
                "search_status": "status",
                "search_type": "type",
                "search_nature": "nature",
            }

            tool_map = {
                "search_pokemon": "search_pokemon",
                "search_moves": "search_moves",
                "search_abilities": "search_abilities",
                "search_items": "search_items",
                "search_stat": "search_stat",
                "search_status": "search_status",
                "search_type": "search_type",
                "search_nature": "search_nature",
                "search_moves_by_keyword": "search_moves_by_keyword",
                "filter_moves": "filter_moves",
                "get_pokemon_moves": None,
                "get_move_learners": None,
                "get_pokemon_moves_intersection": None,
            }

            if tool_name in tool_map:
                # 批量/列表工具直接格式化
                if tool_name == "get_pokemon_moves":
                    first_param = list(params.values())[0]
                    rows = self.query_service.get_pokemon_moves(first_param)
                    formatted = self._format_pokemon_moves(rows)
                    return formatted if formatted else f"工具 {tool_name} 查询无结果（注：Mega/超极巨等特殊形态无独立招式表，请改用基础形态名称查询）"
                if tool_name == "get_move_learners":
                    first_param = list(params.values())[0]
                    if params.get("learn_method"):
                        rows = self.query_service.get_move_learners(first_param, learn_method=params["learn_method"])
                    else:
                        rows = self.query_service.get_move_learners(first_param)
                    formatted = self._format_move_learners(rows)
                    return formatted if formatted else f"工具 {tool_name} 查询无结果"
                if tool_name == "get_pokemon_moves_intersection":
                    rows = self.query_service.get_pokemon_moves_intersection(params.get("move_names", []))
                    formatted = self._format_moves_intersection(rows)
                    return formatted if formatted else f"工具 {tool_name} 查询无结果"

                method_name = tool_map[tool_name]
                method = getattr(self.query_service, method_name)
                if tool_name == "search_moves_by_keyword":
                    rows = method(params["keyword"], limit=params.get("limit", 30))
                elif tool_name == "filter_moves":
                    rows = method(**{k: v for k, v in params.items()})
                else:
                    first_param = list(params.values())[0]
                    rows = method(first_param)

                if not rows:
                    return f"工具 {tool_name} 查询无结果"

                # 单实体工具：结构化数据 + wiki 全文
                if tool_name in _SINGLE_ENTITY_TOOLS:
                    category = _SINGLE_ENTITY_CATEGORY[tool_name]
                    formatted = self._format_tool_rows(category, rows)
                    wiki_text = self._extract_and_expand_wiki(rows)
                    if wiki_text:
                        return f"{formatted}\n\n---\n\n【Wiki 百科】\n{wiki_text}"
                    return formatted

                # 批量/筛选工具：仅结构化数据
                if tool_name == "search_moves_by_keyword":
                    formatted = self._format_tool_rows("move", rows)
                elif tool_name == "filter_moves":
                    formatted = self._format_tool_rows("move", rows)
                else:
                    formatted = self._format_tool_rows(tool_name, rows)
                return formatted if formatted else f"工具 {tool_name} 查询无结果"

            return f"未知工具: {tool_name}"
        except Exception as e:
            print(f"工具 {tool_name} 执行失败: {e}")
            return f"工具 {tool_name} 执行失败: {str(e)}"

    def _execute_stat_calculator(self, params: Dict[str, Any]) -> str:
        """计算宝可梦实际能力值。"""
        pokemon_name = params.get("pokemon_name", "")
        stat_key = params.get("stat", "")  # hp/atk/def/spa/spd/spe
        nature = params.get("nature", "")
        evs = params.get("evs", 252)
        ivs = params.get("ivs", 31)
        level = params.get("level", 50)
        boosts = params.get("boosts", 0)

        if not pokemon_name or not stat_key:
            return "缺少必要参数：pokemon_name 和 stat"

        # 限制参数范围
        evs = max(0, min(252, evs))
        ivs = max(0, min(31, ivs))
        level = max(1, min(100, level))
        boosts = max(-6, min(6, boosts))

        # 1. 从数据库获取种族值
        rows = self.query_service.search_pokemon(pokemon_name)
        if not rows:
            return f"未找到宝可梦「{pokemon_name}」"
        pokemon = rows[0]

        stat_col_map = {
            "hp": "hp", "atk": "attack", "def": "defense",
            "spa": "sp_attack", "spd": "sp_defense", "spe": "speed"
        }
        col = stat_col_map.get(stat_key)
        if not col:
            return f"无效的能力类型：{stat_key}"

        base_stat = pokemon.get(col)
        if base_stat is None:
            return f"宝可梦「{pokemon.get('name_zh', pokemon_name)}」缺少种族值数据"

        # 2. 查性格修正
        nature_mod = 1.0
        nature_desc = "无修正"
        zh_to_key = {"攻击": "atk", "防御": "def", "特攻": "spa", "特防": "spd", "速度": "spe"}
        en_to_zh = {"attack": "攻击", "defense": "防御", "sp_attack": "特攻", "sp_defense": "特防", "speed": "速度"}
        # 支持中文名和英文名
        nature_info = None
        if nature:
            if nature in self._nature_modifiers:
                nature_info = self._nature_modifiers[nature]
            elif nature in self._nature_en_modifiers:
                en_info = self._nature_en_modifiers[nature]
                nature_info = {
                    "plus": en_to_zh.get(en_info["plus"], ""),
                    "minus": en_to_zh.get(en_info["minus"], ""),
                }
                nature = self._nature_en2zh.get(nature, nature)
        if nature_info:
            mod_info = nature_info
            plus_key = zh_to_key.get(mod_info["plus"], "")
            minus_key = zh_to_key.get(mod_info["minus"], "")
            if stat_key == plus_key:
                nature_mod = 1.1
                nature_desc = f"{nature}（+{mod_info['plus']}）"
            elif stat_key == minus_key:
                nature_mod = 0.9
                nature_desc = f"{nature}（-{mod_info['minus']}）"
            else:
                nature_desc = f"{nature}（无影响）"

        # 3. 计算能力值
        if stat_key == "hp":
            # HP 公式（Gen 3-9）
            stat_value = math.floor((base_stat * 2 + ivs + evs // 4) * level / 100) + level + 10
            # HP 没有性格修正和能力等级变化
            return self._format_stat_result(
                pokemon.get("name_zh", pokemon_name), stat_key, base_stat,
                nature_desc, evs, ivs, level, stat_value, 0, 1.0, stat_value
            )

        # 非 HP（Gen 3-9）
        inner = math.floor((base_stat * 2 + ivs + evs // 4) * level / 100 + 5)
        stat_before_boost = math.floor(inner * nature_mod)

        # 4. 应用能力等级变化
        if boosts >= 0:
            multiplier = (boosts + 2) / 2
        else:
            multiplier = 2 / (abs(boosts) + 2)
        stat_after_boost = math.floor(stat_before_boost * multiplier)

        return self._format_stat_result(
            pokemon.get("name_zh", pokemon_name), stat_key, base_stat,
            nature_desc, evs, ivs, level, stat_before_boost, boosts, multiplier, stat_after_boost
        )

    def _format_stat_result(self, pokemon_name: str, stat_key: str, base_stat: int,
                            nature_desc: str, evs: int, ivs: int, level: int,
                            stat_before: int, boosts: int, multiplier: float,
                            stat_after: int) -> str:
        """格式化能力值计算结果。"""
        STAT_ZH = {"hp": "HP", "atk": "攻击", "def": "防御", "spa": "特攻", "spd": "特防", "spe": "速度"}
        stat_zh = STAT_ZH.get(stat_key, stat_key)

        lines = [
            f"【{pokemon_name} {stat_zh}能力值】",
            f"种族值：{base_stat} | 性格：{nature_desc} | 个体：{ivs} | 努力：{evs} | 等级：{level}",
            f"能力值：{stat_before}",
        ]
        if boosts != 0:
            pct = f"{int(multiplier * 100)}%"
            lines.append(f"能力等级变化：{'+' if boosts > 0 else ''}{boosts}（×{pct}）")
            lines.append(f"变化后能力值：{stat_after}")
        return "\n".join(lines)
