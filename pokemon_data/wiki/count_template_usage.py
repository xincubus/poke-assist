"""
扫 wikitext_cache 里的内容页，统计每个模板被引用的频次。

输出两维：
  1. page_count —— 有多少个不同页面引用了该模板（更反映"重要性"）
  2. call_count —— 总调用次数（一个页面里多次调用算多次）

按 wiki_templates 表里的 category 分组显示，方便人肉决策：
  - unknown 高频 → 优先分类
  - semantic/infobox/inline/drop 高频 → 验证现有分类质量

用法：
    # 全量扫（45K 页，预计 10-30 分钟）
    python count_template_usage.py

    # 只扫前 N 页（抽样）
    python count_template_usage.py --limit 2000

    # 只看 unknown 高频榜
    python count_template_usage.py --list unknown --top 100

    # 把结果保存到 CSV
    python count_template_usage.py --csv template_usage.csv
"""

import argparse
import csv
import os
import sqlite3
import sys
import time
from collections import defaultdict

import mwparserfromhell


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")
CACHE_DIR = os.path.join(SCRIPT_DIR, "wikitext_cache")


def normalize_template_name(name: str) -> str:
    """MediaWiki Template namespace 是 first-letter case —— 首字母自动大写。

    对 ASCII 首字母做 upper，中文等非 ASCII 字符保留原样。
    把空白 strip 掉。"""
    n = name.strip()
    if not n:
        return n
    first = n[0]
    if first.isascii() and first.isalpha():
        return first.upper() + n[1:]
    return n


def load_classifications(conn) -> dict:
    """从 wiki_templates 加载分类。key 用 normalize 后的名字。"""
    rows = conn.execute(
        "SELECT name, COALESCE(category, 'unknown') FROM wiki_templates"
    ).fetchall()
    return {normalize_template_name(name): cat for name, cat in rows}


def iter_content_pages(conn, limit=None):
    q = ("SELECT page_id, title, file_path FROM wiki_pages "
         "WHERE namespace = 0 AND status = 'done' AND file_path IS NOT NULL")
    if limit:
        q += f" LIMIT {int(limit)}"
    return conn.execute(q).fetchall()


def scan_page(path: str):
    """返回这个页面里每个模板名的调用次数（key 已 normalize）。"""
    counts = defaultdict(int)
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return counts
    try:
        code = mwparserfromhell.parse(src)
    except Exception:
        return counts
    for tpl in code.filter_templates(recursive=True):
        name = normalize_template_name(str(tpl.name))
        if not name or name.startswith("#"):
            continue
        counts[name] += 1
    return counts


def fmt_int(n: int) -> str:
    return f"{n:>7}"


def main():
    parser = argparse.ArgumentParser(description="统计 Template 被 wiki 内容页引用的频次")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--cache-dir", default=CACHE_DIR)
    parser.add_argument("--limit", type=int, help="只扫前 N 个内容页（抽样）")
    parser.add_argument("--top", type=int, default=50, help="显示前 N 条（默认 50）")
    parser.add_argument("--list", dest="filter_cat",
                        choices=["unknown", "semantic", "infobox", "inline", "drop", "all"],
                        default="all", help="只列某分类（默认 all 分组显示）")
    parser.add_argument("--csv", help="把完整结果保存到 CSV")
    parser.add_argument("--progress", type=int, default=2000, help="进度报告间隔（页数）")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    categories = load_classifications(conn)
    print(f"已加载 {len(categories)} 条分类")

    pages = iter_content_pages(conn, limit=args.limit)
    pages = list(pages)
    total = len(pages)
    print(f"准备扫描 {total} 个内容页")

    call_counts = defaultdict(int)
    page_counts = defaultdict(int)
    t0 = time.time()
    for i, (page_id, title, file_path) in enumerate(pages, 1):
        per_page = scan_page(file_path)
        for name, c in per_page.items():
            call_counts[name] += c
            page_counts[name] += 1
        if i % args.progress == 0:
            elapsed = time.time() - t0
            speed = i / max(elapsed, 1e-6)
            eta = (total - i) / max(speed, 1e-6)
            print(f"  [{i}/{total}] {speed:.0f} 页/秒  ETA {int(eta)}s  "
                  f"已统计 {len(call_counts)} 个模板")

    elapsed = time.time() - t0
    print(f"\n扫描完成：{total} 页，耗时 {elapsed:.1f}s，发现 {len(call_counts)} 个不同模板\n")

    # 按分类聚合
    by_cat = defaultdict(list)   # cat -> [(name, page_count, call_count), ...]
    for name, pc in page_counts.items():
        cat = categories.get(name, "unknown")
        by_cat[cat].append((name, pc, call_counts[name]))
    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: (-x[1], -x[2]))

    # 展示
    if args.filter_cat == "all":
        order = ["unknown", "semantic", "infobox", "inline", "drop"]
        for cat in order:
            rows = by_cat.get(cat, [])
            if not rows:
                continue
            total_pc = sum(r[1] for r in rows)
            print(f"─── {cat} ({len(rows)} 个模板，总页引用 {total_pc}) ───")
            print(f"{'pages':>7} {'calls':>7}  name")
            for name, pc, cc in rows[:args.top]:
                print(f"{fmt_int(pc)} {fmt_int(cc)}  {name}")
            if len(rows) > args.top:
                print(f"  ... 另有 {len(rows) - args.top} 个未显示")
            print()
    else:
        rows = by_cat.get(args.filter_cat, [])
        print(f"─── {args.filter_cat}（前 {args.top} / 共 {len(rows)}）───")
        print(f"{'pages':>7} {'calls':>7}  name")
        for name, pc, cc in rows[:args.top]:
            print(f"{fmt_int(pc)} {fmt_int(cc)}  {name}")

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "category", "page_count", "call_count"])
            all_rows = [(n, categories.get(n, "unknown"), pc, call_counts[n])
                        for n, pc in page_counts.items()]
            all_rows.sort(key=lambda r: (-r[2], -r[3]))
            w.writerows(all_rows)
        print(f"\n完整结果已写入 {args.csv}（{len(all_rows)} 行）")

    conn.close()


if __name__ == "__main__":
    main()
