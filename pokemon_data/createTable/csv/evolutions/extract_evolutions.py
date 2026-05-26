#!/usr/bin/env python3
"""
从 52poke Wiki wikitext 提取进化关系，生成 evolutions.csv

数据源：pokemon_data/wiki/wiki_meta.db + wikitext_cache/
输出：evolutions.csv

evotype 枚举值：
- Level: 升级进化（需 level）
- Stone: 石头进化（需 stone）
- Happiness: 亲密度进化
- Trade: 交换进化
- Item: 道具进化（需 item）
- Move: 学会招式进化（需 move）
- Location: 地点进化（需 location）
- Held: 携带道具进化（需 hold）
- Affection: 好感度进化
- Beautiful: 美丽度进化
- Damage: 受伤进化
- Letsgo: Let's Go 游戏特殊
- Movetimes: 使用招式次数
- Pokémon: 与特定宝可梦相关
- Spin: 旋转进化
- Other: 其他
"""

import sqlite3
import re
import csv
import json
import os
import sys

# 路径配置
WIKI_DB = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'wiki', 'wiki_meta.db')
POKEMON_DB = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'pokemonData.db')
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), 'evolutions.csv')

# evotype 到 method 的映射
EVOTYPE_TO_METHOD = {
    'Level': 'level-up',
    'Stone': 'use-item',
    'Happiness': 'level-up-friendship',
    'Trade': 'trade',
    'Item': 'use-item',
    'Move': 'level-up-move',
    'Location': 'level-up-location',
    'Held': 'level-up-hold-item',
    'Affection': 'level-up-affection',
    'Beautiful': 'level-up-beautiful',
    'Damage': 'other',
    'Letsgo': 'other',
    'Movetimes': 'other',
    'Pokémon': 'other',
    'Spin': 'other',
    'Other': 'other',
    'None': None,  # 无进化
}

# 进化石名称到英文的映射
STONE_MAP = {
    '火之石': 'fire-stone',
    '水之石': 'water-stone',
    '雷之石': 'thunder-stone',
    '叶之石': 'leaf-stone',
    '月之石': 'moon-stone',
    '太阳之石': 'sun-stone',
    '光之石': 'shiny-stone',
    '暗之石': 'dusk-stone',
    '觉醒之石': 'dawn-stone',
    '冰之石': 'ice-stone',
}


def load_pokemon_name_map(db_path):
    """加载中文名 → pokemons.id 映射"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, name_zh, name_en FROM pokemons WHERE name_zh IS NOT NULL AND name_zh != ""')
    name_map = {}
    for row in cur.fetchall():
        pid, name_zh, name_en = row
        name_map[name_zh] = pid
        # 也用英文名映射（小写）
        if name_en:
            name_map[name_en.lower()] = pid
    conn.close()
    return name_map


def load_item_name_map(db_path):
    """加载道具中文名 → items.id 映射"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, name_zh, name_en FROM items WHERE name_zh IS NOT NULL AND name_zh != ""')
    name_map = {}
    for row in cur.fetchall():
        iid, name_zh, name_en = row
        name_map[name_zh] = iid
        if name_en:
            name_map[name_en.lower()] = iid
    conn.close()
    return name_map


def parse_evolution_box(template_text):
    """
    解析 {{进化框}} 模板，提取进化关系

    返回：[(name1, name2, evotype, level, stone, condition), ...]
    """
    relations = []

    # 提取所有 name 和 evotype
    names = {}
    evotypes = {}
    levels = {}
    stones = {}
    times = {}
    locations = {}
    moves = {}
    holds = {}

    # 支持两种格式：
    # 1. |name1=xxx（带数字索引）
    # 2. |item=xxx（不带数字索引，默认为1）
    for match in re.finditer(r'\|(\w+?)(\d*)=([^\|}]+)', template_text):
        field = match.group(1)
        index = match.group(2) if match.group(2) else '1'  # 默认索引为1
        value = match.group(3).strip()

        if field == 'name':
            names[index] = value
        elif field == 'evotype':
            evotypes[index] = value
        elif field == 'level':
            levels[index] = value
        elif field in ('evostone', 'item'):
            # 支持 evostone 和 item 两种字段名
            stones[index] = value
        elif field == 'time':
            times[index] = value
        elif field == 'location':
            locations[index] = value
        elif field == 'move':
            moves[index] = value
        elif field == 'hold':
            holds[index] = value

    # 构建进化关系（1→2, 2→3）
    # 注意：evotype(i) 表示从 i 进化到 i+1 的方式
    for i in range(1, 10):
        i_str = str(i)
        next_i_str = str(i + 1)

        if i_str in names and next_i_str in names:
            from_name = names[i_str]
            to_name = names[next_i_str]
            # 用当前 i 的 evotype，而不是 next_i 的
            evotype = evotypes.get(i_str, 'None')

            if evotype == 'None':
                continue

            # 构建 condition
            condition = {}
            if i_str in times:
                condition['time'] = times[i_str]
            if i_str in locations:
                condition['location'] = locations[i_str]
            if i_str in moves:
                condition['move'] = moves[i_str]
            if i_str in holds:
                condition['hold'] = holds[i_str]

            relations.append({
                'from_name': from_name,
                'to_name': to_name,
                'evotype': evotype,
                'level': levels.get(i_str),
                'stone': stones.get(i_str),
                'condition': condition if condition else None,
            })

    return relations


