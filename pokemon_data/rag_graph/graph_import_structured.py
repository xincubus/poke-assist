"""结构化数据导入：pokemonData.db → graph.db"""
import json
import os
import sqlite3
import sys
import time

# 让模块可以独立运行
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pokemon_data.rag_graph.graph_db import GraphDB

SRC_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pokemonData.db")

# ── generation 静态元数据 ──────────────────────────────────────────
GENERATIONS = [
    {"id": 1, "name_en": "Generation I",   "gen_zh": "第一世代", "region": "关都"},
    {"id": 2, "name_en": "Generation II",  "gen_zh": "第二世代", "region": "城都"},
    {"id": 3, "name_en": "Generation III", "gen_zh": "第三世代", "region": "丰缘"},
    {"id": 4, "name_en": "Generation IV",  "gen_zh": "第四世代", "region": "神奥"},
    {"id": 5, "name_en": "Generation V",   "gen_zh": "第五世代", "region": "合众"},
    {"id": 6, "name_en": "Generation VI",  "gen_zh": "第六世代", "region": "卡洛斯"},
    {"id": 7, "name_en": "Generation VII", "gen_zh": "第七世代", "region": "阿罗拉"},
    {"id": 8, "name_en": "Generation VIII","gen_zh": "第八世代", "region": "伽勒尔"},
    {"id": 9, "name_en": "Generation IX",  "gen_zh": "第九世代", "region": "帕底亚"},
    {"id": 10,"name_en": "Generation X",   "gen_zh": "第十世代", "region": "—"},
]


