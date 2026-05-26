#!/usr/bin/env python3
"""
将 weather_updated.csv（或 weather.csv）导入 pokemonData.db 的 weather 表
表结构：
  id, name_en, name_zh, name_ja,
  description_zh, description_en, description_ja,
  effect_zh, effect_en, effect_ja

用法：
  python import_weather_csv.py              # 从 weather_updated.csv 导入（优先）
  python import_weather_csv.py --source weather.csv  # 指定源文件
  python import_weather_csv.py --dry-run   # 预览，不写入数据库
"""

import csv
import sqlite3
import sys
import argparse
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CSV_DIR = Path(__file__).parent
BASE_DIR = CSV_DIR.parent.parent.parent.parent  # pokemon root
DB_PATH = BASE_DIR / "pokemon_data" / "pokemonData.db"

FIELDS = [
    "id", "name_en", "name_zh", "name_ja",
    "description_zh", "description_en", "description_ja",
    "effect_zh", "effect_en", "effect_ja",
]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS weather (
    id INTEGER PRIMARY KEY,
    name_en TEXT,
    name_zh TEXT,
    name_ja TEXT,
    description_zh TEXT,
    description_en TEXT,
    description_ja TEXT,
    effect_zh TEXT,
    effect_en TEXT,
    effect_ja TEXT
)
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None, help="指定 CSV 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="预览，不写入数据库")
    args = parser.parse_args()

    # 确定源文件
    if args.source:
        csv_path = Path(args.source)
    else:
        updated = CSV_DIR / "weather_updated.csv"
        base = CSV_DIR / "weather.csv"
        csv_path = updated if updated.exists() else base

    if not csv_path.exists():
        print(f"❌ 找不到 CSV 文件：{csv_path}")
        print("请先运行 extract_weather_to_csv.py")
        return

    print(f"源文件：{csv_path}")

    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"读取 {len(rows)} 条记录\n")

    if args.dry_run:
        print("=== 预览（dry-run，不写入数据库）===")
        for row in rows:
            print(f"  id={row['id']} {row['name_zh']} / {row['name_en']} / {row['name_ja']}")
            print(f"    description_zh: {row.get('description_zh','')[:60]}...")
            print(f"    type_effect_zh: {row.get('type_effect_zh','')[:60]}...")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 重建表（DROP + CREATE 保证结构最新）
    cursor.execute("DROP TABLE IF EXISTS weather")
    cursor.execute(CREATE_SQL)
    print("✓ weather 表结构已重建")

    count = 0
    for row in rows:
        values = [row.get(f, "") or "" for f in FIELDS]
        placeholders = ", ".join(["?"] * len(FIELDS))
        cols = ", ".join(FIELDS)
        cursor.execute(f"INSERT OR REPLACE INTO weather ({cols}) VALUES ({placeholders})", values)
        count += 1
        print(f"  ✓ {row.get('name_zh', '?')} ({row.get('name_en', '?')})")

    conn.commit()
    conn.close()
    print(f"\n✓ 已导入 {count} 条记录到 {DB_PATH}")


if __name__ == "__main__":
    main()
