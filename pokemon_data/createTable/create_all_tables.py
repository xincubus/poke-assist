#!/usr/bin/env python3
"""
宝可梦数据库生成总脚本
整合所有数据表的创建和导入流程
"""

import json
import sqlite3
import os
import sys
import io
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置路径
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"
ABILITY_DIR = BASE_DIR / "ability"
MOVES_DIR = BASE_DIR / "moves"
ITEMS_DIR = BASE_DIR / "heldItem"
POKEMON_DIR = BASE_DIR / "pokemon"
TYPE_DIR = BASE_DIR / "type"

# 版本组到世代的映射
VERSION_GROUP_TO_GENERATION = {
    'red-blue': 1, 'yellow': 1, 'red-green-japan': 1, 'blue-japan': 1,
    'gold-silver': 2, 'crystal': 2,
    'ruby-sapphire': 3, 'emerald': 3, 'firered-leafgreen': 3, 'colosseum': 3, 'xd': 3,
    'diamond-pearl': 4, 'platinum': 4, 'heartgold-soulsilver': 4,
    'black-white': 5, 'black-2-white-2': 5,
    'x-y': 6, 'omega-ruby-alpha-sapphire': 6,
    'sun-moon': 7, 'ultra-sun-ultra-moon': 7, 'lets-go-pikachu-lets-go-eevee': 7,
    'sword-shield': 8, 'brilliant-diamond-shining-pearl': 8, 'legends-arceus': 8,
    'scarlet-violet': 9
}

# 学习方式映射
LEARN_METHOD_MAP = {
    'level-up': '等级提升',
    'egg': '蛋招式',
    'tutor': '教学招式',
    'machine': '招式机',
    'stadium-surfing-pikachu': '特殊',
    'light-ball-egg': '特殊',
    'colosseum-purification': '特殊',
    'xd-shadow': '特殊',
    'xd-purification': '特殊',
    'form-change': '形态变化'
}


