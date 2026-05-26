#!/usr/bin/env python3
"""
从 natures.csv 导入性格数据到 pokemonData.db 的 natures 表

用法：python import_natures_csv.py
默认读取 pokemon_data/createTable/csv/natures/natures.csv
"""

import csv
import sqlite3
import sys
import io
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent.parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"
CSV_PATH = Path(__file__).parent / "natures.csv"


def main():
    print('=' * 60)
    print('从 CSV 导入 natures（性格）表')
    print('=' * 60)
    print(f'CSV 文件: {CSV_PATH}')
    print(f'数据库: {DB_PATH}\n')

    if not CSV_PATH.exists():
        print(f'✗ CSV 文件不存在: {CSV_PATH}')
        print('  请先运行 extract_natures_to_csv.py 生成 CSV 并手动修正')
        sys.exit(1)

    raw = open(CSV_PATH, 'rb').read()
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
        try:
            text = raw.decode(enc)
            print(f'使用编码: {enc}')
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        print('✗ 无法识别 CSV 文件编码')
        sys.exit(1)

    reader = csv.DictReader(io.StringIO(text), delimiter=',')
    rows = list(reader)

    if not rows:
        print('✗ CSV 文件为空')
        sys.exit(1)

    print(f'读取到 {len(rows)} 条记录')

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS natures')
    cursor.execute('''
        CREATE TABLE natures (
            id INTEGER PRIMARY KEY,
            name_ja TEXT,
            name_en TEXT,
            name_zh TEXT,
            decreased_stat_id INTEGER,
            increased_stat_id INTEGER,
            decreased_stat_en TEXT,
            increased_stat_en TEXT,
            decreased_stat_zh TEXT,
            increased_stat_zh TEXT,
            decreased_stat_ja TEXT,
            increased_stat_ja TEXT,
            FOREIGN KEY (decreased_stat_id) REFERENCES stats(id),
            FOREIGN KEY (increased_stat_id) REFERENCES stats(id)
        )
    ''')
    print('✓ natures 表结构创建成功\n')

    for row in rows:
        def to_int_or_none(val):
            return int(val) if val.strip() else None

        cursor.execute('''
            INSERT OR REPLACE INTO natures
            (id, name_ja, name_en, name_zh,
             decreased_stat_id, increased_stat_id,
             decreased_stat_en, increased_stat_en,
             decreased_stat_zh, increased_stat_zh,
             decreased_stat_ja, increased_stat_ja)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(row['id']),
            row['name_ja'],
            row['name_en'],
            row['name_zh'],
            to_int_or_none(row['decreased_stat_id']),
            to_int_or_none(row['increased_stat_id']),
            row['decreased_stat_en'],
            row['increased_stat_en'],
            row['decreased_stat_zh'],
            row['increased_stat_zh'],
            row['decreased_stat_ja'],
            row['increased_stat_ja'],
        ))

        inc_label = row['increased_stat_zh'] or '无'
        dec_label = row['decreased_stat_zh'] or '无'
        print(f"  [{row['id']:2}] {row['name_en']:<12} ({row['name_zh']}): +{inc_label} / -{dec_label}")

    conn.commit()
    conn.close()

    print(f'\n{"=" * 60}')
    print(f'✓ 已成功导入 {len(rows)} 个性格到 natures 表')
    print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
