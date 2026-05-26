#!/usr/bin/env python3
"""
创建属性克制表
从 type 目录读取属性信息，生成 19x19 的属性克制表
表结构: type_effectiveness (attacker_type_id, defender_type_id, effectiveness)
- effectiveness: 0 (无效), 0.5 (效果不好), 1 (正常), 2 (效果拔群)
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
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # pokemon_data/
DB_PATH = BASE_DIR / "pokemonData.db"
TYPE_DIR = BASE_DIR / "type"


def create_type_effectiveness_table():
    """创建属性克制表"""
    print("=" * 60)
    print("创建属性克制表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建 type_effectiveness 表
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

    print("✓ type_effectiveness 表结构创建成功")

    # 创建索引
    cursor.execute('CREATE INDEX idx_type_eff_attacker ON type_effectiveness(attacker_type_id)')
    cursor.execute('CREATE INDEX idx_type_eff_defender ON type_effectiveness(defender_type_id)')
    print("✓ 索引创建成功")

    return conn, cursor


def load_type_effectiveness_data(cursor):
    """从 JSON 文件加载属性克制数据"""
    print("\n" + "=" * 60)
    print("加载属性克制数据")
    print("=" * 60)

    # 获取所有属性的 ID 映射
    cursor.execute('SELECT id, name_en FROM types ORDER BY id')
    types = cursor.fetchall()
    type_name_to_id = {name_en: type_id for type_id, name_en in types}
    all_type_ids = [type_id for type_id, _ in types]

    print(f"✓ 加载了 {len(types)} 个属性")

    # 初始化克制关系矩阵（默认值为 1.0，表示正常伤害）
    effectiveness_matrix = {}
    for attacker_id in all_type_ids:
        for defender_id in all_type_ids:
            effectiveness_matrix[(attacker_id, defender_id)] = 1.0

    # 读取每个属性的 JSON 文件
    processed_count = 0
    for filename in os.listdir(TYPE_DIR):
        if not filename.endswith('.json'):
            continue

        with open(TYPE_DIR / filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        attacker_name = data['name']
        attacker_id = type_name_to_id.get(attacker_name)

        if not attacker_id:
            print(f"⚠ 跳过未知属性: {attacker_name}")
            continue

        damage_relations = data.get('damage_relations', {})

        # 处理效果拔群 (double_damage_to)
        for defender in damage_relations.get('double_damage_to', []):
            defender_name = defender['name']
            defender_id = type_name_to_id.get(defender_name)
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 2.0

        # 处理效果不好 (half_damage_to)
        for defender in damage_relations.get('half_damage_to', []):
            defender_name = defender['name']
            defender_id = type_name_to_id.get(defender_name)
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 0.5

        # 处理无效 (no_damage_to)
        for defender in damage_relations.get('no_damage_to', []):
            defender_name = defender['name']
            defender_id = type_name_to_id.get(defender_name)
            if defender_id:
                effectiveness_matrix[(attacker_id, defender_id)] = 0.0

        processed_count += 1

    print(f"✓ 处理了 {processed_count} 个属性的克制关系")

    return effectiveness_matrix, type_name_to_id


def insert_effectiveness_data(cursor, effectiveness_matrix):
    """将克制关系数据插入数据库"""
    print("\n" + "=" * 60)
    print("插入克制关系数据")
    print("=" * 60)

    data_to_insert = [
        (attacker_id, defender_id, effectiveness)
        for (attacker_id, defender_id), effectiveness in effectiveness_matrix.items()
    ]

    cursor.executemany('''
        INSERT INTO type_effectiveness (attacker_type_id, defender_type_id, effectiveness)
        VALUES (?, ?, ?)
    ''', data_to_insert)

    print(f"✓ 已插入 {len(data_to_insert)} 条克制关系记录")


def verify_data(cursor, type_name_to_id):
    """验证数据"""
    print("\n" + "=" * 60)
    print("数据验证")
    print("=" * 60)

    # 统计各种效果的数量
    cursor.execute('SELECT COUNT(*) FROM type_effectiveness WHERE effectiveness = 0')
    no_effect_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM type_effectiveness WHERE effectiveness = 0.5')
    not_very_effective_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM type_effectiveness WHERE effectiveness = 1.0')
    normal_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM type_effectiveness WHERE effectiveness = 2.0')
    super_effective_count = cursor.fetchone()[0]

    print(f"✓ 无效 (0): {no_effect_count} 条")
    print(f"✓ 效果不好 (0.5): {not_very_effective_count} 条")
    print(f"✓ 正常 (1.0): {normal_count} 条")
    print(f"✓ 效果拔群 (2.0): {super_effective_count} 条")
    print(f"✓ 总计: {no_effect_count + not_very_effective_count + normal_count + super_effective_count} 条")

    # 显示示例：火属性对其他属性的克制关系
    fire_id = type_name_to_id.get('fire')
    if fire_id:
        print(f"\n示例：火属性的克制关系")
        cursor.execute('''
            SELECT t.name_zh, t.name_en, te.effectiveness
            FROM type_effectiveness te
            JOIN types t ON te.defender_type_id = t.id
            WHERE te.attacker_type_id = ?
            ORDER BY te.effectiveness DESC, t.id
        ''', (fire_id,))

        for row in cursor.fetchall():
            eff_text = {0: "无效", 0.5: "效果不好", 1.0: "正常", 2.0: "效果拔群"}.get(row[2], str(row[2]))
            print(f"  火 → {row[0]} ({row[1]}): {eff_text}")


def main():
    print("=" * 60)
    print("宝可梦属性克制表创建脚本")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"属性数据目录: {TYPE_DIR}\n")

    # 检查 type 目录是否存在
    if not TYPE_DIR.exists():
        print(f"❌ 错误: 属性数据目录不存在: {TYPE_DIR}")
        print("请先运行 download/download_types_json.py 下载属性数据")
        return

    # 检查数据库是否存在
    if not DB_PATH.exists():
        print(f"❌ 错误: 数据库文件不存在: {DB_PATH}")
        print("请先运行 create_all_tables.py 创建数据库")
        return

    # 步骤 1: 创建表
    conn, cursor = create_type_effectiveness_table()

    # 步骤 2: 加载数据
    effectiveness_matrix, type_name_to_id = load_type_effectiveness_data(cursor)

    # 步骤 3: 插入数据
    insert_effectiveness_data(cursor, effectiveness_matrix)

    # 提交更改
    conn.commit()

    # 步骤 4: 验证数据
    verify_data(cursor, type_name_to_id)

    conn.close()

    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)
    print(f"数据库文件: {DB_PATH}")
    print("\n说明:")
    print("- 表名: type_effectiveness")
    print("- 字段: attacker_type_id, defender_type_id, effectiveness")
    print("- effectiveness 值: 0 (无效), 0.5 (效果不好), 1 (正常), 2 (效果拔群)")


if __name__ == '__main__':
    main()
