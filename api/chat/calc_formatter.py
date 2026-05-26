"""
计算器格式化 Mixin：URL 构建 + 伤害结果格式化 + 润色文本
"""
import math
import os
import urllib.parse
from typing import Dict, Any, List


class CalcFormatterMixin:
    """计算器 URL 构建和伤害结果格式化相关方法"""

    def _build_calc_url(self, params: Dict[str, Any]) -> str:
        """根据计算参数构建在线计算器 URL"""
        api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
        # 手机端用 mobile.html，网页端用 index_zh.html
        page = "mobile.html" if getattr(self, "_platform", None) == "mobile" else "index_zh.html"
        base = f"{api_base}/cale/{page}"
        q = {"gen": params.get("generation", 10)}  # default: Champions

        # 攻守方宝可梦
        if params.get("attacker_name"):
            q["p1"] = params["attacker_name"]
        if params.get("defender_name"):
            q["p2"] = params["defender_name"]

        # 招式
        if params.get("move_name"):
            q["move1"] = params["move_name"]

        # 道具
        if params.get("attacker_item"):
            q["item1"] = params["attacker_item"]
        if params.get("defender_item"):
            q["item2"] = params["defender_item"]

        # 特性
        if params.get("attacker_ability"):
            q["ability1"] = params["attacker_ability"]
        if params.get("defender_ability"):
            q["ability2"] = params["defender_ability"]

        # 性格
        if params.get("attacker_nature"):
            q["nature1"] = params["attacker_nature"]
        if params.get("defender_nature"):
            q["nature2"] = params["defender_nature"]

        # 努力值/点数: hp,atk,def,spa,spd,spe
        ev_order = ["hp", "atk", "def", "spa", "spd", "spe"]
        if params.get("generation", 10) == 10:
            # Gen 10 用 sps（能力点，0-32），_detect_generation 已将 evs 转为 sps
            for side, key in [("attacker", "sps1"), ("defender", "sps2")]:
                sps = params.get(f"{side}_sps")
                if sps:
                    q[key] = ",".join(str(sps.get(s, 0)) for s in ev_order)
        else:
            for side, key in [("attacker", "evs1"), ("defender", "evs2")]:
                evs = params.get(f"{side}_evs")
                if evs:
                    q[key] = ",".join(str(evs.get(s, 0)) for s in ev_order)

        # 太晶属性
        if params.get("attacker_tera_type"):
            q["tera1"] = params["attacker_tera_type"]
        if params.get("defender_tera_type"):
            q["tera2"] = params["defender_tera_type"]

        # 天气 & 场地
        if params.get("weather"):
            q["weather"] = params["weather"]
        if params.get("terrain"):
            q["terrain"] = params["terrain"]

        # 状态
        if params.get("attacker_status"):
            q["status1"] = params["attacker_status"]
        if params.get("defender_status"):
            q["status2"] = params["defender_status"]

        # 能力等级变化: atk,def,spa,spd,spe
        boost_order = ["atk", "def", "spa", "spd", "spe"]
        for side, key in [("attacker", "boosts1"), ("defender", "boosts2")]:
            boosts = params.get(f"{side}_boosts")
            if boosts and isinstance(boosts, dict):
                vals = [str(boosts.get(s, 0)) for s in boost_order]
                if any(v != "0" for v in vals):
                    q[key] = ",".join(vals)

        # 壁（防守方侧，suffix=2）
        if params.get("is_reflect"):
            q["reflect2"] = "true"
        if params.get("is_light_screen"):
            q["lightscreen2"] = "true"
        if params.get("is_aurora_veil"):
            q["auroraveil2"] = "true"

        # 对战模式
        q["mode"] = params.get("mode") or "Doubles"

        return base + "?" + urllib.parse.urlencode(q)

    def _format_evs(self, evs: dict, stat_keys: list) -> str:
        """将努力值 dict 格式化为可读字符串，只显示指定的 stat_keys"""
        parts = []
        for key in stat_keys:
            val = evs.get(key, 0) if evs else 0
            parts.append(f"{val} {key.upper()}")
        return " / ".join(parts)

    @staticmethod
    def _format_chance_pct(chance: float) -> str:
        """将 0-1 的概率格式化为百分比字符串，<0.1% 时保留2位有效数字"""
        pct = chance * 100
        if pct >= 0.1:
            return f"{round(pct, 1)}%"
        # <0.1%：保留2位有效数字，如 0.000244140625 -> "0.024%"
        digits = -math.floor(math.log10(pct)) + 1  # 小数点后需要的位数
        return f"{round(pct, digits)}%"

    def _format_ko_text_short(self, kochance: Dict[str, Any]) -> str:
        """击杀结论的紧凑格式，用于单行显示"""
        text = kochance.get("text", "")
        chance = kochance.get("chance")
        n = kochance.get("n") or self._parse_n_from_text(text)
        n_map = {1: "一击", 2: "2次攻击", 3: "3次攻击", 4: "4次攻击", 5: "5次攻击"}
        n_text = n_map.get(n, f"{n}次攻击")
        if "guaranteed" in text:
            return f"确定{n_text}击杀" if n == 1 else f"确定 {n_text}击杀"
        elif "possible" in text and n > 0:
            return f"可能 {n_text}击杀"
        elif chance is not None and chance > 0:
            return f"{self._format_chance_pct(chance)} 几率 {n_text}击杀"
        else:
            return "无法击杀"

    def _format_calc_line(self, calc_params: Dict[str, Any], result: Dict[str, Any]) -> str:
        """生成伤害计算器风格的单行格式"""
        # 宝可梦冠军用 sps，其他世代用 evs
        atk_evs = calc_params.get("attacker_sps") or calc_params.get("attacker_evs") or {}
        def_evs = calc_params.get("defender_sps") or calc_params.get("defender_evs") or {}
        if "atk" in atk_evs or "def" in def_evs:
            is_physical = True
        elif "spa" in atk_evs or "spd" in def_evs:
            is_physical = False
        else:
            is_physical = " Atk " in result.get("description", "")
        atk_stat_key = "atk" if is_physical else "spa"
        def_stat_key = "def" if is_physical else "spd"
        atk_stat_zh = "攻击" if is_physical else "特攻"
        def_stat_zh = "防御" if is_physical else "特防"

        # 性格加减符号
        atk_stat_en = "Attack" if is_physical else "Special Attack"
        def_stat_en = "Defense" if is_physical else "Special Defense"
        atk_nature = calc_params.get("attacker_nature", "")
        def_nature = calc_params.get("defender_nature", "")
        atk_mod = self._nature_en_modifiers.get(atk_nature, {})
        def_mod = self._nature_en_modifiers.get(def_nature, {})
        atk_sign = "+" if atk_mod.get("plus") == atk_stat_en else ("-" if atk_mod.get("minus") == atk_stat_en else "")
        def_sign = "+" if def_mod.get("plus") == def_stat_en else ("-" if def_mod.get("minus") == def_stat_en else "")
        def_hp_sign = "+" if def_mod.get("plus") == "HP" else ("-" if def_mod.get("minus") == "HP" else "")

        atk_ev_val = atk_evs.get(atk_stat_key, 0)
        def_hp_val = def_evs.get("hp", 0)
        def_def_val = def_evs.get(def_stat_key, 0)

        # 攻击方：能力等级 EV 特性 名字 道具 招式 [太晶类型]
        atk_parts = []
        # 能力等级提升（如 +1, -1）
        atk_boosts = calc_params.get("attacker_boosts") or {}
        boost_val = atk_boosts.get(atk_stat_key, 0)
        if boost_val:
            atk_parts.append(f"+{boost_val}" if boost_val > 0 else str(boost_val))
        atk_parts.append(f"{atk_ev_val}{atk_sign} {atk_stat_zh}")
        if calc_params.get("attacker_ability"):
            atk_parts.append(self._en2zh(calc_params["attacker_ability"], "ability"))
        atk_name = self._en2zh(calc_params.get("attacker_name", ""), "pokemon")
        atk_item_str = f" {self._en2zh(calc_params['attacker_item'], 'item')}" if calc_params.get("attacker_item") else ""
        move_name = self._en2zh(calc_params.get("move_name", ""), "move")
        tera_str = ""
        if calc_params.get("attacker_tera_type"):
            tera_raw = calc_params["attacker_tera_type"]
            tera_zh = self._type_en2zh.get(tera_raw.lower(), tera_raw)
            tera_str = f" (太晶{tera_zh}属性)"
        atk_str = " ".join(atk_parts) + f" {atk_name}{atk_item_str} {move_name}{tera_str}"

        # 防守方：HP EV / 防御 EV 名字[天气/场地][太晶类型]
        def_name = self._en2zh(calc_params.get("defender_name", ""), "pokemon")
        field_parts = []
        if calc_params.get("weather"):
            field_parts.append(self.WEATHER_ZH.get(calc_params["weather"], calc_params["weather"]))
        if calc_params.get("terrain"):
            field_parts.append(self.TERRAIN_ZH.get(calc_params["terrain"], calc_params["terrain"]))
        field_str = f"[{''.join(field_parts)}]" if field_parts else ""
        if calc_params.get("defender_tera_type"):
            tera_raw = calc_params["defender_tera_type"]
            tera_zh = self._type_en2zh.get(tera_raw.lower(), tera_raw)
            field_str += f"(太晶{tera_zh}属性)"
        critical_str = " 击中要害" if calc_params.get("is_critical_hit") else ""
        def_item_str = f" {self._en2zh(calc_params['defender_item'], 'item')}" if calc_params.get("defender_item") else ""
        def_str = f"{def_hp_val}{def_hp_sign} HP / {def_def_val}{def_sign} {def_stat_zh}{def_item_str} {def_name}{field_str}{critical_str}"

        # 伤害
        damage_range = result.get("damageRange", [0, 0])
        defender_hp = result.get("defender", {}).get("hp", 1)
        pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
        pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
        ko_str = self._format_ko_text_short(result.get("kochance", {}))

        return f"{atk_str} vs. {def_str} : {damage_range[0]}-{damage_range[1]} ({pct_min} - {pct_max}%) -- {ko_str}"

    def _build_multi_scenario_raw_summary(
        self, params: Dict[str, Any], results: list
    ) -> str:
        """为 LLM#3 构建多情况结构化文本（按天气/场地分组，附格式化行）"""
        atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
        def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
        move_name = self._en2zh(params.get("move_name", "?"), "move")

        mode = "单打" if params.get("mode") == "Singles" else "双打"
        lines = [f"对战模式: {mode}", f"攻击方: {atk_name}", f"防守方: {def_name}", f"招式: {move_name}", ""]

        # 按天气/场地分组（label 格式："{天气/场地} {情况}" 或 "{情况}"）
        EV_LABELS = {"满攻 vs 无耐久", "极攻 vs 极限耐久"}
        groups: Dict[str, list] = {}
        for item in results:
            label = item["label"]
            # 尝试从 label 中分离出分组 key 和情况 key
            group_key = "无天气/场地"
            ev_label = label
            for ev in EV_LABELS:
                if label.endswith(ev):
                    prefix = label[: -len(ev)].strip()
                    if prefix:
                        group_key = prefix
                        ev_label = ev
                    break
            groups.setdefault(group_key, []).append((ev_label, item))

        for group_key, items in groups.items():
            if group_key != "无天气/场地":
                lines.append(f"【{group_key}】")
            for ev_label, item in items:
                result = item["result"]
                calc_params = item["params"]
                damage_range = result.get("damageRange", [0, 0])
                defender_hp = result.get("defender", {}).get("hp", 1)
                kochance = result.get("kochance", {})
                pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
                pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0

                atk_evs = calc_params.get("attacker_sps") or calc_params.get("attacker_evs") or {}
                def_evs = calc_params.get("defender_sps") or calc_params.get("defender_evs") or {}
                if "atk" in atk_evs or "def" in def_evs:
                    is_physical = True
                elif "spa" in atk_evs or "spd" in def_evs:
                    is_physical = False
                else:
                    is_physical = " Atk " in result.get("description", "")
                atk_ev_key = "atk" if is_physical else "spa"
                def_ev_keys = ["hp", "def" if is_physical else "spd"]
                def_evs = calc_params.get("defender_sps") or calc_params.get("defender_evs") or {}

                atk_parts = []
                if calc_params.get("attacker_nature"):
                    atk_parts.append(f"性格={self._nature_en2zh.get(calc_params['attacker_nature'], calc_params['attacker_nature'])}")
                atk_parts.append(f"努力值={self._format_evs(atk_evs, [atk_ev_key])}")
                if calc_params.get("attacker_item"):
                    atk_parts.append(f"道具={self._en2zh(calc_params['attacker_item'], 'item')}")
                if calc_params.get("attacker_ability"):
                    atk_parts.append(f"特性={self._en2zh(calc_params['attacker_ability'], 'ability')}")
                def_parts = []
                if calc_params.get("defender_nature"):
                    def_parts.append(f"性格={self._nature_en2zh.get(calc_params['defender_nature'], calc_params['defender_nature'])}")
                def_parts.append(f"努力值={self._format_evs(def_evs, def_ev_keys)}")
                if calc_params.get("defender_ability"):
                    def_parts.append(f"特性={self._en2zh(calc_params['defender_ability'], 'ability')}")
                if calc_params.get("weather"):
                    def_parts.append(f"天气={self.WEATHER_ZH.get(calc_params['weather'], calc_params['weather'])}")
                if calc_params.get("terrain"):
                    def_parts.append(f"场地={self.TERRAIN_ZH.get(calc_params['terrain'], calc_params['terrain'])}")

                lines.append(f"  情况: {ev_label}")
                lines.append(f"  攻击方: {', '.join(atk_parts)}")
                lines.append(f"  防守方: {', '.join(def_parts)}")
                lines.append(f"  伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)")
                lines.append(f"  击杀: {self._format_ko_text(kochance)}")
                lines.append(f"  格式化行: {self._format_calc_line(calc_params, result)}")
                lines.append(f"  在线计算器: [点击查看]({self._build_calc_url(calc_params)})")
            lines.append("")

        return "\n".join(lines)

    def _build_raw_summary(self, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        """为 LLM#3 构建单情况结构化文本（中文可读，附格式化行）"""
        atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
        def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
        move_name = self._en2zh(params.get("move_name", "?"), "move")
        damage_range = result.get("damageRange", [0, 0])
        defender_hp = result.get("defender", {}).get("hp", 1)
        kochance = result.get("kochance", {})
        pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
        pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0

        atk_evs = params.get("attacker_sps") or params.get("attacker_evs") or {}
        def_evs = params.get("defender_sps") or params.get("defender_evs") or {}
        if "atk" in atk_evs or "def" in def_evs:
            is_physical = True
        elif "spa" in atk_evs or "spd" in def_evs:
            is_physical = False
        else:
            is_physical = " Atk " in result.get("description", "")
        atk_ev_key = "atk" if is_physical else "spa"
        def_ev_keys = ["hp", "def" if is_physical else "spd"]

        mode = "单打" if params.get("mode") == "Singles" else "双打"
        lines = [f"对战模式: {mode}", f"攻击方: {atk_name}", f"防守方: {def_name}", f"招式: {move_name}"]
        if params.get("weather"):
            lines.append(f"天气: {self.WEATHER_ZH.get(params['weather'], params['weather'])}")
        if params.get("terrain"):
            lines.append(f"场地: {self.TERRAIN_ZH.get(params['terrain'], params['terrain'])}")
        if params.get("attacker_item"):
            lines.append(f"攻击方道具: {self._en2zh(params['attacker_item'], 'item')}")
        if params.get("attacker_nature"):
            lines.append(f"攻击方性格: {self._nature_en2zh.get(params['attacker_nature'], params['attacker_nature'])}")
        ev_label = "点数" if params.get("generation") == 10 else "努力值"
        lines.append(f"攻击方{ev_label}: {self._format_evs(atk_evs, [atk_ev_key])}")
        if params.get("attacker_ability"):
            lines.append(f"攻击方特性: {self._en2zh(params['attacker_ability'], 'ability')}")
        if params.get("defender_nature"):
            lines.append(f"防守方性格: {self._nature_en2zh.get(params['defender_nature'], params['defender_nature'])}")
        lines.append(f"防守方{ev_label}: {self._format_evs(def_evs, def_ev_keys)}")
        if params.get("defender_item"):
            lines.append(f"防守方道具: {self._en2zh(params['defender_item'], 'item')}")
        if params.get("defender_ability"):
            lines.append(f"防守方特性: {self._en2zh(params['defender_ability'], 'ability')}")
        lines.append(f"伤害范围: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)")
        ko_text = kochance.get("text", "")
        if "immune" in ko_text.lower():
            lines.append("结果: 属性免疫，该招式对防守方完全无效（伤害为0）")
        else:
            lines.append(f"击杀: {self._format_ko_text(kochance)}")
        lines.append(f"格式化行: {self._format_calc_line(params, result)}")
        lines.append(f"在线计算器: [点击查看]({self._build_calc_url(params)})")
        return "\n".join(lines)

    def _format_stat_with_evs_nature(
        self, stat_value: int, stat_key: str, evs: dict, nature: str, label: str
    ) -> str:
        """
        格式化能力值，带努力值和性格增减标记。
        例: "(252+) 222 SpA" 或 "(0) 170 SpD" 或 "(252-) 108 Atk"
        """
        ev_value = evs.get(stat_key, 0) if evs else 0
        modifier = self._nature_modifiers.get(nature, {})
        stat_cn = self.STAT_NAMES.get(stat_key, stat_key)

        # 性格修正符号
        if modifier.get("plus") == stat_cn:
            nature_mark = "+"
        elif modifier.get("minus") == stat_cn:
            nature_mark = "-"
        else:
            nature_mark = ""

        return f"({ev_value}{nature_mark}) {stat_value} {label}"

    def _format_multi_scenario_response(self, results: list) -> str:
        """格式化多情况计算结果"""
        lines = []

        # 标题
        atk_name = self._en2zh(results[0]["params"].get("attacker_name", ""), "pokemon")
        def_name = self._en2zh(results[0]["params"].get("defender_name", ""), "pokemon")
        move_name = self._en2zh(results[0]["params"].get("move_name", ""), "move")

        # 检查是否有天气/场地
        weather = results[0]["params"].get("weather")
        terrain = results[0]["params"].get("terrain")
        prefix = []
        if weather:
            prefix.append(self.WEATHER_ZH.get(weather, weather))
        if terrain:
            prefix.append(self.TERRAIN_ZH.get(terrain, terrain))
        prefix_str = "，".join(prefix) + "，" if prefix else ""

        lines.append(f"【{prefix_str}{atk_name}使用{move_name}对{def_name}】\n")

        # 各情况详细结果
        for i, item in enumerate(results, 1):
            label = item["label"]
            params = item["params"]
            result = item["result"]

            # 获取能力值信息
            atk_stats = result.get("attacker", {}).get("stats", {})
            def_stats = result.get("defender", {}).get("stats", {})

            # 判断物攻/特攻
            desc = result.get("description", "")
            if " Atk " in desc:
                atk_stat_key, atk_label = "atk", "Atk"
                def_stat_key, def_label = "def", "Def"
            else:
                atk_stat_key, atk_label = "spa", "SpA"
                def_stat_key, def_label = "spd", "SpD"

            # 格式化能力值
            atk_evs = params.get("attacker_evs", {})
            def_evs = params.get("defender_evs", {})
            atk_nature = params.get("attacker_nature", "认真")
            def_nature = params.get("defender_nature", "认真")

            atk_stat_str = self._format_stat_with_evs_nature(
                atk_stats.get(atk_stat_key, 0), atk_stat_key, atk_evs, atk_nature, atk_label
            )
            def_hp_str = self._format_stat_with_evs_nature(
                def_stats.get("hp", 0), "hp", def_evs, def_nature, "HP"
            )
            def_def_str = self._format_stat_with_evs_nature(
                def_stats.get(def_stat_key, 0), def_stat_key, def_evs, def_nature, def_label
            )

            # 伤害信息
            damage_range = result.get("damageRange", [0, 0])
            defender_hp = result.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1)
            pct_max = round(damage_range[1] / defender_hp * 100, 1)
            ko_text = self._format_ko_text(result.get("kochance", {}))

            lines.append(
                f"{i}. {label}：{atk_stat_str} 对 {def_hp_str} / {def_def_str}\n"
                f"   伤害 {damage_range[0]}-{damage_range[1]}（{pct_min}%-{pct_max}%），{ko_text}\n"
                f"   [在线计算器]({self._build_calc_url(params)})"
            )

        # 总结
        lines.append("\n" + self._generate_multi_scenario_summary(results))

        return "\n".join(lines)

    def _generate_multi_scenario_summary(self, results: list) -> str:
        """生成多情况总结"""
        # 提取关键信息
        min_scenario = results[0]  # 最低配置
        max_scenario = results[-1]  # 极限配置

        min_ko = min_scenario["result"].get("kochance", {})
        max_ko = max_scenario["result"].get("kochance", {})

        min_n = min_ko.get("n", 0)
        max_n = max_ko.get("n", 0)

        # 生成总结
        if min_n == 1 and max_n == 1:
            return "总结：无论配置如何，都能一发击杀。"
        elif min_n == 1:
            return f"总结：满攻配置可以一发，但无耐久配置需要{max_n}发。建议根据对手配置调整。"
        elif max_n == 1:
            return "总结：极限配置下可以一发，但常规配置可能需要多发。"
        elif min_n == max_n:
            return f"总结：大致需要{min_n}发击杀，配置影响不大。"
        else:
            return f"总结：根据配置不同，需要{max_n}-{min_n}发击杀。建议携带增伤道具。"

    def _format_damage_response(self, params: Dict[str, Any], result: Dict[str, Any]) -> str:
        """
        将伤害计算结果格式化为中文对话。

        格式：
        【天气，】【场地，】【xx SpA(+/-)】【携带xx】的 攻击方 使用 招式，
        对【xx SpD(+/-)】【携带xx】的 防御方 造成 min-max (min%-max%) 伤害，
        击杀描述。润色文本。
        """
        atk_name = self._en2zh(params.get("attacker_name", "???"), "pokemon")
        def_name = self._en2zh(params.get("defender_name", "???"), "pokemon")
        move_name = self._en2zh(params.get("move_name", "???"), "move")
        atk_nature = params.get("attacker_nature", "认真")
        def_nature = params.get("defender_nature", "认真")
        atk_stats = result.get("attacker", {}).get("stats", {})
        def_stats = result.get("defender", {}).get("stats", {})
        defender_hp = result.get("defender", {}).get("hp", 0)
        damage_range = result.get("damageRange", [0, 0])
        kochance = result.get("kochance", {})

        # ── 1. 判断物攻/特攻 ──
        desc = result.get("description", "")
        if " Atk " in desc:
            atk_stat_key, atk_label = "atk", "Atk"
            def_stat_key, def_label = "def", "Def"
        else:
            atk_stat_key, atk_label = "spa", "SpA"
            def_stat_key, def_label = "spd", "SpD"

        # ── 2. 前缀部分（天气、场地） ──
        prefix_parts = []
        if params.get("weather"):
            prefix_parts.append(self.WEATHER_ZH.get(params["weather"], params["weather"]))
        if params.get("terrain"):
            prefix_parts.append(self.TERRAIN_ZH.get(params["terrain"], params["terrain"]))

        # ── 3. 攻击方描述 ──
        atk_parts = []
        atk_stat_val = atk_stats.get(atk_stat_key, 0)
        atk_evs = params.get("attacker_evs", {})
        atk_parts.append(self._format_stat_with_evs_nature(atk_stat_val, atk_stat_key, atk_evs, atk_nature, atk_label))
        if params.get("attacker_item"):
            item_zh = self._en2zh(params["attacker_item"], "item")
            atk_parts.append(f"携带{item_zh}")

        # ── 4. 防御方描述 ──
        def_parts = []
        def_hp_val = def_stats.get("hp", 0)
        def_def_val = def_stats.get(def_stat_key, 0)
        def_evs = params.get("defender_evs", {})
        def_parts.append(self._format_stat_with_evs_nature(def_hp_val, "hp", def_evs, def_nature, "HP"))
        def_parts.append(self._format_stat_with_evs_nature(def_def_val, def_stat_key, def_evs, def_nature, def_label))
        if params.get("defender_item"):
            item_zh = self._en2zh(params["defender_item"], "item")
            def_parts.append(f"携带{item_zh}")

        # ── 5. 伤害百分比 ──
        if defender_hp > 0:
            pct_min = round(damage_range[0] / defender_hp * 100, 1)
            pct_max = round(damage_range[1] / defender_hp * 100, 1)
        else:
            pct_min, pct_max = 0, 0

        # ── 6. 击杀描述 ——
        ko_text = self._format_ko_text(kochance)

        # ── 7. 组装 ──
        line_prefix = "，".join(prefix_parts) + "，" if prefix_parts else ""
        atk_desc = " / ".join(atk_parts)
        def_desc = " / ".join(def_parts)

        main_line = (
            f"{line_prefix}"
            f"{atk_desc} 的{atk_name}使用{move_name}，"
            f"对 {def_desc} 的{def_name}"
            f"造成 {damage_range[0]}-{damage_range[1]}（{pct_min}%-{pct_max}%）伤害，"
            f"{ko_text}。"
        )

        # ── 8. 润色 ──
        flavor = self._generate_flavor(pct_min, pct_max, kochance)

        return f"{main_line}\n{flavor}" if flavor else main_line

    def _format_ko_text(self, kochance: Dict[str, Any]) -> str:
        """将英文击杀概率转为中文"""
        text = kochance.get("text", "")
        chance = kochance.get("chance")
        n = kochance.get("n") or self._parse_n_from_text(text)

        ko_n_map = {1: "一发", 2: "两发", 3: "三发", 4: "四发", 5: "五发"}
        n_text = ko_n_map.get(n, f"{n}发")

        if "guaranteed" in text:
            return f"确定{n_text}击杀"
        elif "possible" in text and n > 0:
            return f"可能{n_text}击杀"
        elif chance is not None and chance > 0:
            return f"{self._format_chance_pct(chance)} 概率{n_text}击杀"
        else:
            return "无法击杀"

    @staticmethod
    def _parse_n_from_text(text: str) -> int:
        """从 KO chance 文本中解析击杀次数（fallback）"""
        import re
        if not text:
            return 0
        if "OHKO" in text:
            return 1
        m = re.search(r'(\d+)HKO', text)
        return int(m.group(1)) if m else 0

    def _generate_flavor(self, pct_min: float, pct_max: float, kochance: Dict[str, Any]) -> str:
        """根据伤害情况生成一句口语化的润色"""
        chance = kochance.get("chance", 0)
        n = kochance.get("n", 0)

        if n == 1 and chance == 1:
            return "稳稳一发带走，不用考虑乱数。"
        elif n == 1 and chance >= 0.8:
            return "乱数大概率一发，运气不差就能秒。"
        elif n == 1 and chance >= 0.5:
            return "一半一半的乱数，有点看脸。"
        elif n == 1 and chance > 0:
            return "乱数偏低，一发秒杀要看运气。"
        elif n == 2 and chance == 1:
            if pct_min >= 45:
                return "两下稳杀，打一发对面基本就得换了。"
            else:
                return "确定两发带走，不过单发伤害不算高。"
        elif n == 2 and chance > 0:
            return "大致两发能倒，但不是很稳。"
        elif n == 3 and chance == 1:
            return "三发才能击杀，伤害有点不够看。"
        elif pct_max < 20:
            return "伤害太低了，基本挠痒痒，建议换个打法。"
        elif pct_max < 35:
            return "伤害偏低，正面硬刚不太现实。"
        else:
            return ""
