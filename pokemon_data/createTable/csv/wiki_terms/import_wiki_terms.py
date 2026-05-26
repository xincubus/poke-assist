"""
将 wiki_terms_clean.json 导入 pokemonData.db。

建两张表：
  wiki_pages    — 页面级元数据（833 行）
  wiki_sections — 段落级内容（~4362 行）

用法：
    python import_wiki_terms.py              # 导入（先删旧表再建新表）
    python import_wiki_terms.py --dry-run    # 只建表不导入，看 SQL
"""

import os
import json
import sqlite3
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "wiki_terms_clean.json")
DB_PATH = os.path.join(SCRIPT_DIR, "..", "..", "..", "pokemonData.db")

CREATE_PAGES = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL UNIQUE,
    url TEXT,
    summary TEXT,
    category TEXT
);
"""

CREATE_SECTIONS = """
CREATE TABLE IF NOT EXISTS wiki_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    heading TEXT,
    level INTEGER,
    text TEXT,
    section_order INTEGER,
    FOREIGN KEY (page_id) REFERENCES wiki_pages(id)
);
"""

CREATE_INDEX_TITLE = "CREATE INDEX IF NOT EXISTS idx_wiki_pages_title ON wiki_pages(title);"
CREATE_INDEX_CAT = "CREATE INDEX IF NOT EXISTS idx_wiki_pages_category ON wiki_pages(category);"
CREATE_INDEX_PAGE_ID = "CREATE INDEX IF NOT EXISTS idx_wiki_sections_page_id ON wiki_sections(page_id);"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印 SQL 不执行")
    args = parser.parse_args()

    db_path = os.path.normpath(DB_PATH)
    print(f"数据库: {db_path}")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"读取 {len(data)} 个页面")

    if args.dry_run:
        print("\n--- DDL ---")
        print(CREATE_PAGES)
        print(CREATE_SECTIONS)
        print(CREATE_INDEX_TITLE)
        print(CREATE_INDEX_CAT)
        print(CREATE_INDEX_PAGE_ID)
        total_sections = sum(len(p["sections"]) for p in data)
        print(f"\n将插入 {len(data)} 页 + {total_sections} 段落")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS wiki_sections;")
    cur.execute("DROP TABLE IF EXISTS wiki_pages;")
    cur.execute(CREATE_PAGES)
    cur.execute(CREATE_SECTIONS)
    cur.execute(CREATE_INDEX_TITLE)
    cur.execute(CREATE_INDEX_CAT)
    cur.execute(CREATE_INDEX_PAGE_ID)

    page_count = 0
    section_count = 0

    for page in data:
        cur.execute(
            "INSERT INTO wiki_pages (title, url, summary, category) VALUES (?, ?, ?, ?);",
            (page["title"], page["url"], page["summary"], page["category"]),
        )
        page_id = cur.lastrowid
        page_count += 1

        for order, section in enumerate(page["sections"]):
            cur.execute(
                "INSERT INTO wiki_sections (page_id, heading, level, text, section_order) VALUES (?, ?, ?, ?, ?);",
                (page_id, section["heading"], section["level"], section["text"], order),
            )
            section_count += 1

    conn.commit()
    conn.close()

    print(f"完成: {page_count} 页, {section_count} 段落")


if __name__ == "__main__":
    main()
