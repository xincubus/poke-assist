"""
RAG 索引构建器 - 从数据库构建 FAISS 向量索引

用法：python -m api.rag_index [--db DB_PATH] [--output OUTPUT_DIR]
"""
import os
import sys
import sqlite3
import pickle
import time
from typing import List, Dict, Any

import numpy as np
import faiss
from .onnx_embedder import OnnxEmbedder

# 默认路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Embedding 模型（本地路径）
MODEL_NAME = os.path.join(PROJECT_ROOT, "models", "bge-small-zh-v1.5")


class DocumentBuilder:
    """从数据库各表构建文档"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def build_all(self) -> List[Dict[str, Any]]:
        """构建所有表的文档"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        docs = []
        docs.extend(self._build_pokemons(conn))
        docs.extend(self._build_moves(conn))
        docs.extend(self._build_abilities(conn))
        docs.extend(self._build_items(conn))
        docs.extend(self._build_type_effectiveness(conn))
        docs.extend(self._build_natures(conn))
        docs.extend(self._build_battle_terms(conn))
        docs.extend(self._build_status(conn))
        docs.extend(self._build_wiki_terms(conn))

        conn.close()
        return docs

    def _build_pokemons(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, pokedex_id, name_zh, name_ja, name_en, name_ncp,
                   type1, type2,
                   ability1_name, ability2_name, hidden_ability_name,
                   hp, attack, defense, sp_attack, sp_defense, speed, total_stats,
                   weight_kg, description_zh
            FROM pokemons WHERE name_zh IS NOT NULL
        """).fetchall()

        # 加载属性映射（英文 → 中/英）
        type_map = {}
        for r in conn.execute("SELECT name_en, name_zh FROM types").fetchall():
            zh = r["name_zh"] or r["name_en"]
            en = r["name_en"]
            type_map[en] = f"{zh}({en})" if zh and en and zh != en else (zh or en)

        # 加载特性映射（英文 → 中/英/日）
        ability_map = {}
        for r in conn.execute("SELECT name_en, name_zh, name_ja FROM abilities WHERE name_en IS NOT NULL").fetchall():
            parts = [n for n in [r["name_zh"], r["name_en"], r["name_ja"]] if n]
            ability_map[r["name_en"]] = " / ".join(parts)

        # 加载等级提升/蛋招式（按宝可梦英文名分组）
        pokemon_moves: Dict[str, List[str]] = {}
        for r in conn.execute("""
            SELECT pokemon_name_en, move_name_zh
            FROM pokemon_moves
            WHERE learn_method IN ('等级提升', '蛋招式')
              AND move_name_zh IS NOT NULL
            ORDER BY pokemon_name_en, learn_method
        """).fetchall():
            key = r["pokemon_name_en"].lower() if r["pokemon_name_en"] else None
            if key:
                pokemon_moves.setdefault(key, []).append(r["move_name_zh"])

        docs = []
        for row in rows:
            row = dict(row)
            # 属性
            t1 = type_map.get(row["type1"], row["type1"] or "")
            t2 = type_map.get(row["type2"], row["type2"] or "")
            types_str = t1
            if t2:
                types_str += f"/{t2}"

            # 特性（中/英/日）
            abilities = []
            for key, label in [("ability1_name", ""), ("ability2_name", ""), ("hidden_ability_name", "隐藏特性")]:
                if row[key]:
                    name = ability_map.get(row[key], row[key])
                    if label:
                        abilities.append(f"{name}（{label}）")
                    else:
                        abilities.append(name)
            abilities_str = " / ".join(abilities)

            # 种族值
            stats_str = (f"HP{row['hp']} 攻击{row['attack']} 防御{row['defense']} "
                         f"特攻{row['sp_attack']} 特防{row['sp_defense']} 速度{row['speed']} "
                         f"合计{row['total_stats']}")

            # 名称（中/英/日）
            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)
            ncp = row.get("name_ncp")
            if ncp:
                name_str += f"（NCP名称：{ncp}）"

            text = f"宝可梦：{name_str}\n属性：{types_str}\n特性：{abilities_str}\n种族值：{stats_str}"
            if row["weight_kg"]:
                text += f"\n体重：{row['weight_kg']}kg"
            if row["description_zh"]:
                text += f"\n描述：{row['description_zh']}"

            # 等级提升/蛋招式
            name_en_key = (row["name_en"] or "").lower()
            moves = pokemon_moves.get(name_en_key, [])
            if moves:
                # 去重保序
                seen = set()
                unique_moves = []
                for m in moves:
                    if m not in seen:
                        seen.add(m)
                        unique_moves.append(m)
                text += f"\n可学招式（不含通过技能机器学习的招式）：{'、'.join(unique_moves)}"

            docs.append({
                "id": f"pokemons:{row['id']}",
                "table": "pokemons",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_moves(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, name_zh, name_ja, name_en,
                   type, damage_class, power, accuracy, priority, pp
            FROM moves WHERE name_zh IS NOT NULL
        """).fetchall()

        type_map = {}
        for r in conn.execute("SELECT name_en, name_zh FROM types").fetchall():
            type_map[r["name_en"]] = r["name_zh"]

        class_map = {"physical": "物理", "special": "特殊", "status": "变化"}

        # 加载等级提升/蛋招式的学习者（按招式英文名分组）
        move_learners: Dict[str, List[str]] = {}
        for r in conn.execute("""
            SELECT move_name_en, pokemon_name_zh
            FROM pokemon_moves
            WHERE learn_method IN ('等级提升', '蛋招式')
              AND move_name_en IS NOT NULL AND pokemon_name_zh IS NOT NULL
            ORDER BY move_name_en, pokemon_name_zh
        """).fetchall():
            key = r["move_name_en"].lower().replace(" ", "-") if r["move_name_en"] else None
            if key:
                move_learners.setdefault(key, []).append(r["pokemon_name_zh"])

        docs = []
        for row in rows:
            row = dict(row)
            type_zh = type_map.get(row["type"], row["type"] or "")
            class_zh = class_map.get(row["damage_class"], row["damage_class"] or "")

            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)

            text = f"招式：{name_str}\n属性：{type_zh} / 分类：{class_zh}"
            if row["power"]:
                text += f"\n威力：{row['power']}"
            if row["accuracy"]:
                text += f" / 命中：{row['accuracy']}"
            if row["pp"]:
                text += f" / PP：{row['pp']}"
            if row["priority"] and row["priority"] != 0:
                text += f" / 优先度：{row['priority']}"

            # 可学习该招式的宝可梦（等级提升/蛋招式）
            name_en_key = (row["name_en"] or "").lower()
            learners = move_learners.get(name_en_key, [])
            if learners:
                # 去重保序
                seen = set()
                unique = []
                for p in learners:
                    if p not in seen:
                        seen.add(p)
                        unique.append(p)
                text += f"\n可学习的宝可梦：{'、'.join(unique)}"

            docs.append({
                "id": f"moves:{row['id']}",
                "table": "moves",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_abilities(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, name_zh, name_ja, name_en,
                   pokemon_list
            FROM abilities WHERE name_zh IS NOT NULL
        """).fetchall()

        # 英文名→中文名映射
        pokemon_name_map = {}
        for r in conn.execute("SELECT name_en, name_zh FROM pokemons WHERE name_en IS NOT NULL AND name_zh IS NOT NULL").fetchall():
            pokemon_name_map[r["name_en"]] = r["name_zh"]

        docs = []
        for row in rows:
            row = dict(row)
            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)

            text = f"特性：{name_str}"
            if row["pokemon_list"]:
                # 英文名转中文名
                en_names = [n.strip() for n in row["pokemon_list"].split(",")]
                zh_names = []
                for en in en_names:
                    zh = pokemon_name_map.get(en, en)
                    zh_names.append(zh)
                plist = "、".join(zh_names)
                text += f"\n拥有该特性的宝可梦：{plist}"

            docs.append({
                "id": f"abilities:{row['id']}",
                "table": "abilities",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_items(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, name_zh, name_ja, name_en,
                   category, fling_power
            FROM items WHERE name_zh IS NOT NULL
        """).fetchall()

        docs = []
        for row in rows:
            row = dict(row)
            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)

            text = f"道具：{name_str}"
            if row["category"]:
                text += f"\n分类：{row['category']}"

            docs.append({
                "id": f"items:{row['id']}",
                "table": "items",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_type_effectiveness(self, conn) -> List[Dict[str, Any]]:
        """按攻击属性分组，每个属性一个文档"""
        rows = conn.execute("""
            SELECT t1.name_zh as atk_type, t2.name_zh as def_type, te.effectiveness
            FROM type_effectiveness te
            JOIN types t1 ON te.attacker_type_id = t1.id
            JOIN types t2 ON te.defender_type_id = t2.id
            ORDER BY t1.id, te.effectiveness DESC
        """).fetchall()

        # 按攻击属性分组
        groups: Dict[str, List] = {}
        for row in rows:
            atk = row["atk_type"]
            if atk not in groups:
                groups[atk] = []
            groups[atk].append((row["def_type"], row["effectiveness"]))

        eff_labels = {
            0.0: "无效（0倍）",
            0.5: "效果不好（0.5倍）",
            1.0: "普通（1倍）",
            2.0: "效果拔群（2倍）",
        }

        docs = []
        for atk_type, matchups in groups.items():
            lines = [f"属性克制：{atk_type}属性"]
            for def_type, eff in matchups:
                label = eff_labels.get(eff, f"{eff}倍")
                if eff != 1.0:  # 只列出非普通倍率
                    lines.append(f"  {atk_type} → {def_type}：{label}")
            text = "\n".join(lines)

            docs.append({
                "id": f"type_eff:{atk_type}",
                "table": "type_effectiveness",
                "pk": atk_type,
                "name_zh": atk_type,
                "text": text,
            })
        return docs

    def _build_natures(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, name_zh, name_en, name_ja,
                   increased_stat_zh, increased_stat_en,
                   decreased_stat_zh, decreased_stat_en
            FROM natures WHERE name_zh IS NOT NULL
        """).fetchall()

        docs = []
        for row in rows:
            row = dict(row)
            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)

            text = f"性格：{name_str}"
            inc_zh = row.get("increased_stat_zh")
            dec_zh = row.get("decreased_stat_zh")
            inc_en = row.get("increased_stat_en")
            dec_en = row.get("decreased_stat_en")
            if inc_zh and dec_zh:
                inc_str = f"{inc_zh}({inc_en})" if inc_en else inc_zh
                dec_str = f"{dec_zh}({dec_en})" if dec_en else dec_zh
                text += f"\n能力修正：{inc_str}+10% / {dec_str}-10%"
            elif not inc_zh and not dec_zh:
                text += "\n能力修正：无（平衡性格）"

            docs.append({
                "id": f"natures:{row['id']}",
                "table": "natures",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_battle_terms(self, conn) -> List[Dict[str, Any]]:
        rows = conn.execute("""
            SELECT id, term, aliases, category, definition, formula,
                   related_field, related_value
            FROM battle_terms WHERE language = 'zh'
        """).fetchall()

        docs = []
        for row in rows:
            row = dict(row)
            text = f"术语：{row['term']}"
            if row["aliases"]:
                text += f"（别名：{row['aliases']}）"
            if row["category"]:
                text += f"\n分类：{row['category']}"
            if row["definition"]:
                text += f"\n定义：{row['definition']}"
            if row["formula"]:
                text += f"\n公式：{row['formula']}"

            docs.append({
                "id": f"battle_terms:{row['id']}",
                "table": "battle_terms",
                "pk": row["id"],
                "name_zh": row["term"],
                "text": text,
            })
        return docs

    def _build_status(self, conn) -> List[Dict[str, Any]]:
        try:
            rows = conn.execute("""
                SELECT id, name_zh, name_en, name_ja, category,
                       effect_en, effect_ja
                FROM status WHERE name_zh IS NOT NULL
            """).fetchall()
        except Exception:
            return []

        category_labels = {
            "weather": "天气", "terrain": "场地", "field": "场地效果",
            "abnormal": "异常状态", "stat_change": "能力变化",
            "special": "特殊状态",
        }
        docs = []
        for row in rows:
            row = dict(row)
            cat = row.get("category") or ""
            label = category_labels.get(cat, "状态")
            names = [n for n in [row["name_zh"], row["name_en"], row["name_ja"]] if n]
            name_str = " / ".join(names)
            text = f"{label}：{name_str}"
            for lang, key in [("EN", "effect_en"), ("日本語", "effect_ja")]:
                if row.get(key):
                    text += f"\n效果({lang})：{row[key]}"
            docs.append({
                "id": f"status:{row['id']}",
                "table": "status",
                "pk": row["id"],
                "name_zh": row["name_zh"],
                "text": text,
            })
        return docs

    def _build_wiki_terms(self, conn) -> List[Dict[str, Any]]:
        """wiki_terms 表：术语/游戏系统/地形/宝可梦特殊能力"""
        try:
            rows = conn.execute("""
                SELECT id, title, category, summary
                FROM wiki_terms
            """).fetchall()
        except Exception:
            return []

        docs = []
        for row in rows:
            row = dict(row)
            text = f"{row['category']}：{row['title']}"
            if row["summary"]:
                # 截取摘要前 300 字，避免过长
                summary = row["summary"][:300]
                text += f"\n{summary}"
            docs.append({
                "id": f"wiki_terms:{row['id']}",
                "table": "wiki_terms",
                "pk": row["id"],
                "name_zh": row["title"],
                "text": text,
            })
        return docs


def build_index(db_path: str = DEFAULT_DB_PATH, output_dir: str = DEFAULT_OUTPUT_DIR):
    """构建 FAISS 向量索引"""
    os.makedirs(output_dir, exist_ok=True)

    print(f"数据库路径: {db_path}")
    print(f"输出目录: {output_dir}")

    # 1. 构建文档
    print("\n[1/4] 构建文档...")
    builder = DocumentBuilder(db_path)
    docs = builder.build_all()
    print(f"  共 {len(docs)} 个文档")

    # 统计各表文档数
    table_counts: Dict[str, int] = {}
    for doc in docs:
        t = doc["table"]
        table_counts[t] = table_counts.get(t, 0) + 1
    for t, c in sorted(table_counts.items()):
        print(f"    {t}: {c}")

    # 2. 加载 embedding 模型
    print(f"\n[2/4] 加载 embedding 模型 ({MODEL_NAME})...")
    model = OnnxEmbedder(MODEL_NAME)
    print(f"  模型维度: {model.get_sentence_embedding_dimension()}")

    # 3. 编码所有文档
    print("\n[3/4] 编码文档向量...")
    texts = [doc["text"] for doc in docs]
    start = time.time()
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,  # L2 归一化，用于 cosine 相似度
    )
    elapsed = time.time() - start
    print(f"  编码完成: {elapsed:.1f}s, shape={embeddings.shape}")

    # 4. 构建 FAISS 索引
    print("\n[4/4] 构建 FAISS 索引...")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # 内积（因为已归一化 = cosine 相似度）
    index.add(embeddings.astype(np.float32))
    print(f"  索引大小: {index.ntotal} 向量, 维度 {dim}")

    # 保存
    faiss_path = os.path.join(output_dir, "rag.faiss")
    docs_path = os.path.join(output_dir, "rag_docs.pkl")

    faiss.write_index(index, faiss_path)
    with open(docs_path, "wb") as f:
        pickle.dump(docs, f)

    faiss_size = os.path.getsize(faiss_path) / 1024 / 1024
    docs_size = os.path.getsize(docs_path) / 1024 / 1024
    print(f"\n索引已保存:")
    print(f"  {faiss_path} ({faiss_size:.1f} MB)")
    print(f"  {docs_path} ({docs_size:.1f} MB)")
    print(f"\n构建完成！")

    return index, docs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="构建 RAG 向量索引")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="数据库路径")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    args = parser.parse_args()

    build_index(args.db, args.output)
