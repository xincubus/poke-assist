#!/usr/bin/env python3
"""
从 pokemon_data/type_html 目录下的 HTML 文件中提取 18 种属性信息，导出为 CSV
数据来源：
  中文：52poke Wiki（wiki.52poke.com）
  英文：Bulbapedia（bulbapedia.bulbagarden.net）
  日文：ポケモンWiki（wiki.xn--rckteqa2e.com）

表字段：
  id, name_en, name_zh, name_ja,
  description_zh, description_en, description_ja,
  effect_zh, effect_en, effect_ja

CSV 输出到 pokemon_data/createTable/csv/types/types.csv
"""

import csv
import sys
import io
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("需要安装 beautifulsoup4: pip install beautifulsoup4")
    sys.exit(1)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # pokemon_data/
TYPE_HTML_DIR = BASE_DIR / "type_html"
OUTPUT_CSV = Path(__file__).resolve().parent / "types.csv"

# 18 个正式属性（id 与 PokeAPI 一致）
TYPES_CONFIG = [
    {"id": 1,  "en": "normal"},
    {"id": 2,  "en": "fighting"},
    {"id": 3,  "en": "flying"},
    {"id": 4,  "en": "poison"},
    {"id": 5,  "en": "ground"},
    {"id": 6,  "en": "rock"},
    {"id": 7,  "en": "bug"},
    {"id": 8,  "en": "ghost"},
    {"id": 9,  "en": "steel"},
    {"id": 10, "en": "fire"},
    {"id": 11, "en": "water"},
    {"id": 12, "en": "grass"},
    {"id": 13, "en": "electric"},
    {"id": 14, "en": "psychic"},
    {"id": 15, "en": "ice"},
    {"id": 16, "en": "dragon"},
    {"id": 17, "en": "dark"},
    {"id": 18, "en": "fairy"},
]

CSV_HEADERS = [
    "id", "name_en", "name_zh", "name_ja",
    "description_zh", "description_en", "description_ja",
    "effect_zh", "effect_en", "effect_ja",
    "image_path",
]


