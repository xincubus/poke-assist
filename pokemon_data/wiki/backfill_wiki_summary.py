"""
为 wiki_pages 表补充 summary 列并建立 FTS5 索引。

用法：python backfill_wiki_summary.py [--rebuild]
  --rebuild  重建 FTS5（删除旧表再建）

流程：
  1. ALTER TABLE wiki_pages ADD COLUMN summary TEXT（如不存在）
  2. 遍历所有 status='done' 的页面，从 wikitext 提取首段摘要
  3. 创建/重建 wiki_pages_fts (FTS5 on title, summary)
"""

import argparse
import os
import re
import sqlite3
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")
CACHE_DIR = os.path.join(SCRIPT_DIR, "wikitext_cache")

# ============================================================
# wikitext 摘要提取
# ============================================================

# 匹配 infobox 模板块（从文件开头的 {{ 到匹配的 }}）
_RE_WIKI_LINK = re.compile(r"\[\[([^\]|]*\|)?([^\]]+)\]\]")  # [[link|text]] → text, [[text]] → text
_RE_WIKI_BOLD_ITALIC = re.compile(r"'{2,3}([^']*)'{2,3}")   # '''bold''' / ''italic'' → text
_RE_WIKI_TAG = re.compile(r"<[^>]+>")                        # <ref>...</ref>, <br/>, etc.
_RE_WIKI_TEMPLATE_SIMPLE = re.compile(r"\{\{[^{}]*\}\}")     # simple {{...}} on one line
_RE_WIKI_FILE = re.compile(r"\[\[(?:文件|File|Image):[^\]]*\]\]", re.IGNORECASE)
_RE_WIKI_CATEGORY = re.compile(r"\[\[(?:分类|Category):[^\]]*\]\]", re.IGNORECASE)
_RE_SECTION_HEADER = re.compile(r"^={2,}.+?={2,}\s*$", re.MULTILINE)
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _find_infobox_end(text: str) -> int:
    """找到文件开头 {{infobox...}} 的结束位置（匹配的 }}）。"""
    if not text.startswith("{{"):
        return 0
    depth = 0
    i = 0
    while i < len(text):
        if text[i:i+2] == "{{":
            depth += 1
            i += 2
        elif text[i:i+2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def _strip_templates(text: str, max_depth: int = 5) -> str:
    """递归去除所有 {{...}} 模板调用（包括嵌套）。"""
    for _ in range(max_depth):
        new = re.sub(r"\{\{[^{}]*\}\}", "", text)
        if new == text:
            break
        text = new
    return text


def _clean_wikitext(text: str) -> str:
    """去除 wikitext 标记，保留纯文本。"""
    text = _RE_HTML_COMMENT.sub("", text)
    text = _RE_WIKI_FILE.sub("", text)
    text = _RE_WIKI_CATEGORY.sub("", text)
    text = _RE_WIKI_TAG.sub("", text)
    text = _strip_templates(text)
    text = _RE_WIKI_LINK.sub(r"\2", text)
    text = _RE_WIKI_BOLD_ITALIC.sub(r"\1", text)
    # 去 ---- 分隔线和 __TOC__ 等 magic word
    text = re.sub(r"^-{4,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"__\w+__", "", text)
    # 去多余空白
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip()
    return text


def extract_summary(wikitext: str, max_len: int = 300) -> str:
    """从 wikitext 提取首段摘要（跳过 infobox 和 section headers）。
    策略：优先取前言段，不足则取第一个二级标题下的正文。"""
    # 跳过开头的 infobox
    end = _find_infobox_end(wikitext)
    body = wikitext[end:].lstrip("\n")

    # 按 section header 分段
    sections = _RE_SECTION_HEADER.split(body)
    headers = _RE_SECTION_HEADER.findall(body)

    # sections[0] = 前言（第一个 == 之前）
    candidates = []

    # 1. 前言段
    if sections:
        candidates.append(sections[0])

    # 2. 第一个二级标题后的内容
    for i, hdr in enumerate(headers):
        level = hdr.count("=") // 2  # ==X== level 2, ===X=== level 3
        if level <= 2 and i + 1 < len(sections):
            candidates.append(sections[i + 1])

    for candidate in candidates:
        cleaned = _clean_wikitext(candidate)
        lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
        for line in lines:
            if len(line) < 5:
                continue
            if len(line) > max_len:
                line = line[:max_len] + "..."
            return line

    return ""


# ============================================================
# 主流程
# ============================================================

def add_summary_column(conn: sqlite3.Connection):
    """确保 wiki_pages 有 summary 列。"""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(wiki_pages)").fetchall()}
    if "summary" not in cols:
        conn.execute("ALTER TABLE wiki_pages ADD COLUMN summary TEXT")
        conn.commit()
        print("✓ 新增 summary 列")
    else:
        print("  summary 列已存在")


def backfill_summaries(conn: sqlite3.Connection):
    """遍历所有 done 页面，提取摘要回填。"""
    rows = conn.execute("""
        SELECT page_id, title, file_path
        FROM wiki_pages
        WHERE status = 'done' AND file_path IS NOT NULL AND file_path != ''
          AND namespace = 0
          AND (summary IS NULL OR summary = '')
    """).fetchall()

    if not rows:
        print("  所有页面已有摘要，跳过")
        return

    print(f"  待处理 {len(rows)} 个页面...")
    updated = 0
    skipped = 0
    batch = []
    t0 = time.time()

    for i, (page_id, title, file_path) in enumerate(rows):
        path = file_path
        if not os.path.isabs(path):
            path = os.path.join(CACHE_DIR, os.path.basename(path))

        try:
            with open(path, "r", encoding="utf-8") as f:
                wikitext = f.read()
        except OSError:
            skipped += 1
            continue

        summary = extract_summary(wikitext)
        if not summary:
            skipped += 1
            continue

        batch.append((summary, page_id))
        updated += 1

        if len(batch) >= 500:
            conn.executemany("UPDATE wiki_pages SET summary = ? WHERE page_id = ?", batch)
            conn.commit()
            batch = []

        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t0
            print(f"    进度 {i+1}/{len(rows)} ({elapsed:.1f}s), 已更新 {updated}, 跳过 {skipped}")

    if batch:
        conn.executemany("UPDATE wiki_pages SET summary = ? WHERE page_id = ?", batch)
        conn.commit()

    elapsed = time.time() - t0
    print(f"  ✓ 完成：更新 {updated} 条, 跳过 {skipped} 条, 耗时 {elapsed:.1f}s")


def build_fts5(conn: sqlite3.Connection, rebuild: bool = False):
    """创建或重建 FTS5 虚拟表。"""
    existing = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='wiki_pages_fts'"
    ).fetchall()}

    if existing and rebuild:
        conn.execute("DROP TABLE wiki_pages_fts")
        conn.execute("DROP TABLE IF EXISTS wiki_pages_fts_config")
        conn.execute("DROP TABLE IF EXISTS wiki_pages_fts_content")
        conn.execute("DROP TABLE IF EXISTS wiki_pages_fts_data")
        conn.execute("DROP TABLE IF EXISTS wiki_pages_fts_docsize")
        conn.execute("DROP TABLE IF EXISTS wiki_pages_fts_idx")
        conn.commit()
        print("  ✓ 删除旧 FTS5 表")

    if not existing or rebuild:
        conn.execute("""
            CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(
                title, summary, content=wiki_pages, content_rowid=page_id
            )
        """)
        # 填充
        conn.execute("""
            INSERT INTO wiki_pages_fts(rowid, title, summary)
            SELECT page_id, title, COALESCE(summary, '')
            FROM wiki_pages
            WHERE status = 'done' AND namespace = 0
        """)
        conn.commit()

        count = conn.execute("SELECT count(*) FROM wiki_pages_fts").fetchone()[0]
        print(f"  ✓ FTS5 已创建，索引 {count} 条记录")
    else:
        count = conn.execute("SELECT count(*) FROM wiki_pages_fts").fetchone()[0]
        print(f"  FTS5 已存在（{count} 条记录）")


