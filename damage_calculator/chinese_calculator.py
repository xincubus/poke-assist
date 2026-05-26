"""
支持中文输入的伤害计算器
从 pokemonData.db 加载中→英映射，替代原 name_mappings.json
"""

import os
import re
import sqlite3
from pokemon_damage_calculator import PokemonDamageCalculator

# 天气映射（DB name_en → @smogon/calc 格式）
WEATHER_MAP = {
    "Sunny Day": "Sun",
    "Rain Dance": "Rain",
    "Sandstorm": "Sand",
    "Hail": "Snow",
    "Snowscape": "Snow",
    "Primordial Sea": "Heavy Rain",
    "Desolate Land": "Harsh Sunshine",
    "Delta Stream": "Strong Winds",
}

# 状态映射（DB name_en → @smogon/calc 格式）
STATUS_MAP = {
    "Burn": "brn",
    "Paralysis": "par",
    "Poison": "psn",
    "Badly poisoned": "tox",
    "Sleep": "slp",
    "Freeze": "frz",
}

# 场地后缀，需要去掉
TERRAIN_SUFFIX = " Terrain"


class ChineseDamageCalculator:
    """支持中文输入的伤害计算器"""

    def __init__(self, db_path: str = None, alias_resolver=None):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        calculator_js = os.path.join(current_dir, 'calculator.js')
        self.calc = PokemonDamageCalculator(node_script_path=calculator_js)
        self._alias_resolver = alias_resolver

        # 默认数据库路径
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(current_dir), "pokemon_data", "pokemonData.db"
            )

        self.db_path = db_path
        self.mappings = self._load_mappings_from_db(db_path)

    @staticmethod
    def _normalize_name(name_en: str) -> str:
        """只保留英文字母，小写。light-of-ruin → lightofruin"""
        return re.sub(r'[^a-zA-Z]', '', name_en).lower()

    @classmethod
    def _normalize_pokemon_name(cls, name_en: str) -> str:
        """宝可梦名 normalize，子类可覆写处理 mega/primal 等形态差异"""
        return cls._normalize_name(name_en)

    def _load_mappings_from_db(self, db_path: str) -> dict:
        """从数据库加载所有中→英映射"""
        conn = sqlite3.connect(db_path)
        mappings = {}

        # 宝可梦
        mappings["pokemon_names"] = {
            row[0]: self._normalize_pokemon_name(row[1])
            for row in conn.execute("SELECT name_zh, name_en FROM pokemons WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 招式
        mappings["move_names"] = {
            row[0]: self._normalize_name(row[1])
            for row in conn.execute("SELECT name_zh, name_en FROM moves WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 特性
        mappings["ability_names"] = {
            row[0]: self._normalize_name(row[1])
            for row in conn.execute("SELECT name_zh, name_en FROM abilities WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 道具
        mappings["item_names"] = {
            row[0]: self._normalize_name(row[1])
            for row in conn.execute("SELECT name_zh, name_en FROM items WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 性格
        mappings["nature_names"] = {
            row[0]: self._normalize_name(row[1])
            for row in conn.execute("SELECT name_zh, name_en FROM natures WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 属性：首字母大写
        mappings["type_names"] = {
            row[0]: row[1].capitalize()
            for row in conn.execute("SELECT name_zh, name_en FROM types WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 天气：通过硬编码映射转换，再 normalize
        mappings["weather_names"] = {
            row[0]: self._normalize_name(WEATHER_MAP.get(row[1], row[1]))
            for row in conn.execute("SELECT name_zh, name_en FROM status WHERE category='weather' AND name_zh IS NOT NULL AND name_en IS NOT NULL")
            if WEATHER_MAP.get(row[1])
        }

        # 场地：去掉 " Terrain" 后缀，再 normalize
        mappings["terrain_names"] = {
            row[0]: self._normalize_name(row[1].replace(TERRAIN_SUFFIX, ""))
            for row in conn.execute("SELECT name_zh, name_en FROM status WHERE category='terrain' AND name_zh IS NOT NULL AND name_en IS NOT NULL")
        }

        # 状态：通过硬编码映射转换，再 normalize
        mappings["status_names"] = {
            row[0]: self._normalize_name(STATUS_MAP.get(row[1], row[1]))
            for row in conn.execute("SELECT name_zh, name_en FROM status WHERE name_zh IS NOT NULL AND name_en IS NOT NULL")
            if STATUS_MAP.get(row[1])
        }

        # 宝可梦英文名 → 唯一特性英文名（key 用 pokemon normalize，value 用通用 normalize）
        mappings["pokemon_sole_ability"] = {
            self._normalize_pokemon_name(row[0]): self._normalize_name(row[1])
            for row in conn.execute(
                "SELECT name_en, ability1_name FROM pokemons "
                "WHERE ability1_name IS NOT NULL AND ability1_name != '' "
                "AND (ability2_name IS NULL OR ability2_name = '') "
                "AND (hidden_ability_name IS NULL OR hidden_ability_name = '')"
            )
        }

        conn.close()
        return mappings

    def _translate(self, chinese_name: str, category: str) -> str:
        """将中文名称翻译为英文"""
        mapping_key = f"{category}_names"
        if mapping_key in self.mappings:
            # 1. 精确匹配
            result = self.mappings[mapping_key].get(chinese_name)
            if result:
                return result
            # 2. 别名解析 fallback
            if self._alias_resolver:
                resolved_zh = self._alias_resolver(chinese_name, category)
                if resolved_zh and resolved_zh != chinese_name:
                    result = self.mappings[mapping_key].get(resolved_zh)
                    if result:
                        return result
            return chinese_name
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
        """
        使用中文名称计算伤害

        Args:
            attacker_name: 攻击方宝可梦名称（中文）
            defender_name: 防御方宝可梦名称（中文）
            move_name: 招式名称（中文）
            attacker_status: 攻击方状态（'烧伤', '麻痹', '中毒', '剧毒', '睡眠', '冰冻'）
            attacker_cur_hp: 攻击方当前HP百分比（0-100）
            attacker_tera_type: 攻击方太晶属性（中文，如 '水', '火'）
            defender_status: 防御方状态
            defender_cur_hp: 防御方当前HP百分比（0-100，满血触发多重鳞片等）
            defender_tera_type: 防御方太晶属性
            其他参数同 PokemonDamageCalculator.calculate
        """
        attacker_name_en = self._translate(attacker_name, 'pokemon')
        defender_name_en = self._translate(defender_name, 'pokemon')
        move_name_en = self._translate(move_name, 'move')
        attacker_nature_en = self._translate(attacker_nature, 'nature')
        defender_nature_en = self._translate(defender_nature, 'nature')

        attacker_ability_en = self._translate(attacker_ability, 'ability') if attacker_ability else None
        defender_ability_en = self._translate(defender_ability, 'ability') if defender_ability else None

        # 没有传入特性时，自动查唯一特性
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
            defender_name=defender_name_en,
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


# 使用示例
if __name__ == '__main__':
    calc = ChineseDamageCalculator()

    print('=' * 60)
    print('使用中文输入计算伤害')
    print('=' * 60)

    result = calc.calculate_chinese(
        attacker_name='原始盖欧卡',
        attacker_evs={'spa': 252, 'spe': 252, 'hp': 4},
        attacker_nature='胆小',
        attacker_ability='始源之海',
        attacker_item='讲究眼镜',

        defender_name='故勒顿',
        defender_evs={'hp': 252, 'atk': 252, 'spe': 4},
        defender_nature='固执',
        defender_ability='绯红脉动',

        move_name='喷水',
        weather='大雨',
    )

    if result['success']:
        print(f"\n攻击方: {result['attacker']['name']}")
        print(f"防御方: {result['defender']['name']}")
        print(f"伤害范围: {result['damageRange'][0]} - {result['damageRange'][1]}")
        print(f"击杀概率: {result['kochance']['text']}")
        print(f"\n完整描述:")
        print(f"  {result['description']}")
    else:
        print(f"错误: {result['error']}")