def parse_html(file_path, encoding="utf-8"):
    with open(file_path, encoding=encoding, errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    return soup


def _collect_after_heading(heading_tag, tags=None, stop_at_h2=True):
    """收集 heading_tag 之后的兄弟节点文本，直到下一个 h2"""
    parts = []
    for sib in heading_tag.next_siblings:
        if not hasattr(sib, "name") or sib.name is None:
            continue
        if stop_at_h2 and sib.name == "h2":
            break
        if tags and sib.name not in tags:
            continue
        text = sib.get_text(" ", strip=True)
        if text:
            parts.append(text)
    return "\n".join(parts)


def extract_zh_info(file_path):
    """从中文 52poke HTML 提取：name_zh, name_en, name_ja, description_zh, effect_zh"""
    soup = parse_html(file_path)
    content = soup.find("div", class_="mw-parser-output")
    if not content:
        return "", "", "", "", ""

    name_zh = name_en = name_ja = description_zh = effect_zh = ""

    # 名称从信息表格提取（52poke 属性页有 infobox 表格）
    table = content.find("table")
    if table:
        # 中文名：表格标题行的粗体
        b_tag = table.find("b")
        if b_tag:
            name_zh = b_tag.get_text().strip()
        # 日文名：span lang="ja"
        ja_span = table.find("span", {"lang": "ja"})
        if ja_span:
            name_ja = ja_span.get_text().strip()
        # 英文名：span lang="en" 或 ASCII 粗体
        en_span = table.find("span", {"lang": "en"})
        if en_span:
            name_en = en_span.get_text().strip()
        if not name_en:
            for b in table.find_all("b"):
                candidate = b.get_text().strip()
                if candidate and re.match(r'^[A-Za-z][A-Za-z\s]+$', candidate):
                    name_en = candidate
                    break

    # 如果表格没有名称，从第一个 <p> 的 <b> 提取
    if not name_zh:
        first_p = content.find("p")
        if first_p:
            b_tag = first_p.find("b")
            if b_tag:
                name_zh = b_tag.get_text().strip()

    # 描述：第一个 <p>（介绍句）
    first_p = content.find("p")
    if first_p:
        description_zh = first_p.get_text().strip()

    # 效果：h2 "特点" 章节
    for h2 in content.find_all("h2"):
        h2_text = h2.get_text().strip()
        if h2_text in ("特点", "特性", "效果", "属性特性"):
            effect_zh = _collect_after_heading(h2, tags=["p", "ul", "h3"], stop_at_h2=True)
            break

    return name_zh, name_en, name_ja, description_zh, effect_zh


def extract_en_info(file_path):
    """从英文 Bulbapedia HTML 提取：name_en（备用）, description_en, effect_en"""
    soup = parse_html(file_path)
    content = soup.find("div", id="mw-content-text")
    if not content:
        return "", "", ""
    po = content.find("div", class_="mw-parser-output") or content

    name_en = ""
    # 从页面标题提取英文名
    h1 = soup.find("h1", id="firstHeading")
    if h1:
        title = h1.get_text().strip()
        # "Grass (type)" → "Grass"
        name_en = re.sub(r'\s*\(.*?\)', '', title).strip()

    # 描述：第一个非空 <p>
    description_en = ""
    for p in po.find_all("p"):
        text = p.get_text().strip()
        if text and "If you were looking for" not in text:
            description_en = text
            break

    # 效果：h2 "Characteristics" 或 "Properties" 章节
    effect_en = ""
    for h2 in po.find_all("h2"):
        h2_text = h2.get_text().strip()
        if h2_text in ("Characteristics", "Properties", "Battle properties"):
            effect_en = _collect_after_heading(h2, tags=["h3", "p", "ul"], stop_at_h2=True)
            break

    return name_en, description_en, effect_en


def extract_ja_info(file_path):
    """从日文 ポケモンWiki HTML 提取：name_ja（备用）, description_ja, effect_ja"""
    soup = parse_html(file_path)
    # ポケモンWiki 用 mw-content-text，不是 mw-parser-output
    content = soup.find("div", id="mw-content-text") or soup.find("div", class_="mw-parser-output")
    if not content:
        return "", "", ""

    name_ja = ""
    h1 = soup.find("h1", id="firstHeading")
    if h1:
        name_ja = h1.get_text().strip()

    # 描述：概要 h2 下的第一个 <p>
    description_ja = ""
    for h2 in content.find_all("h2"):
        if "概要" in h2.get_text():
            for sib in h2.next_siblings:
                if not hasattr(sib, "name") or sib.name is None:
                    continue
                if sib.name == "h2":
                    break
                if sib.name == "p":
                    text = sib.get_text().strip()
                    if text:
                        description_ja = text
                        break
            break
    # fallback：第一个 <p>
    if not description_ja:
        for p in content.find_all("p"):
            text = p.get_text().strip()
            if text and "このページでは" not in text and "曖昧さ回避" not in text:
                description_ja = text
                break

    # 効果：「ポケモンとして」で始まる h2 下の最初の ul（相性・免疫情報）
    effect_ja = ""
    for h2 in content.find_all("h2"):
        if "ポケモン" in h2.get_text():
            for sib in h2.next_siblings:
                if not hasattr(sib, "name") or sib.name is None:
                    continue
                if sib.name == "h2":
                    break
                if sib.name == "ul":
                    effect_ja = sib.get_text(" ", strip=True)
                    break
            break

    return name_ja, description_ja, effect_ja


def main():
    print("=" * 60)
    print("从 type_html HTML 提取属性数据 → CSV")
    print("=" * 60)
    print(f"HTML 目录: {TYPE_HTML_DIR}")
    print(f"输出文件: {OUTPUT_CSV}\n")

    if not TYPE_HTML_DIR.exists():
        print(f"✗ HTML 目录不存在: {TYPE_HTML_DIR}")
        print("  请先运行 download/download_types_html.py 下载 HTML 文件")
        sys.exit(1)

    rows = []
    for t in TYPES_CONFIG:
        type_id = t["id"]
        en_name = t["en"]

        zh_file = TYPE_HTML_DIR / f"{en_name}-zh.html"
        en_file = TYPE_HTML_DIR / f"{en_name}-en.html"
        ja_file = TYPE_HTML_DIR / f"{en_name}-ja.html"

        print(f"  [{type_id}] {en_name}")

        name_zh = name_en = name_ja = description_zh = effect_zh = ""
        description_en = effect_en = ""
        description_ja = effect_ja = ""

        if zh_file.exists():
            name_zh, name_en_zh, name_ja_zh, description_zh, effect_zh = extract_zh_info(zh_file)
            if name_en_zh:
                name_en = name_en_zh
            if name_ja_zh:
                name_ja = name_ja_zh
        else:
            print(f"      ⚠ 缺少: {zh_file.name}")

        if en_file.exists():
            name_en_en, description_en, effect_en = extract_en_info(en_file)
            if not name_en and name_en_en:
                name_en = name_en_en
        else:
            print(f"      ⚠ 缺少: {en_file.name}")

        if ja_file.exists():
            name_ja_ja, description_ja, effect_ja = extract_ja_info(ja_file)
            if not name_ja and name_ja_ja:
                name_ja = name_ja_ja
        else:
            print(f"      ⚠ 缺少: {ja_file.name}")

        # 英文名 fallback：用 PokeAPI 的 en_name 首字母大写
        if not name_en:
            name_en = en_name.capitalize()

        image_file = BASE_DIR / "typeImage" / f"{en_name}.png"
        image_path = f"typeImage/{en_name}.png" if image_file.exists() else ""

        row = {
            "id": type_id,
            "name_en": name_en,
            "name_zh": name_zh,
            "name_ja": name_ja,
            "description_zh": description_zh,
            "description_en": description_en,
            "description_ja": description_ja,
            "effect_zh": effect_zh,
            "effect_en": effect_en,
            "effect_ja": effect_ja,
            "image_path": image_path,
        }
        rows.append(row)

        print(f"      名称: {name_zh} / {name_en} / {name_ja}")
        desc_preview = (description_zh[:50] + "...") if len(description_zh) > 50 else (description_zh or "(空)")
        print(f"      描述zh: {desc_preview}")
        effect_preview = (effect_zh[:60] + "...") if len(effect_zh) > 60 else (effect_zh or "(空)")
        print(f"      效果zh: {effect_preview}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, delimiter=",")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'=' * 60}")
    print(f"✓ 已导出 {len(rows)} 条记录到 {OUTPUT_CSV}")
    print(f"  请检查并手动修正后，运行 import_types_csv.py 导入数据库")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
