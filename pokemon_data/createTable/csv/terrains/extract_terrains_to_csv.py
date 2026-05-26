#!/usr/bin/env python3
"""
从 pokemon_data/terrain 目录下的 HTML 文件中提取 4 种场地信息，导出为 CSV
description = 页面首段介绍句（"X场地是宝可梦游戏中的一种状态变化。"）
effect = 详细对战机制（h2 效果/の効果 章节）
英文 HTML 为 Bulbapedia 空页（页面不存在），description_en / effect_en 暂留空
CSV 输出到 pokemon_data/createTable/csv/terrains/terrains.csv
"""

import csv
import sys
import io
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("需要安装 beautifulsoup4: pip install beautifulsoup4")
    sys.exit(1)

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # pokemon_data/
TERRAIN_DIR = BASE_DIR / "terrain"
OUTPUT_CSV = Path(__file__).resolve().parent / "terrains.csv"

TERRAINS_CONFIG = [
    {"id": 1, "file_prefix": "psychic-terrain"},
    {"id": 2, "file_prefix": "electric-terrain"},
    {"id": 3, "file_prefix": "misty-terrain"},
    {"id": 4, "file_prefix": "grassy-terrain"},
]

CSV_HEADERS = [
    "id", "name_en", "name_ja", "name_zh",
    "description_zh", "description_en", "description_ja",
    "effect_zh", "effect_en", "effect_ja",
]


def parse_html(file_path, encoding="utf-8"):
    """用 lxml 解析 HTML，返回 mw-parser-output div"""
    with open(file_path, encoding=encoding, errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    return soup.find("div", class_="mw-parser-output")


def extract_zh_info(file_path):
    """从中文 HTML 提取：name_zh, name_en, name_ja, description_zh, effect_zh"""
    content = parse_html(file_path)
    if not content:
        return "", "", "", "", ""

    # 名称从信息表格提取
    name_zh = name_en = name_ja = ""
    table = content.find("table")
    if table:
        font_tag = table.find("font", attrs={"size": "4px"})
        if font_tag:
            name_zh = font_tag.get_text().strip()
        ja_span = table.find("span", {"lang": "ja"})
        if ja_span:
            name_ja = ja_span.get_text().strip()
        en_span = table.find("span", {"lang": "en"})
        if en_span:
            name_en = en_span.get_text().strip()

    # 描述：页面第一个 <p>（介绍句，如"X场地是宝可梦游戏中的一种状态变化。"）
    description_zh = ""
    first_p = content.find("p")
    if first_p:
        description_zh = first_p.get_text().strip()

    # 效果：h2 "效果" 到下一个 h2 之间的 p 和 ul 内容
    effect_zh = _extract_section(content, "效果", stop_at_h2=True)

    return name_zh, name_en, name_ja, description_zh, effect_zh


def extract_en_info(file_path):
    """从英文 Bulbapedia HTML 提取：description_en, effect_en"""
    with open(file_path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    content = soup.find("div", id="mw-content-text")
    if not content:
        return "", ""
    po = content.find("div", class_="mw-parser-output")
    target = po or content

    # 描述：第一个 <p>
    description_en = ""
    first_p = target.find("p")
    if first_p:
        description_en = first_p.get_text().strip()

    # 效果：h2 "Effect" 到下一个 h2 之间的 h3/p/ul 内容
    effect_en = ""
    for h2 in target.find_all("h2"):
        if h2.get_text().strip() == "Effect":
            effect_en = _collect_after_heading(h2, tags=["h3", "p", "ul"], stop_at_h2=True)
            break

    return description_en, effect_en


def extract_ja_info(file_path):
    """从日文 HTML 提取：description_ja, effect_ja"""
    content = parse_html(file_path)
    if not content:
        return "", ""

    # 描述：页面第一个 <p>（介绍句，如"Xとは、場の状態の一つ。"）
    description_ja = ""
    first_p = content.find("p")
    if first_p:
        description_ja = first_p.get_text().strip()

    # 效果：h2 "の効果" 结尾的标题下的 ul 标签
    effect_ja = ""
    for h2 in content.find_all("h2"):
        if h2.get_text().strip().endswith("の効果"):
            effect_ja = _collect_after_heading(h2, tags=["ul", "p"], stop_at_h2=True)
            break

    return description_ja, effect_ja


def _extract_section(content, heading_text, tags=None, stop_at_h2=True):
    """从 content 中找到包含 heading_text 的 h2，收集其后的指定标签内容"""
    target_h2 = None
    for h2 in content.find_all("h2"):
        if h2.get_text().strip() == heading_text:
            target_h2 = h2
            break
    if not target_h2:
        return ""
    return _collect_after_heading(target_h2, tags=tags, stop_at_h2=stop_at_h2)


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
        text = sib.get_text().strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def main():
    print("=" * 60)
    print("从 terrain HTML 提取场地数据 → CSV")
    print("=" * 60)
    print(f"HTML 目录: {TERRAIN_DIR}")
    print(f"输出文件: {OUTPUT_CSV}\n")

    rows = []
    for terrain in TERRAINS_CONFIG:
        terrain_id = terrain["id"]
        prefix = terrain["file_prefix"]

        zh_file = TERRAIN_DIR / f"{prefix}-zh.html"
        en_file = TERRAIN_DIR / f"{prefix}-en.html"
        ja_file = TERRAIN_DIR / f"{prefix}-ja.html"

        print(f"  [{terrain_id}] {prefix}")

        name_zh = name_en = name_ja = description_zh = effect_zh = ""
        description_en = effect_en = ""
        description_ja = effect_ja = ""

        if zh_file.exists():
            name_zh, name_en, name_ja, description_zh, effect_zh = extract_zh_info(zh_file)
        else:
            print(f"      ⚠ 缺少: {zh_file.name}")

        if ja_file.exists():
            description_ja, effect_ja = extract_ja_info(ja_file)
        else:
            print(f"      ⚠ 缺少: {ja_file.name}")

        if en_file.exists():
            description_en, effect_en = extract_en_info(en_file)
        else:
            print(f"      ⚠ 缺少: {en_file.name}")

        row = {
            "id": terrain_id,
            "name_en": name_en,
            "name_ja": name_ja,
            "name_zh": name_zh,
            "description_zh": description_zh,
            "description_en": description_en,
            "description_ja": description_ja,
            "effect_zh": effect_zh,
            "effect_en": effect_en,
            "effect_ja": effect_ja,
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
    print(f"  请检查并手动修正后，运行 import_terrains_csv.py 导入数据库")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
