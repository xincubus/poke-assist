#!/usr/bin/env python3
"""
更新 pokemons 表，添加 image_official_artwork 列并填充图片路径
用于已有数据库的升级
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
BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"
IMAGE_DIR = BASE_DIR / "pokemonImage"
POKEMON_JSON_DIR = BASE_DIR / "pokemon"


def build_pokemon_name_map():
    """构建 pokeapi_id 到名称的映射表"""
    print("构建宝可梦名称映射表...")
    name_map = {}

    for filename in os.listdir(POKEMON_JSON_DIR):
        if not filename.endswith('.json') or filename.endswith('_species.json'):
            continue

        json_path = POKEMON_JSON_DIR / filename
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            pokeapi_id = data.get('id')
            pokemon_name = data.get('name')
            if pokeapi_id and pokemon_name:
                name_map[pokeapi_id] = pokemon_name
        except Exception:
            continue

    print(f"✓ 已加载 {len(name_map)} 个宝可梦名称")
    return name_map


def update_pokemons_image_path():
    """更新 pokemons 表，添加 image_official_artwork 列并填充数据"""
    print("=" * 60)
    print("更新 pokemons 表 - 添加官方插图路径")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"图片目录: {IMAGE_DIR}")
    print(f"JSON 目录: {POKEMON_JSON_DIR}\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查 image_official_artwork 列是否已存在
    cursor.execute('PRAGMA table_info(pokemons)')
    columns = [row[1] for row in cursor.fetchall()]

    if 'image_official_artwork' not in columns:
        print("添加 image_official_artwork 列...")
        cursor.execute('ALTER TABLE pokemons ADD COLUMN image_official_artwork TEXT')
        print("✓ image_official_artwork 列已添加")
    else:
        print("⚠ image_official_artwork 列已存在，将更新现有数据")

    # 获取所有 pokemons 的 pokeapi_id
    cursor.execute('SELECT id, pokeapi_id FROM pokemons')
    pokemons = cursor.fetchall()

    # 构建名称映射表
    name_map = build_pokemon_name_map()

    print(f"\n开始更新 {len(pokemons)} 个宝可梦的图片路径...")

    updated_count = 0
    missing_count = 0

    for pk_id, pokeapi_id in pokemons:
        # 从映射表中获取原始名称（包含形态后缀）
        pokemon_name = name_map.get(pokeapi_id)

        if not pokemon_name:
            missing_count += 1
            cursor.execute('UPDATE pokemons SET image_official_artwork = NULL WHERE id = ?', (pk_id,))
            continue

        # 构建图片文件名：{pokeapi_id:03d}-{pokemon_name}-officialArtwork.png
        # 注意：ID 小于 1000 时用 3 位数字格式化，大于等于 1000 时直接使用
        if pokeapi_id < 1000:
            image_filename = f"{pokeapi_id:03d}-{pokemon_name}-officialArtwork.png"
        else:
            image_filename = f"{pokeapi_id}-{pokemon_name}-officialArtwork.png"

        image_path = f"pokemonImage/{image_filename}"
        full_image_path = IMAGE_DIR / image_filename

        # 检查图片文件是否存在
        if full_image_path.exists():
            cursor.execute('UPDATE pokemons SET image_official_artwork = ? WHERE id = ?', (image_path, pk_id))
            updated_count += 1
        else:
            # 图片不存在，设置为 NULL
            cursor.execute('UPDATE pokemons SET image_official_artwork = NULL WHERE id = ?', (pk_id,))
            missing_count += 1
            if missing_count <= 10:  # 只显示前 10 个缺失的
                print(f"  ⚠ 图片不存在: {image_filename}")

    if missing_count > 10:
        print(f"  ... 还有 {missing_count - 10} 个图片文件不存在")

    conn.commit()

    print(f"\n✓ 已更新 {updated_count} 个宝可梦的图片路径")
    if missing_count > 0:
        print(f"⚠ {missing_count} 个宝可梦的图片文件不存在")

    # 验证数据
    print("\n验证数据（前 5 条）:")
    cursor.execute('''
        SELECT name_zh, name_en, pokeapi_id, image_official_artwork
        FROM pokemons
        WHERE image_official_artwork IS NOT NULL
        LIMIT 5
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]} ({row[1]}, ID:{row[2]}): {row[3]}")

    # 验证妙蛙花的所有形态
    print("\n验证妙蛙花的所有形态:")
    cursor.execute('''
        SELECT name_zh, pokeapi_id, image_official_artwork
        FROM pokemons
        WHERE pokedex_id = 3
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]} (ID:{row[1]}): {row[2]}")

    conn.close()

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == '__main__':
    update_pokemons_image_path()

