"""
宝可梦数据查询服务
"""
import sqlite3
import os
from typing import List, Dict, Any, Optional


class PokemonQueryService:
    """宝可梦数据查询服务"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def execute_query(self, sql: str) -> List[Dict[str, Any]]:
        """执行SQL查询并返回结果"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            conn.close()

            # 转换为字典列表
            return [dict(row) for row in rows]
        except Exception as e:
            raise Exception(f"查询执行失败: {str(e)}")

    def execute_sql(self, sql: str, limit: int = 100) -> List[Dict[str, Any]]:
        """执行只读 SQL 查询（仅允许 SELECT 语句）"""
        sql_stripped = sql.strip()
        if not sql_stripped.upper().startswith("SELECT"):
            raise ValueError("只允许 SELECT 查询")
        # 禁止危险关键词（防止 SELECT INTO、SELECT ... FOR UPDATE 等）
        upper = sql_stripped.upper()
        for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "ATTACH", "DETACH"):
            if forbidden in upper:
                raise ValueError(f"SQL 包含禁止关键词: {forbidden}")
        # 注入 LIMIT 防止结果过大
        if "LIMIT" not in upper:
            sql_stripped = sql_stripped.rstrip(";") + f" LIMIT {limit}"
        return self.execute_query(sql_stripped)

    def search_pokemon(self, name: str) -> List[Dict[str, Any]]:
        """搜索宝可梦基础信息"""
        sql = f"""
        SELECT
            p.name_zh, p.name_ja, p.name_en, p.name_ncp,
            p.type1, p.type2,
            p.ability1_name, p.ability2_name, p.hidden_ability_name,
            a1.name_zh AS ability1_zh, a2.name_zh AS ability2_zh, a3.name_zh AS hidden_ability_zh,
            p.hp, p.attack, p.defense, p.sp_attack, p.sp_defense, p.speed, p.total_stats,
            p.description_zh, p.description_en, p.description_ja,
            p.wiki_file_path
        FROM pokemons p
        LEFT JOIN abilities a1 ON p.ability1_name = a1.name_en
        LEFT JOIN abilities a2 ON p.ability2_name = a2.name_en
        LEFT JOIN abilities a3 ON p.hidden_ability_name = a3.name_en
        WHERE p.name_zh LIKE '%{name}%'
           OR p.name_ja LIKE '%{name}%'
           OR p.name_en LIKE '%{name}%'
           OR p.name_pinyin LIKE '%{name}%'
           OR p.name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_moves(self, name: str) -> List[Dict[str, Any]]:
        """搜索招式信息"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            type, damage_class, power, accuracy, priority, pp,
            wiki_file_path
        FROM moves
        WHERE name_zh LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_moves_by_keyword(self, keyword: str, limit: int = 30) -> List[Dict[str, Any]]:
        """按名称关键词搜索招式（中英日+拼音匹配）"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            type, damage_class, power, accuracy, priority, pp,
            wiki_file_path
        FROM moves
        WHERE name_zh LIKE '%{keyword}%'
           OR name_en LIKE '%{keyword}%'
           OR name_ja LIKE '%{keyword}%'
           OR name_pinyin LIKE '%{keyword}%'
        LIMIT {limit}
        """
        return self.execute_query(sql)

    def filter_moves(self, priority_min: int = None, priority_max: int = None,
                  accuracy: str = None, damage_class: str = None,
                  type_name: str = None, power_min: int = None, power_max: int = None,
                  limit: int = 50) -> List[Dict[str, Any]]:
        """按数值条件筛选招式。accuracy='null' 表示必中（accuracy IS NULL）"""
        conditions = []
        if priority_min is not None:
            conditions.append(f"priority >= {int(priority_min)}")
        if priority_max is not None:
            conditions.append(f"priority <= {int(priority_max)}")
        if accuracy == "null":
            conditions.append("accuracy IS NULL")
        elif accuracy is not None:
            conditions.append(f"accuracy = {int(accuracy)}")
        if damage_class:
            safe_dc = damage_class.replace("'", "")
            conditions.append(f"damage_class = '{safe_dc}'")
        if type_name:
            safe_type = type_name.replace("'", "")
            conditions.append(f"(type = '{safe_type}' OR type_id IN (SELECT id FROM types WHERE name_zh = '{safe_type}' OR name_zh = '{safe_type}属性' OR name_zh LIKE '{safe_type}%' OR name_en = '{safe_type}'))")
        if power_min is not None:
            conditions.append(f"power >= {int(power_min)}")
        if power_max is not None:
            conditions.append(f"power <= {int(power_max)}")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
        SELECT name_zh, name_ja, name_en,
               type, damage_class, power, accuracy, priority, pp,
               wiki_file_path
        FROM moves
        {where}
        ORDER BY priority DESC, power DESC
        LIMIT {int(limit)}
        """
        return self.execute_query(sql)

    def search_abilities(self, name: str) -> List[Dict[str, Any]]:
        """搜索特性信息"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            pokemon_list,
            wiki_file_path
        FROM abilities
        WHERE name_zh LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_items(self, name: str) -> List[Dict[str, Any]]:
        """搜索道具信息"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            category, fling_power,
            wiki_file_path
        FROM items
        WHERE name_zh LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_stat(self, name: str) -> List[Dict[str, Any]]:
        """搜索能力值信息（HP、攻击、防御、特攻、特防、速度等）"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            abbr_zh, abbr_ja, abbr_en,
            description_zh, description_ja, description_en,
            wiki_file_path
        FROM stats
        WHERE name_zh LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR abbr_zh LIKE '%{name}%'
           OR abbr_en LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_status(self, name: str) -> List[Dict[str, Any]]:
        """搜索状态信息（异常状态、天气、场地等）"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            category, type_zh, duration,
            wiki_file_path
        FROM status
        WHERE name_zh LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_type(self, name: str) -> List[Dict[str, Any]]:
        """搜索属性信息（火、水、草等）"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            description_zh, description_ja, description_en,
            effect_zh, effect_en,
            color,
            wiki_file_path
        FROM types
        WHERE name_zh LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def search_nature(self, name: str) -> List[Dict[str, Any]]:
        """搜索性格信息"""
        sql = f"""
        SELECT
            name_zh, name_ja, name_en,
            increased_stat_zh, decreased_stat_zh,
            increased_stat_en, decreased_stat_en,
            wiki_file_path
        FROM natures
        WHERE name_zh LIKE '%{name}%'
           OR name_en LIKE '%{name}%'
           OR name_ja LIKE '%{name}%'
           OR name_pinyin LIKE '%{name}%'
           OR name_pinyin_abbr LIKE '%{name}%'
        LIMIT 20
        """
        return self.execute_query(sql)

    def get_type_effectiveness(self, attacker_type: str, defender_type: str = None) -> List[Dict[str, Any]]:
        """查询属性克制关系，支持中文（火/火属性）和英文（Fire）"""
        def _type_condition(col: str, val: str) -> str:
            return f"({col} = '{val}' OR {col} = '{val}属性' OR {col} LIKE '{val}%' OR t_en.name_en = '{val}')"

        if defender_type:
            sql = f"""
            SELECT
                t1.name_zh as attacker_type,
                t2.name_zh as defender_type,
                te.effectiveness
            FROM type_effectiveness te
            JOIN types t1 ON te.attacker_type_id = t1.id
            JOIN types t2 ON te.defender_type_id = t2.id
            WHERE {_type_condition('t1.name_zh', attacker_type).replace('t_en.name_en', 't1.name_en')}
              AND {_type_condition('t2.name_zh', defender_type).replace('t_en.name_en', 't2.name_en')}
            """
        else:
            sql = f"""
            SELECT
                t1.name_zh as attacker_type,
                t2.name_zh as defender_type,
                te.effectiveness
            FROM type_effectiveness te
            JOIN types t1 ON te.attacker_type_id = t1.id
            JOIN types t2 ON te.defender_type_id = t2.id
            WHERE {_type_condition('t1.name_zh', attacker_type).replace('t_en.name_en', 't1.name_en')}
            ORDER BY te.effectiveness DESC
            """
        return self.execute_query(sql)

    def get_type_effectiveness_by_defender(self, defender_type: str) -> List[Dict[str, Any]]:
        """查询什么属性克制指定防御属性"""
        def _type_condition(col: str, col_en: str, val: str) -> str:
            return f"({col} = '{val}' OR {col} = '{val}属性' OR {col} LIKE '{val}%' OR {col_en} = '{val}')"

        sql = f"""
        SELECT
            t1.name_zh as attacker_type,
            t2.name_zh as defender_type,
            te.effectiveness
        FROM type_effectiveness te
        JOIN types t1 ON te.attacker_type_id = t1.id
        JOIN types t2 ON te.defender_type_id = t2.id
        WHERE {_type_condition('t2.name_zh', 't2.name_en', defender_type)}
        ORDER BY te.effectiveness DESC
        """
        return self.execute_query(sql)

    def get_dual_type_effectiveness(self, type1: str, type2: str = None) -> List[Dict[str, Any]]:
        """查询单属性或双属性作为防御方时的克制关系（倍率相乘）"""
        def _type_condition(col: str, col_en: str, val: str) -> str:
            return f"({col} = '{val}' OR {col} = '{val}属性' OR {col} LIKE '{val}%' OR {col_en} = '{val}')"

        if not type2:
            return self.get_type_effectiveness_by_defender(type1)

        sql = f"""
        SELECT
            t_atk.name_zh as attacker_type,
            e1.effectiveness as eff_vs_type1,
            e2.effectiveness as eff_vs_type2,
            (e1.effectiveness * e2.effectiveness) as total_effectiveness
        FROM types t_atk
        JOIN types t_def1 ON {_type_condition('t_def1.name_zh', 't_def1.name_en', type1)}
        JOIN types t_def2 ON {_type_condition('t_def2.name_zh', 't_def2.name_en', type2)}
        JOIN type_effectiveness e1 ON e1.attacker_type_id = t_atk.id AND e1.defender_type_id = t_def1.id
        JOIN type_effectiveness e2 ON e2.attacker_type_id = t_atk.id AND e2.defender_type_id = t_def2.id
        ORDER BY total_effectiveness DESC
        """
        return self.execute_query(sql)

    def get_pokemon_moves(self, pokemon_name: str, version: str = "sv") -> List[Dict[str, Any]]:
        """查询宝可梦可学招式"""
        table = "pokemon_moves"
        sql = f"""
        SELECT
            move_name_zh, move_name_en,
            learn_method, level
        FROM {table}
        WHERE pokemon_name_zh LIKE '%{pokemon_name}%'
           OR pokemon_name_ja LIKE '%{pokemon_name}%'
           OR pokemon_name_en LIKE '%{pokemon_name}%'
        ORDER BY
            CASE learn_method
                WHEN 'level-up' THEN 1
                WHEN 'machine' THEN 2
                WHEN 'egg' THEN 3
                ELSE 4
            END,
            level
        """
        return self.execute_query(sql)

    def get_move_learners(self, move_name: str, learn_method: str = None) -> List[Dict[str, Any]]:
        """反向查询某招式能被哪些宝可梦学会。优先查 Champions 表，不足时补全世代数据。"""
        safe = move_name.replace("'", "''")
        method_filter = ""
        if learn_method:
            method_filter = f"AND pm.learn_method = '{learn_method}'"

        # Champions 优先
        sql_champions = f"""
        SELECT DISTINCT
            p.name_zh, p.name_en, p.type1, p.type2,
            pm.learn_method, pm.level, 'champions' AS source
        FROM pokemon_moves_champions pm
        JOIN pokemons p ON pm.pokeapi_id = p.pokeapi_id
        WHERE (pm.move_name_zh LIKE '%{safe}%' OR pm.move_name_en LIKE '%{safe}%')
          {method_filter}
        """
        champions_rows = self.execute_query(sql_champions)
        if champions_rows:
            return champions_rows

        # Fallback: 全世代数据
        sql_all = f"""
        SELECT DISTINCT
            p.name_zh, p.name_en, p.type1, p.type2,
            pm.learn_method, pm.level, 'historical' AS source
        FROM pokemon_moves pm
        JOIN pokemons p ON pm.pokeapi_id = p.pokeapi_id
        WHERE (pm.move_name_zh LIKE '%{safe}%' OR pm.move_name_en LIKE '%{safe}%')
          {method_filter}
        ORDER BY
            CASE pm.learn_method
                WHEN 'level-up' THEN 1
                WHEN 'machine' THEN 2
                WHEN 'egg' THEN 3
                ELSE 4
            END,
            pm.level, p.name_en
        """
        return self.execute_query(sql_all)

    def get_pokemon_moves_intersection(self, move_names: list) -> List[Dict[str, Any]]:
        """查询同时会多个招式的宝可梦。优先查 Champions 表，不足时补全世代数据。"""
        if not move_names:
            return []

        def _escape(s):
            return s.replace("'", "''")

        def _make_subqueries(table):
            return " INTERSECT ".join(
                f"SELECT DISTINCT pokeapi_id FROM {table} "
                f"WHERE move_name_zh LIKE '%{_escape(m)}%' OR move_name_en LIKE '%{_escape(m)}%'"
                for m in move_names
            )

        # Champions 优先
        ch_parts = _make_subqueries("pokemon_moves_champions")
        sql_ch = ("SELECT p.name_zh, p.name_en, p.type1, p.type2, 'champions' AS source "
                  "FROM pokemons p WHERE p.pokeapi_id IN (" + ch_parts + ") ORDER BY p.pokeapi_id")
        champions_rows = self.execute_query(sql_ch)
        if champions_rows:
            return champions_rows

        # Fallback: 全世代 pokemon_moves
        all_parts = _make_subqueries("pokemon_moves")
        sql_all = ("SELECT p.name_zh, p.name_en, p.type1, p.type2, 'historical' AS source "
                   "FROM pokemons p WHERE p.pokeapi_id IN (" + all_parts + ") ORDER BY p.pokeapi_id")
        return self.execute_query(sql_all)

    def search_battle_term(self, term: str) -> Optional[Dict[str, Any]]:
        """搜索对战术语"""
        sql = f"""
        SELECT *
        FROM battle_terms
        WHERE term = '{term}' OR aliases LIKE '%{term}%'
        LIMIT 1
        """
        results = self.execute_query(sql)
        return results[0] if results else None

    def add_battle_term(self, term: str, aliases: str, category: str,
                       definition: str, formula: str = "",
                       related_field: str = "", related_value: str = "") -> bool:
        """添加新的对战术语"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO battle_terms
                (term, aliases, category, definition, formula, related_field, related_value, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'zh')
            """, (term, aliases, category, definition, formula, related_field, related_value))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"添加术语失败: {str(e)}")
            return False

    def intelligent_query(self, user_query: str) -> Dict[str, Any]:
        """
        智能查询 - 根据用户问题自动判断查询类型并执行

        返回格式:
        {
            "success": bool,
            "query_type": str,  # pokemon/move/ability/item/type_effectiveness/pokemon_moves
            "data": List[Dict],
            "message": str
        }
        """
        query_lower = user_query.lower()

        # 关键词匹配判断查询类型
        if any(kw in user_query for kw in ["种族值", "属性", "特性", "宝可梦"]):
            # 提取宝可梦名称（简单实现，可以改进）
            # 这里需要更智能的NLP处理
            return {
                "success": True,
                "query_type": "pokemon",
                "data": [],
                "message": "宝可梦查询功能需要进一步实现"
            }

        elif any(kw in user_query for kw in ["招式", "技能", "威力", "命中"]):
            return {
                "success": True,
                "query_type": "move",
                "data": [],
                "message": "招式查询功能需要进一步实现"
            }

        elif any(kw in user_query for kw in ["克制", "效果拔群", "效果不好"]):
            return {
                "success": True,
                "query_type": "type_effectiveness",
                "data": [],
                "message": "属性克制查询功能需要进一步实现"
            }

        else:
            return {
                "success": False,
                "query_type": "unknown",
                "data": [],
                "message": "无法识别查询类型，请提供更具体的问题"
            }
