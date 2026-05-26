"""
智能聊天服务 - 基于 LLM 的意图识别和参数提取

使用 Mixin 模式拆分为多个模块：
- TextProcessorMixin: 文本处理、jieba 切词、拼音匹配、形态名 normalize、中英互译
- DamagePipelineMixin: 伤害计算管线（参数提取 → 计算执行 → 结果格式化）
- ThresholdPipelineMixin: 阈值计算管线（攻击阈值 + 防御阈值搜索）
- CalcFormatterMixin: URL 构建 + 伤害结果格式化 + 润色文本
- QueryPipelineMixin: 查询处理 + 工具结果格式化
- ToolExecutorMixin: 工具分发 + 能力值计算
- WikiToolsMixin: Wiki 页面查找/读取/搜索
- HomeQueryMixin: HOME 对战使用率查询
"""
import os
import sqlite3
import time
from typing import Dict, Any, Optional

from .llm_service import LLMService
from .chat.text_processor import TextProcessorMixin
from .chat.damage_pipeline import DamagePipelineMixin
from .chat.threshold_pipeline import ThresholdPipelineMixin
from .chat.calc_formatter import CalcFormatterMixin
from .chat.query_pipeline import QueryPipelineMixin
from .chat.tool_executor import ToolExecutorMixin
from .chat.wiki_tools import WikiToolsMixin
from .chat.home_queries import HomeQueryMixin

# 数据库路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_BASE_DIR, "pokemon_data", "pokemonData.db")


