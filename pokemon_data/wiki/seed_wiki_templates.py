"""
把 wiki_pages 表里 namespace=10 的所有 Template 灌进 wiki_templates 表。

初始全部标 category='unknown'，param_fmt 为空。
后续由 classify_templates.py 或人工 SQL 修正。

使用：
    python seed_wiki_templates.py              # 灌表 + 显示统计
    python seed_wiki_templates.py --stats      # 只看统计
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")

TEMPLATE_PREFIX = "Template:"

DDL = """
CREATE TABLE IF NOT EXISTS wiki_templates (
    name        TEXT PRIMARY KEY,
    page_id     INTEGER,
    file_path   TEXT,
    category    TEXT NOT NULL DEFAULT 'unknown',
    param_fmt   TEXT,
    note        TEXT,
    updated_at  TEXT
);
"""


def init_table(conn: sqlite3.Connection) -> None:
    conn.execute(DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tpl_cat ON wiki_templates(category)")
    conn.commit()


def seed(conn: sqlite3.Connection) -> int:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    inserted = 0

    rows = conn.execute("""
        SELECT page_id, title, file_path
        FROM wiki_pages
        WHERE namespace = 10 AND status IN ('done', 'redirect')
    """).fetchall()

    for page_id, title, file_path in rows:
        if not title.startswith(TEMPLATE_PREFIX):
            continue
        name = title[len(TEMPLATE_PREFIX):]
        cur = conn.execute(
            "INSERT OR IGNORE INTO wiki_templates (name, page_id, file_path, category, updated_at) "
            "VALUES (?, ?, ?, 'unknown', ?)",
            (name, page_id, file_path, now),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def show_stats(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM wiki_templates").fetchone()[0]
    print(f"wiki_templates 总计: {total}")
    rows = conn.execute(
        "SELECT category, COUNT(*) FROM wiki_templates GROUP BY category ORDER BY 2 DESC"
    ).fetchall()
    print("按分类:")
    for cat, n in rows:
        print(f"  {cat:<10} {n}")


def main():
    parser = argparse.ArgumentParser(description="把 Template 页灌进 wiki_templates 表")
    parser.add_argument("--stats", action="store_true", help="只显示统计，不灌表")
    parser.add_argument("--db", default=DB_PATH, help="wiki_meta.db 路径")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    init_table(conn)

    if args.stats:
        show_stats(conn)
        conn.close()
        return

    n = seed(conn)
    print(f"新灌入 {n} 条模板")
    show_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
