"""
Phase 3 迁移脚本：删除 moves/abilities/items/status 表中的残缺文本字段。
wiki 现在是唯一事实源，这些字段不再需要。

可重复运行（检测列是否存在，不存在则跳过）。

删除列表：
  moves:     description_zh, description_ja, description_en, effect_zh, effect_ja, effect_en
  abilities: description_zh, description_en, effect_battle, effect_overworld
  items:     description_zh, description_en
  status:    description_zh, effect_zh, effect_overworld_zh
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pokemonData.db")

# 表名 → 要删除的列
DROP_COLUMNS = {
    "moves": ["description_zh", "description_ja", "description_en", "effect_zh", "effect_ja", "effect_en"],
    "abilities": ["description_zh", "description_en", "effect_battle", "effect_overworld"],
    "items": ["description_zh", "description_en"],
    "status": ["description_zh", "effect_zh", "effect_overworld_zh"],
}


def get_columns(conn, table):
    """获取表的列名列表"""
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def get_create_sql(conn, table):
    """获取表的 CREATE TABLE 语句"""
    row = conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row[0] if row else None


def get_indexes(conn, table):
    """获取表的索引定义（排除自动索引）"""
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (table,)
    ).fetchall()
    return rows


def drop_columns_from_table(conn, table, cols_to_drop):
    """从表中删除指定列（CREATE new → INSERT → DROP → RENAME）"""
    existing = get_columns(conn, table)
    # 过滤掉已不存在的列
    actual_drop = [c for c in cols_to_drop if c in existing]
    if not actual_drop:
        print(f"  {table}: 无需删除的列已不存在，跳过")
        return

    keep = [c for c in existing if c not in actual_drop]
    keep_str = ", ".join(keep)

    # 保存索引
    indexes = get_indexes(conn, table)

    # 1. CREATE TABLE new
    new_table = f"{table}_new"
    # 从原表 CREATE 语句改造：移除要删的列
    create_sql = get_create_sql(conn, table)
    # 简单方案：用新列列表重建
    # 先获取每列的类型信息
    col_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    col_defs = []
    for cid, name, ctype, notnull, dflt, pk in col_info:
        if name in actual_drop:
            continue
        parts = f"{name} {ctype}"
        if pk:
            parts += " PRIMARY KEY"
        if notnull and not pk:
            parts += " NOT NULL"
        if dflt is not None:
            parts += f" DEFAULT {dflt}"
        col_defs.append(parts)
    create_new = f"CREATE TABLE {new_table} ({', '.join(col_defs)})"
    conn.execute(create_new)

    # 2. INSERT INTO new SELECT keep columns
    conn.execute(f"INSERT INTO {new_table} ({keep_str}) SELECT {keep_str} FROM {table}")

    # 3. DROP old
    conn.execute(f"DROP TABLE {table}")

    # 4. RENAME
    conn.execute(f"ALTER TABLE {new_table} RENAME TO {table}")

    # 5. 重建索引
    for idx_name, idx_sql in indexes:
        # 替换索引名中的表名前缀
        conn.execute(idx_sql.replace(idx_name, idx_name))

    print(f"  {table}: 已删除 {len(actual_drop)} 列 → {actual_drop}")


def main():
    conn = sqlite3.connect(DB_PATH)

    # 检查 wiki_pages / wiki_sections 是否存在于 pokemonData.db
    tables_in_db = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    for table, cols in DROP_COLUMNS.items():
        drop_columns_from_table(conn, table, cols)

    # 删除 pokemonData.db 中的 wiki_pages / wiki_sections（如果存在）
    for wt in ("wiki_pages", "wiki_sections"):
        if wt in tables_in_db:
            conn.execute(f"DROP TABLE {wt}")
            print(f"  {wt}: 已从 pokemonData.db 删除")

    conn.commit()
    conn.close()
    print("\n完成")


if __name__ == "__main__":
    main()
