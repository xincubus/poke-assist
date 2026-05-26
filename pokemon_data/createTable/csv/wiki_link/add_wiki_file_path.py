"""
迁移脚本：为实体表添加 wiki_file_path 列
可重复运行，已存在列时跳过。
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pokemonData.db")

TABLES = [
    "pokemons",
    "moves",
    "abilities",
    "items",
    "stats",
    "status",
    "types",
    "natures",
]


def main():
    conn = sqlite3.connect(DB_PATH)
    for table in TABLES:
        # 检查列是否已存在
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "wiki_file_path" in cols:
            print(f"  {table}: wiki_file_path 已存在，跳过")
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN wiki_file_path TEXT")
        print(f"  {table}: 已添加 wiki_file_path 列")
    conn.commit()
    conn.close()
    print("完成")


if __name__ == "__main__":
    main()
