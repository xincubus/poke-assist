#!/usr/bin/env python3
"""
从 status.csv 导入异常状态数据到 pokemonData.db 的 status 表

用法：python import_status_csv.py
默认读取 pokemon_data/createTable/csv/status/status.csv
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
CSV_PATH = Path(__file__).parent / "status.csv"


def main():
    print("=" * 60)
    print("从 CSV 导入 status（异常状态）表")
    print("=" * 60)
    print(f"CSV 文件: {CSV_PATH}")
    print(f"数据库: {DB_PATH}\n")

    if not CSV_PATH.exists():
        print(f"✗ CSV 文件不存在: {CSV_PATH}")
        print("  请先运行 extract_status_to_csv.py 生成 CSV 并手动修正")
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
    # 自动检测分隔符（Excel 保存可能是 Tab 或逗号）
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters='\t,')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = '\t' if '\t' in text[:500] else ','
    print(f"检测到分隔符: {'Tab' if delimiter == chr(9) else repr(delimiter)}")

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        print("✗ CSV 文件为空")
        sys.exit(1)

    print(f"读取到 {len(rows)} 条记录")

    # 创建表
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS status')
    cursor.execute('''
        CREATE TABLE status (
            id INTEGER PRIMARY KEY,
            name_en TEXT NOT NULL,
            name_ja TEXT,
            name_zh TEXT NOT NULL,
            description_zh TEXT,
            description_en TEXT,
            description_ja TEXT
        )
    ''')
    print("✓ status 表结构创建成功\n")

    # 插入数据
    for row in rows:
        cursor.execute('''
            INSERT OR REPLACE INTO status
            (id, name_en, name_ja, name_zh,
             description_zh, description_en, description_ja)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            int(row['id']),
            row['name_en'],
            row['name_ja'],
            row['name_zh'],
            row['description_zh'],
            row['description_en'],
            row['description_ja'],
        ))

        print(f"  [{row['id']}] {row['name_zh']} / {row['name_en']} / {row['name_ja']}")

    conn.commit()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✓ 已成功导入 {len(rows)} 种异常状态到 status 表")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