def verify_fts5(conn: sqlite3.Connection):
    """简单验证 FTS5 搜索。"""
    test_queries = ["击中要害", "威吓", "太晶化", "血月"]
    print("\n=== FTS5 验证 ===")
    for q in test_queries:
        rows = conn.execute("""
            SELECT wp.title, wp.summary
            FROM wiki_pages_fts fts
            JOIN wiki_pages wp ON wp.page_id = fts.rowid
            WHERE wiki_pages_fts MATCH ?
            LIMIT 3
        """, (q,)).fetchall()
        print(f"\n搜索「{q}」：")
        for title, summary in rows:
            print(f"  {title}: {summary[:80]}...")
        if not rows:
            print("  （无结果）")


def main():
    parser = argparse.ArgumentParser(description="补 wiki_pages.summary + 建 FTS5")
    parser.add_argument("--rebuild", action="store_true", help="重建 FTS5")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)

    print("=== Step 1: schema ===")
    add_summary_column(conn)

    print("\n=== Step 2: 提取摘要 ===")
    backfill_summaries(conn)

    print("\n=== Step 3: FTS5 ===")
    build_fts5(conn, rebuild=args.rebuild)

    verify_fts5(conn)

    conn.close()
    print("\n全部完成。")


if __name__ == "__main__":
    main()
