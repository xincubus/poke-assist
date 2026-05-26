#!/usr/bin/env python3
"""
补全 items.csv 中缺失的字段，生成 items_updated.csv

阶段1: 从 52poke 道具列表页补全 name_zh、name_ja、description_zh
阶段2: cloudscraper 访问52poke道具中文页，提取 interwiki-ja 跨语言链接（带缓存）
阶段3: undetected-chromedriver 模拟浏览器访问日文ポケモンWiki，用户手动过Cloudflare
阶段4: 解析日文道具说明，回写 CSV

用法：
  python supplement_items_csv.py              # 完整流程
  python supplement_items_csv.py --zh-only    # 只补中文（阶段1）
  python supplement_items_csv.py --ja-only    # 只补日文（阶段2-4）
  python supplement_items_csv.py --probe      # 日文只处理1个，确认HTML结构
  python supplement_items_csv.py --parse-only # 跳过爬取，只从缓存解析日文
"""

import csv
import sys
import time
import json
import argparse
import requests
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, unquote

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ========== 配置 ==========
BASE_DIR       = Path(__file__).parent
CSV_FILE       = BASE_DIR / "items.csv"
OUTPUT_CSV     = BASE_DIR / "items_updated.csv"
HTML_CACHE_DIR = BASE_DIR / "item_ja_cache"
URL_CACHE_FILE = BASE_DIR / "item_ja_urls.json"

LIST_URL   = "https://wiki.52poke.com/wiki/道具列表"
WIKI_BASE  = "https://wiki.52poke.com"
MAX_RETRIES   = 3
RETRY_DELAY   = 8
REQUEST_DELAY = 3
# ==========================

scraper_session = cloudscraper.create_scraper()
scraper_session.headers.update({
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
})


# ========== 阶段1：从52poke列表页补中文 ==========

