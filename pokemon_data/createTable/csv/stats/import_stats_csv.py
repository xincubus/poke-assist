#!/usr/bin/env python3
"""
从 stats.csv 导入能力数据到 pokemonData.db 的 stats 表

用法：python import_stats_csv.py
默认读取 pokemon_data/stat/stats.csv
"""

import csv
import sqlite3
import sys
import io
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent.parent.parent  # pokemon_data/
DB_PATH = BASE_DIR / "pokemonData.db"
CSV_PATH = Path(__file__).parent / "stats.csv"  # csv/stats/stats.csv


def main():
    print("=" * 60)
    print("从 CSV 导入 stats（能力）表")
    print("=" * 60)
    print(f"CSV 文件: {CSV_PATH}")
    print(f"数据库: {DB_PATH}\n")

    if not CSV_PATH.exists():
        print(f"✗ CSV 文件不存在: {CSV_PATH}")
        print("  请先运行 extract_stats_to_csv.py 生成 CSV 并手动修正")
        sys.exit(1)

    # 读取 CSV（自动检测编码）
    raw = open(CSV_PATH, 'rb').read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
        try:
            text = raw.decode(enc)
            print(f"使用编码: {enc}")
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        print("✗ 无法识别 CSV 文件编码")
        sys.exit(1)
    reader = csv.DictReader(io.StringIO(text), delimiter=',')
    rows = list(reader)

    if not rows:
        print("✗ CSV 文件为空")
        sys.exit(1)

    print(f"读取到 {len(rows)} 条记录")

    # 创建表
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS stats')
    cursor.execute('''
        CREATE TABLE stats (
            id INTEGER PRIMARY KEY,
            name_en TEXT NOT NULL,
            name_zh TEXT NOT NULL,
            abbr_zh TEXT,
            abbr_ja TEXT,
            abbr_en TEXT,
            name_ja TEXT,
            description_zh TEXT,
            description_en TEXT,
            description_ja TEXT
        )
    ''')
    print("✓ stats 表结构创建成功\n")

    # 插入数据
    for row in rows:
        cursor.execute('''
            INSERT OR REPLACE INTO stats
            (id, name_en, name_zh, abbr_zh, abbr_ja, abbr_en, name_ja,
             description_zh, description_en, description_ja)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(row['id']),
            row['name_en'],
            row['name_zh'],
            row['abbr_zh'],
            row['abbr_ja'],
            row['abbr_en'],
            row['name_ja'],
            row['description_zh'],
            row['description_en'],
            row['description_ja'],
        ))

        print(f"  [{row['id']}] {row['name_zh']} / {row['name_en']} / {row['name_ja']}")

    conn.commit()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✓ 已成功导入 {len(rows)} 种能力到 stats 表")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
