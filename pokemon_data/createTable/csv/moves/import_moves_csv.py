"""
将 moves_updated.csv 导入 pokemonData.db 的 moves 表。
- 自动为 moves 表添加 effect_zh、effect_en、effect_ja 列（如不存在）
- 用 COALESCE 更新所有文本字段，不覆盖已有值
"""

import csv
import sqlite3
from pathlib import Path

CSV_FILE = Path(__file__).parent / 'moves_updated.csv'
DB_FILE  = Path(__file__).parent.parent.parent.parent / 'pokemonData.db'

NEW_COLS = ['effect_zh', 'effect_en', 'effect_ja']


def ensure_columns(cur):
    cur.execute("PRAGMA table_info(moves)")
    existing = {row[1] for row in cur.fetchall()}
    for col in NEW_COLS:
        if col not in existing:
            cur.execute(f"ALTER TABLE moves ADD COLUMN {col} TEXT")
            print(f"  已添加列：{col}")


def import_moves():
    with open(CSV_FILE, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    ensure_columns(cur)

    updated = skipped = 0
    for row in rows:
        move_id = int(row['id'])
        cur.execute(
            '''UPDATE moves
               SET name_zh        = COALESCE(NULLIF(?, ''), name_zh),
                   name_ja        = COALESCE(NULLIF(?, ''), name_ja),
                   description_zh = COALESCE(NULLIF(?, ''), description_zh),
                   description_ja = COALESCE(NULLIF(?, ''), description_ja),
                   description_en = COALESCE(NULLIF(?, ''), description_en),
                   effect_zh      = COALESCE(NULLIF(?, ''), effect_zh),
                   effect_en      = COALESCE(NULLIF(?, ''), effect_en),
                   effect_ja      = COALESCE(NULLIF(?, ''), effect_ja)
               WHERE id = ?''',
            (
                row['name_zh'],
                row['name_ja'],
                row['description_zh'],
                row['description_ja'],
                row['description_en'],
                row['effect_zh'],
                row['effect_en'],
                row['effect_ja'],
                move_id,
            )
        )
        if cur.rowcount:
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f'导入完成：更新 {updated} 条，跳过（ID不存在）{skipped} 条')

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM moves")
    total = cur.fetchone()[0]
    for col in ['name_zh', 'description_zh', 'effect_zh', 'effect_en', 'effect_ja']:
        cur.execute(f"SELECT COUNT(*) FROM moves WHERE {col} IS NOT NULL AND {col} != ''")
        count = cur.fetchone()[0]
        print(f'  有 {col}：{count}/{total}')
    conn.close()


if __name__ == '__main__':
    import_moves()
