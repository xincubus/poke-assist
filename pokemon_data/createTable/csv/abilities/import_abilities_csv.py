"""
将 abilities_updated.csv 导入 pokemonData.db 的 abilities 表。
只更新 name_zh、name_ja、description_zh、description_en、description_ja 字段，
保留数据库中已有的 pokemon_list 字段不变。
"""

import csv
import sqlite3
from pathlib import Path

CSV_FILE = Path(__file__).parent / 'abilities_updated.csv'
DB_FILE  = Path(__file__).parent.parent.parent.parent / 'pokemonData.db'


def import_abilities():
    with open(CSV_FILE, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    updated = skipped = 0

    for row in rows:
        ability_id = int(row['id'])
        cur.execute(
            '''UPDATE abilities
               SET name_zh        = COALESCE(NULLIF(?, ''), name_zh),
                   name_ja        = COALESCE(NULLIF(?, ''), name_ja),
                   description_zh = COALESCE(NULLIF(?, ''), description_zh),
                   description_en = COALESCE(NULLIF(?, ''), description_en),
                   description_ja = COALESCE(NULLIF(?, ''), description_ja)
               WHERE id = ?''',
            (
                row['name_zh'],
                row['name_ja'],
                row['description_zh'],
                row['description_en'],
                row['description_ja'],
                ability_id,
            )
        )
        if cur.rowcount:
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    print(f'导入完成：更新 {updated} 条，跳过（ID不存在）{skipped} 条')

    # 验证
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM abilities WHERE name_zh IS NOT NULL AND name_zh != ''")
    has_zh = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM abilities")
    total = cur.fetchone()[0]
    conn.close()
    print(f'数据库 abilities 表：共 {total} 条，有中文名 {has_zh} 条')


if __name__ == '__main__':
    import_abilities()
