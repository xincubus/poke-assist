"""
将 pokemon_moves.csv（或 pokemon_moves_updated.csv）导入 pokemonData.db，
重建 pokemon_moves 表和 pokemon_moves_sv 表。

用法：
  python import_pokemon_moves_csv.py                        # 使用 pokemon_moves.csv
  python import_pokemon_moves_csv.py --csv pokemon_moves_updated.csv
"""

import csv
import sqlite3
import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
DB_FILE    = SCRIPT_DIR.parent.parent.parent / "pokemonData.db"
CSV_FILE   = SCRIPT_DIR / "pokemon_moves.csv"


def recreate_tables(conn):
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS pokemon_moves_sv")
    cur.execute("DROP TABLE IF EXISTS pokemon_moves")

    cur.execute("""
        CREATE TABLE pokemon_moves (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id       INTEGER NOT NULL,
            pokeapi_id       INTEGER NOT NULL,
            pokemon_name_zh  TEXT,
            pokemon_name_ja  TEXT,
            pokemon_name_en  TEXT NOT NULL,
            move_id          INTEGER NOT NULL,
            move_name_zh     TEXT,
            move_name_en     TEXT NOT NULL,
            move_name_ja     TEXT,
            learn_method     TEXT NOT NULL,
            level            INTEGER,
            version_group    TEXT NOT NULL,
            generation       INTEGER NOT NULL,
            FOREIGN KEY (pokeapi_id) REFERENCES pokemons(pokeapi_id),
            FOREIGN KEY (move_id)    REFERENCES moves(id)
        )
    """)
    cur.execute("CREATE INDEX idx_pokemon_moves_pokedex    ON pokemon_moves(pokedex_id)")
    cur.execute("CREATE INDEX idx_pokemon_moves_pokeapi    ON pokemon_moves(pokeapi_id)")
    cur.execute("CREATE INDEX idx_pokemon_moves_move       ON pokemon_moves(move_id)")
    cur.execute("CREATE INDEX idx_pokemon_moves_generation ON pokemon_moves(generation)")

    cur.execute("""
        CREATE TABLE pokemon_moves_sv (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id       INTEGER NOT NULL,
            pokeapi_id       INTEGER NOT NULL,
            pokemon_name_zh  TEXT,
            pokemon_name_ja  TEXT,
            pokemon_name_en  TEXT NOT NULL,
            move_id          INTEGER NOT NULL,
            move_name_zh     TEXT,
            move_name_en     TEXT NOT NULL,
            move_name_ja     TEXT,
            learn_method     TEXT NOT NULL,
            level            INTEGER,
            version_group    TEXT NOT NULL,
            generation       INTEGER NOT NULL,
            FOREIGN KEY (pokeapi_id) REFERENCES pokemons(pokeapi_id),
            FOREIGN KEY (move_id)    REFERENCES moves(id)
        )
    """)

    conn.commit()
    print("✓ 表结构已重建（pokemon_moves + pokemon_moves_sv）")


def import_csv(conn, csv_path):
    cur = conn.cursor()

    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"读取 {len(rows):,} 条记录，开始导入...")

    batch = []
    for row in rows:
        batch.append((
            int(row["pokedex_id"]),
            int(row["pokeapi_id"]),
            row["pokemon_name_zh"] or None,
            row["pokemon_name_ja"] or None,
            row["pokemon_name_en"],
            int(row["move_id"]),
            row["move_name_zh"] or None,
            row["move_name_en"],
            row["move_name_ja"] or None,
            row["learn_method"],
            int(row["level"]) if row["level"] else None,
            row["version_group"],
            int(row["generation"]),
        ))

    cur.executemany("""
        INSERT INTO pokemon_moves (
            pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_ja, pokemon_name_en,
            move_id, move_name_zh, move_name_en, move_name_ja,
            learn_method, level, version_group, generation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, batch)
    conn.commit()
    print(f"✓ pokemon_moves 导入完成：{len(batch):,} 条")


def build_sv_table(conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pokemon_moves_sv (
            pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_ja, pokemon_name_en,
            move_id, move_name_zh, move_name_en, move_name_ja,
            learn_method, level, version_group, generation
        )
        SELECT
            pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_ja, pokemon_name_en,
            move_id, move_name_zh, move_name_en, move_name_ja,
            learn_method, level, version_group, generation
        FROM pokemon_moves
        WHERE version_group = 'scarlet-violet'
        ORDER BY pokedex_id ASC, pokeapi_id ASC, level ASC
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM pokemon_moves_sv")
    count = cur.fetchone()[0]
    print(f"✓ pokemon_moves_sv 构建完成：{count:,} 条")


def verify(conn):
    cur = conn.cursor()
    print("\n--- 验证 ---")

    cur.execute("SELECT COUNT(*) FROM pokemon_moves")
    print(f"pokemon_moves 总记录：{cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(DISTINCT pokeapi_id) FROM pokemon_moves")
    print(f"不同宝可梦数：{cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(DISTINCT move_id) FROM pokemon_moves")
    print(f"不同招式数：{cur.fetchone()[0]}")

    cur.execute("SELECT COUNT(*) FROM pokemon_moves WHERE move_name_zh IS NULL OR move_name_zh = ''")
    print(f"move_name_zh 为空：{cur.fetchone()[0]:,} 条")

    cur.execute("SELECT generation, COUNT(*) FROM pokemon_moves GROUP BY generation ORDER BY generation")
    print("各世代记录数：")
    for gen, cnt in cur.fetchall():
        print(f"  第{gen}世代：{cnt:,} 条")

    cur.execute("SELECT COUNT(*) FROM pokemon_moves_sv")
    print(f"\npokemon_moves_sv（朱紫）：{cur.fetchone()[0]:,} 条")


def main():
    parser = argparse.ArgumentParser(description="pokemon_moves.csv → pokemonData.db")
    parser.add_argument("--csv", default=str(CSV_FILE), help="输入 CSV 路径")
    args = parser.parse_args()
    csv_path = Path(args.csv)

    if not csv_path.exists():
        print(f"[ERROR] CSV 文件不存在：{csv_path}")
        return
    if not DB_FILE.exists():
        print(f"[ERROR] 数据库不存在：{DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    try:
        recreate_tables(conn)
        import_csv(conn, csv_path)
        build_sv_table(conn)
        verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