class ChatService(
    TextProcessorMixin,
    DamagePipelineMixin,
    ThresholdPipelineMixin,
    CalcFormatterMixin,
    ToolExecutorMixin,
    WikiToolsMixin,
    HomeQueryMixin,
    QueryPipelineMixin,
):
    """智能聊天服务"""

    def __init__(self, query_service, damage_calc, llm_service: Optional[LLMService] = None, rag_service=None, user_pokemon_service=None):
        self.query_service = query_service
        self.damage_calc = damage_calc
        self.llm_service = llm_service
        self.rag_service = rag_service
        self.user_pokemon_service = user_pokemon_service

        # 从数据库加载查表缓存
        self._en2zh_cache: Dict[str, Dict[str, str]] = {}
        self._nature_modifiers: Dict[str, Dict[str, str]] = {}
        # 拼音 → 中文名映射（无空格拼音 → name_zh）
        self._pinyin_to_zh: Dict[str, str] = {}
        self._load_db_mappings()

        # 初始化 jieba 自定义词典
        self._init_jieba()

    def _load_db_mappings(self):
        """从数据库加载英文→中文映射缓存和性格增减数据"""
        try:
            conn = sqlite3.connect(DB_PATH)

            # 宝可梦：英文名 → 中文名 + 拼音映射 + NCP 名称缓存 + 世代可用性
            pokemon_map = {}
            self._ncp_cache = {}
            self._gen_availability = {}  # name_en → (first_gen, in_sv, in_champions)
            for row in conn.execute(
                "SELECT name_en, name_zh, name_pinyin, name_ncp, first_gen, in_sv, in_champions "
                "FROM pokemons WHERE name_en IS NOT NULL"
            ):
                name_en, name_zh, name_pinyin, name_ncp, first_gen, in_sv, in_champions = row
                pokemon_map[name_en] = name_zh
                if name_zh and name_pinyin:
                    self._pinyin_to_zh[name_pinyin.replace(" ", "")] = name_zh
                if name_ncp:
                    self._ncp_cache[name_en] = name_ncp
                    if name_zh:
                        pokemon_map[name_ncp] = name_zh
                avail = (first_gen, in_sv or 0, in_champions or 0)
                self._gen_availability[name_en] = avail
                if name_ncp and name_ncp != name_en:
                    self._gen_availability[name_ncp] = avail
            self._en2zh_cache["pokemon"] = pokemon_map

            # 招式：英文名 → 中文名（英文名是 kebab-case，如 ice-beam）
            move_map = {}
            for row in conn.execute("SELECT name_en, name_zh, name_pinyin FROM moves WHERE name_en IS NOT NULL"):
                # 存两份：原始 kebab-case 和转为 Title Case 带空格的
                move_map[row[0]] = row[1]
                title = row[0].replace("-", " ").title()
                move_map[title] = row[1]
                if row[1] and row[2]:
                    self._pinyin_to_zh[row[2].replace(" ", "")] = row[1]
            self._en2zh_cache["move"] = move_map

            # 特性：英文名 → 中文名
            ability_map = {}
            for row in conn.execute("SELECT name_en, name_zh, name_pinyin FROM abilities WHERE name_en IS NOT NULL"):
                ability_map[row[0]] = row[1]
                title = row[0].replace("-", " ").title()
                ability_map[title] = row[1]
                if row[1] and row[2]:
                    self._pinyin_to_zh[row[2].replace(" ", "")] = row[1]
            self._en2zh_cache["ability"] = ability_map

            # 道具：英文名 → 中文名
            item_map = {}
            self._item_gen_availability = {}  # name_en(Title Case) → (first_gen, in_sv, in_champions)
            for row in conn.execute("SELECT name_en, name_zh, name_pinyin, name_ncp, first_gen, in_sv, in_champions FROM items WHERE name_en IS NOT NULL"):
                name_en, name_zh, name_pinyin, name_ncp, first_gen, in_sv, in_champions = row
                item_map[name_en] = name_zh
                title = name_en.replace("-", " ").title()
                item_map[title] = name_zh
                if name_zh and name_pinyin:
                    self._pinyin_to_zh[name_pinyin.replace(" ", "")] = name_zh
                # 加载道具世代可用性（仅 NCP 列表中的道具有值）
                if first_gen is not None:
                    key = name_ncp or title
                    self._item_gen_availability[key] = (first_gen, in_sv or 0, in_champions or 0)
            self._en2zh_cache["item"] = item_map

            # 性格：从 natures 表加载增减能力 + 英文→中文映射
            self._nature_en2zh: Dict[str, str] = {}
            self._nature_en_modifiers: Dict[str, Dict[str, str]] = {}  # 英文名 → {plus, minus}（英文属性）
            for row in conn.execute(
                "SELECT name_zh, name_en, increased_stat_zh, decreased_stat_zh, increased_stat_en, decreased_stat_en FROM natures"
            ):
                name_zh, name_en, plus_zh, minus_zh, plus_en, minus_en = row
                if plus_zh or minus_zh:
                    self._nature_modifiers[name_zh] = {"plus": plus_zh or "", "minus": minus_zh or ""}
                if name_en and name_zh:
                    self._nature_en2zh[name_en] = name_zh
                    self._nature_en2zh[name_en.title()] = name_zh
                if name_en and (plus_en or minus_en):
                    self._nature_en_modifiers[name_en] = {"plus": plus_en or "", "minus": minus_en or ""}
                    self._nature_en_modifiers[name_en.title()] = {"plus": plus_en or "", "minus": minus_en or ""}

            # 唯一特性：宝可梦英文名 → 特性英文名（只有 ability1，无 ability2 和 hidden_ability）
            self._sole_ability_map: Dict[str, str] = {}
            for row in conn.execute(
                "SELECT name_en, name_ncp, ability1_name FROM pokemons "
                "WHERE ability1_name IS NOT NULL AND ability1_name != '' "
                "AND (ability2_name IS NULL OR ability2_name = '') "
                "AND (hidden_ability_name IS NULL OR hidden_ability_name = '')"
            ):
                en_name, ncp_name, ability_en = row
                ability_title = ability_en.replace("-", " ").title()
                if en_name:
                    self._sole_ability_map[en_name] = ability_title
                if ncp_name:
                    self._sole_ability_map[ncp_name.lower().replace(" ", "-")] = ability_title

            # 属性：英文名(小写) → 中文名
            self._type_en2zh: Dict[str, str] = {}
            for row in conn.execute("SELECT name_en, name_zh FROM types WHERE name_en IS NOT NULL"):
                if row[0] and row[1]:
                    self._type_en2zh[row[0].lower()] = row[1]

            conn.close()

        except Exception as e:
            print(f"加载数据库映射失败: {e}")

    def process_message(self, message: str, context: Optional[list] = None, model: str = None, tool_model: str = None, debug: bool = False, platform: str = None, user_id: int = None, progress_callback=None, thinking_callback=None) -> Dict[str, Any]:
        """
        处理用户消息（Agent Loop 管线）

        流程：整句混合检索 → Agent Loop（多轮工具调用）→ 路由
        - final_answer + 有工具历史 → LLM#3 总结
        - final_answer + 无工具历史 → 直接返回（纯闲聊/常识）
        - terminal_tool → 独立预处理管线（damage/threshold）
        - max_rounds → LLM#3 兜底总结
        """
        # 记录客户端平台，用于决定伤害计算器链接页面
        self._platform = platform

        # 构建上下文
        context_messages = []
        if context:
            for msg in context:
                if isinstance(msg, dict):
                    context_messages.append(msg)
                else:
                    context_messages.append({"role": msg.role, "content": msg.content})

        # ── 无 LLM 降级模式 ──
        if not self.llm_service:
            intent, params = self._parse_intent_fallback(message)
            if intent == "damage_calc":
                return self._handle_damage_calc(params)
            elif intent == "query":
                return self._handle_query(params)
            else:
                return self._handle_chat(params)

        # ── Agent Loop 管线 ──
        call_log = [] if debug else None
        timings = {} if debug else None
        try:
            # 尽早推送"思考中"，避免 UI 卡在 typing dots
            if progress_callback:
                progress_callback(1, "思考中", "", "active")

            # Step 1: RAG 检索（整句 + jieba 逐词）
            t_rag = time.time()
            search_results = []
            if self.rag_service:
                sentence_results = self.rag_service.hybrid_search(message)
                jieba_words = self._tokenize(message)
                word_results = self.rag_service.search_words(jieba_words) if jieba_words else []
                seen_ids = set()
                for doc in sentence_results + word_results:
                    if doc["id"] not in seen_ids:
                        seen_ids.add(doc["id"])
                        search_results.append(doc)
            search_context = "\n\n---\n\n".join(
                [doc["text"] for doc in search_results]
            ) if search_results else ""
            if timings is not None:
                timings["rag_s1"] = round(time.time() - t_rag, 2)

            # "思考中" → "检索完成"，为 agent loop 每轮展示腾位置
            if progress_callback:
                progress_callback(1, "检索完成", "", "done")

            # Step 2: Agent Loop（替代 LLM#1 意图识别 + LLM#2b 工具调用）
            t_loop = time.time()
            loop_result = self.llm_service.agent_loop(
                message, search_context,
                context=context_messages,
                model=model,
                call_log=call_log,
                tool_executor=self._execute_single_tool,
                progress_callback=progress_callback,
                thinking_callback=thinking_callback,
            )
            if timings is not None:
                timings["agent_loop"] = round(time.time() - t_loop, 2)

            stop_reason = loop_result["stop_reason"]
            tool_history = loop_result["tool_history"]

            # Step 2.5: 用户宝可梦上下文
            user_context = None
            user_pokemon_list = None
            if loop_result.get("needs_user_pokemon") and user_id and self.user_pokemon_service:
                try:
                    user_context = self.user_pokemon_service.format_user_context(user_id)
                    user_pokemon_list = self.user_pokemon_service.get_user_pokemon(user_id)
                except Exception as e:
                    print(f"查询用户宝可梦失败: {e}")

            # Step 3: 根据 stop_reason 路由
            if stop_reason == "terminal_tool":
                # 终结性工具：走独立预处理管线
                terminal_tool = loop_result["terminal_tool"]
                terminal_args = loop_result["terminal_args"]

                if terminal_tool == "request_damage_calc":
                    result = self._handle_damage_calc_pipeline(
                        message, context_messages,
                        model=model, tool_model=tool_model,
                        call_log=call_log, timings=timings,
                        user_context=user_context, user_pokemon_list=user_pokemon_list,
                        progress_callback=progress_callback,
                        thinking_callback=thinking_callback,
                    )
                else:  # ev_threshold_calculator
                    result = self._handle_threshold_pipeline(
                        message, context_messages,
                        model=model, tool_model=tool_model,
                        call_log=call_log, timings=timings,
                        user_context=user_context, user_pokemon_list=user_pokemon_list,
                        progress_callback=progress_callback,
                        thinking_callback=thinking_callback,
                        pre_tool_history=tool_history, terminal_args=terminal_args,
                    )

            elif stop_reason == "final_answer":
                # LLM 直接给出答案
                if tool_history:
                    # 查过数据 → LLM#3 总结做格式化
                    if progress_callback:
                        progress_callback(90, "整理回答", "", "active")
                    context_text = self._format_tool_history(tool_history)
                    try:
                        t_summary = time.time()
                        answer = self.llm_service.summarize_query_result(
                            message, context_text, context_messages, model=model, call_log=call_log,
                            thinking_callback=thinking_callback,
                        )
                        if timings is not None:
                            timings["llm_summary"] = round(time.time() - t_summary, 2)
                        if progress_callback:
                            progress_callback(90, "整理完成", "", "done")
                        result = {"success": True, "type": "skills", "response": answer}
                    except Exception as e:
                        print(f"LLM#3 总结失败: {e}")
                        result = {"success": True, "type": "skills", "response": loop_result["final_answer"]}
                else:
                    # 纯闲聊/常识，直接用 final_answer
                    result = {"success": True, "type": "skills", "response": loop_result["final_answer"]}

            else:  # max_rounds
                # 兜底：5 轮没收尾
                if progress_callback:
                    progress_callback(90, "整理回答", "", "active")
                context_text = self._format_tool_history(tool_history) or search_context
                if user_context:
                    context_text = user_context + "\n\n---\n\n" + context_text
                try:
                    answer = self.llm_service.summarize_query_result(
                        message, context_text, context_messages, model=model, call_log=call_log,
                        thinking_callback=thinking_callback,
                    )
                    if progress_callback:
                        progress_callback(90, "整理完成", "", "done")
                    result = {"success": True, "type": "skills", "response": answer, "truncated": True}
                except Exception as e:
                    print(f"兜底总结失败: {e}")
                    result = {"success": True, "type": "skills", "response": "抱歉，处理过程中出现问题，请换个方式提问。"}

            # debug 模式
            if debug and call_log:
                result["llm_calls"] = call_log
            if debug and timings:
                result["timings"] = timings
            if debug:
                result["agent_loop"] = {
                    "stop_reason": stop_reason,
                    "rounds": loop_result["rounds"],
                    "tool_count": len(tool_history),
                }
            return result

        except Exception as e:
            print(f"Agent Loop 管线失败，降级到旧流程: {e}")
            import traceback
            traceback.print_exc()
            intent, params = self._parse_intent_fallback(message)
            if intent == "damage_calc":
                return self._handle_damage_calc(params)
            elif intent == "query":
                return self._handle_query(params, model=model)
            else:
                return self._handle_chat(params)