def parse_eevee_evolution(template_text):
    """
    解析 {{进化框/伊布}} 特殊模板

    伊布有 8 种进化，需要特殊处理
    """
    # 伊布的进化框是嵌入的模板，内容在别处
    # 这里返回 None，需要特殊处理
    return None


def parse_form_evolution(template_text, base_name):
    """
    解析 {{进化框/形态}} 模板，提取 Mega 和超极巨进化

    返回：[{'from_name', 'to_name', 'is_mega', 'is_gmax', 'stone'}, ...]
    """
    relations = []

    # 提取字段
    fields = {}
    for match in re.finditer(r'\|(\w+?)(\d*)=([^\|}]+)', template_text):
        field = match.group(1)
        index = match.group(2) if match.group(2) else '1'
        value = match.group(3).strip()
        key = f'{field}{index}'
        fields[key] = value

    # 检查位置1的形态（Mega X/Y 等）
    forme1 = fields.get('forme1', '')
    sprite1 = fields.get('sprite1', '')

    # 检查位置2的形态（Mega 或超极巨）
    forme2 = fields.get('forme2', '')
    sprite2 = fields.get('sprite2', '')

    # 识别 Mega（位置1）
    if '超级' in forme1 or '-Mega' in sprite1:
        # 生成正确的中文名：基础名（超级进化）或 基础名（超级进化X/Y）
        if 'Ｘ' in forme1 or 'X' in forme1:
            to_name = f'{base_name}（超级进化X）'
        elif 'Ｙ' in forme1 or 'Y' in forme1:
            to_name = f'{base_name}（超级进化Y）'
        else:
            to_name = f'{base_name}（超级进化）'
        relations.append({
            'from_name': base_name,
            'to_name': to_name,
            'is_mega': 1,
            'is_gmax': 0,
            'stone': None,
        })

    # 识别 Mega（位置2）
    if '超级' in forme2 or '-Mega' in sprite2:
        if 'Ｘ' in forme2 or 'X' in forme2:
            to_name = f'{base_name}（超级进化X）'
        elif 'Ｙ' in forme2 or 'Y' in forme2:
            to_name = f'{base_name}（超级进化Y）'
        else:
            to_name = f'{base_name}（超级进化）'
        relations.append({
            'from_name': base_name,
            'to_name': to_name,
            'is_mega': 1,
            'is_gmax': 0,
            'stone': None,
        })

    # 识别超极巨（位置2）
    if '超极巨' in forme2 or 'Gigantamax' in forme2 or '-Gigantamax' in sprite2:
        to_name = f'{base_name}（超极巨化）'
        relations.append({
            'from_name': base_name,
            'to_name': to_name,
            'is_mega': 0,
            'is_gmax': 1,
            'stone': None,
        })

    return relations


def extract_from_wikitext(content, pokemon_name):
    """从 wikitext 内容中提取进化关系"""
    relations = []

    # 找所有 {{进化框}} 模板（标准进化）
    pattern = r'\{\{进化框\s*\n(.*?)\}\}'
    matches = re.findall(pattern, content, re.DOTALL)

    for match in matches:
        template_text = '{{进化框\n' + match + '}}'
        parsed = parse_evolution_box(template_text)
        relations.extend(parsed)

    # 找所有 {{进化框/形态}} 模板（Mega/超极巨）
    pattern_form = r'\{\{进化框/形态\s*\n?(.*?)\}\}'
    matches_form = re.findall(pattern_form, content, re.DOTALL)

    for match in matches_form:
        template_text = '{{进化框/形态\n' + match + '}}'
        parsed = parse_form_evolution(template_text, pokemon_name)
        relations.extend(parsed)

    # 特殊处理伊布
    if '伊布' in pokemon_name or pokemon_name == 'eevee':
        # 伊布的进化在模板 {{进化框/伊布}} 中，需要单独处理
        pass

    return relations


