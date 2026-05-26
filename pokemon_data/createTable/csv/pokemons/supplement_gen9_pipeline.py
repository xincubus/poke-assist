#!/usr/bin/env python3
"""
补充第九世代（图鉴编号900+）的中日文图鉴说明 — 联合管道

将两个阶段串联执行：
  步骤1: 从52poke爬取中日文图鉴说明（原 supplement_gen9_descriptions_v2.py）
  步骤2: 从日文ポケモンWiki补充日文图鉴说明（原 supplement_gen9_ja_descriptions.py）

用法：
  python supplement_gen9_pipeline.py              # 依次执行步骤1和步骤2
  python supplement_gen9_pipeline.py --step1-only # 只执行步骤1（52poke中日文）
  python supplement_gen9_pipeline.py --step2-only # 只执行步骤2（日文wiki）
  python supplement_gen9_pipeline.py --probe      # 步骤2只处理1个，用于确认HTML结构
  python supplement_gen9_pipeline.py --parse-only  # 步骤2跳过爬取，只从缓存HTML解析
"""

import csv
import os
import sys
import time
import argparse
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ========== 配置参数 ==========
BASE_DIR = Path(__file__).parent
CSV_FILE = BASE_DIR / 'pokemon_data.csv'
OUTPUT_FILE = BASE_DIR / 'pokemon_data_gen9_updated.csv'
PROGRESS_FILE_STEP1 = BASE_DIR / 'gen9_progress.txt'
PROGRESS_FILE_STEP2 = BASE_DIR / 'gen9_ja_progress.txt'
HTML_CACHE_DIR = BASE_DIR.parent.parent.parent / 'pokemon' / 'ja_wiki_cache'

# 爬取配置
MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_DELAY = 3
SAVE_INTERVAL = 10

# 步骤2 专用配置
WIKI_BASE = "https://wiki.52poke.com"
SV_VERSIONS = ['スカーレット', 'バイオレット']
# ==============================


# ============================================================
#  步骤1: 从52poke爬取中日文图鉴说明
# ============================================================

