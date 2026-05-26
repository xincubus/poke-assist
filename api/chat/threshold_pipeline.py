"""
阈值计算管线 Mixin：攻击阈值 + 防御阈值搜索
"""
import json
import time
from typing import Dict, Any, Optional, List


class ThresholdPipelineMixin:
    """阈值计算管线相关方法"""

    # 能力缩写 → 中文名
    STAT_NAMES = {
        "hp": "HP", "atk": "攻击", "def": "防御",
        "spa": "特攻", "spd": "特防", "spe": "速度",
    }

    @staticmethod
    def stat_to_ev(stat_points: int) -> int:
        """将能力点数转换为对应的 EV 投入（旧世代）。
        0点→0EV, 1点→4EV, 2点→12EV, 3点→20EV, n点→(8n-4)EV
        """
        if stat_points <= 0:
            return 0
        return 8 * stat_points - 4

    @staticmethod
    def _ensure_gen10_sps(test_params: dict, is_champ: bool) -> dict:
        """Gen 10 时将 evs 转换为 sps，确保计算器使用正确的参数"""
        if not is_champ:
            return test_params
        for side in ("attacker", "defender"):
            ev_key = f"{side}_evs"
            sp_key = f"{side}_sps"
            evs = test_params.get(ev_key)
            if evs and not test_params.get(sp_key):
                sps = {}
                for k, v in evs.items():
                    try:
                        sps[k] = (int(v) + 4) // 8 if int(v) > 0 else 0  # 252 evs → 32 sps
                    except (ValueError, TypeError):
                        sps[k] = 0
                test_params[sp_key] = sps
                del test_params[ev_key]
        return test_params

    def _handle_threshold_pipeline(
        self, message: str, context: Optional[list] = None, model: str = None, tool_model: str = None,
        call_log: list = None, keywords: List[str] = None, timings: dict = None, user_context: str = None,
        user_pokemon_list: List[Dict[str, Any]] = None, progress_callback=None, thinking_callback=None,
        pre_tool_history: List[Dict[str, Any]] = None, terminal_args: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        阈值搜索完整管线：共享检索 -> LLM#2t 参数提取 -> 阈值扫描 -> LLM#3t 总结
        """
        try:
            # Step 0-2: 共享检索
            search_text, words = self._retrieve_for_calc(message, keywords, user_context, timings)

            # 如果 agent loop 已经查过数据，注入到 search_text 避免重复查询
            if pre_tool_history:
                loop_context = self._format_tool_history(pre_tool_history)
                if loop_context:
                    search_text = f"【已查数据】\n{loop_context}\n\n---\n\n{search_text}"

            # Step 3: LLM#2t 提取阈值参数
            if progress_callback:
                progress_callback(91, "提取参数", "", "active")
            t_llm2 = time.time()
            params = self.llm_service.extract_threshold_params(
                message, search_text, context, model=tool_model, call_log=call_log
            )
            if timings is not None:
                timings["llm2t"] = round(time.time() - t_llm2, 2)

            if not params or not params.get("attacker_name"):
                return {
                    "success": False,
                    "type": "threshold_calc",
                    "response": "抱歉，我没能从你的描述中提取出阈值搜索参数。\n\n"
                               "你可以这样问：\n"
                               "  mega雪妖女加多少能力值使用暗影球能秒无耐久mega耿鬼\n"
                               "  mega耿鬼加多少耐久能抗住满攻雪妖女的暗影球",
                    "data": None,
                }

            # 发送 step 91 进度
            if progress_callback:
                atk = params.get("attacker_name", "")
                threshold_type = params.get("threshold_type", "defensive")
                target_ko = params.get("target_ko", 1)
                type_label = "攻击阈值" if threshold_type == "offensive" else "防御阈值"
                detail = f"{atk}, {type_label}, 目标{target_ko}HKO"
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
            # 自动检测世代
            params = self._detect_generation(params)
            if params.get("_error"):
                return {
                    "success": False,
                    "type": "threshold_calc",
                    "response": params["_error"],
                    "data": None,
                }

            # 用户宝可梦配置补全
            if user_pokemon_list:
                params = self._apply_user_pokemon_config(params, user_pokemon_list)

            # 确保 target_ko 默认为 1
            if not params.get("target_ko"):
                params["target_ko"] = 1

            # 发送 step 92 进度：计算中
            if progress_callback:
                progress_callback(92, "计算中", "", "active")

            # Step 4: 根据 threshold_type 路由到具体计算
            t_calc = time.time()
            threshold_type = params.get("threshold_type", "defensive")
            if threshold_type == "offensive":
                calc_result = self._handle_offensive_threshold(params)
            else:
                calc_result = self._handle_defensive_threshold(params)
            calc_elapsed = round(time.time() - t_calc, 2)
            if timings is not None:
                timings["threshold_calc"] = calc_elapsed

            if not calc_result.get("success"):
                return calc_result

            # 计算完成 + 开始整理
            if progress_callback:
                progress_callback(92, "计算完成", "", "done")
                progress_callback(93, "整理回答", "", "active")

            # Step 5: LLM#3t 总结
            raw_summary = calc_result["raw_summary"]
            try:
                t_llm3 = time.time()
                response_text = self.llm_service.summarize_threshold_result(
                    message, raw_summary, context, model=model, call_log=call_log,
                    thinking_callback=thinking_callback,
                )
                llm3t_elapsed = round(time.time() - t_llm3, 2)
                if timings is not None:
                    timings["llm3t"] = llm3t_elapsed
                if not response_text or not response_text.strip():
                    raise ValueError("LLM#3t 返回空内容")
                if progress_callback:
                    progress_callback(93, "整理完成", "", "done")
                return {
                    "success": True,
                    "type": "threshold_calc",
                    "response": response_text,
                    "data": calc_result.get("data"),
                }
            except Exception as e:
                print(f"LLM#3t 总结失败，使用模板 fallback: {e}")
                fallback = calc_result.get("fallback_response", "")
                if progress_callback:
                    progress_callback(93, "整理完成", "", "done")
                return {
                    "success": True,
                    "type": "threshold_calc",
                    "response": fallback,
                    "data": calc_result.get("data"),
                }

        except Exception as e:
            print(f"阈值搜索管线失败: {e}")
            return {
                "success": False,
                "type": "threshold_calc",
                "response": f"阈值搜索出错: {str(e)}",
                "data": None,
            }

    def _handle_offensive_threshold(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """攻击阈值搜索：扫描攻击能力值，找到满足 target_ko 的最低投入"""
        generation = params.get("generation", 10)
        is_champ = generation == 10
        # 统一按能力点数扫描（0-32），再转换为努力值
        max_points = 32
        target_ko = params.get("target_ko", 1)

        move_name = params.get("move_name", "")
        is_physical = self._is_physical_move(move_name)
        atk_stat_key = "atk" if is_physical else "spa"
        def_stat_key = "def" if is_physical else "spd"
        # 防守方默认极限耐久（满 HP + 满防），性格由 LLM 决定
        if not params.get("defender_evs") and not params.get("defender_sps"):
            if is_champ:
                params.setdefault("defender_sps", {"hp": 32, def_stat_key: 32})
            else:
                params.setdefault("defender_evs", {"hp": 252, def_stat_key: 252})

        results = []
        last_valid_result = None  # 跟踪最后一次有效计算结果
        last_valid_params = None
        for pts in range(0, max_points + 1):
            test_params = {k: v for k, v in params.items() if not k.startswith("_") and k not in ("threshold_type", "target_ko")}
            # Gen 10: 将 LLM 提取的 evs 转换为 sps
            test_params = self._ensure_gen10_sps(test_params, is_champ)
            # 设置攻击方投入
            if is_champ:
                test_params["attacker_sps"] = {atk_stat_key: pts}
            else:
                test_params["attacker_evs"] = {atk_stat_key: self.stat_to_ev(pts)}
            # 防守方默认极限耐久（满 HP + 满防 + 加防性格）
            if not test_params.get("defender_evs") and not test_params.get("defender_sps"):
                if is_champ:
                    test_params["defender_sps"] = {"hp": 32, def_stat_key: 32}
                else:
                    test_params["defender_evs"] = {"hp": 252, def_stat_key: 252}
                # 防守方性格由 LLM 决定，不硬编码默认值

            calc_result = self.damage_calc.calc.calculate(**test_params)
            if not calc_result.get("success"):
                continue

            last_valid_result = calc_result
            last_valid_params = test_params.copy()

            kochance = calc_result.get("kochance", {})
            ko_n = kochance.get("n", 999)
            ko_chance = kochance.get("chance", 0)

            # 检查是否达到目标确数（必须 guaranteed，不接受概率击杀）
            if ko_n <= target_ko and ko_chance == 1:
                ev_invested = pts if is_champ else self.stat_to_ev(pts)
                ev_label = "能力点" if is_champ else "努力值"
                results.append({
                    "stat_value": pts,
                    "ev_invested": ev_invested,
                    "ev_label": ev_label,
                    "atk_stat_key": atk_stat_key,
                    "params": test_params,
                    "result": calc_result,
                })

        if not results:
            # 即使无法达成目标，也展示满投入的伤害数据和计算器链接
            atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
            def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
            move_zh = self._en2zh(move_name, "move")
            mode = "单打" if params.get("mode") == "Singles" else "双打"
            ev_label = "能力点" if is_champ else "努力值"
            stat_zh = self.STAT_NAMES.get(atk_stat_key, atk_stat_key)

            # 防守方配置描述
            def_evs = params.get("defender_evs") or {}
            def_sps = params.get("defender_sps") or {}
            def_all_zero = all(v == 0 for v in list(def_evs.values()) + list(def_sps.values())) if (def_evs or def_sps) else False
            if def_all_zero:
                def_desc = f"无耐久 {def_name}"
            else:
                def_stat_zh = self.STAT_NAMES.get(def_stat_key, def_stat_key)
                def_nature = params.get("defender_nature")
                def_invest_hp = 32 if is_champ else 252
                def_invest_def = 32 if is_champ else 252
                def_desc = f"{def_invest_hp} HP / {def_invest_def} {def_stat_zh} {def_nature + ' ' if def_nature else ''}{def_name}"
            weather = params.get("weather")
            if weather:
                def_desc += f" [{weather}]"

            # 用满投入的计算结果展示最接近的伤害
            rr = last_valid_result or {}
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_text_str = self._format_ko_text(rr.get("kochance", {}))
            max_pts = 32
            max_ev = max_pts if is_champ else self.stat_to_ev(max_pts)
            stat_str = f"{stat_zh}+{max_pts}({max_ev}{ev_label})"

            lines = [
                f"对战模式: {mode}",
                f"阈值类型: 攻击阈值",
                f"目标: {target_ko}确击杀",
                f"攻击方: {atk_name}",
                f"防守方: {def_desc}",
                f"招式: {move_zh}",
                f"结论: 即使投入全部{ev_label}也无法达成 {target_ko} 确击杀",
                "",
                f"  满投入参考: {stat_str}",
                f"  伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)",
                f"  击杀: {ko_text_str}",
            ]
            if last_valid_params:
                lines.append(f"  在线计算器: [点击查看]({self._build_calc_url(last_valid_params)})")

            raw_summary = "\n".join(lines)

            fallback_parts = [f"即使投入全部{ev_label}也无法达成 {target_ko} 确击杀。"]
            if last_valid_result:
                fallback_parts.append(f"满投入参考: {stat_str} {atk_name} {move_zh} vs. {def_name} : {damage_range[0]}-{damage_range[1]} ({pct_min}-{pct_max}%) -- {ko_text_str}")
                if last_valid_params:
                    fallback_parts.append(f"  [在线计算器]({self._build_calc_url(last_valid_params)})")
            fallback = "\n".join(fallback_parts)

            return {
                "success": True,
                "raw_summary": raw_summary,
                "fallback_response": fallback,
                "data": {"threshold_type": "offensive", "max_investment_reached": True},
            }

        # 输出方案：最少投入 + 满投入
        min_result = results[0]
        max_result = results[-1]
        if len(results) == 1:
            output_list = [min_result]
        else:
            output_list = [min_result, max_result]

        # 构建 raw_summary
        atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
        def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
        move_zh = self._en2zh(move_name, "move")
        mode = "单打" if params.get("mode") == "Singles" else "双打"
        ev_label = min_result["ev_label"]
        stat_zh = self.STAT_NAMES.get(min_result["atk_stat_key"], min_result["atk_stat_key"])

        # 防守方配置描述
        def_evs = params.get("defender_evs") or {}
        def_sps = params.get("defender_sps") or {}
        def_all_zero = all(v == 0 for v in list(def_evs.values()) + list(def_sps.values())) if (def_evs or def_sps) else False
        def_label = "能力点" if is_champ else "努力值"
        def_stat_zh = self.STAT_NAMES.get(def_stat_key, def_stat_key)
        if def_all_zero:
            def_desc = f"无耐久 {def_name}"
        else:
            def_nature = params.get("defender_nature")
            def_invest_hp = 32 if is_champ else 252
            def_invest_def = 32 if is_champ else 252
            def_desc = f"{def_invest_hp} HP / {def_invest_def} {def_stat_zh} {def_nature + ' ' if def_nature else ''}{def_name}"
        weather = params.get("weather")
        if weather:
            def_desc += f" [{weather}]"

        lines = [
            f"对战模式: {mode}",
            f"阈值类型: 攻击阈值",
            f"目标: {target_ko}确击杀",
            f"攻击方: {atk_name}",
            f"防守方: {def_desc}",
            f"招式: {move_zh}",
            "",
        ]

        output_results = []
        for r in output_list:
            label = "最少投入" if r == min_result else "满投入"
            rp = r["params"]
            rr = r["result"]
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_text_str = self._format_ko_text(rr.get("kochance", {}))

            stat_str = f"{stat_zh}+{r['stat_value']}({r['ev_invested']}{r['ev_label']})"
            lines.append(f"  方案: {label}")
            lines.append(f"  投入: {stat_str}")
            lines.append(f"  伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)")
            lines.append(f"  击杀: {ko_text_str}")
            lines.append(f"  在线计算器: [点击查看]({self._build_calc_url(rp)})")
            lines.append("")
            output_results.append({"label": label, "params": rp, "result": rr})

        raw_summary = "\n".join(lines)

        # 构建 fallback
        fallback_lines = [f"双打模式下，至少需要 {stat_zh}+{min_result['stat_value']}({min_result['ev_invested']}{ev_label}) 才能{target_ko}确击杀。", ""]
        for r in output_list:
            label = "最少投入" if r == min_result else "满投入"
            rp = r["params"]
            rr = r["result"]
            stat_str = f"{stat_zh}+{r['stat_value']}({r['ev_invested']}{r['ev_label']})"
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_str = self._format_ko_text_short(rr.get("kochance", {}))
            atk_name_zh = self._en2zh(rp.get("attacker_name", ""), "pokemon")
            move_name_zh = self._en2zh(rp.get("move_name", ""), "move")
            def_name_zh = self._en2zh(rp.get("defender_name", ""), "pokemon")
            fallback_lines.append(f"{label}: {stat_str} {atk_name_zh} {move_name_zh} vs. {def_name_zh} : {damage_range[0]}-{damage_range[1]} ({pct_min}-{pct_max}%) -- {ko_str}")
            fallback_lines.append(f"  [在线计算器]({self._build_calc_url(rp)})")
        fallback = "\n".join(fallback_lines)

        return {
            "success": True,
            "raw_summary": raw_summary,
            "fallback_response": fallback,
            "data": {"results": output_results, "threshold_type": "offensive"},
        }

    def _handle_defensive_threshold(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """防御阈值搜索：扫描 HP 和防御能力值，找到满足存活条件的最低投入"""
        generation = params.get("generation", 10)
        is_champ = generation == 10
        # 统一按能力点数扫描（0-32），再转换为努力值
        max_points = 32
        target_ko = params.get("target_ko", 1)
        max_damage_pct = params.get("max_damage_pct")  # 最大掉血百分比（可选，0-100）

        move_name = params.get("move_name", "")
        is_physical = self._is_physical_move(move_name)
        def_stat_key = "def" if is_physical else "spd"
        def_stat_zh = self.STAT_NAMES.get(def_stat_key, def_stat_key)
        atk_stat_key = "atk" if is_physical else "spa"
        ev_label = "能力点" if is_champ else "努力值"

        def _test_survival(hp_points, def_points):
            """测试给定 HP+防御能力点数能否存活 target_ko 确"""
            test_params = {k: v for k, v in params.items() if not k.startswith("_") and k not in ("threshold_type", "target_ko", "max_damage_pct")}
            # Gen 10: 将 LLM 提取的 evs 转换为 sps
            test_params = self._ensure_gen10_sps(test_params, is_champ)
            if is_champ:
                test_params["defender_sps"] = {"hp": hp_points, def_stat_key: def_points}
            else:
                # 旧世代：能力点数转努力值
                test_params["defender_evs"] = {
                    "hp": self.stat_to_ev(hp_points),
                    def_stat_key: self.stat_to_ev(def_points),
                }

            calc_result = self.damage_calc.calc.calculate(**test_params)
            if not calc_result.get("success"):
                return None, None

            kochance = calc_result.get("kochance", {})
            ko_n = kochance.get("n", 999)
            return calc_result, ko_n

        # 攻击方默认满投资（性格由 LLM 决定，满攻不需要加攻性格）
        if not params.get("attacker_evs") and not params.get("attacker_sps"):
            if is_champ:
                params.setdefault("attacker_sps", {atk_stat_key: 32})
            else:
                params.setdefault("attacker_evs", {atk_stat_key: 252})

        # 全局搜索：遍历所有 HP+防御 组合，找总投入最少的
        best_combo = None  # (hp, def, result, total_ev)
        hp_only = None
        def_only = None
        hp_max = None
        full_invest = None

        for hp_pts in range(0, max_points + 1):
            hp_ev = hp_pts if is_champ else self.stat_to_ev(hp_pts)
            for def_pts in range(0, max_points + 1):
                result, ko_n = _test_survival(hp_pts, def_pts)
                if not result:
                    continue
                if max_damage_pct is not None:
                    # 按掉血百分比判断：最大伤害 <= 最大HP * 百分比
                    dmg_range = result.get("damageRange", [0, 0])
                    def_hp = result.get("defender", {}).get("hp", 1)
                    if dmg_range[1] > def_hp * max_damage_pct / 100:
                        continue
                elif ko_n <= target_ko:
                    continue

                def_ev = def_pts if is_champ else self.stat_to_ev(def_pts)
                total = hp_ev + def_ev

                # 记录全局最优（总投入最少）
                if best_combo is None or total < best_combo[3]:
                    best_combo = (hp_pts, def_pts, result, total)

                # 记录只投 HP（def=0）
                if def_pts == 0 and hp_only is None:
                    hp_only = {"hp": hp_pts, "def": 0, "result": result, "total_ev": hp_ev}
                # 记录只投防御（hp=0）
                if hp_pts == 0 and def_only is None:
                    def_only = {"hp": 0, "def": def_pts, "result": result, "total_ev": def_ev}
                # 记录满 HP + 最少防御
                if hp_pts == max_points and hp_max is None:
                    hp_max = {"hp": max_points, "def": def_pts, "result": result, "total_ev": total}
                # 记录满投入
                if hp_pts == max_points and def_pts == max_points:
                    full_invest = {"hp": max_points, "def": max_points, "result": result, "total_ev": total}

                break  # 找到当前 hp_pts 的最小 def，继续下一组 hp

        # 收集所有可行方案
        ev_label = "能力点" if is_champ else "努力值"
        all_schemes = []
        if hp_only:
            all_schemes.append(("只投HP", hp_only))
        if def_only:
            all_schemes.append(("只投防御", def_only))
        if best_combo:
            hp_val, def_val, result, total = best_combo
            # 如果最优组合和已有的只投HP/只投防御相同，标记"最少投入"
            is_dup = False
            for i, (label, s) in enumerate(all_schemes):
                if s["hp"] == hp_val and s["def"] == def_val:
                    all_schemes[i] = (label + "（最少投入）", s)
                    is_dup = True
                    break
            if not is_dup:
                all_schemes.append(("最少投入", {
                    "hp": hp_val, "def": def_val, "result": result, "total_ev": total,
                }))
        if hp_max:
            all_schemes.append(("满HP+防御", hp_max))
        if full_invest:
            all_schemes.append(("满投入", full_invest))

        if not all_schemes:
            # 检查不加耐久能否接住
            base_result, base_ko_n = _test_survival(0, 0)
            base_survives = False
            if base_result:
                if max_damage_pct is not None:
                    dmg_range = base_result.get("damageRange", [0, 0])
                    def_hp = base_result.get("defender", {}).get("hp", 1)
                    base_survives = dmg_range[1] <= def_hp * max_damage_pct / 100
                else:
                    base_survives = base_ko_n > target_ko
            if base_survives:
                # 展示无投入时的伤害数据和计算器链接
                mode = "单打" if params.get("mode") == "Singles" else "双打"
                atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
                def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
                move_zh = self._en2zh(move_name, "move")
                damage_range = base_result.get("damageRange", [0, 0])
                defender_hp = base_result.get("defender", {}).get("hp", 1)
                pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
                pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
                ko_text_str = self._format_ko_text(base_result.get("kochance", {}))

                # 构建无投入的 URL 参数
                url_params = {k: v for k, v in params.items() if not k.startswith("_") and k not in ("threshold_type", "target_ko", "max_damage_pct")}
                url_params = self._ensure_gen10_sps(url_params, is_champ)
                if is_champ:
                    url_params["defender_sps"] = {"hp": 0, def_stat_key: 0}
                else:
                    url_params["defender_evs"] = {"hp": 0, def_stat_key: 0}

                lines = [
                    f"对战模式: {mode}",
                    f"阈值类型: 防御阈值",
                    f"结论: 不加耐久也能接住",
                    f"攻击方: {atk_name} {move_zh}",
                    f"防守方: {def_name}",
                    "",
                    f"  无投入伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)",
                    f"  击杀: {ko_text_str}",
                    f"  在线计算器: [点击查看]({self._build_calc_url(url_params)})",
                ]
                raw_summary = "\n".join(lines)
                fallback = f"不加耐久也能接住 {atk_name} {move_zh} 的攻击。无投入伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}-{pct_max}%) -- {ko_text_str}\n  [在线计算器]({self._build_calc_url(url_params)})"
                return {
                    "success": True,
                    "raw_summary": raw_summary,
                    "fallback_response": fallback,
                    "data": {"threshold_type": "defensive", "no_investment_needed": True},
                }
            # 即使无法达成目标，也展示满投入的伤害数据和计算器链接
            max_result, _ = _test_survival(max_points, max_points)
            atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
            def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
            move_zh = self._en2zh(move_name, "move")
            mode = "单打" if params.get("mode") == "Singles" else "双打"
            hp_ev = max_points if is_champ else self.stat_to_ev(max_points)
            def_ev = max_points if is_champ else self.stat_to_ev(max_points)
            stat_str = f"HP+{max_points}({hp_ev}{ev_label}) / {def_stat_zh}+{max_points}({def_ev}{ev_label})"

            rr = max_result or {}
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_text_str = self._format_ko_text(rr.get("kochance", {}))

            # 构建满投入的 URL 参数
            url_params = {k: v for k, v in params.items() if not k.startswith("_") and k not in ("threshold_type", "target_ko", "max_damage_pct")}
            url_params = self._ensure_gen10_sps(url_params, is_champ)
            if is_champ:
                url_params["defender_sps"] = {"hp": max_points, def_stat_key: max_points}
            else:
                url_params["defender_evs"] = {"hp": self.stat_to_ev(max_points), def_stat_key: self.stat_to_ev(max_points)}

            if max_damage_pct is not None:
                conclusion = f"即使投入全部{ev_label}也无法将掉血控制在{max_damage_pct}%以下"
            else:
                conclusion = f"即使投入全部{ev_label}也无法存活 {target_ko} 确"

            lines = [
                f"对战模式: {mode}",
                f"阈值类型: 防御阈值",
                f"结论: {conclusion}",
                f"攻击方: {atk_name} {move_zh}",
                f"防守方: {def_name}",
                "",
                f"  满投入参考: {stat_str}",
                f"  伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)",
                f"  击杀: {ko_text_str}",
            ]
            if max_result:
                lines.append(f"  在线计算器: [点击查看]({self._build_calc_url(url_params)})")

            raw_summary = "\n".join(lines)
            fallback_parts = [f"{conclusion}。"]
            if max_result:
                fallback_parts.append(f"满投入参考: {stat_str} {atk_name} {move_zh} vs. {def_name} : {damage_range[0]}-{damage_range[1]} ({pct_min}-{pct_max}%) -- {ko_text_str}")
                fallback_parts.append(f"  [在线计算器]({self._build_calc_url(url_params)})")
            fallback = "\n".join(fallback_parts)

            return {
                "success": True,
                "raw_summary": raw_summary,
                "fallback_response": fallback,
                "data": {"threshold_type": "defensive", "max_investment_reached": True},
            }

        # 推荐方案：总投入最少的
        best_scheme = min(all_schemes, key=lambda x: x[1]["total_ev"])

        # 构建 raw_summary
        atk_name = self._en2zh(params.get("attacker_name", "?"), "pokemon")
        def_name = self._en2zh(params.get("defender_name", "?"), "pokemon")
        move_zh = self._en2zh(move_name, "move")
        mode = "单打" if params.get("mode") == "Singles" else "双打"

        # 攻击方配置描述
        atk_stat_zh = self.STAT_NAMES.get(atk_stat_key, atk_stat_key)
        atk_nature = params.get("attacker_nature")
        atk_invest = 32 if is_champ else 252
        atk_label = "能力点" if is_champ else "努力值"
        atk_desc = f"{atk_invest}{atk_label} {atk_nature + ' ' if atk_nature else ''}{atk_name} {move_zh}"
        weather = params.get("weather")
        if weather:
            atk_desc += f" [{weather}]"

        goal_desc = f"不被{target_ko}确击杀"
        if max_damage_pct is not None:
            goal_desc += f"，掉血不超过{max_damage_pct}%"
        # 构建推荐方案的投入描述
        best_r = best_scheme[1]
        best_hp_ev = best_r["hp"] if is_champ else self.stat_to_ev(best_r["hp"])
        best_def_ev = best_r["def"] if is_champ else self.stat_to_ev(best_r["def"])
        best_hp_str = f"HP+{best_r['hp']}({best_hp_ev}{ev_label})" if best_r["hp"] > 0 else ""
        best_def_str = f"{def_stat_zh}+{best_r['def']}({best_def_ev}{ev_label})" if best_r["def"] > 0 else ""
        best_parts = [p for p in [best_hp_str, best_def_str] if p]
        best_invest = " / ".join(best_parts) if best_parts else "无投入"

        lines = [
            f"对战模式: {mode}",
            f"阈值类型: 防御阈值",
            f"目标: {goal_desc}",
            f"攻击方: {atk_desc}",
            f"防守方: {def_name}",
            f"推荐方案: {best_scheme[0]}，{best_invest}，总投入={best_r['total_ev']}{ev_label}",
            "",
        ]

        output_results = []
        for label, r in all_schemes:
            rr = r["result"]
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_text_str = self._format_ko_text(rr.get("kochance", {}))

            hp_ev = r["hp"] if is_champ else self.stat_to_ev(r["hp"])
            def_ev = r["def"] if is_champ else self.stat_to_ev(r["def"])
            hp_str = f"HP+{r['hp']}({hp_ev}{ev_label})" if r["hp"] > 0 else ""
            def_str = f"{def_stat_zh}+{r['def']}({def_ev}{ev_label})" if r["def"] > 0 else ""
            invest_parts = [p for p in [hp_str, def_str] if p]
            invest_str = " / ".join(invest_parts) if invest_parts else "无投入"

            # 构建含防守方投入的 URL 参数
            url_params = {**params}
            if is_champ:
                url_params["defender_sps"] = {"hp": r["hp"], def_stat_key: r["def"]}
            else:
                url_params["defender_evs"] = {"hp": self.stat_to_ev(r["hp"]), def_stat_key: self.stat_to_ev(r["def"])}
            # 确保攻击方默认参数也在 URL 中
            if not url_params.get("attacker_sps") and not url_params.get("attacker_evs"):
                if is_champ:
                    url_params["attacker_sps"] = {atk_stat_key: 32}
                else:
                    url_params["attacker_evs"] = {atk_stat_key: 252}

            lines.append(f"  方案: {label}")
            lines.append(f"  投入: {invest_str} (总投入={r['total_ev']}{ev_label})")
            lines.append(f"  伤害: {damage_range[0]}-{damage_range[1]} ({pct_min}%-{pct_max}%)")
            lines.append(f"  击杀: {ko_text_str}")
            lines.append(f"  在线计算器: [点击查看]({self._build_calc_url(url_params)})")
            lines.append("")
            output_results.append({"label": label, "params": r, "result": rr})

        raw_summary = "\n".join(lines)

        # 构建 fallback
        best_r = best_scheme[1]
        best_hp_ev = best_r["hp"] if is_champ else self.stat_to_ev(best_r["hp"])
        best_def_ev = best_r["def"] if is_champ else self.stat_to_ev(best_r["def"])
        best_hp_str = f"HP+{best_r['hp']}({best_hp_ev}{ev_label})" if best_r["hp"] > 0 else ""
        best_def_str = f"{def_stat_zh}+{best_r['def']}({best_def_ev}{ev_label})" if best_r["def"] > 0 else ""
        best_parts = [p for p in [best_hp_str, best_def_str] if p]
        best_invest = " / ".join(best_parts) if best_parts else "无投入"

        fallback_lines = [
            f"双打模式下，推荐 {best_invest}，总投入={best_r['total_ev']}{ev_label}。",
            "",
        ]
        for label, r in all_schemes:
            rr = r["result"]
            damage_range = rr.get("damageRange", [0, 0])
            defender_hp = rr.get("defender", {}).get("hp", 1)
            pct_min = round(damage_range[0] / defender_hp * 100, 1) if defender_hp else 0
            pct_max = round(damage_range[1] / defender_hp * 100, 1) if defender_hp else 0
            ko_str = self._format_ko_text_short(rr.get("kochance", {}))
            hp_ev = r["hp"] if is_champ else self.stat_to_ev(r["hp"])
            def_ev = r["def"] if is_champ else self.stat_to_ev(r["def"])
            hp_part = f"HP+{r['hp']}({hp_ev}{ev_label})" if r["hp"] > 0 else ""
            def_part = f"{def_stat_zh}+{r['def']}({def_ev}{ev_label})" if r["def"] > 0 else ""
            invest = " / ".join(p for p in [hp_part, def_part] if p) or "无投入"
            # 构建含防守方投入的 URL 参数
            url_params = {**params}
            if is_champ:
                url_params["defender_sps"] = {"hp": r["hp"], def_stat_key: r["def"]}
            else:
                url_params["defender_evs"] = {"hp": self.stat_to_ev(r["hp"]), def_stat_key: self.stat_to_ev(r["def"])}
            # 确保攻击方默认参数也在 URL 中
            if not url_params.get("attacker_sps") and not url_params.get("attacker_evs"):
                if is_champ:
                    url_params["attacker_sps"] = {atk_stat_key: 32}
                else:
                    url_params["attacker_evs"] = {atk_stat_key: 252}
            fallback_lines.append(f"{label}: {invest} -> {damage_range[0]}-{damage_range[1]} ({pct_min}-{pct_max}%) -- {ko_str}")
            fallback_lines.append(f"  [在线计算器]({self._build_calc_url(url_params)})")
        fallback = "\n".join(fallback_lines)

        return {
            "success": True,
            "raw_summary": raw_summary,
            "fallback_response": fallback,
            "data": {"results": output_results, "threshold_type": "defensive", "recommended": best_scheme[0]},
        }