def fetch_52poke_list():
    """抓取道具列表页，返回 {name_en: {name_zh, name_ja, description_zh}}"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(LIST_URL, headers=headers, timeout=20)
            r.encoding = "utf-8"
            if r.status_code != 200:
                print(f"[WARN] HTTP {r.status_code}，尝试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(2)
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            result = {}
            for table in soup.find_all("table"):
                for row in table.find_all("tr"):
                    cells = row.find_all(["td", "th"])
                    # 列结构：图标 | 中文名 | 日文名 | 英文名 | 说明
                    if len(cells) < 4:
                        continue
                    name_en = cells[3].get_text(strip=True)
                    if not name_en or name_en in ("英文", "English"):
                        continue
                    name_zh = cells[1].get_text(strip=True)
                    name_ja = cells[2].get_text(strip=True)
                    desc_zh = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                    if not name_zh:
                        continue
                    result[name_en] = {
                        "name_zh":        name_zh,
                        "name_ja":        name_ja,
                        "description_zh": desc_zh,
                    }
            print(f"[OK] 从道具列表页获取到 {len(result)} 条数据")
            return result
        except Exception as e:
            print(f"[ERROR] {e}，尝试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(2)
    return {}


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "-").replace("'", "").replace("\u2019", "")


def supplement_zh(data):
    """用52poke列表页补全 name_zh、name_ja、description_zh"""
    to_fix = [r for r in data if not r["name_zh"] or not r["description_zh"]]
    print(f"需要补充中文的条目：{len(to_fix)} 条")
    if not to_fix:
        print("中文数据已完整，跳过。")
        return 0

    print(f"\n正在抓取 {LIST_URL} ...")
    wiki_data = fetch_52poke_list()
    if not wiki_data:
        print("[ERROR] 未能获取道具列表数据。")
        return 0

    # 建立多种 key 的查找表
    wiki_map = {}
    for k, v in wiki_data.items():
        wiki_map[k] = v
        wiki_map[_normalize(k)] = v

    updated = 0
    not_found = []
    for row in data:
        if row["name_zh"] and row["description_zh"]:
            continue
        name_en = row["name_en"]
        info = (
            wiki_map.get(name_en) or
            wiki_map.get(_normalize(name_en)) or
            wiki_map.get(name_en.replace("-", " ").title()) or
            wiki_map.get(_normalize(name_en.replace("-", " ")))
        )
        if not info:
            not_found.append(name_en)
            continue
        changed = False
        for field, key in [("name_zh", "name_zh"), ("name_ja", "name_ja"), ("description_zh", "description_zh")]:
            if not row[field] and info.get(key):
                row[field] = info[key]
                changed = True
        if changed:
            updated += 1
            print(f"  [OK] id={row['id']} {name_en} → {row['name_zh']}")

    print(f"\n中文补全：更新 {updated} 条，未找到 {len(not_found)} 条")
    if not_found[:10]:
        print("  未找到示例：", not_found[:10])
    return updated


# ========== 日文链接缓存 ==========

def load_url_cache():
    if URL_CACHE_FILE.exists():
        return json.loads(URL_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_url_cache(cache):
    URL_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


# ========== 阶段2：从52poke提取日文wiki链接 ==========

def fetch_page_cloudscraper(url, retries=4):
    for attempt in range(retries):
        try:
            r = scraper_session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            time.sleep(REQUEST_DELAY)
            return r.text
        except Exception as e:
            print(f"  [WARN] 请求失败 {url}: {e}")
            if attempt < retries - 1:
                print(f"  {RETRY_DELAY}秒后重试 ({attempt+2}/{retries})...")
                time.sleep(RETRY_DELAY)
    return None


def find_ja_link(html):
    soup = BeautifulSoup(html, "html.parser")
    li = soup.find("li", class_="interwiki-ja")
    if li:
        a = li.find("a")
        if a and a.get("href"):
            return a["href"]
    a = soup.find("a", hreflang="ja")
    if a and a.get("href"):
        return a["href"]
    for a in soup.find_all("a"):
        if a.get_text(strip=True) == "日本語" and a.get("href", "").startswith("http"):
            return a["href"]
    return None


def collect_ja_urls(items):
    """返回 {name_en: ja_wiki_url}，命中缓存的直接跳过请求"""
    url_cache = load_url_cache()
    ja_urls = dict(url_cache)
    total = len(items)
    new_count = 0

    for idx, row in enumerate(items, 1):
        name_en = row["name_en"]
        name_zh = row["name_zh"]
        name_ja = row["name_ja"]

        if name_en in url_cache:
            print(f"[{idx}/{total}] [CACHE] {name_zh}: {url_cache[name_en]}")
            continue

        print(f"[{idx}/{total}] 获取日文链接: {name_zh} ({name_en})")
        html = None

        # 52poke 道具页面通常是 /wiki/<中文名>（道具）
        candidates = []
        if name_zh:
            candidates.append(f"{WIKI_BASE}/wiki/{name_zh}（道具）")
            candidates.append(f"{WIKI_BASE}/wiki/{name_zh}")
        candidates.append(f"{WIKI_BASE}/wiki/{name_en.replace('-', '_').replace(' ', '_')}")

        for url in candidates:
            html = fetch_page_cloudscraper(url)
            if html and len(html) > 2000:
                break

        if html:
            ja_link = find_ja_link(html)
            if ja_link:
                ja_urls[name_en] = url_cache[name_en] = ja_link
                new_count += 1
                print(f"  [OK] {ja_link}")
                save_url_cache(url_cache)
                continue

        # fallback：用日文名直接构造日文wiki链接
        if name_ja:
            fallback = f"https://wiki.xn--rckteqa2e.com/wiki/{name_ja}"
            ja_urls[name_en] = url_cache[name_en] = fallback
            new_count += 1
            print(f"  [FALLBACK] {fallback}")
            save_url_cache(url_cache)
        else:
            print(f"  [SKIP] 无日文名，跳过")

    if new_count:
        print(f"\n新增 {new_count} 条链接缓存 → {URL_CACHE_FILE}")
    return ja_urls


# ========== 阶段3：浏览器批量访问日文wiki ==========

def save_html_cache(name_en, html):
    HTML_CACHE_DIR.mkdir(exist_ok=True)
    safe = name_en.replace("/", "_").replace("\\", "_").replace("'", "_").replace("\u2019", "_")
    (HTML_CACHE_DIR / f"{safe}.html").write_text(html, encoding="utf-8")


def load_html_cache(name_en):
    safe = name_en.replace("/", "_").replace("\\", "_").replace("'", "_").replace("\u2019", "_")
    f = HTML_CACHE_DIR / f"{safe}.html"
    return f.read_text(encoding="utf-8") if f.exists() else None


def fetch_with_browser(url_dict):
    if not url_dict:
        return {}
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    results = {}
    print("\n  启动浏览器...")
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(300)
        driver.set_page_load_timeout(300)

        # 按域名分组，每个域名只需过一次 Cloudflare
        domains = {}
        for key, url in url_dict.items():
            domains.setdefault(urlparse(url).netloc, []).append((key, url))

        for domain, domain_urls in domains.items():
            first_key, first_url = domain_urls[0]
            print(f"\n  浏览器访问: {first_url}")
            try:
                driver.get(first_url)
            except Exception:
                pass
            time.sleep(5)
            print(f"  >>> 如果弹出 Cloudflare 验证，请手动完成 <<<")
            input("  [验证通过后按 Enter 继续]")

            html = driver.page_source
            if html and len(html) > 1000:
                results[first_key] = html
                save_html_cache(first_key, html)
                print(f"  [OK] {first_key} ({len(html)} 字符)")
            time.sleep(REQUEST_DELAY)

            for key, url in domain_urls[1:]:
                print(f"  浏览器访问: {url}")
                try:
                    driver.get(url)
                except Exception:
                    pass
                time.sleep(3)
                try:
                    html = driver.page_source
                    if html and len(html) > 1000:
                        results[key] = html
                        save_html_cache(key, html)
                        print(f"  [OK] {key} ({len(html)} 字符)")
                    else:
                        print(f"  [WARN] {key} 页面内容过短")
                except Exception as e:
                    print(f"  [FAIL] {key}: {e}")
                time.sleep(REQUEST_DELAY)
    finally:
        if driver:
            driver.quit()
            print("  浏览器已关闭\n")
    return results


# ========== 阶段4：解析日文道具说明 ==========

def parse_ja_item(html, name_en=""):
    """从日文wiki页面提取 name_ja 和 description_ja"""
    soup = BeautifulSoup(html, "html.parser")

    # 提取日文名：页面标题 <h1>
    name_ja = None
    h1 = soup.find("h1", id="firstHeading") or soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        # 去掉括号注释，如「モンスターボール（どうぐ）」→「モンスターボール」
        if "（" in text:
            text = text[:text.index("（")]
        if text:
            name_ja = text

    # 提取日文说明：找「ゲーム内説明」或「説明文」章节下的表格最后一行
    desc_ja = None
    for keyword in ["ゲーム内説明", "ゲームでの説明", "説明文", "どうぐの説明"]:
        for heading in soup.find_all(["h2", "h3"]):
            if keyword in heading.get_text(strip=True):
                cur = heading.find_next_sibling()
                while cur:
                    if cur.name in ["h2", "h3"]:
                        break
                    if cur.name == "table":
                        for row in reversed(cur.find_all("tr")):
                            cells = row.find_all(["td", "th"])
                            if len(cells) >= 2:
                                text = cells[-1].get_text(strip=True)
                                if text and len(text) >= 4:
                                    desc_ja = text
                                    break
                        if desc_ja:
                            break
                    if cur.name == "dl":
                        dds = cur.find_all("dd")
                        if dds:
                            text = dds[-1].get_text(strip=True)
                            if text and len(text) >= 4:
                                desc_ja = text
                                break
                    if cur.name == "p":
                        text = cur.get_text(strip=True)
                        if text and len(text) >= 4:
                            desc_ja = text
                            break
                    cur = cur.find_next_sibling()
                if desc_ja:
                    break
        if desc_ja:
            break

    if not desc_ja:
        print(f"  [WARN] {name_en}: 未找到日文说明")

    return name_ja, desc_ja


# ========== 日文补全主流程 ==========

def supplement_ja(data, probe=False, parse_only=False):
    """补全 name_ja 和 description_ja"""
    # 有中文名但缺日文名或日文说明的条目
    to_process = [r for r in data if r["name_zh"] and (not r["name_ja"] or not r["description_ja"])]
    print(f"需要补充日文的条目：{len(to_process)} 条")
    if not to_process:
        print("日文数据已完整，跳过。")
        return 0

    if probe:
        to_process = to_process[:1]
        print(f"[PROBE] 只处理: {to_process[0]['name_en']}")

    if not parse_only:
        print("\n=== 阶段2：收集日文wiki链接 ===\n")
        ja_urls = collect_ja_urls(to_process)
        print(f"\n收集到 {len(ja_urls)} 个链接\n")

        urls_to_fetch = {k: v for k, v in ja_urls.items()
                        if k in {r["name_en"] for r in to_process} and load_html_cache(k) is None}
        cached = len([r for r in to_process if load_html_cache(r["name_en"]) is not None])
        if cached:
            print(f"已有HTML缓存：{cached} 个，跳过")

        if urls_to_fetch:
            print(f"\n=== 阶段3：浏览器访问日文wiki（{len(urls_to_fetch)} 个） ===\n")
            fetch_with_browser(urls_to_fetch)
        else:
            print("\n所有页面已有缓存，跳过浏览器阶段\n")

    print("=== 阶段4：解析日文数据 ===\n")
    updated = 0
    for row in to_process:
        name_en = row["name_en"]
        html = load_html_cache(name_en)
        if not html:
            print(f"  [SKIP] {name_en}: 无缓存")
            continue
        name_ja, desc_ja = parse_ja_item(html, name_en)
        changed = False
        if name_ja and not row["name_ja"]:
            row["name_ja"] = name_ja
            changed = True
        if desc_ja and not row["description_ja"]:
            row["description_ja"] = desc_ja
            changed = True
        if changed:
            updated += 1
            print(f"  [OK] {name_en} → name_ja={row['name_ja']} desc={row['description_ja'][:30] if row['description_ja'] else ''}")

    print(f"\n成功更新：{updated}/{len(to_process)}")
    return updated


# ========== 主流程 ==========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zh-only",    action="store_true", help="只补中文（阶段1）")
    parser.add_argument("--ja-only",    action="store_true", help="只补日文（阶段2-4）")
    parser.add_argument("--probe",      action="store_true", help="日文只处理1个，确认HTML结构")
    parser.add_argument("--parse-only", action="store_true", help="跳过爬取，只从缓存解析日文")
    args = parser.parse_args()

    print("=" * 60)
    print("补全道具 CSV 缺失数据")
    print("=" * 60)

    # 优先读已有的 updated 文件（包含上次阶段1的结果）
    read_file = OUTPUT_CSV if OUTPUT_CSV.exists() else CSV_FILE
    print(f"读取：{read_file.name}")
    with open(read_file, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        data = list(reader)

    total_updated = 0

    if not args.ja_only:
        print("\n=== 阶段1：补全中文数据 ===\n")
        total_updated += supplement_zh(data)

    if not args.zh_only:
        print("\n=== 日文数据补全 ===\n")
        total_updated += supplement_ja(data, probe=args.probe, parse_only=args.parse_only)

    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n{'='*60}")
    print(f"共更新 {total_updated} 条，输出：{OUTPUT_CSV}")

    still = {
        "name_zh":        sum(1 for r in data if not r["name_zh"]),
        "name_ja":        sum(1 for r in data if not r["name_ja"]),
        "description_zh": sum(1 for r in data if not r["description_zh"]),
        "description_ja": sum(1 for r in data if not r["description_ja"]),
    }
    for k, v in still.items():
        if v:
            print(f"仍缺失 {k}：{v} 条")


if __name__ == "__main__":
    main()
