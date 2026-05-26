"""
查询管线 Mixin：查询处理 + 工具结果格式化

工具执行已拆分到同目录：
- tool_executor.py: ToolExecutorMixin - 工具分发 + 能力值计算
- wiki_tools.py: WikiToolsMixin - Wiki 页面查找/读取/搜索
- home_queries.py: HomeQueryMixin - HOME 使用率查询
"""
from typing import Dict, Any, List


class QueryPipelineMixin:
    """查询处理 + 工具结果格式化"""

    def _handle_query(self, params: Dict[str, Any], model: str = None) -> Dict[str, Any]:
        """处理查询（降级模式：无 Agent Loop 时使用）"""
        query = params["query"]

        try:
            # 降级：纯 RAG 回答
            if self.rag_service:
                try:
                    search_results = self.rag_service.hybrid_search(query)
                    return self._rag_fallback(query, search_results)
                except Exception:
                    pass

            # 再降级：旧的 intelligent_query
            result = self.query_service.intelligent_query(query)

            if result.get("success"):
                data = result.get("data", [])
                if data:
                    response = self._format_query_result(result["query_type"], data)
                else:
                    response = result.get("message", "未找到相关数据")

                return {
                    "success": True,
                    "type": "query",
                    "response": response,
                    "data": data
                }
            else:
                return {
                    "success": False,
                    "type": "query",
                    "response": result.get("message", "查询失败"),
                    "data": None
                }

        except Exception as e:
            return {
                "success": False,
                "type": "query",
                "response": f"查询出错: {str(e)}",
                "data": None
            }

    def _rag_fallback(self, query: str, search_results: list) -> Dict[str, Any]:
        """RAG fallback：用 llm_service 基于检索结果生成回复（不依赖 rag_service 的 LLM client）"""
        if search_results:
            context_text = "\n\n---\n\n".join([doc["text"] for doc in search_results])
        else:
            context_text = "无相关资料"
        if self.llm_service:
            try:
                response_text = self.llm_service.summarize_query_result(query, context_text)
                return {
                    "success": True,
                    "type": "query",
                    "response": response_text,
                    "data": None,
                }
            except Exception:
                pass
        return {
            "success": True,
            "type": "query",
            "response": f"以下是检索到的相关信息：\n\n{context_text}",
            "data": None,
        }

    def _handle_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理普通聊天（通过 RAG 检索 + LLM 生成对话回复）"""
        message = params.get("message", "")

        if self.rag_service and message.strip():
            try:
                # 先做 RAG 检索
                search_results = self.rag_service.hybrid_search(message)
                if search_results:
                    context_text = "\n\n---\n\n".join([doc["text"] for doc in search_results])
                    # 用 LLM 生成对话回复
                    if self.llm_service:
                        response_text = self.llm_service.summarize_query_result(message, context_text)
                    else:
                        response_text = f"以下是检索到的相关信息：\n\n{context_text}"
                    return {
                        "success": True,
                        "type": "chat",
                        "response": response_text,
                        "data": {
                            "sources": [d.get("id") for d in search_results],
                            "source_count": len(search_results),
                        },
                    }
            except Exception:
                pass

        # RAG 没有结果或出错，用 LLM 直接回答
        if self.llm_service:
            try:
                response_text = self.llm_service.summarize_query_result(message, "无相关资料")
                return {
                    "success": True,
                    "type": "chat",
                    "response": response_text,
                    "data": None,
                }
            except Exception:
                pass

        return {
            "success": True,
            "type": "chat",
            "response": "你好！我是宝可梦助手，可以帮你查询宝可梦数据和计算对战伤害。\n\n"
                       "你可以问我：\n"
                       "- 查询宝可梦信息：'查询喷火龙的种族值'\n"
                       "- 计算伤害：'Mega喷火龙Y对Mega妙蛙花使用热风'\n"
                       "- 属性克制：'火属性克制什么'",
            "data": None
        }

    # ==================== 格式化方法 ====================

    def _format_query_result(self, query_type: str, data: list) -> str:
        """格式化查询结果为文本"""
        if not data:
            return "未找到相关数据"

        if query_type == "pokemon":
            result = []
            for pokemon in data[:5]:
                text = f"【{pokemon.get('name_zh')}】\n"
                text += f"属性: {pokemon.get('type1')}"
                if pokemon.get('type2'):
                    text += f"/{pokemon.get('type2')}"
                text += f"\n种族值: HP{pokemon.get('hp')} 攻{pokemon.get('attack')} "
                text += f"防{pokemon.get('defense')} 特攻{pokemon.get('sp_attack')} "
                text += f"特防{pokemon.get('sp_defense')} 速{pokemon.get('speed')}"
                result.append(text)
            return "\n\n".join(result)

        elif query_type == "move":
            result = []
            for move in data[:5]:
                text = f"【{move.get('name_zh')}】\n"
                text += f"属性: {move.get('type')} | 分类: {move.get('damage_class')}\n"
                text += f"威力: {move.get('power')} | 命中: {move.get('accuracy')}"
                result.append(text)
            return "\n\n".join(result)

        else:
            return f"找到 {len(data)} 条结果"

    def _format_tool_history(self, history: List[Dict[str, Any]]) -> str:
        """将 agent loop 内所有工具调用结果格式化成可喂给 LLM#3 的文本"""
        if not history:
            return ""
        parts = []
        for entry in history:
            name = entry.get("name", "")
            args = entry.get("args", {})
            result = entry.get("result", "")
            arg_str = ", ".join(f"{k}={v}" for k, v in args.items() if v and k != "needs_user_pokemon")
            parts.append(f"【工具 {name} 查询: {arg_str}】\n{result}")
        return "\n\n---\n\n".join(parts)

    def _format_tool_rows(self, category: str, rows: List[Dict]) -> str:
        """复用 RAGService._format_row 格式化查询结果"""
        if not rows:
            return ""
        from ..rag_service import RAGService
        limit = len(rows) if len(rows) <= 50 else 50
        return "\n\n".join([RAGService._format_row(category, row) for row in rows[:limit]])

    def _format_pokemon_moves(self, rows: List[Dict]) -> str:
        """格式化宝可梦可学招式列表"""
        if not rows:
            return ""
        _pokemon_name = rows[0].get("pokemon_name_zh", rows[0].get("move_name_zh", ""))
        method_groups: Dict[str, List[str]] = {}
        for row in rows:
            method = row.get("learn_method", "other")
            move = row.get("move_name_zh", row.get("move_name_en", ""))
            level = row.get("level")
            if method == "level-up" and level:
                entry = f"Lv.{level} {move}"
            else:
                entry = move
            method_groups.setdefault(method, []).append(entry)

        method_labels = {"level-up": "升级", "machine": "招式机", "egg": "遗传", "tutor": "教授"}
        lines = [f"宝可梦可学招式"]
        for method, moves in method_groups.items():
            label = method_labels.get(method, method)
            lines.append(f"\n【{label}】{', '.join(moves)}")
        return "\n".join(lines)

    def _format_move_learners(self, rows: List[Dict]) -> str:
        """格式化能学会某招式的宝可梦列表"""
        if not rows:
            return ""
        source = rows[0].get("source", "")
        method_groups: Dict[str, List[str]] = {}
        for row in rows:
            method = row.get("learn_method", "other")
            name = row.get("name_zh", row.get("name_en", ""))
            level = row.get("level")
            if method == "level-up" and level:
                entry = f"{name}(Lv.{level})"
            else:
                entry = name
            method_groups.setdefault(method, []).append(entry)

        method_labels = {"level-up": "升级习得", "machine": "招式机习得", "egg": "遗传习得", "Champions": "Champions习得"}
        data_tag = "宝可梦冠军（Champions）" if source == "champions" else "全世代"
        lines = [f"【{data_tag}数据】能学会该招式的宝可梦（共{len(rows)}只）"]
        for method, learners in method_groups.items():
            label = method_labels.get(method, method)
            lines.append(f"\n【{label}】（{len(learners)}只）")
            lines.append(", ".join(learners))
        return "\n".join(lines)

    def _format_moves_intersection(self, rows: List[Dict]) -> str:
        """格式化同时会多个招式的宝可梦列表，分 Champions 和全世代"""
        champions = [r for r in rows if r.get("source") == "champions"]
        historical = [r for r in rows if r.get("source") == "historical"]

        def fmt(r):
            return r.get("name_zh", r.get("name_en", ""))

        lines = []
        if champions:
            lines.append(f"【宝可梦冠军（Champions）数据】同时会这些招式的宝可梦（{len(champions)}只）：{', '.join(fmt(r) for r in champions)}")
        if historical:
            label = "【全世代数据】中还有" if champions else "【全世代数据】同时会这些招式的宝可梦"
            lines.append(f"{label}（{len(historical)}只）：{', '.join(fmt(r) for r in historical)}")
        if not champions and not historical:
            lines.append("没有宝可梦同时会这些招式")
        return "\n".join(lines)

    def _format_type_effectiveness(self, attacker_type: str, rows: List[Dict]) -> str:
        """格式化属性克制关系"""
        eff_groups: Dict[str, List[str]] = {}
        for row in rows:
            eff = row.get("effectiveness", 1.0)
            if eff != 1.0:
                label = {0.0: "无效（0倍）", 0.5: "效果不好（0.5倍）", 2.0: "效果拔群（2倍）"}.get(eff, f"{eff}倍")
                eff_groups.setdefault(label, []).append(row.get("defender_type", ""))

        lines = [f"{attacker_type}属性克制关系"]
        for label, types in eff_groups.items():
            lines.append(f"  {label}：{', '.join(types)}")
        return "\n".join(lines)

    def _format_type_effectiveness_by_defender(self, defender_type: str, rows: List[Dict]) -> str:
        """格式化：什么属性克制指定防御属性"""
        eff_groups: Dict[str, List[str]] = {}
        for row in rows:
            eff = row.get("effectiveness", 1.0)
            if eff != 1.0:
                label = {0.0: "无效（0倍）", 0.5: "效果不好（0.5倍）", 2.0: "效果拔群（2倍）"}.get(eff, f"{eff}倍")
                eff_groups.setdefault(label, []).append(row.get("attacker_type", ""))

        lines = [f"对{defender_type}属性的克制关系"]
        for label, types in eff_groups.items():
            lines.append(f"  {label}：{', '.join(types)}")
        return "\n".join(lines)

    def _format_dual_type_effectiveness(self, type1: str, type2: str, rows: List[Dict]) -> str:
        """格式化双属性克制关系（倍率相乘后的结果）"""
        eff_groups: Dict[str, List[str]] = {}
        for row in rows:
            total = row.get("total_effectiveness", 1.0)
            if total != 1.0:
                label = {
                    0.0: "无效（0倍）", 0.25: "四分之一（0.25倍）",
                    0.5: "效果不好（0.5倍）", 2.0: "效果拔群（2倍）", 4.0: "四倍弱点（4倍）",
                }.get(total, f"{total}倍")
                eff_groups.setdefault(label, []).append(row.get("attacker_type", ""))

        type_label = f"{type1}+{type2}" if type2 else type1
        lines = [f"{type_label}属性的克制关系"]
        for label, types in eff_groups.items():
            lines.append(f"  {label}：{', '.join(types)}")
        return "\n".join(lines)
