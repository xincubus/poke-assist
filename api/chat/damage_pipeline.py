"""
伤害计算管线 Mixin：参数提取 → 计算执行 → 结果格式化
"""
import json
import re
import time
from typing import Dict, Any, Optional, List


class DamagePipelineMixin:
    """伤害计算管线相关方法"""

    # 含这些后缀的宝可梦名只存在于宝可梦冠军（gen 10）
    _CHAMPIONS_SUFFIXES = ("-mega", "-primal")

    # 特性 → 天气/场地映射（英文名，大小写不敏感匹配）
    ABILITY_WEATHER_MAP = {
        "drizzle": "Rain",
        "primordial sea": "Heavy Rain",
        "drought": "Sun",
        "desolate land": "Harsh Sunshine",
        "sand stream": "Sand",
        "snow warning": "Snow",
        "delta stream": "Strong Winds",
        "orichalcum pulse": "Sun",
        "cloud nine": None,  # 消除天气，不自动设置
    }
    ABILITY_TERRAIN_MAP = {
        "electric surge": "Electric",
        "grassy surge": "Grassy",
        "psychic surge": "Psychic",
        "misty surge": "Misty",
        "hadron engine": "Electric",
    }
    # 天气/场地英文值 → 中文显示名（用于 label 和 fallback 模板）
    WEATHER_ZH = {
        "Sun": "晴天", "Harsh Sunshine": "大日照",
        "Rain": "雨天", "Heavy Rain": "大雨",
        "Sand": "沙暴", "Snow": "下雪",
        "Strong Winds": "乱流",
    }
    TERRAIN_ZH = {
        "Electric": "电气场地", "Grassy": "青草场地",
        "Psychic": "心灵场地", "Misty": "薄雾场地",
    }

    def _retrieve_for_calc(
        self, message: str, keywords: list, user_context: str = None, timings: dict = None
    ) -> tuple:
        """共享 RAG 检索：预处理形态 + jieba 分词 + 三路检索，返回 (search_text, words)"""
        # Step 0: 预处理 mega/primal 前缀 -> 数据库形态名
        if keywords:
            keywords = self._normalize_forme_keywords(keywords)

        # Step 1: 用 LLM#1 提取的关键词；没有则 fallback 到 jieba 分词
        words = keywords if keywords else self._tokenize(message)

        # Step 2: 三路检索，精确查询优先，RAG 补充
        t_rag2 = time.time()
        seen_ids = set()
        exact_docs = []
        rag_docs = []

        if self.query_service:
            from ..rag_service import RAGService
            for word in words:
                for method_name, category in [
                    ("search_moves", "move"),
                    ("search_pokemon", "pokemon"),
                    ("search_abilities", "ability"),
                    ("search_items", "item"),
                ]:
                    method = getattr(self.query_service, method_name, None)
                    if method:
                        try:
                            resolved = word
                            if self.rag_service and self.rag_service.alias_service:
                                resolved = self.rag_service.alias_service.resolve(word, category) or word
                            rows = method(resolved)
                            for row in rows[:5]:
                                row_key = row.get("name_en") or row.get("name_zh") or resolved
                                doc_id = f"direct:{category}:{row_key}"
                                if doc_id not in seen_ids:
                                    seen_ids.add(doc_id)
                                    exact_docs.append({
                                        "id": doc_id,
                                        "table": category,
                                        "text": RAGService._format_row(category, row),
                                        "score": 1.0,
                                    })
                        except Exception:
                            pass

        if self.rag_service:
            rag_results = self.rag_service.search_words(words) if words else self.rag_service.hybrid_search(message)
            for doc in rag_results:
                if doc["id"] not in seen_ids:
                    seen_ids.add(doc["id"])
                    rag_docs.append(doc)

        all_docs = exact_docs + rag_docs
        search_text = "\n\n---\n\n".join(
            [doc["text"] for doc in all_docs]
        ) if all_docs else "无相关资料"
        if user_context:
            search_text = user_context + "\n\n---\n\n" + search_text
        if timings is not None:
            timings["rag_s2"] = round(time.time() - t_rag2, 2)

        return search_text, words

    def _handle_damage_calc_pipeline(
        self, message: str, context: Optional[list] = None, model: str = None, tool_model: str = None,
        call_log: list = None, keywords: List[str] = None, timings: dict = None, user_context: str = None,
        user_pokemon_list: List[Dict[str, Any]] = None, progress_callback=None, thinking_callback=None,
        pre_tool_history: List[Dict[str, Any]] = None, terminal_args: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        伤害计算完整管线：切词 → 逐词检索 → LLM#2 参数提取 → 计算 → LLM#3 总结

        Fallback:
        - LLM#2 失败 → 友好错误提示
        - 计算失败 → 返回错误
        - LLM#3 失败 → 使用现有模板格式化
        """
        try:
            # 共享检索：预处理 + jieba 分词 + 三路检索
            search_text, words = self._retrieve_for_calc(message, keywords, user_context, timings)

            # 如果 agent loop 已经查过数据，注入到 search_text 避免重复查询
            if pre_tool_history:
                loop_context = self._format_tool_history(pre_tool_history)
                if loop_context:
                    search_text = f"【已查数据】\n{loop_context}\n\n---\n\n{search_text}"

            # Step 3: LLM#2 提取参数
            if progress_callback:
                progress_callback(91, "提取参数", "", "active")
            t_llm2 = time.time()
            params = self.llm_service.extract_damage_calc_params(
                message, search_text, context, model=tool_model, call_log=call_log
            )
            if timings is not None:
                timings["llm2"] = round(time.time() - t_llm2, 2)

            if not params or not params.get("attacker_name"):
                return {
                    "success": False,
                    "type": "damage_calc",
                    "response": "抱歉，我没能从你的描述中提取出计算参数。\n\n"
                               "你可以这样问：\n"
                               "• Mega喷火龙Y对Mega妙蛙花使用热风\n"
                               "• 快龙神速能秒烈咬陆鲨吗\n"
                               "• mega长耳兔三旋击打多鳞mega快龙有多少伤害",
                    "data": None,
                }

            # 发送 step 91 进度：参数已提取
            if progress_callback:
                atk = params.get("attacker_name", "")
                dfn = params.get("defender_name", "")
                mv = params.get("move_name", "")
                detail = f"{atk}→{dfn}" + (f", {mv}" if mv else "")
                progress_callback(91, "参数已提取", detail, "done")

            # LLM 有时把 dict 字段序列化为 JSON 字符串，统一解析
            for dict_key in ("attacker_boosts", "defender_boosts", "attacker_evs", "defender_evs"):
                val = params.get(dict_key)
                if isinstance(val, str):
                    try:
                        params[dict_key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass

            # 自动填充唯一特性
            params = self._fill_sole_ability(params)

            # 自动推断特性触发的场地/天气
            params = self._infer_field_effects(params)

            # 自动检测世代：LLM 显式指定优先，否则根据双方宝可梦自动推断
            params = self._detect_generation(params)
            if params.get("_error"):
                return {
                    "success": False,
                    "type": "damage_calc",
                    "response": params["_error"],
                    "data": None,
                }

            # 如果引用了用户宝可梦，用保存的配置补全缺失参数
            if user_pokemon_list:
                params = self._apply_user_pokemon_config(params, user_pokemon_list)

            # 发送 step 92 进度：计算中
            if progress_callback:
                progress_callback(92, "计算中", "", "active")

            # Step 4: 执行计算
            t_calc = time.time()
            need_multi = self._should_calculate_multiple_scenarios(params)
            if need_multi:
                calc_result = self._execute_multi_scenario_calc(params)
            else:
                calc_result = self._execute_single_calc(params)
            if timings is not None:
                timings["calc"] = round(time.time() - t_calc, 2)

            if not calc_result["success"]:
                return calc_result

            # 计算完成 + 开始整理
            if progress_callback:
                progress_callback(92, "计算完成", "", "done")
                progress_callback(93, "整理回答", "", "active")

            # Step 5: LLM#3 总结
            raw_summary = calc_result["raw_summary"]
            try:
                t_llm3 = time.time()
                response_text = self.llm_service.summarize_damage_result(
                    message, raw_summary, context, model=model, call_log=call_log,
                    thinking_callback=thinking_callback,
                )
                if timings is not None:
                    timings["llm3"] = round(time.time() - t_llm3, 2)
                if not response_text or not response_text.strip():
                    raise ValueError("LLM#3 返回空内容")
                if progress_callback:
                    progress_callback(93, "整理完成", "", "done")
                return {
                    "success": True,
                    "type": "damage_calc",
                    "response": response_text,
                    "data": calc_result.get("data"),
                }
            except Exception as e:
                print(f"LLM#3 总结失败，使用模板 fallback: {e}")
                fallback = calc_result["fallback_response"]
                if progress_callback:
                    progress_callback(93, "整理完成", "", "done")
                return {
                    "success": True,
                    "type": "damage_calc",
                    "response": fallback,
                    "data": calc_result.get("data"),
                }

        except Exception as e:
            print(f"伤害计算管线失败: {e}")
            return {
                "success": False,
                "type": "damage_calc",
                "response": f"计算出错: {str(e)}",
                "data": None,
            }

    def _handle_damage_calc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理伤害计算"""
        try:
            # 检查必需参数
            required = ["attacker_name", "defender_name", "move_name"]
            if not all(k in params for k in required):
                missing = [k for k in required if k not in params]
                return {
                    "success": False,
                    "type": "damage_calc",
                    "response": f"抱歉，我没能理解你的问题。\n\n"
                               f"你可以这样问：\n"
                               f"• Mega喷火龙Y对Mega妙蛙花使用热风\n"
                               f"• 快龙神速能秒烈咬陆鲨吗\n"
                               f"• mega长耳兔三旋击打多鳞mega快龙有多少伤害\n\n"
                               f"缺少信息：{', '.join(missing)}",
                    "data": None
                }

            # 自动推断特性触发的场地/天气
            params = self._infer_field_effects(params)

            # 判断是否需要多情况计算
            need_multi_calc = self._should_calculate_multiple_scenarios(params)

            if need_multi_calc:
                return self._handle_multi_scenario_calc(params)
            else:
                return self._handle_single_calc(params)

        except Exception as e:
            return {
                "success": False,
                "type": "damage_calc",
                "response": f"计算出错: {str(e)}",
                "data": None
            }

    def _should_calculate_multiple_scenarios(self, params: Dict[str, Any]) -> bool:
        """判断是否需要多情况计算"""
        # 天气/场地冲突 → 需要多情况
        if params.get("_weather_conflict") or params.get("_terrain_conflict"):
            return True
        # 如果攻击方或防守方的努力值/点数、性格都没指定，则需要多情况计算
        atk_has_config = params.get("attacker_evs") or params.get("attacker_sps") or params.get("attacker_nature")
        def_has_config = params.get("defender_evs") or params.get("defender_sps") or params.get("defender_nature")
        # 用户宝可梦配置已应用时，标记为已配置
        if params.get("_user_pokemon_applied_attacker"):
            atk_has_config = True
        if params.get("_user_pokemon_applied_defender"):
            def_has_config = True
        return not (atk_has_config and def_has_config)

    def _apply_user_pokemon_config(self, params: Dict[str, Any], user_pokemon_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """用用户保存的宝可梦配置补全 LLM#2 提取的参数"""
        if not user_pokemon_list:
            return params

        # 构建 zh→en 性格映射（反转 _nature_en2zh）
        nature_zh2en = {v: k for k, v in self._nature_en2zh.items()}

        # 按英文名和中文名建索引
        by_en = {}
        by_zh = {}
        for p in user_pokemon_list:
            if p.get("name_en"):
                by_en[p["name_en"].lower()] = p
            if p.get("name"):
                by_zh[p["name"]] = p

        is_champ = params.get("generation") == 10
        ev_key = "sps" if is_champ else "evs"

        for side in ("attacker", "defender"):
            name = params.get(f"{side}_name", "")
            if not name:
                continue

            # 匹配用户宝可梦：先英文精确，再中文精确，再去形态后缀匹配
            matched = by_en.get(name.lower()) or by_zh.get(name)
            if not matched:
                matched = by_en.get(name.lower().replace(" ", "-"))
            if not matched:
                # 去掉形态后缀再匹配（用户存的是基础形态）
                # DB 格式：Charizard-Mega-Y → Charizard
                base_name = re.sub(r'-(mega(-[xy])?|primal|gmax|origin|therian|crowned)$', '', name, flags=re.IGNORECASE)
                if base_name.lower() != name.lower():
                    matched = by_en.get(base_name.lower()) or by_zh.get(base_name)
            if not matched:
                # NCP 格式：Mega Charizard Y → Charizard
                ncp_base = re.sub(r'^(Mega|Primal|Gmax)\s+', '', name, flags=re.IGNORECASE)
                ncp_base = re.sub(r'\s+[XY]$', '', ncp_base, flags=re.IGNORECASE)
                if ncp_base.lower() != name.lower():
                    matched = by_en.get(ncp_base.lower()) or by_zh.get(ncp_base)
            if not matched:
                # 中文形态：Mega喷火龙Y / 超级喷火龙Y → 喷火龙
                zh_base = re.sub(r'^(Mega|mega|超级|原始回归)', '', name)
                zh_base = re.sub(r'[XYxy]$', '', zh_base)
                if zh_base != name:
                    matched = by_zh.get(zh_base)
            if not matched:
                continue

            # 补全能力点数/努力值（仅在 LLM#2 未提取时）
            if not params.get(f"{side}_evs") and not params.get(f"{side}_sps"):
                evs = {}
                ev_mapping = [
                    ("ev_hp", "hp"), ("ev_attack", "atk"), ("ev_defense", "def"),
                    ("ev_sp_attack", "spa"), ("ev_sp_defense", "spd"), ("ev_speed", "spe"),
                ]
                for db_key, calc_key in ev_mapping:
                    val = matched.get(db_key, 0)
                    if val:
                        evs[calc_key] = val
                if evs:
                    params[f"{side}_{ev_key}"] = evs

            # 补全性格
            if not params.get(f"{side}_nature") and matched.get("nature"):
                en_nature = nature_zh2en.get(matched["nature"])
                if en_nature:
                    params[f"{side}_nature"] = en_nature

            # 补全特性
            if not params.get(f"{side}_ability") and matched.get("ability"):
                ability_en = self._zh2en(matched["ability"], "ability")
                if ability_en:
                    params[f"{side}_ability"] = ability_en

            # 补全道具
            if not params.get(f"{side}_item") and matched.get("item"):
                item_en = self._zh2en(matched["item"], "item")
                if item_en:
                    params[f"{side}_item"] = item_en

            params[f"_user_pokemon_applied_{side}"] = True

        return params

    def _execute_single_calc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行单一情况计算，返回含 raw_summary 和 fallback_response 的结果"""
        calc_params = {k: v for k, v in params.items() if not k.startswith("_")}
        result = self.damage_calc.calc.calculate(**calc_params)

        if not result.get("success"):
            return {
                "success": False,
                "type": "damage_calc",
                "response": f"计算失败: {result.get('error')}",
                "data": None,
            }

        return {
            "success": True,
            "raw_summary": self._build_raw_summary(params, result),
            "fallback_response": self._format_damage_response(params, result),
            "data": {
                "damage_range": result.get("damageRange"),
                "ko_chance": result.get("kochance"),
                "attacker": result.get("attacker"),
                "defender": result.get("defender"),
            },
        }

    def _execute_multi_scenario_calc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行多情况计算，返回含 raw_summary 和 fallback_response 的结果"""
        scenarios = self._generate_scenarios(params)
        results = []

        for scenario in scenarios:
            calc_params = {k: v for k, v in {**params, **scenario["params"]}.items() if not k.startswith("_")}
            result = self.damage_calc.calc.calculate(**calc_params)

            if result.get("success"):
                results.append({
                    "label": scenario["label"],
                    "params": calc_params,
                    "result": result,
                })

        if not results:
            return {
                "success": False,
                "type": "damage_calc",
                "response": "所有情况计算都失败了",
                "data": None,
            }

        return {
            "success": True,
            "raw_summary": self._build_multi_scenario_raw_summary(params, results),
            "fallback_response": self._format_multi_scenario_response(results),
            "data": {"scenarios": results},
        }

    def _handle_single_calc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理单一情况计算"""
        calc_params = {k: v for k, v in params.items() if not k.startswith("_")}
        result = self.damage_calc.calc.calculate(**calc_params)

        if result.get("success"):
            response = self._format_damage_response(params, result)
            return {
                "success": True,
                "type": "damage_calc",
                "response": response,
                "data": {
                    "damage_range": result.get("damageRange"),
                    "ko_chance": result.get("kochance"),
                    "attacker": result.get("attacker"),
                    "defender": result.get("defender")
                }
            }
        else:
            return {
                "success": False,
                "type": "damage_calc",
                "response": f"计算失败: {result.get('error')}",
                "data": None
            }

    def _handle_multi_scenario_calc(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理多情况计算"""
        scenarios = self._generate_scenarios(params)
        results = []

        for scenario in scenarios:
            calc_params = {k: v for k, v in {**params, **scenario["params"]}.items() if not k.startswith("_")}
            result = self.damage_calc.calc.calculate(**calc_params)

            if result.get("success"):
                results.append({
                    "label": scenario["label"],
                    "params": calc_params,
                    "result": result
                })

        if not results:
            return {
                "success": False,
                "type": "damage_calc",
                "response": "所有情况计算都失败了",
                "data": None
            }

        # 生成多情况总结
        response = self._format_multi_scenario_response(results)

        return {
            "success": True,
            "type": "damage_calc",
            "response": response,
            "data": {"scenarios": results}
        }

    def _generate_scenarios(self, params: Dict[str, Any]) -> list:
        """生成多种配置情况"""
        scenarios = []
        is_champ = params.get("generation") == 10
        # 宝可梦冠军用 sps（0-32），其他世代用 evs（0-252）
        ev_key = "sps" if is_champ else "evs"
        max_val = 32 if is_champ else 252

        # ── 天气/场地冲突情况（优先级最高，直接生成对应情况）──
        weather_conflict = params.get("_weather_conflict")
        terrain_conflict = params.get("_terrain_conflict")

        if weather_conflict or terrain_conflict:
            move_name = params.get("move_name", "")
            is_physical = self._is_physical_move(move_name)
            atk_stat = "atk" if is_physical else "spa"
            def_stat = "def" if is_physical else "spd"
            atk_nature_plus = "Adamant" if is_physical else "Modest"
            def_nature_plus = "Relaxed" if is_physical else "Careful"

            ev_configs = [
                ("满攻 vs 无耐久", {atk_stat: max_val}, "Serious", {"hp": 0, def_stat: 0}, "Serious"),
                ("极攻 vs 极限耐久", {atk_stat: max_val}, atk_nature_plus, {"hp": max_val, def_stat: max_val}, def_nature_plus),
            ]

            if weather_conflict:
                for weather in weather_conflict:
                    weather_zh = self.WEATHER_ZH.get(weather, weather)
                    for ev_label, atk_evs, atk_nat, def_evs, def_nat in ev_configs:
                        scenario_params = {
                            "weather": weather,
                            f"attacker_{ev_key}": atk_evs,
                            "attacker_nature": atk_nat,
                            f"defender_{ev_key}": def_evs,
                            "defender_nature": def_nat,
                        }
                        if terrain_conflict:
                            scenario_params["terrain"] = terrain_conflict[0]
                        scenarios.append({
                            "label": f"{weather_zh} {ev_label}",
                            "params": scenario_params,
                        })
            elif terrain_conflict:
                for terrain in terrain_conflict:
                    terrain_zh = self.TERRAIN_ZH.get(terrain, terrain)
                    for ev_label, atk_evs, atk_nat, def_evs, def_nat in ev_configs:
                        scenarios.append({
                            "label": f"{terrain_zh} {ev_label}",
                            "params": {
                                "terrain": terrain,
                                f"attacker_{ev_key}": atk_evs,
                                "attacker_nature": atk_nat,
                                f"defender_{ev_key}": def_evs,
                                "defender_nature": def_nat,
                            },
                        })
            return scenarios

        # ── 常规多配置情况（努力值/性格未指定时）──
        move_name = params.get("move_name", "")
        is_physical = self._is_physical_move(move_name)

        if is_physical:
            atk_stat, def_stat = "atk", "def"
            atk_nature_plus = "Adamant"  # +攻击 -特攻
            def_nature_plus = "Relaxed"  # +防御 -速度
        else:
            atk_stat, def_stat = "spa", "spd"
            atk_nature_plus = "Modest"   # +特攻 -攻击
            def_nature_plus = "Careful"  # +特防 -特攻

        # 情况1: 满攻 vs 无耐久
        scenarios.append({
            "label": "满攻 vs 无耐久",
            "params": {
                f"attacker_{ev_key}": {atk_stat: max_val},
                "attacker_nature": "Serious",
                f"defender_{ev_key}": {"hp": 0, def_stat: 0},
                "defender_nature": "Serious"
            }
        })

        # 情况2: 极攻 vs 极限耐久
        scenarios.append({
            "label": "极攻 vs 极限耐久",
            "params": {
                f"attacker_{ev_key}": {atk_stat: max_val},
                "attacker_nature": atk_nature_plus,
                f"defender_{ev_key}": {"hp": max_val, def_stat: max_val},
                "defender_nature": def_nature_plus
            }
        })

        return scenarios

    def _infer_field_effects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """根据特性自动推断天气/场地。
        若双方特性触发不同天气/场地，将冲突信息写入 params['_weather_conflict'] / params['_terrain_conflict']，
        供 _should_calculate_multiple_scenarios / _generate_scenarios 使用。
        """
        weathers = []   # [(side, weather_str), ...]
        terrains = []

        for side in ("attacker", "defender"):
            ability = (params.get(f"{side}_ability") or "").lower().replace("-", " ")
            if not ability:
                continue
            if ability in self.ABILITY_WEATHER_MAP:
                w = self.ABILITY_WEATHER_MAP[ability]
                if w:
                    weathers.append((side, w))
            if ability in self.ABILITY_TERRAIN_MAP:
                terrains.append((side, self.ABILITY_TERRAIN_MAP[ability]))

        # 去重（同一天气不算冲突）
        unique_weathers = list(dict.fromkeys(w for _, w in weathers))
        unique_terrains = list(dict.fromkeys(t for _, t in terrains))

        # 天气处理
        if not params.get("weather"):
            if len(unique_weathers) == 1:
                params["weather"] = unique_weathers[0]
            elif len(unique_weathers) > 1:
                # 冲突：记录所有可能天气，不直接设置
                params["_weather_conflict"] = unique_weathers

        # 场地处理
        if not params.get("terrain"):
            if len(unique_terrains) == 1:
                params["terrain"] = unique_terrains[0]
            elif len(unique_terrains) > 1:
                params["_terrain_conflict"] = unique_terrains

        return params

    def _detect_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """根据宝可梦名+道具自动检测世代，并将名称转为 NCP 格式。

        优先级：LLM 显式指定 > 限定图鉴匹配（含道具约束）> 全国图鉴 fallback > 报错。
        限定图鉴从新到旧：Champions(Gen10) → SV(Gen9)。
        全国图鉴：双方宝可梦+道具 first_gen <= 8 → Gen 8。
        """
        llm_set_gen = "generation" in params

        if not llm_set_gen:
            gen = self._infer_generation(params)
            if gen is None:
                return params  # _infer_generation 已设置 _error
            params["generation"] = gen

        # 根据世代处理努力值/能力点（LLM 输出均为字符串）
        max_val = 32 if params["generation"] == 10 else 252
        for side in ("attacker", "defender"):
            evs = params.get(f"{side}_evs")
            if evs:
                resolved = {}
                for k, v in evs.items():
                    if isinstance(v, str):
                        if v.lower() == "max":
                            resolved[k] = max_val
                        else:
                            try:
                                resolved[k] = min(max_val, max(0, int(v)))
                            except (ValueError, TypeError):
                                resolved[k] = v
                    elif isinstance(v, (int, float)):
                        resolved[k] = min(max_val, max(0, int(v)))
                    else:
                        resolved[k] = v
                if params["generation"] == 10:
                    params.pop(f"{side}_evs", None)
                    params[f"{side}_sps"] = resolved
                else:
                    params[f"{side}_evs"] = resolved

        # 通过 DB 的 name_ncp 列转换名称为 NCP 格式（所有世代都需要）
        for side in ("attacker_name", "defender_name"):
            if params.get(side):
                name = params[side]
                params[side] = self._ncp_cache.get(name) or self._ncp_cache.get(name.lower().replace(" ", "-")) or name
        return params

    def _infer_generation(self, params: Dict[str, Any]) -> Optional[int]:
        """根据双方宝可梦+道具推断世代，返回 generation 值或 None（设置 _error）。"""
        atk_name = params.get("attacker_name", "")
        def_name = params.get("defender_name", "")
        atk = self._gen_availability.get(atk_name) or self._gen_availability.get(atk_name.lower().replace(" ", "-"))
        def_ = self._gen_availability.get(def_name) or self._gen_availability.get(def_name.lower().replace(" ", "-"))

        # 收集所有参与者：宝可梦（必须）+ 道具（可选）
        participants = []  # list of (first_gen, in_sv, in_champions)

        if atk:
            participants.append(atk)
        if def_:
            participants.append(def_)

        for key in ("attacker_item", "defender_item"):
            item_name = params.get(key)
            if item_name:
                item_avail = self._item_gen_availability.get(item_name)
                if not item_avail:
                    # LLM#2 可能输出 kebab-case，转 Title Case 再查
                    item_avail = self._item_gen_availability.get(
                        item_name.replace("-", " ").title()
                    )
                if item_avail:
                    participants.append(item_avail)

        # 需要双方宝可梦都找到
        if not atk or not def_:
            params["_error"] = (
                f"无法推断世代：{atk_name} 和 {def_name} "
                f"没有共同的限定图鉴，也无法在全国图鉴中对战。"
            )
            return None

        # 从新到旧匹配：所有参与者都必须满足
        if all(p[2] for p in participants):  # 所有 in_champions=1
            return 10
        if all(p[1] for p in participants):  # 所有 in_sv=1
            return 9

        # 全国图鉴 fallback（Gen 1-8 统一用 Gen 8）
        atk_gen, _, _ = atk
        def_gen, _, _ = def_
        if atk_gen is not None and atk_gen <= 8 and def_gen is not None and def_gen <= 8:
            # 道具也要满足 first_gen <= 8
            item_gens = []
            for key in ("attacker_item", "defender_item"):
                item_name = params.get(key)
                if item_name:
                    item_avail = self._item_gen_availability.get(item_name)
                    if not item_avail:
                        item_avail = self._item_gen_availability.get(
                            item_name.replace("-", " ").title()
                        )
                    if item_avail:
                        item_gens.append(item_avail[0])
            if all(g is not None and g <= 8 for g in item_gens):
                return 8

        # 都找不到 → 报错
        params["_error"] = (
            f"无法推断世代：{atk_name} 和 {def_name} "
            f"没有共同的限定图鉴，也无法在全国图鉴中对战。"
        )
        return None

    def _fill_sole_ability(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """对只有一个特性的宝可梦自动填充特性（英文名）"""
        sole = getattr(self, "_sole_ability_map", {})
        for side in ("attacker", "defender"):
            if not params.get(f"{side}_ability"):
                name_en = params.get(f"{side}_name", "")
                # 规范化为数据库格式（Title Case → lower-kebab）
                name_key = name_en.lower().replace(" ", "-")
                ability = sole.get(name_key)
                if ability:
                    params = {**params, f"{side}_ability": ability}
        return params
