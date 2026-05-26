"""
基于 NCP 计算引擎的中文伤害计算器
替代 chinese_calculator.py，使用 cale/ 的计算引擎（支持 Gen 1-9 + Champions）
接口与 ChineseDamageCalculator 完全一致
"""

import os
import sqlite3
from chinese_calculator import ChineseDamageCalculator
from cale_pokemon_damage_calculator import CalePokemonDamageCalculator


# DB name_en → NCP 内部天气字符串
CALE_WEATHER_MAP = {
    "rain": "Rain",
    "sunny": "Sun",
    "sandstorm": "Sand",
    "hail": "Snow",
    "snow": "Snow",
    "extremely-harsh-sunlight": "Harsh Sun",
    "heavy-rain": "Heavy Rain",
    "strong-winds": "Strong Winds",
}

# DB name_en → NCP 内部状态字符串
CALE_STATUS_MAP = {
    "Poison": "Poisoned",
    "Badly poisoned": "Badly Poisoned",
    "Burn": "Burned",
    "Freeze": "Frozen",
    "Paralysis": "Paralyzed",
    "Sleep": "Asleep",
}


class CaleChineseDamageCalculator(ChineseDamageCalculator):
    """基于 NCP 计算引擎的中文伤害计算器（支持 Gen 1-9 + Champions）"""

    def __init__(self, db_path: str = None, alias_resolver=None):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        calculator_js = os.path.join(current_dir, 'cale', 'calculator.js')
        self.calc = CalePokemonDamageCalculator()
        self._alias_resolver = alias_resolver

        # 默认数据库路径
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(current_dir), "pokemon_data", "pokemonData.db"
            )

        self.db_path = db_path
        self.mappings = self._load_mappings_from_db(db_path)
        # 用 NCP 兼容的天气/状态映射覆盖基类的映射
        self._fix_weather_status_mappings(db_path)

    def _load_mappings_from_db(self, db_path: str) -> dict:
        """从数据库加载所有中→英映射，pokemon 使用 name_ncp 列直接获取 NCP key"""
        import re as _re
        # 先调用基类加载所有非 pokemon 映射
        mappings = super()._load_mappings_from_db(db_path)

        conn = sqlite3.connect(db_path)

        # pokemon_names: name_zh → (normalize(name_ncp), "")
        # 直接用 DB 的 name_ncp 列，无需任何规则转换
        pokemon_names = {}
        base_name_fallback = {}
        for row in conn.execute(
            "SELECT name_zh, name_ncp FROM pokemons "
            "WHERE name_zh IS NOT NULL AND name_ncp IS NOT NULL"
        ):
            name_zh, name_ncp = row
            pokemon_names[name_zh] = (self._normalize_name(name_ncp), "")
            # 基础名 fallback：去掉（...）后缀，无冲突时可用
            base = _re.sub(r'（.*）$', '', name_zh)
            if base != name_zh and base not in base_name_fallback:
                base_name_fallback[base] = (self._normalize_name(name_ncp), "")
        mappings["pokemon_names"] = pokemon_names
        mappings["_pokemon_base_fallback"] = base_name_fallback

        # pokemon_sole_ability: key 用 normalize(name_ncp)
        pokemon_sole_ability = {}
        for row in conn.execute(
            "SELECT name_ncp, ability1_name FROM pokemons "
            "WHERE name_ncp IS NOT NULL "
            "AND ability1_name IS NOT NULL AND ability1_name != '' "
            "AND (ability2_name IS NULL OR ability2_name = '') "
            "AND (hidden_ability_name IS NULL OR hidden_ability_name = '')"
        ):
            name_ncp, ability1 = row
            pokemon_sole_ability[self._normalize_name(name_ncp)] = self._normalize_name(ability1)
        mappings["pokemon_sole_ability"] = pokemon_sole_ability

        conn.close()
        return mappings

    def _translate(self, chinese_name: str, category: str) -> str:
        """将中文名称翻译为英文。pokemon 类别返回 (base, form) tuple，其余返回 string。"""
        mapping_key = f"{category}_names"
        if mapping_key in self.mappings:
            result = self.mappings[mapping_key].get(chinese_name)
            if result:
                return result
            # pokemon 基础名 fallback：幽尾玄鱼 → 幽尾玄鱼（雄性）的映射
            if category == "pokemon":
                fallback = self.mappings.get("_pokemon_base_fallback", {})
                result = fallback.get(chinese_name)
                if result:
                    return result
            if self._alias_resolver:
                resolved_zh = self._alias_resolver(chinese_name, category)
                if resolved_zh and resolved_zh != chinese_name:
                    result = self.mappings[mapping_key].get(resolved_zh)
                    if result:
                        return result
            # pokemon 类别返回 tuple
            if category == "pokemon":
                return (chinese_name, "")
            return chinese_name
        if category == "pokemon":
            return (chinese_name, "")
        return chinese_name

    def calculate_chinese(
        self,
        attacker_name: str,
        defender_name: str,
        move_name: str,
        attacker_evs: dict = None,
        attacker_nature: str = '认真',
        attacker_ability: str = None,
        attacker_item: str = None,
        attacker_boosts: dict = None,
        attacker_status: str = None,
        attacker_cur_hp: int = None,
        attacker_tera_type: str = None,
        defender_evs: dict = None,
        defender_nature: str = '认真',
        defender_ability: str = None,
        defender_item: str = None,
        defender_boosts: dict = None,
        defender_status: str = None,
        defender_cur_hp: int = None,
        defender_tera_type: str = None,
        weather: str = None,
        terrain: str = None,
        is_critical_hit: bool = False,
        is_reflect: bool = False,
        is_light_screen: bool = False,
    ) -> dict:
        """使用中文名称计算伤害，支持 form 拆分"""
        attacker_name_en, attacker_form = self._translate(attacker_name, 'pokemon')
        defender_name_en, defender_form = self._translate(defender_name, 'pokemon')
        move_name_en = self._translate(move_name, 'move')
        attacker_nature_en = self._translate(attacker_nature, 'nature')
        defender_nature_en = self._translate(defender_nature, 'nature')

        attacker_ability_en = self._translate(attacker_ability, 'ability') if attacker_ability else None
        defender_ability_en = self._translate(defender_ability, 'ability') if defender_ability else None

        sole = self.mappings.get("pokemon_sole_ability", {})
        if not attacker_ability_en:
            sole_en = sole.get(attacker_name_en)
            if sole_en:
                attacker_ability_en = sole_en
        if not defender_ability_en:
            sole_en = sole.get(defender_name_en)
            if sole_en:
                defender_ability_en = sole_en
        attacker_item_en = self._translate(attacker_item, 'item') if attacker_item else None
        defender_item_en = self._translate(defender_item, 'item') if defender_item else None
        weather_en = self._translate(weather, 'weather') if weather else None
        terrain_en = self._translate(terrain, 'terrain') if terrain else None

        attacker_status_en = self._translate(attacker_status, 'status') if attacker_status else None
        defender_status_en = self._translate(defender_status, 'status') if defender_status else None

        attacker_tera_en = self._translate(attacker_tera_type, 'type') if attacker_tera_type else None
        defender_tera_en = self._translate(defender_tera_type, 'type') if defender_tera_type else None

        return self.calc.calculate(
            attacker_name=attacker_name_en,
            attacker_form=attacker_form,
            defender_name=defender_name_en,
            defender_form=defender_form,
            move_name=move_name_en,
            attacker_evs=attacker_evs,
            attacker_nature=attacker_nature_en,
            attacker_ability=attacker_ability_en,
            attacker_item=attacker_item_en,
            attacker_boosts=attacker_boosts,
            attacker_status=attacker_status_en,
            attacker_cur_hp=attacker_cur_hp,
            attacker_tera_type=attacker_tera_en,
            defender_evs=defender_evs,
            defender_nature=defender_nature_en,
            defender_ability=defender_ability_en,
            defender_item=defender_item_en,
            defender_boosts=defender_boosts,
            defender_status=defender_status_en,
            defender_cur_hp=defender_cur_hp,
            defender_tera_type=defender_tera_en,
            weather=weather_en,
            terrain=terrain_en,
            is_critical_hit=is_critical_hit,
            is_reflect=is_reflect,
            is_light_screen=is_light_screen,
        )

    def _fix_weather_status_mappings(self, db_path: str):
        """用 DB name_en → NCP 格式重建天气和状态映射（normalize 输出）"""
        conn = sqlite3.connect(db_path)

        self.mappings["weather_names"] = {
            row[0]: self._normalize_name(CALE_WEATHER_MAP.get(row[1], row[1]))
            for row in conn.execute("SELECT name_zh, name_en FROM status WHERE category='weather' AND name_zh IS NOT NULL AND name_en IS NOT NULL")
            if CALE_WEATHER_MAP.get(row[1])
        }

        self.mappings["status_names"] = {
            row[0]: self._normalize_name(CALE_STATUS_MAP.get(row[1], row[1]))
            for row in conn.execute("SELECT name_zh, name_en FROM status WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
            if CALE_STATUS_MAP.get(row[1])
        }

        conn.close()