def create_types_table():
    """创建并填充 types 表"""
    print("\n" + "=" * 60)
    print("1. 创建 types 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS types')
    cursor.execute('''
        CREATE TABLE types (
            id INTEGER PRIMARY KEY,
            name_en TEXT NOT NULL UNIQUE,
            name_ja TEXT,
            name_zh TEXT
        )
    ''')

    print("✓ types 表结构创建成功")

    # 导入数据
    count = 0
    for filename in os.listdir(TYPE_DIR):
        if not filename.endswith('.json'):
            continue

        with open(TYPE_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        type_id = data['id']
        name_en = data['name']
        name_ja = name_zh = ""

        for name_entry in data.get('names', []):
            lang = name_entry['language']['name']
            if lang == 'ja':
                name_ja = name_entry['name']
            elif lang == 'zh-Hans' or lang == 'zh-hans':
                name_zh = name_entry['name']

        cursor.execute('''
            INSERT OR REPLACE INTO types (id, name_en, name_ja, name_zh)
            VALUES (?, ?, ?, ?)
        ''', (type_id, name_en, name_ja, name_zh))

        count += 1

    conn.commit()
    conn.close()
    print(f"✓ 已导入 {count} 个属性")


def create_type_effectiveness_table():
    """创建并填充属性克制表"""
    print("\n" + "=" * 60)
    print("2. 创建 type_effectiveness 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建表
    cursor.execute('DROP TABLE IF EXISTS type_effectiveness')
    cursor.execute('''
        CREATE TABLE type_effectiveness (
            attacker_type_id INTEGER NOT NULL,
            defender_type_id INTEGER NOT NULL,
            effectiveness REAL NOT NULL,
            PRIMARY KEY (attacker_type_id, defender_type_id),
            FOREIGN KEY (attacker_type_id) REFERENCES types(id),
            FOREIGN KEY (defender_type_id) REFERENCES types(id)
        )
    ''')

    cursor.execute('CREATE INDEX idx_type_eff_attacker ON type_effectiveness(attacker_type_id)')
    cursor.execute('CREATE INDEX idx_type_eff_defender ON type_effectiveness(defender_type_id)')
    print("✓ type_effectiveness 表结构创建成功")

    # 获取所有属性的 ID 映射
    cursor.execute('SELECT id, name_en FROM types ORDER BY id')
    types = cursor.fetchall()
    type_name_to_id = {name_en: type_id for type_id, name_en in types}
    all_type_ids = [type_id for type_id, _ in types]

    # 初始化克制关系矩阵（默认值为 1.0）
    effectiveness_matrix = {}
    for attacker_id in all_type_ids:
        for defender_id in all_type_ids:
            effectiveness_matrix[(attacker_id, defender_id)] = 1.0

    # 读取每个属性的 JSON 文件
    for filename in os.listdir(TYPE_DIR):
        if not filename.endswith('.json'):
            continue

        with open(TYPE_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        attacker_name = data['name']
        attacker_id = type_name_to_id.get(attacker_name)

        if not attacker_id:
            continue

        damage_relations = data.get('damage_relations', {})

        # 效果拔群 (2.0)
        for defender in damage_relations.get('double_damage_to', []):
            defender_id = type_name_to_id.get(defender['name'])
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 2.0

        # 效果不好 (0.5)
        for defender in damage_relations.get('half_damage_to', []):
            defender_id = type_name_to_id.get(defender['name'])
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 0.5

        # 无效 (0.0)
        for defender in damage_relations.get('no_damage_to', []):
            defender_id = type_name_to_id.get(defender['name'])
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 0.0

    # 插入数据
    data_to_insert = [
        (attacker_id, defender_id, effectiveness)
        for (attacker_id, defender_id), effectiveness in effectiveness_matrix.items()
    ]

    cursor.executemany('''
        INSERT INTO type_effectiveness (attacker_type_id, defender_type_id, effectiveness)
        VALUES (?, ?, ?)
    ''', data_to_insert)

    conn.commit()
    conn.close()
    print(f"✓ 已导入 {len(data_to_insert)} 条克制关系记录")


def create_abilities_table():
    """创建并填充 abilities 表"""
    print("\n" + "=" * 60)
    print("3. 创建 abilities 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS abilities')
    cursor.execute('''
        CREATE TABLE abilities (
            id INTEGER PRIMARY KEY,
            name_ja TEXT,
            name_zh TEXT,
            name_en TEXT,
            description_ja TEXT,
            description_zh TEXT,
            description_en TEXT,
            pokemon_list TEXT
        )
    ''')

    print("✓ abilities 表结构创建成功")

    # 导入数据
    count = 0
    for filename in os.listdir(ABILITY_DIR):
        if not filename.endswith('.json'):
            continue

        with open(ABILITY_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        ability_id = data['id']
        name_en = data['name']
        name_ja = name_zh = desc_ja = desc_zh = desc_en = ""

        for name_entry in data['names']:
            lang = name_entry['language']['name']
            if lang == 'ja':
                name_ja = name_entry['name']
            elif lang == 'zh-hans':
                name_zh = name_entry['name']

        ja_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'ja']
        zh_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'zh-hans']
        en_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'en']

        desc_ja = ja_flavors[-1] if ja_flavors else ""
        desc_zh = zh_flavors[-1] if zh_flavors else ""
        desc_en = en_flavors[-1] if en_flavors else ""

        pokemon_names = ','.join([p['pokemon']['name'] for p in data['pokemon']])

        cursor.execute('''
            INSERT OR REPLACE INTO abilities
            (id, name_ja, name_zh, name_en, description_ja, description_zh, description_en, pokemon_list)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ability_id, name_ja, name_zh, name_en, desc_ja, desc_zh, desc_en, pokemon_names))

        count += 1

    conn.commit()
    conn.close()
    print(f"✓ 已导入 {count} 个特性")


def create_moves_table():
    """创建并填充 moves 表"""
    print("\n" + "=" * 60)
    print("4. 创建 moves 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS moves')
    cursor.execute('''
        CREATE TABLE moves (
            id INTEGER PRIMARY KEY,
            name_ja TEXT,
            name_zh TEXT,
            name_en TEXT,
            type TEXT,
            type_id INTEGER,
            damage_class TEXT,
            power INTEGER,
            accuracy INTEGER,
            priority INTEGER,
            pp INTEGER,
            description_ja TEXT,
            description_zh TEXT,
            description_en TEXT,
            learned_by_pokemon TEXT,
            FOREIGN KEY (type_id) REFERENCES types(id)
        )
    ''')

    print("✓ moves 表结构创建成功")

    # 导入数据
    count = 0

    # 先获取所有 types 的映射
    cursor.execute('SELECT name_en, id FROM types')
    type_map = {row[0].lower(): row[1] for row in cursor.fetchall()}

    for filename in os.listdir(MOVES_DIR):
        if not filename.endswith('.json'):
            continue

        with open(MOVES_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        move_id = data['id']
        name_en = data['name']
        move_type = data['type']['name']
        damage_class = data['damage_class']['name']
        power = data['power']
        accuracy = data['accuracy']
        priority = data['priority']
        pp = data['pp']

        name_ja = name_zh = desc_ja = desc_zh = desc_en = ""

        for name_entry in data['names']:
            lang = name_entry['language']['name']
            if lang == 'ja':
                name_ja = name_entry['name']
            elif lang == 'zh-hans':
                name_zh = name_entry['name']

        ja_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'ja']
        zh_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'zh-hans']
        en_flavors = [f['flavor_text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'en']

        desc_ja = ja_flavors[-1] if ja_flavors else ""
        desc_zh = zh_flavors[-1] if zh_flavors else ""
        desc_en = en_flavors[-1] if en_flavors else ""

        pokemon_names = ','.join([p['name'] for p in data['learned_by_pokemon']])

        # 获取 type_id
        type_id = type_map.get(move_type.lower())

        cursor.execute('''
            INSERT OR REPLACE INTO moves
            (id, name_ja, name_zh, name_en, type, type_id, damage_class, power, accuracy, priority, pp, description_ja, description_zh, description_en, learned_by_pokemon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (move_id, name_ja, name_zh, name_en, move_type, type_id, damage_class, power, accuracy, priority, pp, desc_ja, desc_zh, desc_en, pokemon_names))

        count += 1

    conn.commit()
    conn.close()
    print(f"✓ 已导入 {count} 个招式")


def create_items_table():
    """创建并填充 items 表"""
    print("\n" + "=" * 60)
    print("5. 创建 items 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS items')
    cursor.execute('''
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            name_ja TEXT,
            name_zh TEXT,
            name_en TEXT,
            category TEXT,
            fling_power INTEGER,
            fling_effect TEXT,
            description_ja TEXT,
            description_zh TEXT,
            description_en TEXT,
            image_path TEXT
        )
    ''')

    print("✓ items 表结构创建成功")

    # 导入数据
    count = 0
    for filename in os.listdir(ITEMS_DIR):
        if not filename.endswith('.json'):
            continue

        with open(ITEMS_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        item_id = data['id']
        name_en = data['name']
        category = data['category']['name']
        fling_power = data['fling_power']
        fling_effect = data['fling_effect']['name'] if data['fling_effect'] else ""

        name_ja = name_zh = desc_ja = desc_zh = desc_en = ""

        for name_entry in data['names']:
            lang = name_entry['language']['name']
            if lang == 'ja':
                name_ja = name_entry['name']
            elif lang == 'zh-hans':
                name_zh = name_entry['name']

        ja_flavors = [f['text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'ja']
        zh_flavors = [f['text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'zh-hans']
        en_flavors = [f['text'] for f in data['flavor_text_entries'] if f['language']['name'] == 'en']

        desc_ja = ja_flavors[-1] if ja_flavors else ""
        desc_zh = zh_flavors[-1] if zh_flavors else ""
        desc_en = en_flavors[-1] if en_flavors else ""

        # 构建图片相对路径
        image_path = f"heldItemImage/{name_en}.png"

        cursor.execute('''
            INSERT OR REPLACE INTO items
            (id, name_ja, name_zh, name_en, category, fling_power, fling_effect, description_ja, description_zh, description_en, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (item_id, name_ja, name_zh, name_en, category, fling_power, fling_effect, desc_ja, desc_zh, desc_en, image_path))

        count += 1

    conn.commit()
    conn.close()
    print(f"✓ 已导入 {count} 个道具")


def create_pokemons_table():
    """创建 pokemons 表（需要从 Excel 导入）"""
    print("\n" + "=" * 60)
    print("6. 创建 pokemons 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS pokemons')
    cursor.execute('''
        CREATE TABLE pokemons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id INTEGER NOT NULL,
            pokeapi_id INTEGER NOT NULL,
            name_ja TEXT NOT NULL,
            name_zh TEXT NOT NULL,
            name_en TEXT NOT NULL,
            is_default_form BOOLEAN NOT NULL,
            type1 TEXT NOT NULL,
            type2 TEXT,
            type1_id INTEGER,
            type2_id INTEGER,
            image_official_artwork TEXT,
            ability1_id INTEGER,
            ability1_name TEXT,
            ability2_id INTEGER,
            ability2_name TEXT,
            hidden_ability_id INTEGER,
            hidden_ability_name TEXT,
            weight_kg REAL,
            hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            sp_attack INTEGER NOT NULL,
            sp_defense INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            total_stats INTEGER NOT NULL,
            description_ja TEXT,
            description_en TEXT,
            description_zh TEXT,
            FOREIGN KEY (type1_id) REFERENCES types(id),
            FOREIGN KEY (type2_id) REFERENCES types(id),
            FOREIGN KEY (ability1_id) REFERENCES abilities(id),
            FOREIGN KEY (ability2_id) REFERENCES abilities(id),
            FOREIGN KEY (hidden_ability_id) REFERENCES abilities(id)
        )
    ''')

    cursor.execute('CREATE INDEX idx_pokemons_pokedex ON pokemons(pokedex_id)')
    cursor.execute('CREATE INDEX idx_pokemons_name_en ON pokemons(name_en)')
    cursor.execute('CREATE INDEX idx_pokemons_type1_id ON pokemons(type1_id)')
    cursor.execute('CREATE INDEX idx_pokemons_type2_id ON pokemons(type2_id)')
    cursor.execute('CREATE INDEX idx_pokemons_ability1 ON pokemons(ability1_id)')
    cursor.execute('CREATE INDEX idx_pokemons_ability2 ON pokemons(ability2_id)')
    cursor.execute('CREATE INDEX idx_pokemons_hidden_ability ON pokemons(hidden_ability_id)')

    conn.commit()
    conn.close()

    print("✓ pokemons 表结构创建成功")
    print("⚠ 注意：需要手动从 pokemon.xlsx 导入数据")
    print("  请参考 README.md 中的步骤 4")


def create_pokemon_moves_table():
    """创建并填充 pokemon_moves 表"""
    print("\n" + "=" * 60)
    print("7. 创建 pokemon_moves 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS pokemon_moves')
    cursor.execute('''
        CREATE TABLE pokemon_moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id INTEGER NOT NULL,
            pokeapi_id INTEGER NOT NULL,
            pokemon_name_zh TEXT,
            pokemon_name_ja TEXT,
            pokemon_name_en TEXT NOT NULL,
            move_id INTEGER NOT NULL,
            move_name_zh TEXT,
            move_name_en TEXT NOT NULL,
            move_name_ja TEXT,
            learn_method TEXT NOT NULL,
            level INTEGER,
            version_group TEXT NOT NULL,
            generation INTEGER NOT NULL,
            FOREIGN KEY (pokedex_id) REFERENCES pokemons(pokedex_id),
            FOREIGN KEY (move_id) REFERENCES moves(id)
        )
    ''')

    cursor.execute('CREATE INDEX idx_pokemon_moves_pokedex ON pokemon_moves(pokedex_id)')
    cursor.execute('CREATE INDEX idx_pokemon_moves_move ON pokemon_moves(move_id)')
    cursor.execute('CREATE INDEX idx_pokemon_moves_generation ON pokemon_moves(generation)')

    conn.commit()
    print("✓ pokemon_moves 表结构创建成功")

    # 检查 pokemons 表是否有数据
    cursor.execute('SELECT COUNT(*) FROM pokemons')
    pokemon_count = cursor.fetchone()[0]

    if pokemon_count == 0:
        print("⚠ pokemons 表为空，跳过 pokemon_moves 数据导入")
        print("  请先导入 pokemons 数据后再运行此脚本")
        conn.close()
        return

    print(f"✓ 检测到 {pokemon_count} 个宝可梦，开始导入招式数据...")

    # 导入数据
    def get_pokemon_info(pokemon_en_name):
        cursor.execute('''
            SELECT pokedex_id, name_zh, name_ja, name_en
            FROM pokemons
            WHERE LOWER(name_en) = LOWER(?)
            LIMIT 1
        ''', (pokemon_en_name,))
        result = cursor.fetchone()
        return result if result else (None, None, None, pokemon_en_name)

    def get_move_info(move_en_name):
        cursor.execute('''
            SELECT id, name_zh, name_en, name_ja
            FROM moves
            WHERE LOWER(REPLACE(name_en, ' ', '-')) = LOWER(?)
               OR LOWER(name_en) = LOWER(?)
            LIMIT 1
        ''', (move_en_name, move_en_name.replace('-', ' ')))
        result = cursor.fetchone()
        return result if result else (None, None, move_en_name, None)

    def extract_move_id_from_url(url):
        return int(url.rstrip('/').split('/')[-1])

    json_files = [f for f in os.listdir(POKEMON_DIR)
                  if f.endswith('.json') and not f.endswith('_species.json')]

    total_moves = 0
    processed = 0

    for json_file in json_files:
        json_path = POKEMON_DIR / json_file

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            pokemon_en_name = data['name']
            pokeapi_id = data['id']

            pokedex_id, pokemon_zh, pokemon_ja, pokemon_en = get_pokemon_info(pokemon_en_name)

            if not pokedex_id:
                pokedex_id = pokeapi_id

            moves_data = []

            for move_entry in data.get('moves', []):
                move_name_en = move_entry['move']['name']
                move_url = move_entry['move']['url']
                move_api_id = extract_move_id_from_url(move_url)

                move_id, move_zh, move_en, move_ja = get_move_info(move_name_en)

                if not move_id:
                    move_id = move_api_id

                for detail in move_entry['version_group_details']:
                    version_group = detail['version_group']['name']
                    generation = VERSION_GROUP_TO_GENERATION.get(version_group, 0)

                    if generation == 0:
                        continue

                    learn_method_en = detail['move_learn_method']['name']
                    learn_method = LEARN_METHOD_MAP.get(learn_method_en, learn_method_en)
                    level = detail['level_learned_at'] if detail['level_learned_at'] > 0 else None

                    moves_data.append((
                        pokedex_id, pokeapi_id, pokemon_zh, pokemon_ja, pokemon_en,
                        move_id, move_zh, move_en, move_ja,
                        learn_method, level, version_group, generation
                    ))

            if moves_data:
                cursor.executemany('''
                    INSERT INTO pokemon_moves (
                        pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_ja, pokemon_name_en,
                        move_id, move_name_zh, move_name_en, move_name_ja,
                        learn_method, level, version_group, generation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', moves_data)

                total_moves += len(moves_data)
                processed += 1

                if processed % 50 == 0:
                    print(f"  已处理 {processed}/{len(json_files)} 个宝可梦...")
                    conn.commit()

        except Exception as e:
            print(f"  ✗ 处理 {json_file} 时出错: {e}")
            continue

    conn.commit()
    conn.close()

    print(f"✓ 已处理 {processed} 个宝可梦，插入 {total_moves:,} 条招式学习记录")


def main():
    print("=" * 60)
    print("宝可梦数据库生成脚本")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")

    # 步骤 1: 创建 types 表
    create_types_table()

    # 步骤 2: 创建 type_effectiveness 表
    create_type_effectiveness_table()

    # 步骤 3-5: 创建基础表（abilities, moves, items）
    create_abilities_table()
    create_moves_table()
    create_items_table()

    # 步骤 6: 创建 pokemons 表结构（需要手动导入数据）
    create_pokemons_table()

    # 步骤 7: 创建 pokemon_moves 表（依赖 pokemons 表）
    create_pokemon_moves_table()

    print("\n" + "=" * 60)
    print("数据库生成完成！")
    print("=" * 60)
    print(f"数据库文件: {DB_PATH}")
    print("\n如果 pokemons 表为空，请按照 README.md 的步骤导入数据")


if __name__ == '__main__':
    main()
