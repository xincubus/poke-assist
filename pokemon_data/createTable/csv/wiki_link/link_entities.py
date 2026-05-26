"""
回填脚本：将实体表的 wiki_file_path 与 wiki_meta.wiki_pages 关联。
匹配策略：name_zh 精确匹配 title → wiki_redirects → 未匹配记录到 CSV。
"""
import sqlite3
import csv
import os

POKEMON_DB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pokemonData.db")
WIKI_META_DB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "wiki", "wiki_meta.db")
OUTPUT_DIR = os.path.dirname(__file__)

# (table_name, name_column, extra_columns_for_disambiguation)
# extra_columns: 用于消歧义的列，如招式名和道具名可能重名
TABLES = [
    ("pokemons", "name_zh", None),
    ("moves", "name_zh", None),
    ("abilities", "name_zh", None),
    ("items", "name_zh", None),
    ("stats", "name_zh", None),
    ("status", "name_zh", None),
    ("types", "name_zh", None),
    ("natures", "name_zh", None),
]

# 手动映射：实体名 → wiki 页面标题（用于自动匹配失败的常见情况）
MANUAL_OVERRIDES = {
    # stats 表的 name_zh 和 wiki 页面标题不完全一致
    ("stats", "HP"): "HP",
    ("stats", "攻击"): "攻击",
    ("stats", "防御"): "防御",
    ("stats", "特攻"): "特攻",
    ("stats", "特防"): "特防",
    ("stats", "速度"): "速度",
    ("stats", "命中率"): "命中率",
    ("stats", "闪避率"): "闪避率",
}


def load_wiki_pages(conn):
    """加载 wiki_pages 标题→file_path 映射"""
    rows = conn.execute(
        "SELECT title, file_path FROM wiki_pages WHERE status = 'done' AND file_path IS NOT NULL"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def load_wiki_redirects(conn):
    """加载 redirects: source_title → target_title"""
    rows = conn.execute(
        "SELECT r.source_title, wp.file_path "
        "FROM wiki_redirects r "
        "JOIN wiki_pages wp ON wp.page_id = r.target_page_id "
        "WHERE wp.status = 'done' AND wp.file_path IS NOT NULL"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def main():
    poke_conn = sqlite3.connect(POKEMON_DB)
    wiki_conn = sqlite3.connect(WIKI_META_DB)

    wiki_pages = load_wiki_pages(wiki_conn)
    wiki_redirects = load_wiki_redirects(wiki_conn)
    wiki_conn.close()

    print(f"wiki_pages: {len(wiki_pages)} 条")
    print(f"wiki_redirects: {len(wiki_redirects)} 条")

    total_linked = 0
    total_unlinked = 0

    for table, name_col, _ in TABLES:
        rows = poke_conn.execute(f"SELECT id, {name_col} FROM {table}").fetchall()
        linked = 0
        unlinked = []

        for row_id, name_zh in rows:
            if not name_zh:
                unlinked.append((row_id, name_zh or "", "空名称"))
                continue

            # 检查手动映射
            override_key = (table, name_zh)
            if override_key in MANUAL_OVERRIDES:
                wiki_title = MANUAL_OVERRIDES[override_key]
                file_path = wiki_pages.get(wiki_title) or wiki_redirects.get(wiki_title)
                if file_path:
                    poke_conn.execute(
                        f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                        (file_path, row_id),
                    )
                    linked += 1
                    continue

            # 1. 精确匹配 wiki_pages.title
            file_path = wiki_pages.get(name_zh)
            if file_path:
                poke_conn.execute(
                    f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                    (file_path, row_id),
                )
                linked += 1
                continue

            # 2. 通过 redirects
            file_path = wiki_redirects.get(name_zh)
            if file_path:
                poke_conn.execute(
                    f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                    (file_path, row_id),
                )
                linked += 1
                continue

            # 3. 尝试带消歧义后缀匹配（如「血月（招式）」）
            disambig_suffixes = {
                "pokemons": "（宝可梦）",
                "moves": "（招式）",
                "abilities": "（特性）",
                "items": "（道具）",
            }
            suffix = disambig_suffixes.get(table)
            matched = False
            if suffix:
                for candidate in [name_zh + suffix]:
                    fp = wiki_pages.get(candidate) or wiki_redirects.get(candidate)
                    if fp:
                        poke_conn.execute(
                            f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                            (fp, row_id),
                        )
                        linked += 1
                        matched = True
                        break
            if matched:
                continue

            # 3b. types 表：name_zh="火属性" → wiki "火（属性）"
            if table == "types" and name_zh.endswith("属性"):
                base = name_zh[:-2]  # 去掉"属性"
                candidate = f"{base}（属性）"
                fp = wiki_pages.get(candidate) or wiki_redirects.get(candidate)
                if fp:
                    poke_conn.execute(
                        f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                        (fp, row_id),
                    )
                    linked += 1
                    continue

            # 4. natures 表：所有性格都链接到「性格」页面
            if table == "natures":
                fp = wiki_pages.get("性格") or wiki_redirects.get("性格")
                if fp:
                    poke_conn.execute(
                        f"UPDATE {table} SET wiki_file_path = ? WHERE id = ?",
                        (fp, row_id),
                    )
                    linked += 1
                    continue

            unlinked.append((row_id, name_zh, "未匹配"))

        poke_conn.commit()

        # 写未匹配 CSV
        if unlinked:
            csv_path = os.path.join(OUTPUT_DIR, f"unlinked_{table}.csv")
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "name_zh", "reason"])
                writer.writerows(unlinked)

        pct = linked / len(rows) * 100 if rows else 0
        print(f"  {table}: {linked}/{len(rows)} 匹配 ({pct:.1f}%), {len(unlinked)} 未匹配")
        total_linked += linked
        total_unlinked += len(unlinked)

    poke_conn.close()
    print(f"\n总计: {total_linked} 匹配, {total_unlinked} 未匹配")


if __name__ == "__main__":
    main()
