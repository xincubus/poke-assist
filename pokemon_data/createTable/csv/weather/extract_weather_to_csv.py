#!/usr/bin/env python3
"""
从下载的 52poke HTML 文件提取天气状态数据，生成 weather.csv
数据来源：pokemon_data/weather_html/{en_name}-{lang}.html
输出：pokemon_data/createTable/csv/weather/weather.csv

表结构：
  id, name_en, name_zh, name_ja,
  description_zh, description_en, description_ja,
  effect_zh, effect_en, effect_ja
"""

import os
import sys
import csv
from pathlib import Path
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent  # pokemon_data/createTable/csv/weather -> pokemon root
HTML_DIR = BASE_DIR / "pokemon_data" / "weather_html"
OUTPUT_CSV = Path(__file__).parent / "weather.csv"

# 天气列表：(id, en_name, zh_name)
# id 与 PokeAPI 保持一致（参考旧 create_weather_table.py 的 JSON 文件名）
WEATHERS = [
    (1, "rain",                    "下雨"),
    (2, "sunny",                   "大晴天"),
    (3, "sandstorm",               "沙暴"),
    (4, "hail",                    "冰雹"),
    (5, "snow",                    "下雪"),
    (6, "extremely-harsh-sunlight","大日照"),
    (7, "heavy-rain",              "大雨"),
    (8, "strong-winds",            "乱流"),
]

FIELDNAMES = [
    "id", "name_en", "name_zh", "name_ja",
    "description_zh", "description_en", "description_ja",
    "effect_zh", "effect_en", "effect_ja",
]


def load_html(en_name, lang):
    """加载 HTML 文件，返回 BeautifulSoup 或 None"""
    path = HTML_DIR / f"{en_name}-{lang}.html"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "lxml")


def extract_zh_data(soup, zh_name):
    """从中文页面提取：name_ja（跨语言链接）、description、效果"""
    if not soup:
        return {}

    result = {}

    # 提取日文名（从跨语言链接的文字）
    ja_li = soup.find("li", class_="interwiki-ja")
    if ja_li:
        a = ja_li.find("a")
        if a:
            result["name_ja"] = a.get_text(strip=True)

    # 提取描述：页面第一段正文
    content_div = soup.find("div", class_="mw-parser-output")
    if content_div:
        first_p = content_div.find("p")
        if first_p:
            result["description_zh"] = first_p.get_text(strip=True)

    # 提取效果：h2"效果" → h3"属性"/"招式"/"特性" 合并为一个字段
    parts = []
    for section in ["属性", "招式", "特性"]:
        text = _extract_section(soup, [section], parent_heading="效果")
        if text:
            parts.append(text)
    result["effect_zh"] = "\n".join(parts)

    # 如果为空，把整个效果章节内容放进来
    if not result["effect_zh"]:
        result["effect_zh"] = _extract_section(soup, ["效果"])

    return result


def _extract_section(soup, heading_candidates, parent_heading=None):
    """提取指定标题后的内容（p + ul 合并为文本）
    parent_heading: 若指定，只在该父标题的子节中查找（避免匹配到其他章节的同名标题）
    """
    content_div = soup.find("div", class_="mw-parser-output")
    if not content_div:
        return ""

    # 如果指定了父标题，先定位父标题，再在其范围内查找
    search_tags = list(content_div.find_all(["h2", "h3", "h4"]))

    if parent_heading:
        # 找到父标题的位置
        parent_tag = None
        for tag in search_tags:
            if parent_heading in tag.get_text(strip=True):
                parent_tag = tag
                break
        if not parent_tag:
            return ""
        parent_level = int(parent_tag.name[1])

        # 收集父标题到下一个同级标题之间的所有标签
        section_tags = []
        for sibling in parent_tag.find_next_siblings():
            if sibling.name in ["h2", "h3", "h4"] and int(sibling.name[1]) <= parent_level:
                break
            section_tags.append(sibling)

        # 在 section_tags 中找目标标题
        target_heading = None
        for tag in section_tags:
            if tag.name in ["h2", "h3", "h4"]:
                text = tag.get_text(strip=True)
                for candidate in heading_candidates:
                    if candidate == text:  # 精确匹配，避免"属性"匹配到"属性效果"
                        target_heading = tag
                        break
            if target_heading:
                break
    else:
        target_heading = None
        for tag in search_tags:
            text = tag.get_text(strip=True)
            for candidate in heading_candidates:
                if candidate in text:
                    target_heading = tag
                    break
            if target_heading:
                break

    if not target_heading:
        return ""

    heading_level = int(target_heading.name[1])
    parts = []
    for sibling in target_heading.find_next_siblings():
        tag_name = sibling.name
        if tag_name in ["h2", "h3", "h4"]:
            if int(tag_name[1]) <= heading_level:
                break
        if tag_name in ["p", "ul", "ol"]:
            text = sibling.get_text(separator="\n", strip=True)
            if text:
                parts.append(text)

    return "\n".join(parts)