def main():
    print('=== 提取进化关系 ===')

    # 加载名称映射
    print('加载宝可梦名称映射...')
    pokemon_map = load_pokemon_name_map(POKEMON_DB)
    print(f'  加载 {len(pokemon_map)} 条映射')

    print('加载道具名称映射...')
    item_map = load_item_name_map(POKEMON_DB)
    print(f'  加载 {len(item_map)} 条映射')

    # 连接 wiki 数据库
    conn = sqlite3.connect(WIKI_DB)
    cur = conn.cursor()

    # 获取所有宝可梦页面（namespace=0，且标题在 pokemon_map 中）
    cur.execute('SELECT page_id, title, file_path FROM wiki_pages WHERE namespace = 0 AND status = "done"')
    all_pages = cur.fetchall()
    print(f'共 {len(all_pages)} 个页面')

    # 提取进化关系
    all_relations = []
    matched_count = 0

    for page_id, title, file_path in all_pages:
        # 检查是否是宝可梦页面
        if title not in pokemon_map:
            continue

        matched_count += 1

        # 读取 wikitext
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f'读取失败 {file_path}: {e}')
            continue

        # 提取进化关系
        relations = extract_from_wikitext(content, title)

        for rel in relations:
            rel['from_pokemon_id'] = pokemon_map.get(rel['from_name'])
            rel['to_pokemon_id'] = pokemon_map.get(rel['to_name'])

            # 如果找不到 ID，跳过
            if not rel['from_pokemon_id'] or not rel['to_pokemon_id']:
                print(f'  警告: 无法映射 {rel["from_name"]} 或 {rel["to_name"]}')
                continue

            all_relations.append(rel)

    conn.close()

    print(f'\n匹配到 {matched_count} 个宝可梦页面')
    print(f'提取到 {len(all_relations)} 条进化关系')

    # 去重
    unique_relations = []
    seen = set()
    for rel in all_relations:
        # 对于 Mega/超极巨，使用 is_mega/is_gmax 作为 key 的一部分
        is_mega = rel.get('is_mega', 0)
        is_gmax = rel.get('is_gmax', 0)
        evotype = rel.get('evotype', 'mega' if is_mega else 'gmax' if is_gmax else 'other')
        key = (rel['from_pokemon_id'], rel['to_pokemon_id'], evotype, is_mega, is_gmax)
        if key not in seen:
            seen.add(key)
            unique_relations.append(rel)

    print(f'去重后 {len(unique_relations)} 条')

    # 写入 CSV
    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'from_pokemon_id', 'to_pokemon_id', 'method',
            'level', 'item_id', 'condition', 'is_mega', 'is_gmax'
        ])

        for rel in unique_relations:
            # 确定 is_mega 和 is_gmax（从字典中读取，默认为 0）
            is_mega = rel.get('is_mega', 0)
            is_gmax = rel.get('is_gmax', 0)

            # 确定 method
            if is_mega:
                method = 'mega'
            elif is_gmax:
                method = 'gmax'
            else:
                method = EVOTYPE_TO_METHOD.get(rel.get('evotype', 'other'), 'other')

            # 确定 item_id
            item_id = None
            if rel.get('evotype') in ('Stone', 'Item') and rel.get('stone'):
                stone_name = rel['stone'].strip()
                # 移除可能的换行符和空格
                stone_name = stone_name.replace('\n', '').replace('\r', '').strip()
                item_id = item_map.get(stone_name)

            # 写入行
            writer.writerow([
                rel['from_pokemon_id'],
                rel['to_pokemon_id'],
                method,
                rel.get('level'),
                item_id,
                json.dumps(rel.get('condition'), ensure_ascii=False) if rel.get('condition') else None,
                is_mega,
                is_gmax,
            ])

    print(f'\n已写入 {OUTPUT_CSV}')


if __name__ == '__main__':
    main()
