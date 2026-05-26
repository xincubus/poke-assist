"""
从 52poke wiki 多个分类爬取术语页面 HTML 到本地缓存。

用法：
    python scrape_wiki_terms.py              # 爬取全部分类（跳过已缓存）
    python scrape_wiki_terms.py --force       # 强制重新爬取
    python scrape_wiki_terms.py --list-only   # 只列出页面，不下载
    python scrape_wiki_terms.py --cat 术语    # 只爬指定分类
"""

import os
import re
import json
import time
import argparse
import hashlib
from urllib.parse import quote, unquote, urljoin
import requests

BASE_URL = "https://wiki.52poke.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "html_cache")
INDEX_FILE = os.path.join(SCRIPT_DIR, "page_index.json")

CATEGORIES = [
    "术语",
    "游戏系统",
    "状态变化",
    "特性",
    "属性",
    "宝可梦对战",
    "宝可梦特殊能力",
    "地形",
    "招式",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

DELAY = 1.5  # 请求间隔秒数，对 wiki 友好


def safe_filename(title: str) -> str:
    h = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)[:80]
    return f"{safe}_{h}.html"


def fetch_category_pages(category: str, seen: set) -> list[dict]:
    """从指定分类提取所有页面链接，支持分页。跳过 seen 中已有的。"""
    pages = []
    url = BASE_URL + "/wiki/Category:" + quote(category)

    while url:
        print(f"  分类页: {unquote(url)}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 403:
                print(f"  !! 分页被 403，停止该分类（已收集 {len(pages)} 页）")
                break
            raise
        html = resp.text

        # 提取页面链接（在 mw-pages 区域内）
        pages_section = re.search(
            r'<div id="mw-pages">(.*?)(?=<div id="mw-subcategories"|<div class="printfooter")',
            html, re.DOTALL
        )
        if not pages_section:
            pages_section = re.search(r'<div id="mw-pages">(.*)', html, re.DOTALL)

        if pages_section:
            links = re.findall(
                r'<a[^>]*href="(/wiki/[^"]+)"[^>]*title="([^"]+)"',
                pages_section.group(1)
            )
            for href, title in links:
                if "Category:" in href or "User:" in title:
                    continue
                if title not in seen:
                    seen.add(title)
                    pages.append({
                        "title": title,
                        "url": BASE_URL + href,
                        "path": href,
                        "category": category,
                    })

        # 检查"下一页"链接
        next_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>下一页</a>', html)
        if next_match:
            next_href = next_match.group(1).replace("&amp;", "&")
            url = urljoin(BASE_URL, next_href)
            time.sleep(DELAY)
        else:
            url = None

    return pages


def download_pages(pages: list[dict], force: bool = False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    total = len(pages)
    downloaded = 0
    skipped = 0

    for i, page in enumerate(pages, 1):
        filename = safe_filename(page["title"])
        filepath = os.path.join(CACHE_DIR, filename)
        page["cache_file"] = filename

        if os.path.exists(filepath) and not force:
            skipped += 1
            continue

        print(f"[{i}/{total}] 下载: {page['title']}")
        try:
            resp = requests.get(page["url"], headers=HEADERS, timeout=30)
            resp.raise_for_status()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(resp.text)
            downloaded += 1
            time.sleep(DELAY)
        except Exception as e:
            print(f"  !! 失败: {e}")
            page["error"] = str(e)

    print(f"\n完成: 下载 {downloaded}, 跳过 {skipped}, 总计 {total}")


def save_index(pages: list[dict]):
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    print(f"索引已保存: {INDEX_FILE} ({len(pages)} 条)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="强制重新下载")
    parser.add_argument("--list-only", action="store_true", help="只列出页面不下载")
    parser.add_argument("--cat", type=str, default=None, help="只爬指定分类")
    args = parser.parse_args()

    cats = [args.cat] if args.cat else CATEGORIES
    all_pages = []
    seen = set()

    # 加载已有索引，保留之前的 cache_file 映射
    existing = {}
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for item in json.load(f):
                existing[item["title"]] = item

    for cat in cats:
        print(f"\n=== Category:{cat} ===")
        pages = fetch_category_pages(cat, seen)
        print(f"  新增 {len(pages)} 页")
        all_pages.extend(pages)

    # 合并已有索引中的 cache_file 信息
    for page in all_pages:
        if page["title"] in existing:
            old = existing[page["title"]]
            if "cache_file" in old:
                page["cache_file"] = old["cache_file"]

    print(f"\n总计 {len(all_pages)} 个页面（去重后）\n")

    if args.list_only:
        by_cat = {}
        for p in all_pages:
            by_cat.setdefault(p["category"], []).append(p["title"])
        for cat, titles in by_cat.items():
            print(f"[{cat}] {len(titles)} 页")
            for t in titles[:5]:
                print(f"  {t}")
            if len(titles) > 5:
                print(f"  ... 等 {len(titles)} 页")
        return

    download_pages(all_pages, force=args.force)
    save_index(all_pages)


if __name__ == "__main__":
    main()
