"""
将 pokemons_updated.csv（或 pokemons.csv）导入 pokemonData.db 的 pokemons 表。
只更新 name_zh、name_ja、description_zh、description_en、description_ja 字段，
保留数据库中已有的其他字段不变。

用法：
  python import_pokemons_csv.py                  # 从 pokemons_updated.csv 更新
  python import_pokemons_csv.py --full-rebuild   # 删表重建（从 pokemons_updated.csv 全量导入）
"""

import csv
import sqlite3
import argparse
from pathlib import Path

BASE_DIR        = Path(__file__).parent
UPDATED_CSV     = BASE_DIR / 'pokemons_updated.csv'
CSV_FILE        = BASE_DIR / 'pokemons.csv'
DB_FILE         = BASE_DIR.parent.parent.parent.parent / 'pokemonData.db'


def get_csv_path():
    if UPDATED_CSV.exists():
        return UPDATED_CSV
    print(f"[WARN] {UPDATED_CSV.name} 不存在，使用 {CSV_FILE.name}")
    return CSV_FILE


def get_ability_id(cur, name_en):
    if not name_en:
        return None
    cur.execute('SELECT id FROM abilities WHERE name_en = ?', (name_en,))
    row = cur.fetchone()
    return row[0] if row else None


# ========== 模式1：只更新文本字段 ==========

def update_only(csv_path):
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    updated = skipped = 0
    for row in rows:
        cur.execute(
            '''UPDATE pokemons
               SET name_zh        = COALESCE(NULLIF(?, ''), name_zh),
                   name_ja        = COALESCE(NULLIF(?, ''), name_ja),
                   description_zh = COALESCE(NULLIF(?, ''), description_zh),
                   description_en = COALESCE(NULLIF(?, ''), description_en),
                   description_ja = COALESCE(NULLIF(?, ''), description_ja)
               WHERE name_en = ?''',
            (
                row['name_zh'],
                row['name_ja'],
                row['description_zh'],
                row['description_en'],
                row['description_ja'],
                row['name_en'],
            )
        )
        if cur.rowcount:
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f'更新完成：更新 {updated} 条，跳过（name_en 不存在）{skipped} 条')
    _verify()


# ========== 模式2：全量重建 ==========

def full_rebuild(csv_path):
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 重建表
    cur.execute('DROP TABLE IF EXISTS pokemons')
    cur.executescript('''
        CREATE TABLE pokemons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id INTEGER NOT NULL,
            pokeapi_id INTEGER NOT NULL,
            name_ja TEXT NOT NULL,
            name_zh TEXT NOT NULL,
            name_en TEXT NOT NULL,
            is_default_form BOOLEAN NOT NULL,
            type1 TEXT NOT NULL,
            type2 TEXT,
            ability1_id INTEGER,
            ability1_name TEXT,
            ability2_id INTEGER,
            ability2_name TEXT,
            hidden_ability_id INTEGER,
            hidden_ability_name TEXT,
            weight_kg REAL,
            hp INTEGER NOT NULL,
            attack INTEGER NOT NULL,
            defense INTEGER NOT NULL,
            sp_attack INTEGER NOT NULL,
            sp_defense INTEGER NOT NULL,
            speed INTEGER NOT NULL,
            total_stats INTEGER NOT NULL,
            image_official_artwork TEXT,
            description_ja TEXT,
            description_en TEXT,
            description_zh TEXT,
            name_ncp TEXT,
            FOREIGN KEY (ability1_id) REFERENCES abilities(id),
            FOREIGN KEY (ability2_id) REFERENCES abilities(id),
            FOREIGN KEY (hidden_ability_id) REFERENCES abilities(id)
        );
        CREATE INDEX idx_pokemons_pokedex ON pokemons(pokedex_id);
        CREATE INDEX idx_pokemons_name_en ON pokemons(name_en);
        CREATE INDEX idx_pokemons_name_ncp ON pokemons(name_ncp);
        CREATE INDEX idx_pokemons_ability1 ON pokemons(ability1_id);
        CREATE INDEX idx_pokemons_ability2 ON pokemons(ability2_id);
        CREATE INDEX idx_pokemons_hidden_ability ON pokemons(hidden_ability_id);
    ''')
    print('✓ pokemons 表已重建')

    inserted = failed = 0
    for row in rows:
        try:
            ab1_id = get_ability_id(cur, row.get('ability1_name', ''))
            ab2_id = get_ability_id(cur, row.get('ability2_name', ''))
            hab_id = get_ability_id(cur, row.get('hidden_ability_name', ''))

            cur.execute(
                '''INSERT INTO pokemons (
                    pokedex_id, pokeapi_id, name_ja, name_zh, name_en,
                    is_default_form, type1, type2,
                    ability1_id, ability1_name, ability2_id, ability2_name,
                    hidden_ability_id, hidden_ability_name,
                    weight_kg, hp, attack, defense, sp_attack, sp_defense, speed, total_stats,
                    image_official_artwork,
                    description_ja, description_en, description_zh
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    int(row['pokedex_id']) if row['pokedex_id'] else 0,
                    int(row['pokeapi_id']),
                    row['name_ja'],
                    row['name_zh'],
                    row['name_en'],
                    int(row['is_default_form']),
                    row['type1'],
                    row['type2'] or None,
                    ab1_id, row.get('ability1_name') or None,
                    ab2_id, row.get('ability2_name') or None,
                    hab_id, row.get('hidden_ability_name') or None,
                    float(row['weight_kg']) if row['weight_kg'] else None,
                    int(row['hp']),
                    int(row['attack']),
                    int(row['defense']),
                    int(row['sp_attack']),
                    int(row['sp_defense']),
                    int(row['speed']),
                    int(row['total_stats']),
                    row.get('image_official_artwork') or None,
                    row['description_ja'] or None,
                    row['description_en'] or None,
                    row['description_zh'] or None,
                )
            )
            inserted += 1
            if inserted % 200 == 0:
                print(f'  已插入 {inserted}/{len(rows)} 条...')
                conn.commit()
        except Exception as e:
            print(f'  [ERROR] {row.get("name_en")}: {e}')
            failed += 1

    conn.commit()
    conn.close()
    print(f'全量导入完成：插入 {inserted} 条，失败 {failed} 条')
    _verify()


def _verify():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM pokemons')
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pokemons WHERE name_zh IS NOT NULL AND name_zh != ''")
    has_zh = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pokemons WHERE description_zh IS NOT NULL AND description_zh != ''")
    has_desc = cur.fetchone()[0]
    conn.close()
    print(f'数据库 pokemons 表：共 {total} 条，有中文名 {has_zh} 条，有中文说明 {has_desc} 条')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full-rebuild', action='store_true',
                        help='删表重建（全量导入，会清空现有数据）')
    args = parser.parse_args()

    csv_path = get_csv_path()
    print(f'使用 CSV：{csv_path}')

    if args.full_rebuild:
        confirm = input('⚠️  将删除并重建 pokemons 表，确认？(y/N) ')
        if confirm.lower() != 'y':
            print('已取消。')
            return
        full_rebuild(csv_path)
    else:
        update_only(csv_path)


if __name__ == '__main__':
    main()
