"""
LLM 服务 - Agent Loop 核心循环 + 工具标签/展示

参数提取和结果总结已拆分到 api/llm/ 模块：
- api/llm/param_extractors.py: extract_damage_calc_params, extract_threshold_params
- api/llm/summarizers.py: summarize_query_result, summarize_damage_result, summarize_threshold_result
- api/llm/rejection.py: is_rejection, REJECTION_RETRY_NOTE
- api/llm/helpers.py: load_prompt, load_tools, extra_params, build_messages_with_context
"""
import json
import os
from typing import Dict, Any

from openai import OpenAI
import httpx

from .llm.helpers import load_prompt, load_tools, extra_params, build_messages_with_context
from .llm.rejection import is_rejection, REJECTION_RETRY_NOTE
from .llm.param_extractors import extract_damage_calc_params as _extract_damage, extract_threshold_params as _extract_threshold
from .llm.summarizers import (
    summarize_query_result as _summarize_query,
    summarize_damage_result as _summarize_damage,
    summarize_threshold_result as _summarize_threshold,
)
from .task_planner import TaskPlanner


class LLMService:
    """LLM 服务封装 - Agent Loop 核心"""

    @staticmethod
    def _create_client(api_key: str, base_url: str) -> OpenAI:
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(60, connect=10),
        )

    def __init__(self):
        # Agent Loop / 参数提取 client（工具调用）
        tool_key = os.getenv("LLM_TOOL_USE_API_KEY")
        tool_url = os.getenv("LLM_TOOL_USE_BASE_URL")
        if not tool_key or not tool_url:
            raise ValueError("需要提供 LLM_TOOL_USE_API_KEY 和 LLM_TOOL_USE_BASE_URL 环境变量")
        self.client = self._create_client(tool_key, tool_url)
        self.default_tool_model = os.getenv("LLM_MODEL_TOOL_USE", "deepseek-chat")
        self.default_model = self.default_tool_model  # 外部兼容（main.py generate_title）

        # max_tokens 配置
        self._max_tokens_tool = int(os.getenv("LLM_MAX_TOKENS_TOOL_USE", "16384"))

        # 思考模式开关（enabled / disabled / auto）
        self._thinking_tool = os.getenv("LLM_THINKING_TOOL_USE", "auto").lower()

        # 模型升级：Agent Loop 超过 N 轮后切换更强模型（独立 client，可跨厂商）
        escalation_key = os.getenv("LLM_ESCALATION_API_KEY")
        escalation_url = os.getenv("LLM_ESCALATION_BASE_URL")
        self._escalation_model = os.getenv("LLM_ESCALATION_MODEL", "")
        self._escalation_after = int(os.getenv("LLM_ESCALATION_AFTER_ROUNDS", "6"))
        if escalation_key and escalation_url and self._escalation_model:
            self.escalation_client = self._create_client(escalation_key, escalation_url)
            self._max_tokens_escalation = int(os.getenv("LLM_MAX_TOKENS_ESCALATION", "16384"))
            self._thinking_escalation = os.getenv("LLM_THINKING_ESCALATION", "disabled").lower()
        else:
            self.escalation_client = self.client
            self._max_tokens_escalation = self._max_tokens_tool
            self._thinking_escalation = self._thinking_tool

        # 参数提取 client（伤害计算 LLM#2 / 阈值计算 LLM#2t，独立配置）
        calc_key = os.getenv("LLM_CALC_API_KEY")
        calc_url = os.getenv("LLM_CALC_BASE_URL")
        if calc_key and calc_url:
            self.calc_client = self._create_client(calc_key, calc_url)
            self.default_calc_model = os.getenv("LLM_MODEL_CALC", "deepseek-v4-pro")
            self._max_tokens_calc = int(os.getenv("LLM_MAX_TOKENS_CALC", "16384"))
            self._thinking_calc = os.getenv("LLM_THINKING_CALC", "disabled").lower()
        else:
            # fallback 到 tool_use client
            self.calc_client = self.client
            self.default_calc_model = self.default_tool_model
            self._max_tokens_calc = self._max_tokens_tool
            self._thinking_calc = self._thinking_tool

        # 结果总结 client（查询 / 伤害 / 阈值共用）
        summary_key = os.getenv("LLM_SUMMARY_API_KEY")
        summary_url = os.getenv("LLM_SUMMARY_BASE_URL")
        if not summary_key or not summary_url:
            raise ValueError("需要提供 LLM_SUMMARY_API_KEY 和 LLM_SUMMARY_BASE_URL 环境变量")
        self.summary_client = self._create_client(summary_key, summary_url)
        self.default_summary_model = os.getenv("LLM_MODEL_SUMMARY", "deepseek-v4-flash")
        self._max_tokens_summary = int(os.getenv("LLM_MAX_TOKENS_SUMMARY", "16384"))

        # 各总结环节独立思考模式
        self._thinking_query_summary = os.getenv("LLM_THINKING_QUERY_SUMMARY", "enabled").lower()
        self._thinking_damage_summary = os.getenv("LLM_THINKING_DAMAGE_SUMMARY", "disabled").lower()
        self._thinking_threshold_summary = os.getenv("LLM_THINKING_THRESHOLD_SUMMARY", "disabled").lower()

        # Wiki 同步分析 client
        sync_key = os.getenv("LLM_SYNC_API_KEY")
        sync_url = os.getenv("LLM_SYNC_BASE_URL")
        if sync_key and sync_url:
            self.sync_client = self._create_client(sync_key, sync_url)
            self.default_sync_model = os.getenv("LLM_MODEL_SYNC", "mimo-v2.5")
        else:
            # fallback 到 summary client
            self.sync_client = self.summary_client
            self.default_sync_model = self.default_summary_model

    # ==================== 代理方法：委托到独立函数 ====================

    def extract_damage_calc_params(
        self, message: str, search_results_text: str, context: list = None, model: str = None,
        call_log: list = None
    ) -> Dict[str, Any]:
        """LLM Call #2：基于检索结果提取伤害计算参数"""
        return _extract_damage(
            client=self.calc_client, model=model or self.default_calc_model,
            max_tokens=self._max_tokens_calc,
            message=message, search_results_text=search_results_text,
            context=context, thinking=self._thinking_calc, call_log=call_log,
        )

    def extract_threshold_params(
        self, message: str, search_results_text: str, context: list = None, model: str = None,
        call_log: list = None
    ) -> Dict[str, Any]:
        """LLM Call #2t：基于检索结果提取阈值搜索参数"""
        return _extract_threshold(
            client=self.calc_client, model=model or self.default_calc_model,
            max_tokens=self._max_tokens_calc,
            message=message, search_results_text=search_results_text,
            context=context, thinking=self._thinking_calc, call_log=call_log,
        )

    def summarize_query_result(
        self, message: str, query_results_text: str, context: list = None, model: str = None,
        call_log: list = None, thinking_callback=None
    ) -> str:
        """查询结果总结"""
        return _summarize_query(
            client=self.summary_client, model=model or self.default_summary_model,
            max_tokens=self._max_tokens_summary,
            message=message, query_results_text=query_results_text,
            context=context, thinking=self._thinking_query_summary,
            call_log=call_log, thinking_callback=thinking_callback,
        )

    def summarize_damage_result(
        self, user_message: str, calc_summary_text: str, context: list = None, model: str = None,
        call_log: list = None, thinking_callback=None
    ) -> str:
        """LLM Call #3：伤害计算结果总结"""
        return _summarize_damage(
            client=self.summary_client, model=model or self.default_summary_model,
            max_tokens=self._max_tokens_summary,
            user_message=user_message, calc_summary_text=calc_summary_text,
            context=context, thinking=self._thinking_damage_summary,
            call_log=call_log, thinking_callback=thinking_callback,
        )

    def summarize_threshold_result(
        self, user_message: str, calc_summary_text: str, context: list = None, model: str = None,
        call_log: list = None, thinking_callback=None
    ) -> str:
        """LLM Call #3t：阈值搜索结果总结"""
        return _summarize_threshold(
            client=self.summary_client, model=model or self.default_summary_model,
            max_tokens=self._max_tokens_summary,
            user_message=user_message, calc_summary_text=calc_summary_text,
            context=context, thinking=self._thinking_threshold_summary,
            call_log=call_log, thinking_callback=thinking_callback,
        )

    # ==================== Agent Loop 核心 ====================

    @staticmethod
    def _serialize_agent_messages(messages: list) -> list:
        """将 agent loop 消息（混杂 dict 和 SDK 对象）序列化为纯 dict，用于 call_log"""
        result = []
        for m in messages:
            if isinstance(m, dict):
                entry = {"role": m.get("role", "?"), "content": m.get("content", "")}
                if "tool_calls" in m and m["tool_calls"]:
                    entry["tool_calls"] = [{"name": tc.get("function", {}).get("name", "?"), "args": tc.get("function", {}).get("arguments", "")} for tc in m["tool_calls"]]
                if "tool_call_id" in m:
                    entry["tool_call_id"] = m["tool_call_id"]
            elif hasattr(m, "role"):
                entry = {"role": m.role, "content": m.content or ""}
                if hasattr(m, "tool_calls") and m.tool_calls:
                    entry["tool_calls"] = [{"name": tc.function.name, "args": tc.function.arguments} for tc in m.tool_calls]
                if hasattr(m, "tool_call_id"):
                    entry["tool_call_id"] = m.tool_call_id
            else:
                continue
            result.append(entry)
        return result

    # 工具名 → 中文标签，用于进度展示
    _TOOL_LABEL_ZH = {
        "search_pokemon": "查宝可梦",
        "search_moves": "查招式",
        "search_abilities": "查特性",
        "search_items": "查道具",
        "search_stat": "查能力值",
        "search_status": "查状态",
        "search_type": "查属性",
        "search_nature": "查性格",
        "search_moves_by_keyword": "搜招式",
        "filter_moves": "筛选招式",
        "get_pokemon_moves": "查可学招式",
        "get_move_learners": "查学习者",
        "get_pokemon_moves_intersection": "查共学招式",
        "get_type_effectiveness": "查属性克制",
        "get_dual_type_effectiveness": "查双属性克制",
        "execute_sql": "执行 SQL",
        "semantic_search": "语义检索",
        "fetch_wiki_page": "读 Wiki 页面",
        "search_wiki": "搜 Wiki",
        "damage_calculator": "伤害计算",
        "ev_threshold_calculator": "阈值搜索",
        "stat_calculator": "能力值计算",
        "create_plan": "任务规划",
    }

    @classmethod
    def _tool_display(cls, tool_calls) -> str:
        """把 tool_calls 列表渲染成中文标签字符串"""
        names = []
        for tc in tool_calls:
            n = tc.function.name
            names.append(cls._TOOL_LABEL_ZH.get(n, n))
        return "、".join(names)

    @classmethod
    def _tool_detail(cls, tool_calls) -> str:
        """提取 tool_calls 的关键参数，生成可读的详情字符串，如 '甲贺忍蛙 / 恶之波动'"""
        parts = []
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            detail = ""
            if name in ("search_pokemon", "search_moves", "search_abilities",
                        "search_items", "search_stat", "search_status",
                        "search_type", "search_nature"):
                detail = args.get("name", "")
            elif name == "search_moves_by_keyword":
                detail = args.get("keyword", "")
            elif name == "filter_moves":
                filters = []
                if args.get("type"):
                    filters.append(f"属性={args['type']}")
                if args.get("category"):
                    filters.append(f"分类={args['category']}")
                if args.get("min_power"):
                    filters.append(f"威力≥{args['min_power']}")
                detail = "、".join(filters)
            elif name == "execute_sql":
                sql = " ".join(args.get("sql", "").split())
                detail = sql[:60] + ("..." if len(sql) > 60 else "")
            elif name == "semantic_search":
                detail = args.get("query", "")
            elif name == "fetch_wiki_page":
                detail = args.get("title", "")
            elif name == "search_wiki":
                kw = args.get("keywords", [])
                detail = "、".join(kw) if isinstance(kw, list) else str(kw)
            elif name == "get_type_effectiveness":
                atk = args.get("attacker_type", "")
                dfn = args.get("defender_type", "")
                detail = f"{atk}→{dfn}" if atk and dfn else dfn or atk
            elif name == "get_dual_type_effectiveness":
                detail = f"{args.get('type1', '')}+{args.get('type2', '')}"
            elif name == "get_pokemon_moves":
                detail = str(list(args.values())[0]) if args else ""
            elif name == "get_move_learners":
                detail = str(list(args.values())[0]) if args else ""
            elif name == "get_pokemon_moves_intersection":
                moves = args.get("moves", [])
                detail = "、".join(str(m) for m in moves) if moves else ""
            elif name == "stat_calculator":
                pname = args.get("pokemon_name", "")
                stat = args.get("stat", "")
                boosts = args.get("boosts", 0)
                detail = pname
                if stat:
                    STAT_ZH = {"hp": "HP", "atk": "攻击", "def": "防御", "spa": "特攻", "spd": "特防", "spe": "速度"}
                    detail += f" {STAT_ZH.get(stat, stat)}"
                if boosts:
                    detail += f" {'+' if boosts > 0 else ''}{boosts}"
            elif name == "create_plan":
                detail = args.get("goal", "")
                tasks = args.get("tasks", [])
                if tasks:
                    detail += f"（{len(tasks)}步）"
            if detail:
                parts.append(f"{cls._TOOL_LABEL_ZH.get(name, name)}「{detail}」")
            else:
                parts.append(cls._TOOL_LABEL_ZH.get(name, name))
        return "、".join(parts)

    def agent_loop(
        self, message: str, search_context: str, context: list = None, model: str = None,
        call_log: list = None, tool_executor: callable = None, progress_callback=None,
        thinking_callback=None
    ) -> Dict[str, Any]:
        """
        Agent 循环：LLM 多轮调用工具，直到输出 final_answer 或达到上限

        参数：
          tool_executor(tool_name, args) -> str  工具执行回调，由 chat_service 提供
          progress_callback(step, label, detail, status)  进度回调（可选）
        返回：
          {
            "final_answer": str | None,
            "tool_history": [{"round": 1, "name": "...", "args": {...}, "result": "..."}, ...],
            "terminal_tool": "damage_calculator" | "ev_threshold_calculator" | None,
            "terminal_args": dict | None,
            "rounds": int,
            "stop_reason": "final_answer" | "max_rounds" | "terminal_tool",
            "needs_user_pokemon": bool,
          }
        """
        MAX_ROUNDS = 10
        TERMINAL_TOOLS = {"request_damage_calc", "ev_threshold_calculator"}

        # 加载查询工具并转换为 OpenAI 格式
        query_tools_raw = load_tools("llm2b_query_tools.json")
        tools_openai = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in query_tools_raw
        ]

        # 加载终结性工具
        for terminal_file in ("llm2_request_damage_calc.json", "llm2_threshold_tool.json"):
            for t in load_tools(terminal_file):
                tools_openai.append({
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
                })

        # 加载 create_plan 工具（任务规划器）
        for t in load_tools("create_plan_tool.json"):
            tools_openai.append({
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
            })

        # 拆分静态规则（可缓存前缀）和动态搜索上下文
        _prompt_raw = load_prompt("llm1_unified.txt")
        _split_idx = _prompt_raw.index("{search_context}")
        _rules_prefix = _prompt_raw[:_split_idx]
        messages = [
            {"role": "system", "content": _rules_prefix, "cache_control": {"type": "ephemeral"}},
            {"role": "system", "content": search_context},
        ]
        messages += build_messages_with_context(message, context)

        tool_history = []
        needs_user_pokemon = False
        rejection_retried = False  # 内容安全拒绝重试标记

        for round_idx in range(1, MAX_ROUNDS + 1):
            # 首轮强制调工具，后续轮次允许自由选择
            tool_choice = "required" if round_idx == 1 else "auto"

            # 进度：本轮 LLM 思考开始
            progress_step = 10 + round_idx  # 10-14，排在"思考中"(1)之后、下游总结(90+)之前
            if progress_callback:
                progress_callback(progress_step, f"第{round_idx}轮思考", "", "active")

            try:
                if self._escalation_model and round_idx >= self._escalation_after:
                    use_model = model or self._escalation_model
                    use_client = self.escalation_client
                    use_max_tokens = self._max_tokens_escalation
                    use_thinking = self._thinking_escalation
                else:
                    use_model = model or self.default_tool_model
                    use_client = self.client
                    use_max_tokens = self._max_tokens_tool
                    use_thinking = self._thinking_tool
                response = use_client.chat.completions.create(
                    model=use_model,
                    max_tokens=use_max_tokens,
                    temperature=0,
                    messages=messages,
                    tools=tools_openai,
                    tool_choice=tool_choice,
                    **extra_params(use_model, thinking=use_thinking),
                )
            except Exception as e:
                print(f"Agent loop round {round_idx} 失败: {e}")
                # 如果首轮强制工具调用失败，尝试不强制
                if round_idx == 1 and "tool_choice" in str(e):
                    response = use_client.chat.completions.create(
                        model=use_model,
                        max_tokens=use_max_tokens,
                        temperature=0,
                        messages=messages,
                        tools=tools_openai,
                        **extra_params(use_model, thinking=use_thinking),
                    )
                else:
                    raise

            msg = response.choices[0].message
            messages.append(msg)

            # 情况 A：LLM 没调工具 → 视为 final_answer 收尾
            if not msg.tool_calls:
                # 检测内容安全拒绝
                if is_rejection(msg.content):
                    if not rejection_retried:
                        # 首次拒绝：重试一次
                        rejection_retried = True
                        print(f"Agent loop round {round_idx} 检测到内容安全拒绝，重试...")
                        if progress_callback:
                            progress_callback(progress_step, f"第{round_idx}轮：重试中", "", "active")
                        messages.pop()
                        messages.append({"role": "user", "content": REJECTION_RETRY_NOTE})
                        continue
                    else:
                        # 重试仍被拒绝：返回友好提示
                        print(f"Agent loop round {round_idx} 重试仍被拒绝，返回友好提示")
                        friendly = "抱歉，该问题触发了内容安全过滤，无法回答。请尝试换个方式提问，或避免使用可能被误解的措辞。"
                        if call_log is not None:
                            call_log.append({
                                "call": f"agent_r{round_idx}",
                                "purpose": f"Agent Loop 第{round_idx}轮（拒绝兜底）",
                                "messages": self._serialize_agent_messages(messages),
                                "reply": friendly,
                            })
                        return {
                            "final_answer": friendly,
                            "tool_history": tool_history,
                            "terminal_tool": None,
                            "terminal_args": None,
                            "rounds": round_idx,
                            "stop_reason": "final_answer",
                            "needs_user_pokemon": needs_user_pokemon,
                        }

                if progress_callback:
                    progress_callback(progress_step, f"第{round_idx}轮：直接回答", "", "done")
                if call_log is not None:
                    call_log.append({
                        "call": f"agent_r{round_idx}",
                        "purpose": f"Agent Loop 第{round_idx}轮",
                        "messages": self._serialize_agent_messages(messages),
                        "reply": msg.content or "",
                    })
                return {
                    "final_answer": msg.content,
                    "tool_history": tool_history,
                    "terminal_tool": None,
                    "terminal_args": None,
                    "rounds": round_idx,
                    "stop_reason": "final_answer",
                    "needs_user_pokemon": needs_user_pokemon,
                }

            # 情况 B：LLM 调了工具
            # 进度：本轮 LLM 选择了哪些工具（替换 "思考中" 为具体工具名）
            if progress_callback:
                progress_callback(progress_step, f"第{round_idx}轮：{self._tool_detail(msg.tool_calls)}", "", "active")
            for call in msg.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # 检测 needs_user_pokemon（LLM 可能在任意轮次识别到）
                if args.get("needs_user_pokemon"):
                    needs_user_pokemon = True

                # 任务规划器：create_plan 内联执行
                if name == "create_plan":
                    print(f"[TaskPlanner] LLM 调用了 create_plan，goal={args.get('goal', '')}，tasks={len(args.get('tasks', []))}个")
                    if progress_callback:
                        progress_callback(progress_step, f"第{round_idx}轮：执行任务规划", "", "active")
                    planner = TaskPlanner(
                        tool_executor=tool_executor,
                        llm_client=use_client,
                        llm_model=use_model,
                    )
                    plan_result = planner.execute_plan(args, progress_callback=progress_callback)
                    # 格式化为工具响应，让 LLM 基于结果生成 final_answer
                    plan_summary = plan_result["summary"]
                    tool_history.append({"round": round_idx, "name": "create_plan", "args": args, "result": plan_summary})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": plan_summary,
                    })
                    if progress_callback:
                        progress_callback(progress_step, f"第{round_idx}轮：任务规划完成（{plan_result['success_count']}成功/{plan_result['fail_count']}失败）", "", "done")
                    continue  # 不 return，让 LLM 继续生成 final_answer

                # 终结性工具：damage_calculator / ev_threshold_calculator
                if name in TERMINAL_TOOLS:
                    if progress_callback:
                        label_zh = self._TOOL_LABEL_ZH.get(name, name)
                        progress_callback(progress_step, f"第{round_idx}轮：{label_zh}", "", "done")
                    if call_log is not None:
                        call_log.append({
                            "call": f"agent_r{round_idx}",
                            "purpose": f"Agent Loop 第{round_idx}轮",
                            "messages": self._serialize_agent_messages(messages),
                            "reply": str([tc.function.name for tc in msg.tool_calls]),
                            "tool_calls": [{"name": tc.function.name, "args": tc.function.arguments} for tc in msg.tool_calls],
                        })
                    return {
                        "final_answer": None,
                        "tool_history": tool_history,
                        "terminal_tool": name,
                        "terminal_args": args,
                        "rounds": round_idx,
                        "stop_reason": "terminal_tool",
                        "needs_user_pokemon": needs_user_pokemon,
                    }

                # 普通查询工具：执行并回填
                if tool_executor:
                    result = tool_executor(name, args)
                else:
                    result = f"工具 {name} 执行失败：未提供 tool_executor"
                tool_history.append({"round": round_idx, "name": name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })

            # 工具执行完毕，记录日志（此时 messages 已包含本轮 tool results）
            if progress_callback:
                progress_callback(progress_step, f"第{round_idx}轮：{self._tool_detail(msg.tool_calls)}", "", "done")
            if call_log is not None:
                call_log.append({
                    "call": f"agent_r{round_idx}",
                    "purpose": f"Agent Loop 第{round_idx}轮",
                    "messages": self._serialize_agent_messages(messages),
                    "reply": str([tc.function.name for tc in msg.tool_calls]),
                    "tool_calls": [{"name": tc.function.name, "args": tc.function.arguments} for tc in msg.tool_calls],
                })

        # 情况 C：5 轮上限，兜底退出
        return {
            "final_answer": None,
            "tool_history": tool_history,
            "terminal_tool": None,
            "terminal_args": None,
            "rounds": MAX_ROUNDS,
            "stop_reason": "max_rounds",
            "needs_user_pokemon": needs_user_pokemon,
        }
