#!/usr/bin/env python3
"""
补全 moves.csv 中缺失的字段，生成 moves_updated.csv

阶段1: 从 52poke 招式列表页补全 name_zh、name_ja、description_zh
阶段2: cloudscraper 访问52poke招式中文页，提取 interwiki-ja 跨语言链接（带缓存）
       同时缓存52poke页面HTML，用于提取 effect_zh
阶段3: undetected-chromedriver 模拟浏览器访问日文ポケモンWiki，用户手动过Cloudflare
阶段4: 解析日文招式说明（description_ja）和效果（effect_ja），回写 CSV
阶段5: 从52poke缓存页面解析 effect_zh

用法：
  python supplement_moves_csv.py                # 完整流程
  python supplement_moves_csv.py --zh-only      # 只补中文（阶段1）
  python supplement_moves_csv.py --ja-only      # 只补日文（阶段2-4）
  python supplement_moves_csv.py --effect-only  # 只补效果描述（阶段2+5，effect_zh/effect_ja）
  python supplement_moves_csv.py --probe        # 日文只处理1个，确认HTML结构
  python supplement_moves_csv.py --parse-only   # 跳过爬取，只从缓存解析
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
from urllib.parse import urlparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ========== 配置 ==========
BASE_DIR       = Path(__file__).parent
OUTPUT_CSV     = BASE_DIR / 'moves_updated.csv'
CSV_FILE       = OUTPUT_CSV if OUTPUT_CSV.exists() else BASE_DIR / 'moves.csv'
HTML_CACHE_DIR = BASE_DIR / 'move_ja_cache'
ZH_CACHE_DIR   = BASE_DIR / 'move_zh_cache'
URL_CACHE_FILE = BASE_DIR / 'move_ja_urls.json'

LIST_URL   = 'https://wiki.52poke.com/wiki/招式列表'
WIKI_BASE  = 'https://wiki.52poke.com'
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
    """抓取52poke招式列表页，返回 {name_en: {name_zh, name_ja, description_zh}}"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(LIST_URL, headers=headers, timeout=20)
            r.encoding = 'utf-8'
            if r.status_code != 200:
                print(f"[WARN] HTTP {r.status_code}，尝试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(2)
                continue

            soup = BeautifulSoup(r.text, 'html.parser')
            result = {}
            for table in soup.find_all('table'):
                for row in table.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 5:
                        continue
                    # 跳过表头行
                    if cells[0].get_text(strip=True) in ('编号', '序号', ''):
                        continue
                    # 52poke招式列表列顺序：编号 | 中文名 | 日文名 | 英文名 | 属性 | 分类 | 威力 | 命中 | PP | 说明
                    name_en = cells[3].get_text(strip=True).strip('\u200e\u200f\u200b\ufeff')
                    if not name_en:
                        continue
                    desc_idx = 9 if len(cells) > 9 else len(cells) - 1
                    info = {
                        'name_zh':        cells[1].get_text(strip=True),
                        'name_ja':        cells[2].get_text(strip=True),
                        'description_zh': cells[desc_idx].get_text(strip=True),
                    }
                    result[name_en] = info
                    # 同时存连字符小写版本（如 "Dire Claw" → "dire-claw"）
                    result[name_en.lower().replace(' ', '-')] = info
            print(f"[OK] 从招式列表页获取到 {len(result)} 条数据")
            return result
        except Exception as e:
            print(f"[ERROR] {e}，尝试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(2)
    return {}


def supplement_zh(data):
    """用52poke列表页补全 name_zh、name_ja、description_zh"""
    to_fix = [r for r in data if not r['name_zh'] or not r['description_zh']]
    print(f"需要补充中文的条目：{len(to_fix)} 条")
    if not to_fix:
        print("中文数据已完整，跳过。")
        return 0

    print(f"\n正在抓取 {LIST_URL} ...")
    wiki_data = fetch_52poke_list()
    if not wiki_data:
        print("[ERROR] 未能获取招式列表数据。")
        return 0

    # 构建多种 key 的查找映射
    wiki_map = {}
    for k, v in wiki_data.items():
        wiki_map[k] = v
        wiki_map[k.lower()] = v
        wiki_map[k.lower().replace(' ', '-')] = v

    updated = 0
    not_found = []
    for row in data:
        if row['name_zh'] and row['description_zh']:
            continue
        name_en = row['name_en']
        name_en_norm = name_en.replace('\u2019', "'").replace('\u2018', "'")
        info = (
            wiki_map.get(name_en) or
            wiki_map.get(name_en_norm) or
            wiki_map.get(name_en.lower()) or
            wiki_map.get(name_en_norm.lower()) or
            wiki_map.get(name_en.replace(' ', '-').lower()) or
            wiki_map.get(name_en_norm.replace(' ', '-').lower())
        )
        if not info:
            not_found.append(name_en)
            continue
        changed = False
        for field, key in [('name_zh', 'name_zh'), ('name_ja', 'name_ja'), ('description_zh', 'description_zh')]:
            if not row[field] and info.get(key):
                row[field] = info[key]
                changed = True
        if changed:
            updated += 1
            print(f"  [OK] id={row['id']} {name_en} → {row['name_zh']}")

    print(f"\n中文补全：更新 {updated} 条，未找到 {len(not_found)} 条")
    if not_found:
        print("  未找到：" + ", ".join(not_found[:20]))
    return updated


# ========== 日文链接缓存 ==========

def load_url_cache():
    if URL_CACHE_FILE.exists():
        return json.loads(URL_CACHE_FILE.read_text(encoding='utf-8'))
    return {}


def save_url_cache(cache):
    URL_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


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


def collect_ja_urls(moves):
    """返回 {name_en: ja_wiki_url}，命中缓存的直接跳过请求"""
    url_cache = load_url_cache()
    ja_urls = dict(url_cache)
    total = len(moves)
    new_count = 0

    for idx, row in enumerate(moves, 1):
        name_en = row['name_en']
        name_zh = row['name_zh']
        name_ja = row['name_ja']

        if name_en in url_cache:
            print(f"[{idx}/{total}] [CACHE] {name_zh}: {url_cache[name_en]}")
            continue

        # 没有中文名也没有日文名，52poke 必然无页面，直接跳过
        if not name_zh and not name_ja:
            print(f"[{idx}/{total}] [SKIP] {name_en}: 无中日文名，跳过")
            continue
        print(f"[{idx}/{total}] 获取日文链接: {name_zh} ({name_en})")
        html = None
        for url_name in [name_zh, name_en.replace("'", "\u2019").replace(" ", "_"), name_en.replace(" ", "_")]:
            if not url_name:
                continue
            html = fetch_page_cloudscraper(f"{WIKI_BASE}/wiki/{url_name}")
            if html:
                break

        if html:
            ja_link = find_ja_link(html)
            if ja_link:
                ja_urls[name_en] = url_cache[name_en] = ja_link
                new_count += 1
                print(f"  [OK] {ja_link}")
                save_url_cache(url_cache)
                # 同时缓存52poke页面，供 effect_zh 解析使用
                if not load_zh_html_cache(name_en):
                    save_zh_html_cache(name_en, html)
                continue

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
    safe = name_en.replace('/', '_').replace('\\', '_').replace("'", '_').replace('\u2019', '_')
    (HTML_CACHE_DIR / f"{safe}.html").write_text(html, encoding='utf-8')


def load_html_cache(name_en):
    safe = name_en.replace('/', '_').replace('\\', '_').replace("'", '_').replace('\u2019', '_')
    f = HTML_CACHE_DIR / f"{safe}.html"
    return f.read_text(encoding='utf-8') if f.exists() else None


def save_zh_html_cache(name_en, html):
    ZH_CACHE_DIR.mkdir(exist_ok=True)
    safe = name_en.replace('/', '_').replace('\\', '_').replace("'", '_').replace('\u2019', '_')
    (ZH_CACHE_DIR / f"{safe}.html").write_text(html, encoding='utf-8')


def load_zh_html_cache(name_en):
    safe = name_en.replace('/', '_').replace('\\', '_').replace("'", '_').replace('\u2019', '_')
    f = ZH_CACHE_DIR / f"{safe}.html"
    return f.read_text(encoding='utf-8') if f.exists() else None


def fetch_with_browser(url_dict):
    if not url_dict:
        return {}
    import undetected_chromedriver as uc

    results = {}
    print("\n  启动浏览器...")
    options = uc.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.page_load_strategy = "eager"

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=145)
        driver.set_page_load_timeout(300)

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


# ========== 阶段4：解析日文招式说明 ==========

def parse_ja_description(html, name_en=""):
    """从日文ポケモンWiki页面提取招式说明文"""
    soup = BeautifulSoup(html, "html.parser")
    # 优先找"ゲーム内説明"或"説明文"章节下的表格
    for keyword in ['ゲーム内説明', 'ゲームでの説明', '説明文', '効果の説明']:
        for heading in soup.find_all(['h2', 'h3']):
            if keyword in heading.get_text(strip=True):
                cur = heading.find_next_sibling()
                while cur:
                    if cur.name in ['h2', 'h3']:
                        break
                    if cur.name == 'table':
                        # 取最后一行（最新世代）
                        for row in reversed(cur.find_all('tr')):
                            cells = row.find_all(['td', 'th'])
                            if len(cells) >= 2:
                                text = cells[-1].get_text(strip=True)
                                if text and len(text) >= 5:
                                    return text
                    if cur.name == 'dl':
                        dds = cur.find_all('dd')
                        if dds:
                            text = dds[-1].get_text(strip=True)
                            if text and len(text) >= 5:
                                return text
                    if cur.name == 'p':
                        text = cur.get_text(strip=True)
                        if text and len(text) >= 5:
                            return text
                    cur = cur.find_next_sibling()
    # fallback：找"効果"章节
    for heading in soup.find_all(['h2', 'h3']):
        if heading.get_text(strip=True) in ('効果', '技の効果', 'わざの効果'):
            p = heading.find_next_sibling('p')
            if p:
                text = p.get_text(strip=True)
                if text and len(text) >= 5:
                    return text
    print(f"  [WARN] {name_en}: 未找到日文说明")
    return None


def parse_ja_effect(html, name_en=""):
    """从日文ポケモンWiki页面提取招式效果（机制描述）"""
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.find_all(['h2', 'h3']):
        if heading.get_text(strip=True) in ('技の仕様', '効果', '技の効果', 'わざの効果', '効果・説明'):
            parts = []
            cur = heading.find_next_sibling()
            while cur:
                if cur.name in ['h2', 'h3']:
                    break
                if cur.name in ['ul', 'ol']:
                    items = [li.get_text(strip=True) for li in cur.find_all('li', recursive=False)]
                    if items:
                        parts.extend(items)
                elif cur.name == 'p':
                    text = cur.get_text(strip=True)
                    if text and len(text) >= 5:
                        parts.append(text)
                cur = cur.find_next_sibling()
            if parts:
                return '。'.join(parts)
    return None


def parse_zh_effect(html, name_en=""):
    """从52poke招式页面提取效果描述"""
    soup = BeautifulSoup(html, "html.parser")

    # 优先找"对战中"/"对战内"子章节
    for h in soup.find_all(['h2', 'h3', 'h4']):
        if h.get_text(strip=True) in ('对战中', '对战内'):
            parts = []
            cur = h.find_next_sibling()
            while cur:
                if cur.name in ['h2', 'h3', 'h4']:
                    break
                if cur.name == 'p':
                    text = cur.get_text(strip=True)
                    if text and len(text) >= 2:
                        parts.append(text)
                cur = cur.find_next_sibling()
            if parts:
                return ''.join(parts)

    # fallback：找"招式附加效果"章节下的 p 标签
    for h in soup.find_all(['h2', 'h3', 'h4']):
        if h.get_text(strip=True) in ('招式附加效果', '效果', '招式效果'):
            parts = []
            cur = h.find_next_sibling()
            while cur:
                if cur.name in ['h2', 'h3', 'h4']:
                    break
                if cur.name == 'p':
                    text = cur.get_text(strip=True)
                    if text and len(text) >= 2:
                        parts.append(text)
                cur = cur.find_next_sibling()
            if parts:
                return ''.join(parts)

    # fallback：找"游戏中"或"概述"章节第一个 p
    for h in soup.find_all(['h2', 'h3', 'h4']):
        if h.get_text(strip=True) in ('游戏中', '概述'):
            cur = h.find_next_sibling()
            while cur:
                if cur.name in ['h2', 'h3', 'h4']:
                    break
                if cur.name == 'p':
                    text = cur.get_text(strip=True)
                    if text and len(text) >= 5:
                        return text
                cur = cur.find_next_sibling()

    return None


def supplement_effects(data, parse_only=False):
    """补全 effect_zh 和 effect_ja"""
    to_process_zh = [r for r in data if not r.get('effect_zh')]
    to_process_ja = [r for r in data if not r.get('effect_ja')]
    print(f"需要补充 effect_zh：{len(to_process_zh)} 条")
    print(f"需要补充 effect_ja：{len(to_process_ja)} 条")

    all_to_process = {r['name_en'] for r in to_process_zh + to_process_ja}
    if not all_to_process:
        print("效果描述已完整，跳过。")
        return 0

    if not parse_only:
        # 对没有 zh 缓存的条目直接爬取52poke单页
        need_fetch = [r for r in to_process_zh if not load_zh_html_cache(r['name_en'])
                      and r['name_zh'] and not r['name_en'].startswith('shadow-')]
        if need_fetch:
            print(f"\n=== 爬取52poke单页（{len(need_fetch)} 个，用于 effect_zh） ===\n")
            for idx, row in enumerate(need_fetch, 1):
                name_en = row['name_en']
                name_zh = row['name_zh']
                print(f"[{idx}/{len(need_fetch)}] {name_zh} ({name_en})")
                html = None
                for url_name in [name_zh, name_en.replace('-', '_'), name_en]:
                    if not url_name: continue
                    html = fetch_page_cloudscraper(f"{WIKI_BASE}/wiki/{url_name}")
                    if html and len(html) > 1000:
                        break
                if html and len(html) > 1000:
                    save_zh_html_cache(name_en, html)
                    print(f"  [OK] 已缓存")
                else:
                    print(f"  [SKIP] 获取失败")

    updated = 0

    # 解析 effect_zh
    for row in to_process_zh:
        name_en = row['name_en']
        html = load_zh_html_cache(name_en)
        if not html:
            continue
        effect = parse_zh_effect(html, name_en)
        if effect:
            row['effect_zh'] = effect
            updated += 1
            print(f"  [ZH] {name_en}: {effect[:50]}")

    # 解析 effect_ja
    for row in to_process_ja:
        name_en = row['name_en']
        html = load_html_cache(name_en)
        if not html:
            continue
        effect = parse_ja_effect(html, name_en)
        if effect:
            row['effect_ja'] = effect
            updated += 1
            print(f"  [JA] {name_en}: {effect[:50]}")

    print(f"\n效果描述更新：{updated} 条")
    return updated


def supplement_ja(data, probe=False, parse_only=False):
    """补全 description_ja"""
    to_process = [r for r in data if r['name_zh'] and not r['description_ja']]
    print(f"需要补充 description_ja：{len(to_process)} 条")
    if not to_process:
        print("日文说明已完整，跳过。")
        return 0

    if probe:
        to_process = to_process[:1]
        print(f"[PROBE] 只处理: {to_process[0]['name_en']}")

    if not parse_only:
        print("\n=== 阶段2：收集日文wiki链接 ===\n")
        ja_urls = collect_ja_urls(to_process)
        print(f"\n收集到 {len(ja_urls)} 个链接\n")

        urls_to_fetch = {k: v for k, v in ja_urls.items() if load_html_cache(k) is None}
        cached = len(ja_urls) - len(urls_to_fetch)
        if cached:
            print(f"已有HTML缓存：{cached} 个，跳过")

        if urls_to_fetch:
            print(f"\n=== 阶段3：浏览器访问日文wiki（{len(urls_to_fetch)} 个） ===\n")
            fetch_with_browser(urls_to_fetch)
        else:
            print("\n所有页面已有缓存，跳过浏览器阶段\n")

    print("=== 阶段4：解析日文说明 ===\n")
    ja_desc_map = {}
    for row in to_process:
        name_en = row['name_en']
        html = load_html_cache(name_en)
        if not html:
            print(f"  [SKIP] {name_en}: 无缓存")
            continue
        desc = parse_ja_description(html, name_en)
        if desc:
            ja_desc_map[name_en] = desc
            print(f"  [OK] {name_en}: {desc[:50]}")

    print(f"\n成功解析：{len(ja_desc_map)}/{len(to_process)}")

    updated = 0
    for row in data:
        if row['name_en'] in ja_desc_map and not row['description_ja']:
            row['description_ja'] = ja_desc_map[row['name_en']]
            updated += 1
    return updated


# ========== 主流程 ==========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zh-only',     action='store_true', help='只补中文（阶段1）')
    parser.add_argument('--ja-only',     action='store_true', help='只补日文（阶段2-4）')
    parser.add_argument('--effect-only', action='store_true', help='只补效果描述（effect_zh/effect_ja）')
    parser.add_argument('--probe',       action='store_true', help='日文只处理1个，确认HTML结构')
    parser.add_argument('--parse-only',  action='store_true', help='跳过爬取，只从缓存解析')
    args = parser.parse_args()

    print("=" * 60)
    print("补全招式 CSV 缺失数据")
    print("=" * 60)

    with open(CSV_FILE, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        data = list(reader)

    # 兼容旧版 CSV（没有 effect_* 列）
    for row in data:
        row.setdefault('effect_ja', '')
        row.setdefault('effect_zh', '')
        row.setdefault('effect_en', '')

    total_updated = 0

    if args.effect_only:
        print("\n=== 效果描述补全 ===\n")
        total_updated += supplement_effects(data, parse_only=args.parse_only)
    else:
        if not args.ja_only:
            print("\n=== 阶段1：补全中文数据 ===\n")
            total_updated += supplement_zh(data)

        if not args.zh_only:
            print("\n=== 日文说明补全 ===\n")
            total_updated += supplement_ja(data, probe=args.probe, parse_only=args.parse_only)

            print("\n=== 效果描述补全 ===\n")
            total_updated += supplement_effects(data, parse_only=args.parse_only)

    # 确保输出包含所有字段
    out_fields = list(fieldnames)
    for f in ['effect_ja', 'effect_zh', 'effect_en']:
        if f not in out_fields:
            out_fields.append(f)

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)

    print(f"\n{'='*60}")
    print(f"共更新 {total_updated} 条，输出：{OUTPUT_CSV}")

    still = {
        'name_zh':        sum(1 for r in data if not r['name_zh']),
        'description_zh': sum(1 for r in data if not r['description_zh']),
        'description_ja': sum(1 for r in data if not r['description_ja']),
        'effect_zh':      sum(1 for r in data if not r['effect_zh']),
        'effect_ja':      sum(1 for r in data if not r['effect_ja']),
        'effect_en':      sum(1 for r in data if not r['effect_en']),
    }
    for k, v in still.items():
        if v:
            print(f"仍缺失 {k}：{v} 条")


if __name__ == '__main__':
    main()
