#!/usr/bin/env python3
"""
从 terrains.csv 导入场地数据到 pokemonData.db 的 terrains 表
新增 effect_zh / effect_en / effect_ja 列

用法：python import_terrains_csv.py
"""

import csv
import sqlite3
import sys
import io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # pokemon_data/
DB_PATH = BASE_DIR / "pokemonData.db"
CSV_PATH = Path(__file__).resolve().parent / "terrains.csv"


def main():
    print("=" * 60)
    print("从 CSV 导入 terrains（场地）表")
    print("=" * 60)
    print(f"CSV 文件: {CSV_PATH}")
    print(f"数据库: {DB_PATH}\n")

    if not CSV_PATH.exists():
        print(f"✗ CSV 文件不存在: {CSV_PATH}")
        print("  请先运行 extract_terrains_to_csv.py 生成 CSV")
        sys.exit(1)

    raw = open(CSV_PATH, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            print(f"使用编码: {enc}")
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        print("✗ 无法识别 CSV 文件编码")
        sys.exit(1)

    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    rows = list(reader)

    if not rows:
        print("✗ CSV 文件为空")
        sys.exit(1)

    print(f"读取到 {len(rows)} 条记录")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS terrains")
    cursor.execute("""
        CREATE TABLE terrains (
            id INTEGER PRIMARY KEY,
            name_en TEXT NOT NULL,
            name_ja TEXT,
            name_zh TEXT NOT NULL,
            description_zh TEXT,
            description_en TEXT,
            description_ja TEXT,
            effect_zh TEXT,
            effect_en TEXT,
            effect_ja TEXT
        )
    """)
    print("✓ terrains 表结构创建成功\n")

    for row in rows:
        cursor.execute("""
            INSERT OR REPLACE INTO terrains
            (id, name_en, name_ja, name_zh,
             description_zh, description_en, description_ja,
             effect_zh, effect_en, effect_ja)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(row["id"]),
            row.get("name_en", ""),
            row.get("name_ja", ""),
            row.get("name_zh", ""),
            row.get("description_zh", ""),
            row.get("description_en", ""),
            row.get("description_ja", ""),
            row.get("effect_zh", ""),
            row.get("effect_en", ""),
            row.get("effect_ja", ""),
        ))
        print(f"  [{row['id']}] {row.get('name_zh','')} / {row.get('name_en','')} / {row.get('name_ja','')}")

    conn.commit()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✓ 已成功导入 {len(rows)} 种场地到 terrains 表")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