def extract_en_data(soup):
    """从英文页面（Bulbapedia）提取：description、effect_en
    Bulbapedia 结构：h2"Effects" → h3"In battle"
    """
    if not soup:
        return {}

    result = {}

    content = soup.find("div", id="mw-content-text") or soup.find("div", class_="mw-parser-output")
    if not content:
        return result

    first_p = content.find("p")
    if first_p:
        result["description_en"] = first_p.get_text(strip=True)

    effects_h2 = None
    for h2 in content.find_all("h2"):
        if h2.get_text(strip=True) == "Effects":
            effects_h2 = h2
            break

    if effects_h2:
        in_battle = None
        for sib in effects_h2.find_next_siblings():
            if sib.name == "h2":
                break
            if sib.name == "h3" and "In battle" in sib.get_text():
                in_battle = sib
                break

        target = in_battle or effects_h2
        parts = []
        for sib in target.find_next_siblings():
            if sib.name in (["h2", "h3"] if in_battle else ["h2"]):
                break
            if sib.name in ["p", "ul", "ol"]:
                text = sib.get_text(separator="\n", strip=True)
                if text:
                    parts.append(text)
        result["effect_en"] = "\n".join(parts)

    return result


def extract_ja_data(soup):
    """从日文页面提取：name_ja、description、effect_ja"""
    if not soup:
        return {}

    result = {}

    # 从页面 h1 或 title 提取日文名
    h1 = soup.find("h1")
    if h1:
        result["name_ja"] = h1.get_text(strip=True)
    else:
        title = soup.find("title")
        if title:
            result["name_ja"] = title.get_text(strip=True).split(" - ")[0]

    content_div = soup.find("div", class_="mw-parser-output")
    if not content_div:
        return result

    # 描述：第一段
    first_p = content_div.find("p")
    if first_p:
        result["description_ja"] = first_p.get_text(strip=True)

    # 效果：h2"影響" 下的内容；若无则取 h2"概要"
    for keyword in ["影響", "概要"]:
        for h2 in content_div.find_all("h2"):
            if keyword in h2.get_text():
                parts = []
                for sib in h2.find_next_siblings():
                    if sib.name == "h2":
                        break
                    if sib.name in ["p", "ul", "ol"]:
                        text = sib.get_text(separator="\n", strip=True)
                        if text:
                            parts.append(text)
                if parts:
                    result["effect_ja"] = "\n".join(parts)
                    break
        if result.get("effect_ja"):
            break

    return result


def main():
    if not HTML_DIR.exists():
        print(f"⚠️ HTML 目录不存在：{HTML_DIR}")
        print("请先运行 download/download_weather_html.py 下载 HTML 文件")
        # 仍然生成骨架 CSV
        rows = []
        for wid, en_name, zh_name in WEATHERS:
            row = {f: "" for f in FIELDNAMES}
            row["id"] = wid
            row["name_en"] = en_name
            row["name_zh"] = zh_name
            rows.append(row)
    else:
        rows = []
        for wid, en_name, zh_name in WEATHERS:
            print(f"处理 {zh_name} ({en_name})...")
            row = {f: "" for f in FIELDNAMES}
            row["id"] = wid
            row["name_en"] = en_name
            row["name_zh"] = zh_name

            # 中文页面
            zh_soup = load_html(en_name, "zh")
            if zh_soup:
                zh_data = extract_zh_data(zh_soup, zh_name)
                row.update(zh_data)
                print(f"  ✓ 中文：description={bool(row['description_zh'])}, effect={bool(row['effect_zh'])}")
            else:
                print(f"  ⚠️ 缺少中文 HTML")

            # 英文页面
            en_soup = load_html(en_name, "en")
            if en_soup:
                en_data = extract_en_data(en_soup)
                row.update(en_data)
                print(f"  ✓ 英文：description={bool(row['description_en'])}")
            else:
                print(f"  ⚠️ 缺少英文 HTML")

            # 日文页面
            ja_soup = load_html(en_name, "ja")
            if ja_soup:
                ja_data = extract_ja_data(ja_soup)
                row.update(ja_data)
                print(f"  ✓ 日文：description={bool(row['description_ja'])}")
            else:
                print(f"  ⚠️ 缺少日文 HTML")

            rows.append(row)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✓ 已写入 {len(rows)} 条记录到 {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