def _step1_load_progress():
    if PROGRESS_FILE_STEP1.exists():
        with open(PROGRESS_FILE_STEP1, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    return set()


def _step1_save_progress(pokemon_name):
    with open(PROGRESS_FILE_STEP1, 'a', encoding='utf-8') as f:
        f.write(f"{pokemon_name}\n")


def _fetch_description_from_52poke(pokemon_name_zh):
    """从52poke获取图鉴说明，返回 (日文图鉴说明, 中文图鉴说明)"""
    base_name = pokemon_name_zh.split('（')[0]
    url = f"https://wiki.52poke.com/wiki/{base_name}"

    for attempt in range(MAX_RETRIES):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'

            if response.status_code == 404:
                print(f"  [WARN] 页面不存在 (404)")
                return None, None
            if response.status_code != 200:
                print(f"  [WARN] HTTP {response.status_code} (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None, None

            soup = BeautifulSoup(response.text, 'html.parser')

            # 查找"图鉴介绍"标题
            target_heading = None
            for heading in soup.find_all(['h2', 'h3']):
                span = heading.find('span', id=lambda x: x and '图鉴介绍' in x)
                if span:
                    target_heading = heading
                    break

            if not target_heading:
                print(f"  [WARN] 未找到'图鉴介绍'标题 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None, None

            # 查找标题后的表格
            current = target_heading.find_next_sibling()
            pokedex_table = None
            while current:
                if current.name == 'table':
                    pokedex_table = current
                    break
                elif current.name in ['h2', 'h3']:
                    break
                current = current.find_next_sibling()

            if not pokedex_table:
                print(f"  [WARN] 未找到图鉴表格 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None, None

            # 提取表格数据
            # 52poke 的图鉴表格结构复杂（250+行、360+列），
            # 图鉴说明散布在各列中，需要遍历所有单元格而非只取最后一列
            rows = pokedex_table.find_all('tr')
            descriptions_ja = []
            descriptions_zh = []

            for row in rows:
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    desc = cell.get_text(strip=True)
                    if not desc or len(desc) < 20:
                        continue
                    # 跳过模板占位符和标题性文本
                    if '{{{' in desc or ('世代' in desc and len(desc) > 100):
                        continue

                    has_hiragana = any('\u3040' <= c <= '\u309F' for c in desc)
                    has_katakana = any('\u30A0' <= c <= '\u30FF' for c in desc)
                    kanji_count = sum(1 for c in desc if '\u4E00' <= c <= '\u9FFF')
                    total_chars = len(desc)

                    if has_hiragana or has_katakana:
                        if desc not in descriptions_ja:
                            descriptions_ja.append(desc)
                    elif kanji_count > 0 and kanji_count / total_chars > 0.3:
                        if desc not in descriptions_zh:
                            descriptions_zh.append(desc)

            ja_desc = descriptions_ja[-1] if descriptions_ja else None
            zh_desc = descriptions_zh[-1] if descriptions_zh else None
            if ja_desc or zh_desc:
                return ja_desc, zh_desc
            else:
                print(f"  [WARN] 未提取到图鉴说明 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None, None

        except requests.Timeout:
            print(f"  [TIMEOUT] 请求超时 (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None, None
        except Exception as e:
            print(f"  [ERROR] 爬取失败: {e} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None, None

    return None, None


def run_step1():
    """步骤1: 从52poke爬取中日文图鉴说明"""
    print("=" * 60)
    print("步骤1: 补充第九世代图鉴说明（52poke中日文）")
    print("=" * 60)
    print()

    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        data = list(reader)

    processed = _step1_load_progress()

    to_process = []
    for row in data:
        pokedex_id = int(row['图鉴编号'])
        if pokedex_id >= 900:
            if not row['中文图鉴说明'] or not row['日文图鉴说明']:
                if row['中文名'] not in processed:
                    to_process.append(row)

    print(f"需要补充图鉴说明的宝可梦: {len(to_process)}个")
    print(f"已处理: {len(processed)}个")
    print()

    if not to_process:
        print("所有图鉴说明都已完整！")
        return

    updated_count = 0
    for i, row in enumerate(to_process, 1):
        pokemon_name = row['中文名']
        pokedex_id = row['图鉴编号']
        print(f"[{i}/{len(to_process)}] {pokedex_id} {pokemon_name}")

        ja_desc, zh_desc = _fetch_description_from_52poke(pokemon_name)

        updated_this = False
        if ja_desc and not row['日文图鉴说明']:
            row['日文图鉴说明'] = ja_desc
            updated_this = True
            print(f"  [OK] 日文图鉴已更新")
        if zh_desc and not row['中文图鉴说明']:
            row['中文图鉴说明'] = zh_desc
            updated_this = True
            print(f"  [OK] 中文图鉴已更新")
        if not updated_this:
            print(f"  [WARN] 未找到图鉴说明")

        _step1_save_progress(pokemon_name)
        if i % SAVE_INTERVAL == 0:
            print(f"\n[SAVE] 保存中间结果...")
            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            print(f"已保存到 {OUTPUT_FILE}\n")
        if updated_this:
            updated_count += 1
        if i < len(to_process):
            time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print("保存最终结果...")
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"步骤1完成！更新了 {updated_count} 个宝可梦的图鉴说明")
    print(f"输出文件: {OUTPUT_FILE}")


# ============================================================
#  步骤2: 从日文ポケモンWiki补充日文图鉴说明
# ============================================================

def _get_base_name(chinese_name):
    """去掉形态后缀（全角括号），取基础名"""
    return chinese_name.split('（')[0]


def _step2_load_progress():
    if PROGRESS_FILE_STEP2.exists():
        with open(PROGRESS_FILE_STEP2, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def _step2_save_progress(name):
    with open(PROGRESS_FILE_STEP2, 'a', encoding='utf-8') as f:
        f.write(f"{name}\n")


def _fetch_page_cloudscraper(url, session, retries=4):
    """使用 cloudscraper 请求页面"""
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            time.sleep(REQUEST_DELAY)
            return r.text
        except Exception as e:
            print(f"  [WARN] 请求失败 {url}: {e}")
            if attempt < retries - 1:
                print(f"  8秒后重试 (第 {attempt + 2}/{retries} 次)...")
                time.sleep(8)
            else:
                print(f"  [FAIL] 重试 {retries} 次后仍失败，跳过")
    return None


def _find_ja_link(html):
    """从52poke中文页面提取日文wiki跨语言链接"""
    soup = BeautifulSoup(html, "html.parser")
    li = soup.find("li", class_="interwiki-ja")
    if li:
        a_tag = li.find("a")
        if a_tag and a_tag.get("href"):
            return a_tag["href"]
    a_tag = soup.find("a", hreflang="ja")
    if a_tag and a_tag.get("href"):
        return a_tag["href"]
    for a_tag in soup.find_all("a"):
        text = a_tag.get_text(strip=True)
        href = a_tag.get("href", "")
        if text == "日本語" and href.startswith("http"):
            return href
    return None

def _collect_ja_urls(grouped_pokemon, session):
    """阶段1：对每个基础名，从52poke提取日文wiki链接"""
    ja_urls = {}
    total = len(grouped_pokemon)
    for idx, (base_name, info) in enumerate(grouped_pokemon.items(), 1):
        ja_name = info['ja_name']
        print(f"[{idx}/{total}] 获取日文链接: {base_name} ({ja_name})")
        zh_url = f"{WIKI_BASE}/wiki/{base_name}"
        html = _fetch_page_cloudscraper(zh_url, session)
        if html:
            ja_link = _find_ja_link(html)
            if ja_link:
                ja_urls[base_name] = ja_link
                print(f"  [OK] 找到日文链接: {ja_link}")
                continue
        fallback_url = f"https://wiki.xn--rckteqa2e.com/wiki/{ja_name}"
        ja_urls[base_name] = fallback_url
        print(f"  [FALLBACK] 使用日文名构造: {fallback_url}")
    return ja_urls


def _save_html_cache(base_name, html):
    HTML_CACHE_DIR.mkdir(exist_ok=True)
    safe_name = base_name.replace('/', '_').replace('\\', '_')
    cache_file = HTML_CACHE_DIR / f"{safe_name}.html"
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(html)


def _load_html_cache(base_name):
    safe_name = base_name.replace('/', '_').replace('\\', '_')
    cache_file = HTML_CACHE_DIR / f"{safe_name}.html"
    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()
    return None


def _fetch_with_browser(url_dict):
    """使用 undetected-chromedriver 批量获取日文wiki页面"""
    if not url_dict:
        return {}
    import undetected_chromedriver as uc

    results = {}
    print("\n  启动浏览器下载日文wiki页面...")
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
            domain = urlparse(url).netloc
            if domain not in domains:
                domains[domain] = []
            domains[domain].append((key, url))

        for domain, domain_urls in domains.items():
            first_key, first_url = domain_urls[0]
            print(f"\n  浏览器访问: {first_url}")
            try:
                driver.get(first_url)
            except Exception:
                pass
            time.sleep(5)
            print(f"  >>> 如果浏览器弹出了 Cloudflare 验证，请手动完成 <<<")
            print(f"  >>> 验证通过后，回到终端按 Enter 继续... <<<")
            input("  [按 Enter 继续]")

            html = driver.page_source
            if html and len(html) > 1000:
                results[first_key] = html
                _save_html_cache(first_key, html)
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
                        _save_html_cache(key, html)
                        print(f"  [OK] {key} ({len(html)} 字符)")
                    else:
                        print(f"  [WARN] {key} 页面内容过短，跳过")
                except Exception as e:
                    print(f"  [FAIL] {key}: {e}")
                time.sleep(REQUEST_DELAY)
    finally:
        if driver:
            driver.quit()
            print("  浏览器已关闭\n")
    return results

def _parse_ja_description(html, base_name=""):
    """从日文ポケモンWiki HTML中提取图鉴说明，优先取朱紫版本"""
    soup = BeautifulSoup(html, "html.parser")
    target_heading = None
    for heading in soup.find_all(['h2', 'h3']):
        text = heading.get_text(strip=True)
        if ('ずかん' in text and '説明' in text) or ('図鑑' in text and '説明' in text):
            target_heading = heading
            break
    if not target_heading:
        print(f"  [WARN] {base_name}: 未找到图鉴说明标题")
        return None

    dl = target_heading.find_next_sibling('dl')
    if not dl:
        print(f"  [WARN] {base_name}: 标题后未找到 <dl> 元素")
        return None

    descriptions = []
    for dt in dl.find_all('dt'):
        version = dt.get_text(strip=True)
        dd = dt.find_next_sibling('dd')
        if dd:
            text = dd.get_text(strip=True)
            if text and len(text) >= 10:
                is_sv = any(ver in version for ver in SV_VERSIONS)
                descriptions.append({'version': version, 'text': text, 'is_sv': is_sv})

    if not descriptions:
        print(f"  [WARN] {base_name}: <dl> 中未找到图鉴说明")
        return None

    sv_descs = [d for d in descriptions if d['is_sv']]
    return sv_descs[0]['text'] if sv_descs else descriptions[-1]['text']


def run_step2(probe=False, parse_only=False):
    """步骤2: 从日文ポケモンWiki补充日文图鉴说明"""
    print()
    print("=" * 60)
    print("步骤2: 补充第九世代日文图鉴说明（日文Wiki）")
    print("=" * 60)
    print()

    import cloudscraper
    session = cloudscraper.create_scraper()
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
    })

    # 读取CSV（使用步骤1的输出文件）
    csv_file = OUTPUT_FILE if OUTPUT_FILE.exists() else CSV_FILE
    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        data = list(reader)

    to_process = []
    for row in data:
        pokedex_id = int(row['图鉴编号'])
        if pokedex_id >= 900 and not row['日文图鉴说明']:
            to_process.append(row)

    print(f"需要补充日文图鉴的宝可梦: {len(to_process)} 个")
    if not to_process:
        print("所有日文图鉴说明都已完整！")
        return

    # 按基础名分组去重
    grouped = {}
    for row in to_process:
        base_name = _get_base_name(row['中文名'])
        if base_name not in grouped:
            grouped[base_name] = {'ja_name': _get_base_name(row['日文名']), 'rows': []}
        grouped[base_name]['rows'].append(row)

    print(f"去重后基础宝可梦: {len(grouped)} 个")
    print()

    if probe:
        first_key = next(iter(grouped))
        grouped = {first_key: grouped[first_key]}
        print(f"[PROBE模式] 只处理: {first_key}\n")

    if not parse_only:
        # 先检查哪些已有缓存，只对没缓存的去获取日文wiki链接
        need_fetch = {}
        cached_count = 0
        for base_name, info in grouped.items():
            if _load_html_cache(base_name) is not None:
                cached_count += 1
            else:
                need_fetch[base_name] = info

        if cached_count:
            print(f"已有缓存: {cached_count} 个，跳过获取链接\n")

        if need_fetch:
            print(f"=== 阶段1：从52poke收集日文wiki链接（{len(need_fetch)} 个） ===\n")
            ja_urls = _collect_ja_urls(need_fetch, session)
            print(f"\n收集到 {len(ja_urls)} 个日文wiki链接\n")

            if ja_urls:
                print(f"=== 阶段2：浏览器访问日文wiki（{len(ja_urls)} 个页面） ===\n")
                _fetch_with_browser(ja_urls)
            else:
                print("没有需要下载的页面\n")
        else:
            print("所有页面都已有缓存，跳过阶段1和阶段2\n")

    # 阶段3：解析日文图鉴说明
    print("=== 阶段3：解析日文图鉴说明 ===\n")
    ja_descriptions = {}
    success_count = 0
    for base_name in grouped:
        html = _load_html_cache(base_name)
        if not html:
            print(f"  [SKIP] {base_name}: 无缓存HTML")
            continue
        desc = _parse_ja_description(html, base_name)
        if desc:
            ja_descriptions[base_name] = desc
            success_count += 1
            print(f"  [OK] {base_name}: {desc[:50]}...")
        else:
            print(f"  [FAIL] {base_name}: 解析失败")

    print(f"\n成功解析: {success_count}/{len(grouped)}\n")

    # 阶段4：回写CSV
    if ja_descriptions:
        print("=== 阶段4：回写CSV ===\n")
        updated_count = 0
        for row in to_process:
            base_name = _get_base_name(row['中文名'])
            if base_name in ja_descriptions and not row['日文图鉴说明']:
                row['日文图鉴说明'] = ja_descriptions[base_name]
                updated_count += 1

        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"已更新 {updated_count} 条记录的日文图鉴说明")
        print(f"输出文件: {OUTPUT_FILE}")
    else:
        print("未获取到任何日文图鉴说明，CSV未修改")

    print("\n步骤2完成！")


# ============================================================
#  主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='补充第九世代图鉴说明（联合管道）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python supplement_gen9_pipeline.py              # 依次执行步骤1和步骤2
  python supplement_gen9_pipeline.py --step1-only # 只执行步骤1
  python supplement_gen9_pipeline.py --step2-only # 只执行步骤2
  python supplement_gen9_pipeline.py --probe      # 步骤2 probe模式
        """)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--step1-only', action='store_true', help='只执行步骤1（52poke中日文）')
    group.add_argument('--step2-only', action='store_true', help='只执行步骤2（日文wiki）')
    parser.add_argument('--probe', action='store_true', help='步骤2只处理1个宝可梦')
    parser.add_argument('--parse-only', action='store_true', help='步骤2跳过爬取，只从缓存解析')
    args = parser.parse_args()

    if args.step1_only:
        run_step1()
    elif args.step2_only:
        run_step2(probe=args.probe, parse_only=args.parse_only)
    else:
        run_step1()
        run_step2(probe=args.probe, parse_only=args.parse_only)


if __name__ == '__main__':
    main()
