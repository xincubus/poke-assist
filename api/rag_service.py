"""
RAG 服务 - 混合检索（语义 + 精确匹配）+ LLM 答案生成
"""
import os
import pickle
from typing import List, Dict, Any

import numpy as np
import faiss
from .onnx_embedder import OnnxEmbedder

from .rag_index import build_index, MODEL_NAME, DEFAULT_OUTPUT_DIR, DEFAULT_DB_PATH

# bge-small-zh 推荐的查询前缀
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

# 语义检索相似度阈值
SCORE_THRESHOLD = 0.35

# 最大上下文文档数
MAX_CONTEXT_DOCS = 15


class RAGService:
    """RAG 混合检索服务"""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        index_dir: str = DEFAULT_OUTPUT_DIR,
        alias_service=None,
        query_service=None,
        llm_service=None,
    ):
        self.db_path = db_path
        self.index_dir = index_dir
        self.alias_service = alias_service
        self.query_service = query_service
        self.llm_service = llm_service

        # 加载 embedding 模型
        print(f"RAG: 加载 embedding 模型 ({MODEL_NAME})...")
        self.model = OnnxEmbedder(MODEL_NAME)

        # 加载或构建索引
        faiss_path = os.path.join(index_dir, "rag.faiss")
        docs_path = os.path.join(index_dir, "rag_docs.pkl")

        if os.path.exists(faiss_path) and os.path.exists(docs_path):
            print("RAG: 加载已有索引...")
            self.index = faiss.read_index(faiss_path)
            with open(docs_path, "rb") as f:
                self.documents = pickle.load(f)
            print(f"RAG: 索引加载完成，{self.index.ntotal} 个向量")
        else:
            print("RAG: 索引不存在，开始构建...")
            self.rebuild_index()

    def rebuild_index(self):
        """重建 FAISS 索引"""
        index, docs = build_index(self.db_path, self.index_dir)
        self.index = index
        self.documents = docs

    def hybrid_search(self, query: str) -> List[Dict[str, Any]]:
        """整句混合检索：精确匹配 + 语义检索，合并去重返回"""
        exact_results = self._exact_search(query)
        semantic_results = self.search(query, top_k=10)
        return self._merge_results(exact_results, semantic_results)

    def search_words(self, words: List[str], top_k_per_word: int = 3) -> List[Dict[str, Any]]:
        """逐词混合检索：对每个切词分别做精确+语义检索，去重合并"""
        all_results = []
        seen_ids = set()

        for word in words:
            if len(word.strip()) < 2:
                continue

            # Phase A: 精确/模糊匹配
            for doc in self._exact_search_single(word):
                if doc["id"] not in seen_ids:
                    seen_ids.add(doc["id"])
                    doc["source_word"] = word
                    all_results.append(doc)

            # Phase B: 语义检索
            for doc in self.search(word, top_k=top_k_per_word):
                if doc["id"] not in seen_ids:
                    seen_ids.add(doc["id"])
                    doc["source_word"] = word
                    all_results.append(doc)

        return all_results[:MAX_CONTEXT_DOCS]

    def _exact_search_single(self, word: str) -> List[Dict[str, Any]]:
        """单词精确/模糊匹配：在所有实体类别中解析一个词，每类返回 top-5 候选"""
        if not self.alias_service or not self.query_service:
            return []

        results = []
        categories = [
            ("pokemon", "search_pokemon"),
            ("move", "search_moves"),
            ("ability", "search_abilities"),
            ("item", "search_items"),
        ]

        for category, method_name in categories:
            candidates = self.alias_service.resolve_top(word, category, top_k=5)
            method = getattr(self.query_service, method_name, None)
            if not method:
                continue
            for i, resolved in enumerate(candidates):
                try:
                    rows = method(resolved)
                    for row in rows[:1]:
                        # 精确匹配(i=0且来自battle_terms)分数最高，后续候选依次降低
                        score = 1.0 if i == 0 else max(0.6, 1.0 - i * 0.1)
                        results.append({
                            "id": f"exact:{category}:{resolved}",
                            "table": category,
                            "name_zh": resolved,
                            "text": self._format_row(category, row),
                            "score": score,
                        })
                except Exception:
                    pass
        return results

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """语义检索：编码查询 → FAISS 搜索 → 返回相关文档"""
        query_text = QUERY_PREFIX + query
        query_vec = self.model.encode(
            [query_text], normalize_embeddings=True
        ).astype(np.float32)

        scores, indices = self.index.search(query_vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and score > SCORE_THRESHOLD:
                doc = self.documents[idx].copy()
                doc["score"] = float(score)
                results.append(doc)
        return results

    def _exact_search(self, query: str) -> List[Dict[str, Any]]:
        """Phase A: 精确/模糊匹配，复用现有 AliasService + QueryService"""
        if not self.alias_service or not self.query_service:
            return []

        results = []
        # 尝试在各类别中解析实体名
        categories = [
            ("pokemon", "search_pokemon"),
            ("move", "search_moves"),
            ("ability", "search_abilities"),
            ("item", "search_items"),
        ]

        for category, method_name in categories:
            resolved = self.alias_service.resolve(query, category)
            if resolved:
                method = getattr(self.query_service, method_name, None)
                if method:
                    try:
                        rows = method(resolved)
                        for row in rows[:3]:  # 每个类别最多 3 条
                            results.append({
                                "id": f"exact:{category}:{resolved}",
                                "table": category,
                                "name_zh": resolved,
                                "text": self._format_row(category, row),
                                "score": 1.0,  # 精确匹配最高分
                            })
                    except Exception:
                        pass

        # 属性克制特殊处理
        type_keywords = ["克制", "效果拔群", "打", "属性"]
        if any(kw in query for kw in type_keywords):
            resolved_type = self.alias_service.resolve(query, "type")
            if resolved_type:
                try:
                    rows = self.query_service.get_type_effectiveness(resolved_type)
                    if rows:
                        lines = [f"属性克制：{resolved_type}属性"]
                        eff_labels = {
                            0.0: "无效（0倍）",
                            0.5: "效果不好（0.5倍）",
                            2.0: "效果拔群（2倍）",
                        }
                        for row in rows:
                            eff = row.get("effectiveness", 1.0)
                            if eff != 1.0:
                                label = eff_labels.get(eff, f"{eff}倍")
                                lines.append(f"  {resolved_type} → {row['defender_type']}：{label}")
                        results.append({
                            "id": f"exact:type_eff:{resolved_type}",
                            "table": "type_effectiveness",
                            "name_zh": resolved_type,
                            "text": "\n".join(lines),
                            "score": 1.0,
                        })
                except Exception:
                    pass

        return results

    @staticmethod
    def _format_row(category: str, row: Dict[str, Any]) -> str:
        """将查询结果行格式化为文本，包含所有语言字段"""
        if category == "pokemon":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            ncp = row.get("name_ncp")
            text = f"宝可梦 / Pokemon：{' / '.join(names)}"
            if ncp:
                text += f"（NCP名称：{ncp}）"
            parts = []
            if row.get("type1"):
                t = row["type1"]
                if row.get("type2"):
                    t += f"/{row['type2']}"
                parts.append(f"属性 / Type：{t}")
            abilities = []
            for zh_key, en_key, ja_key, label in [
                ("ability1_zh", "ability1_name", "ability1_ja", ""),
                ("ability2_zh", "ability2_name", "ability2_ja", ""),
                ("hidden_ability_zh", "hidden_ability_name", "hidden_ability_ja", "隐藏特性/Hidden"),
            ]:
                zh = row.get(zh_key)
                en = row.get(en_key)
                ja = row.get(ja_key)
                parts_name = [n for n in [zh, en, ja] if n]
                name = " / ".join(parts_name) if parts_name else None
                if name:
                    abilities.append(f"{name}（{label}）" if label else name)
            if abilities:
                parts.append(f"特性 / Ability：{' / '.join(abilities)}")
            stats = []
            for k, label in [("hp", "HP"), ("attack", "Atk"), ("defense", "Def"),
                              ("sp_attack", "SpA"), ("sp_defense", "SpD"), ("speed", "Spe")]:
                if row.get(k) is not None:
                    stats.append(f"{label}{row[k]}")
            if stats:
                parts.append(f"种族值 / Base Stats：{' '.join(stats)} 合计{row.get('total_stats', '')}")
            for lang, key in [("中文", "description_zh"), ("EN", "description_en"), ("日本語", "description_ja")]:
                if row.get(key):
                    parts.append(f"描述({lang})：{row[key]}")
            return text + "\n" + "\n".join(parts) if parts else text

        elif category == "ability":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"特性 / Ability：{' / '.join(names)}"
            return text

        elif category == "move":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"招式 / Move：{' / '.join(names)}"
            parts = []
            if row.get("type"):
                dc = row.get("damage_class", "")
                parts.append(f"属性 / Type：{row['type']} / 分类 / Category：{dc}")
            nums = []
            if row.get("power"):
                nums.append(f"威力/Power：{row['power']}")
            if row.get("accuracy"):
                nums.append(f"命中/Acc：{row['accuracy']}")
            if row.get("pp"):
                nums.append(f"PP：{row['pp']}")
            if nums:
                parts.append(" / ".join(nums))
            return text + "\n" + "\n".join(parts) if parts else text

        elif category == "item":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"道具 / Item：{' / '.join(names)}"
            if row.get("category"):
                text += f"\n分类 / Category：{row['category']}"
            return text

        elif category == "stat":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"能力值 / Stat：{' / '.join(names)}"
            abbrs = [n for n in [row.get("abbr_zh"), row.get("abbr_en"), row.get("abbr_ja")] if n]
            if abbrs:
                text += f"\n缩写：{' / '.join(abbrs)}"
            for lang, key in [("中文", "description_zh"), ("EN", "description_en"), ("日本語", "description_ja")]:
                if row.get(key):
                    text += f"\n描述({lang})：{row[key]}"
            return text

        elif category == "status":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"状态 / Status：{' / '.join(names)}"
            parts = []
            if row.get("category"):
                parts.append(f"分类：{row['category']}")
            if row.get("type_zh"):
                parts.append(f"类型：{row['type_zh']}")
            if row.get("duration"):
                parts.append(f"持续：{row['duration']}")
            return text + "\n" + "\n".join(parts) if parts else text

        elif category == "type":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"属性 / Type：{' / '.join(names)}"
            parts = []
            if row.get("color"):
                parts.append(f"颜色：{row['color']}")
            for lang, key in [("中文", "description_zh"), ("EN", "description_en"), ("日本語", "description_ja")]:
                if row.get(key):
                    parts.append(f"描述({lang})：{row[key]}")
            for lang, key in [("中文", "effect_zh"), ("EN", "effect_en")]:
                if row.get(key):
                    parts.append(f"效果({lang})：{row[key]}")
            return text + "\n" + "\n".join(parts) if parts else text

        elif category == "nature":
            names = [n for n in [row.get("name_zh"), row.get("name_en"), row.get("name_ja")] if n]
            text = f"性格 / Nature：{' / '.join(names)}"
            inc = row.get("increased_stat_zh") or row.get("increased_stat_en")
            dec = row.get("decreased_stat_zh") or row.get("decreased_stat_en")
            if inc or dec:
                text += f"\n加成：{inc or '无'} / 减弱：{dec or '无'}"
            return text

        else:
            return str(row)

    def _merge_results(
        self,
        exact_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """合并精确匹配和语义检索结果，去重"""
        seen_ids = set()
        merged = []

        # 精确匹配优先
        for doc in exact_results:
            if doc["id"] not in seen_ids:
                seen_ids.add(doc["id"])
                merged.append(doc)

        # 语义检索补充
        for doc in semantic_results:
            if doc["id"] not in seen_ids:
                # 额外去重：如果精确结果已包含同名实体，跳过
                name = doc.get("name_zh", "")
                if any(name and name in d.get("text", "") for d in exact_results):
                    continue
                seen_ids.add(doc["id"])
                merged.append(doc)

            if len(merged) >= MAX_CONTEXT_DOCS:
                break

        return merged[:MAX_CONTEXT_DOCS]

    def answer(self, query: str, context: list = None, search_results: list = None) -> Dict[str, Any]:
        """
        完整 RAG 流程：混合检索 → LLM 生成回答

        Args:
            query: 用户查询
            context: 对话历史（可选）
            search_results: 预计算的检索结果（可选），传入则跳过检索步骤

        Returns:
            {"success": bool, "type": str, "response": str, "data": dict}
        """
        if search_results is not None:
            all_context = search_results
        else:
            all_context = self.hybrid_search(query)

        if not all_context:
            return {
                "success": True,
                "type": "query",
                "response": "抱歉，未找到与您问题相关的数据。请尝试更具体的描述。",
                "data": None,
            }

        # 生成回答
        context_text = "\n\n---\n\n".join([doc["text"] for doc in all_context])
        response_text = self._generate_answer(query, context_text, context)

        return {
            "success": True,
            "type": "query",
            "response": response_text,
            "data": {
                "sources": [d["id"] for d in all_context],
                "source_count": len(all_context),
            },
        }

    def _generate_answer(
        self, query: str, context_text: str, conversation: list = None
    ) -> str:
        """调用 LLM 基于检索到的上下文生成回答"""
        if self.llm_service:
            try:
                return self.llm_service.summarize_query_result(
                    query, context_text, context=conversation
                )
            except Exception as e:
                print(f"RAG llm_service 生成失败: {e}")

        return f"以下是检索到的相关信息：\n\n{context_text}"
