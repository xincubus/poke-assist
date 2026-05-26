"""分析关键模板的参数结构，为写渲染函数做准备"""
import sqlite3
import re
from pathlib import Path

WIKI_META_DB = Path(__file__).parent / "wiki_meta.db"
WIKITEXT_CACHE = Path(__file__).parent / "wikitext_cache"

def analyze_pokemon_infobox():
    """分析寶可夢信息框/形態的参数结构"""
    # 读取皮卡丘的原始 wikitext
    pika_file = WIKITEXT_CACHE / "皮卡丘.wiki"
    if not pika_file.exists():
        print("皮卡丘.wiki 不存在")
        return

    with open(pika_file, "r", encoding="utf-8") as f:
        wikitext = f.read()

    # 找到信息框模板
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)

    for tpl in code.filter_templates():
        name = str(tpl.name).strip()
        if "信息框" in name:
            print(f"\n=== 模板: {name} ===")
            print(f"参数数量: {len(tpl.params)}")
            for i, p in enumerate(tpl.params):
                key = str(p.name).strip() if p.showkey else f"[{i+1}]"
                val = str(p.value).strip()[:80]
                print(f"  {key}: {val}")
            break

def analyze_toggle():
    """分析 Toggle/Header 和 Toggle/Content 的参数结构"""
    pika_file = WIKITEXT_CACHE / "皮卡丘.wiki"
    if not pika_file.exists():
        return

    with open(pika_file, "r", encoding="utf-8") as f:
        wikitext = f.read()

    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)

    for tpl in code.filter_templates():
        name = str(tpl.name).strip()
        if "Toggle" in name:
            print(f"\n=== 模板: {name} ===")
            print(f"参数数量: {len(tpl.params)}")
            for i, p in enumerate(tpl.params):
                key = str(p.name).strip() if p.showkey else f"[{i+1}]"
                val = str(p.value).strip()[:60]
                print(f"  {key}: {val}")

def analyze_race_value():
    """分析种族值模板的参数结构"""
    pika_file = WIKITEXT_CACHE / "皮卡丘.wiki"
    if not pika_file.exists():
        return

    with open(pika_file, "r", encoding="utf-8") as f:
        wikitext = f.read()

    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)

    for tpl in code.filter_templates():
        name = str(tpl.name).strip()
        if "种族值" in name:
            print(f"\n=== 模板: {name} ===")
            print(f"参数数量: {len(tpl.params)}")
            for i, p in enumerate(tpl.params):
                key = str(p.name).strip() if p.showkey else f"[{i+1}]"
                val = str(p.value).strip()[:60]
                print(f"  {key}: {val}")

def analyze_type_effectiveness():
    """分析属性相性模板的参数结构"""
    pika_file = WIKITEXT_CACHE / "皮卡丘.wiki"
    if not pika_file.exists():
        return

    with open(pika_file, "r", encoding="utf-8") as f:
        wikitext = f.read()

    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)

    for tpl in code.filter_templates():
        name = str(tpl.name).strip()
        if "属性相性" in name:
            print(f"\n=== 模板: {name} ===")
            print(f"参数数量: {len(tpl.params)}")
            for i, p in enumerate(tpl.params):
                key = str(p.name).strip() if p.showkey else f"[{i+1}]"
                val = str(p.value).strip()[:60]
                print(f"  {key}: {val}")

def analyze_obtain_method():
    """分析获得方式模板的参数结构"""
    pika_file = WIKITEXT_CACHE / "皮卡丘.wiki"
    if not pika_file.exists():
        return

    with open(pika_file, "r", encoding="utf-8") as f:
        wikitext = f.read()

    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)

    for tpl in code.filter_templates():
        name = str(tpl.name).strip()
        if "获得方式" in name:
            print(f"\n=== 模板: {name} ===")
            print(f"参数数量: {len(tpl.params)}")
            for i, p in enumerate(tpl.params):
                key = str(p.name).strip() if p.showkey else f"[{i+1}]"
                val = str(p.value).strip()[:60]
                print(f"  {key}: {val}")

if __name__ == "__main__":
    print("=== 宝可梦信息框分析 ===")
    analyze_pokemon_infobox()

    print("\n\n=== Toggle 模板分析 ===")
    analyze_toggle()

    print("\n\n=== 种族值模板分析 ===")
    analyze_race_value()

    print("\n\n=== 属性相性模板分析 ===")
    analyze_type_effectiveness()

    print("\n\n=== 获得方式模板分析 ===")
    analyze_obtain_method()