def import_all(src_path=None, graph_path=None, verbose=True):
    src_path = src_path or SRC_DB
    src = sqlite3.connect(src_path)
    graph = GraphDB(graph_path)
    t0 = time.time()

    # ── 查找表 ─────────────────────────────────────────────────────
    name_to_pokeapi = {}
    name_to_item_id = {}
    name_to_ability_id = {}
    name_to_move_id = {}
    type_name_to_id = {}  # 英文名 → id
    type_zh_to_id = {}    # 中文名 → id（type_matchups_by_gen 用）

    for row in src.execute("SELECT name_en, pokeapi_id FROM pokemons WHERE name_en IS NOT NULL"):
        name_to_pokeapi[row[0].lower()] = row[1]
    for row in src.execute("SELECT name_en, id FROM items WHERE name_en IS NOT NULL"):
        name_to_item_id[row[0].lower()] = row[1]
    for row in src.execute("SELECT name_en, id FROM abilities WHERE name_en IS NOT NULL"):
        name_to_ability_id[row[0].lower()] = row[1]
    for row in src.execute("SELECT name_en, id FROM moves WHERE name_en IS NOT NULL"):
        name_to_move_id[row[0].lower()] = row[1]
    for row in src.execute("SELECT name_en, name_zh, id FROM types"):
        if row[0]: type_name_to_id[row[0].lower()] = row[2]
        if row[1]: type_zh_to_id[row[1]] = row[2]

    if verbose:
        print(f"查找表构建完成: pokemon={len(name_to_pokeapi)}, item={len(name_to_item_id)}, "
              f"ability={len(name_to_ability_id)}, move={len(name_to_move_id)}, type={len(type_name_to_id)}")

    # ── 节点导入 ──────────────────────────────────────────────────
    counts = {"nodes": {}, "edges": {}, "aliases": 0}

    def _import_nodes():
        # 1. type
        n = 0
        for row in src.execute("SELECT id, name_en, name_zh, name_ja FROM types"):
            graph.add_node(f"type:{row[0]}", "type", name_zh=row[2], name_en=row[1], name_ja=row[3])
            n += 1
        counts["nodes"]["type"] = n

        # 2. ability
        n = 0
        for row in src.execute(
            "SELECT id, name_en, name_zh, name_ja, description_zh, "
            "affected_by_mold_breaker, triggers_on_entry, effect_battle FROM abilities"
        ):
            props = {}
            if row[4]: props["description_zh"] = row[4]
            if row[5] is not None: props["mold_breaker"] = row[5]
            if row[6] is not None: props["triggers_on_entry"] = row[6]
            if row[7]: props["effect_battle"] = row[7]
            graph.add_node(f"ability:{row[0]}", "ability",
                           name_zh=row[2], name_en=row[1], name_ja=row[3],
                           properties=props if props else None)
            n += 1
        counts["nodes"]["ability"] = n

        # 3. move
        n = 0
        for row in src.execute(
            "SELECT id, name_en, name_zh, name_ja, type, damage_class, power, "
            "makes_contact, can_protect, target, effect_zh FROM moves"
        ):
            props = {}
            if row[4]: props["type"] = row[4]
            if row[5]: props["class"] = row[5]
            if row[6] is not None: props["power"] = row[6]
            if row[7] is not None: props["contact"] = row[7]
            if row[8] is not None: props["protectable"] = row[8]
            if row[9]: props["target"] = row[9]
            if row[10]: props["effect"] = row[10]
            graph.add_node(f"move:{row[0]}", "move",
                           name_zh=row[2], name_en=row[1], name_ja=row[3],
                           properties=props if props else None)
            n += 1
        counts["nodes"]["move"] = n

        # 4. item
        n = 0
        for row in src.execute("SELECT id, name_en, name_zh, name_ja, category FROM items"):
            props = {"category": row[4]} if row[4] else None
            graph.add_node(f"item:{row[0]}", "item",
                           name_zh=row[2], name_en=row[1], name_ja=row[3],
                           properties=props)
            n += 1
        counts["nodes"]["item"] = n

        # 5. pokemon
        n = 0
        for row in src.execute(
            "SELECT pokeapi_id, name_en, name_zh, name_ja, pokedex_id, "
            "type1, type2, ability1_name, ability2_name, hidden_ability_name, "
            "species, egg_group1, egg_group2, gender_ratio, catch_rate, color, "
            "ev_yield, base_exp, height_m, weight_kg, hp, attack, defense, "
            "sp_attack, sp_defense, speed FROM pokemons"
        ):
            types = [t for t in [row[5], row[6]] if t]
            abilities = [a for a in [row[7], row[8]] if a]
            if row[9]:
                abilities.append(f"{row[9]} (hidden)")
            stats = {}
            for i, stat_name in enumerate(["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]):
                val = row[20 + i]
                if val is not None:
                    stats[stat_name] = val
            egg_groups = [e for e in [row[11], row[12]] if e]
            props = {"pokedex_id": row[4]}
            if types: props["types"] = types
            if abilities: props["abilities"] = abilities
            if stats: props["stats"] = stats
            if row[10]: props["species"] = row[10]
            if egg_groups: props["egg_groups"] = egg_groups
            if row[13] is not None: props["gender_ratio"] = row[13]
            if row[14] is not None: props["catch_rate"] = row[14]
            if row[15]: props["color"] = row[15]
            if row[16]: props["ev_yield"] = row[16]
            if row[17] is not None: props["base_exp"] = row[17]
            if row[18] is not None: props["height_m"] = row[18]
            if row[19] is not None: props["weight_kg"] = row[19]
            graph.add_node(f"pokemon:{row[0]}", "pokemon",
                           name_zh=row[2], name_en=row[1], name_ja=row[3],
                           properties=props)
            n += 1
        counts["nodes"]["pokemon"] = n

        # 6. nature
        n = 0
        for row in src.execute("SELECT id, name_en, name_zh, name_ja FROM natures"):
            graph.add_node(f"nature:{row[0]}", "nature",
                           name_zh=row[2], name_en=row[1], name_ja=row[3])
            n += 1
        counts["nodes"]["nature"] = n

        # 7. status（含 weather / terrain）
        n = 0
        for row in src.execute(
            "SELECT id, name_en, name_zh, name_ja, category, description_zh FROM status"
        ):
            props = {}
            if row[4]: props["category"] = row[4]
            if row[5]: props["effect"] = row[5]
            graph.add_node(f"status:{row[0]}", "status",
                           name_zh=row[2], name_en=row[1], name_ja=row[3],
                           properties=props if props else None)
            n += 1
        counts["nodes"]["status"] = n

        # 8. generation（静态数据）
        for gen in GENERATIONS:
            graph.add_node(f"gen:{gen['id']}", "generation",
                           name_zh=gen["gen_zh"], name_en=gen["name_en"],
                           properties={"region": gen["region"]})
        counts["nodes"]["generation"] = len(GENERATIONS)

        # 9. game（从 pokemon_moves 取 DISTINCT version_group, generation）
        n = 0
        seen = set()
        for row in src.execute(
            "SELECT DISTINCT version_group, generation FROM pokemon_moves ORDER BY generation"
        ):
            vg = row[0]
            if vg in seen:
                continue
            seen.add(vg)
            graph.add_node(f"game:{vg}", "game",
                           name_en=vg.replace("-", " ").title(),
                           properties={"generation": row[1]})
            n += 1
        counts["nodes"]["game"] = n

        graph.commit()

    def _import_edges():
        # 1. has_type
        n = 0
        for row in src.execute("SELECT pokeapi_id, type1, type2 FROM pokemons"):
            pid = row[0]
            for type_name in [row[1], row[2]]:
                if type_name:
                    tid = type_name_to_id.get(type_name.lower())
                    if tid:
                        graph.add_edge(f"pokemon:{pid}", f"type:{tid}", "has_type")
                        n += 1
        counts["edges"]["has_type"] = n

        # 2. has_ability
        n = 0
        for row in src.execute(
            "SELECT pokeapi_id, ability1_id, ability2_id, hidden_ability_id FROM pokemons"
        ):
            pid = row[0]
            for aid in [row[1], row[2], row[3]]:
                if aid:
                    graph.add_edge(f"pokemon:{pid}", f"ability:{aid}", "has_ability")
                    n += 1
        counts["edges"]["has_ability"] = n

        # 3. learns（去重：按 pokeapi_id+move_id 分组，properties 存 version_groups + methods）
        n = 0
        groups = {}
        for row in src.execute(
            "SELECT pokeapi_id, move_id, version_group, learn_method FROM pokemon_moves"
        ):
            key = (row[0], row[1])
            if key not in groups:
                groups[key] = {"vgs": set(), "methods": set()}
            groups[key]["vgs"].add(row[2])
            groups[key]["methods"].add(row[3])
        for (pid, mid), data in groups.items():
            props = {
                "version_groups": sorted(data["vgs"]),
                "methods": sorted(data["methods"]),
            }
            graph.add_edge(f"pokemon:{pid}", f"move:{mid}", "learns", properties=props)
            n += 1
        counts["edges"]["learns"] = n

        # 4. type_matchup（一条边存全世代倍率）
        n = 0
        matchups = {}
        for row in src.execute(
            "SELECT attacker_type, defender_type, generation, effectiveness FROM type_matchups_by_gen"
        ):
            key = (row[0], row[1])
            if key not in matchups:
                matchups[key] = {}
            matchups[key][f"gen_{row[2]}"] = row[3]
        for (atk, defe), gen_map in matchups.items():
            atk_id = type_zh_to_id.get(atk)
            defe_id = type_zh_to_id.get(defe)
            if atk_id and defe_id:
                graph.add_edge(f"type:{atk_id}", f"type:{defe_id}",
                               "type_matchup", properties=gen_map)
                n += 1
        counts["edges"]["type_matchup"] = n

        # 5. evolves_to（普通进化）
        n = 0
        for row in src.execute(
            "SELECT p1.pokeapi_id, p2.pokeapi_id, e.method, e.level, e.item_id, e.condition "
            "FROM evolutions e "
            "JOIN pokemons p1 ON p1.id = e.from_pokemon_id "
            "JOIN pokemons p2 ON p2.id = e.to_pokemon_id "
            "WHERE e.is_mega = 0 AND e.is_gmax = 0"
        ):
            props = {}
            if row[2]: props["method"] = row[2]
            if row[3] is not None: props["level"] = row[3]
            if row[4] is not None: props["item_id"] = row[4]
            if row[5]: props["condition"] = row[5]
            graph.add_edge(f"pokemon:{row[0]}", f"pokemon:{row[1]}",
                           "evolves_to", properties=props if props else None)
            n += 1
        counts["edges"]["evolves_to"] = n

        # 6. mega_evolves_to
        n = 0
        for row in src.execute(
            "SELECT p1.pokeapi_id, p2.pokeapi_id, e.method, e.item_id "
            "FROM evolutions e "
            "JOIN pokemons p1 ON p1.id = e.from_pokemon_id "
            "JOIN pokemons p2 ON p2.id = e.to_pokemon_id "
            "WHERE e.is_mega = 1"
        ):
            props = {}
            if row[2]: props["method"] = row[2]
            if row[3] is not None: props["item_id"] = row[3]
            graph.add_edge(f"pokemon:{row[0]}", f"pokemon:{row[1]}",
                           "mega_evolves_to", properties=props if props else None)
            n += 1
        counts["edges"]["mega_evolves_to"] = n

        # 7. gigantamaxes_to
        n = 0
        for row in src.execute(
            "SELECT p1.pokeapi_id, p2.pokeapi_id, e.method, e.condition "
            "FROM evolutions e "
            "JOIN pokemons p1 ON p1.id = e.from_pokemon_id "
            "JOIN pokemons p2 ON p2.id = e.to_pokemon_id "
            "WHERE e.is_gmax = 1"
        ):
            props = {}
            if row[2]: props["method"] = row[2]
            if row[3]: props["condition"] = row[3]
            graph.add_edge(f"pokemon:{row[0]}", f"pokemon:{row[1]}",
                           "gigantamaxes_to", properties=props if props else None)
            n += 1
        counts["edges"]["gigantamaxes_to"] = n

        # 8. available_in（pokemon → game）
        n = 0
        seen = set()
        for row in src.execute(
            "SELECT DISTINCT pokeapi_id, version_group FROM pokemon_moves"
        ):
            key = (row[0], row[1])
            if key in seen:
                continue
            seen.add(key)
            graph.add_edge(f"pokemon:{row[0]}", f"game:{row[1]}", "available_in")
            n += 1
        counts["edges"]["available_in"] = n

        # 9. game_in_generation
        n = 0
        seen = set()
        for row in src.execute(
            "SELECT DISTINCT version_group, generation FROM pokemon_moves"
        ):
            if row[0] in seen:
                continue
            seen.add(row[0])
            graph.add_edge(f"game:{row[0]}", f"gen:{row[1]}", "game_in_generation")
            n += 1
        counts["edges"]["game_in_generation"] = n

        graph.commit()

    def _import_aliases():
        # 1. battle_terms
        n = 0
        for row in src.execute(
            "SELECT term, aliases, category, related_value FROM battle_terms"
        ):
            term, aliases_str, category, related_value = row
            node_id = _resolve_term_to_node(related_value, category,
                                            name_to_pokeapi, name_to_item_id)
            if not node_id:
                continue
            # term 本身
            graph.add_alias(term.lower(), node_id)
            n += 1
            # aliases（逗号分隔）
            if aliases_str:
                for alias in aliases_str.split(","):
                    alias = alias.strip()
                    if alias:
                        graph.add_alias(alias.lower(), node_id)
                        n += 1
        counts["aliases"] += n

        # 2. 各节点 name_zh / name_en 注册为别名
        n = 0
        for row in graph.conn.execute(
            "SELECT node_id, name_zh, name_en FROM graph_nodes"
        ):
            node_id, name_zh, name_en = row
            if name_zh:
                graph.add_alias(name_zh, node_id)
                n += 1
            if name_en:
                graph.add_alias(name_en.lower(), node_id)
                n += 1
        counts["aliases"] += n
        graph.commit()

    def _resolve_term_to_node(related_value, category, name_to_pokeapi, name_to_item_id):
        if not related_value:
            return None
        if category == "item_alias":
            item_id = name_to_item_id.get(related_value.lower())
            return f"item:{item_id}" if item_id else None
        elif category == "pokemon_alias":
            pokeapi_id = name_to_pokeapi.get(related_value.lower())
            return f"pokemon:{pokeapi_id}" if pokeapi_id else None
        return None

    # ── 执行 ──────────────────────────────────────────────────────
    if verbose:
        print("开始导入节点...")
    _import_nodes()

    if verbose:
        print("开始导入边...")
    _import_edges()

    if verbose:
        print("开始导入别名...")
    _import_aliases()

    graph.close()
    src.close()

    elapsed = time.time() - t0
    if verbose:
        print(f"\n导入完成 ({elapsed:.1f}s)")
        print(f"节点: {counts['nodes']}")
        print(f"边:   {counts['edges']}")
        print(f"别名: {counts['aliases']}")
    return counts


if __name__ == "__main__":
    import_all()
