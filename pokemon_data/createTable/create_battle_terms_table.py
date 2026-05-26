#!/usr/bin/env python3
"""
创建 battle_terms 表并分批插入对战术语数据
用于将中文对战术语映射到数据库字段、公式、道具等
"""

import sqlite3
import sys
import io
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置路径
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"


def create_battle_terms_table():
    """创建 battle_terms 表"""
    print("\n" + "=" * 60)
    print("创建 battle_terms 表")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS battle_terms')
    cursor.execute('''
        CREATE TABLE battle_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            aliases TEXT,
            category TEXT NOT NULL,
            definition TEXT,
            formula TEXT,
            related_field TEXT,
            related_value TEXT,
            language TEXT DEFAULT 'zh'
        )
    ''')

    cursor.execute('CREATE INDEX idx_battle_terms_term ON battle_terms(term)')
    cursor.execute('CREATE INDEX idx_battle_terms_category ON battle_terms(category)')

    conn.commit()
    conn.close()
    print("✓ battle_terms 表结构创建成功")


def insert_stat_spread():
    """插入 stat_spread（能力值配置术语）分类数据"""
    print("\n" + "=" * 60)
    print("插入 stat_spread 分类数据")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    data = [
        ('极速', '满速,最速', 'stat_spread',
         '速度IV31+EV252+加速性格(×1.1)',
         'floor((floor((base×2+31+63)×50/100)+5)×1.1)',
         'speed', None),
        ('满攻', '极攻', 'stat_spread',
         '攻击IV31+EV252',
         None, 'attack', None),
        ('满特攻', '极特攻', 'stat_spread',
         '特攻IV31+EV252',
         None, 'sp_attack', None),
        ('耐久', 'bulk', 'stat_spread',
         'HP+防御或特防的综合能力',
         None, 'hp,defense,sp_defense', None),
        ('物耐', '物理耐久', 'stat_spread',
         'HP×防御的乘积，衡量物理承受力',
         'HP实数值×防御实数值', 'hp,defense', None),
        ('特耐', '特殊耐久', 'stat_spread',
         'HP×特防的乘积，衡量特殊承受力',
         'HP实数值×特防实数值', 'hp,sp_defense', None),
        ('双攻', '混合攻击', 'stat_spread',
         '攻击和特攻都高',
         None, 'attack,sp_attack', None),
        ('无补正极速', '准速', 'stat_spread',
         '速度IV31+EV252但性格不加速(×1.0)',
         'floor((base×2+31+63)×50/100)+5',
         'speed', None),
    ]

    cursor.executemany('''
        INSERT INTO battle_terms (term, aliases, category, definition, formula, related_field, related_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', data)

    conn.commit()
    conn.close()
    print(f"✓ 已插入 {len(data)} 条 stat_spread 术语")


def main():
    print("=" * 60)
    print("宝可梦对战术语表生成脚本")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")

    # 步骤 1: 创建表
    create_battle_terms_table()

    # 步骤 2: 插入 stat_spread 数据
    insert_stat_spread()

    # 验证
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM battle_terms')
    count = cursor.fetchone()[0]
    cursor.execute('SELECT term, aliases, definition FROM battle_terms')
    rows = cursor.fetchall()
    conn.close()

    print(f"\n✓ battle_terms 表当前共 {count} 条记录：")
    for term, aliases, definition in rows:
        print(f"  {term} ({aliases}) - {definition}")

    print("\n" + "=" * 60)
    print("完成！后续分类可追加到此脚本中执行")
    print("=" * 60)


if __name__ == '__main__':
    main()
