"""
测试 normalize 方案：验证 Python 端所有 normalized 名称能否在 JS 端匹配到
支持 form 拆分：python 端拆出 (base, form)，用 base+form / form+base / base 三种方式匹配 JS 端
"""
import os
import re
import json
import subprocess
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "..", "pokemon_data", "pokemonData.db")
DUMP_JS = os.path.join(SCRIPT_DIR, "cale", "dump_ncp_keys.js")

# ========== Python 端 normalize 函数（与 chinese_calculator.py 一致）==========

def normalize_name(name_en: str) -> str:
    return re.sub(r'[^a-zA-Z]', '', name_en).lower()

# mega/primal 前缀转换（与 cale_chinese_calculator.py 一致）
_FORME_PREFIX_RE = re.compile(r'^(.+)-(mega|primal)(?:-(x|y|z))?$', re.IGNORECASE)

def normalize_pokemon_name(name_en: str) -> str:
    m = _FORME_PREFIX_RE.match(name_en)
    if m:
        base = m.group(1)
        prefix = m.group(2)
        suffix = m.group(3) or ""
        return normalize_name(f"{prefix}{base}{suffix}")
    return normalize_name(name_en)

# ========== Form 拆分（与 cale_chinese_calculator.py 一致）==========

DEFAULT_FORMS = {
    "male", "disguised", "busted", "full-belly", "zero",
    "family-of-four", "family-of-three",
    "totem-disguised", "totem-busted",
}

FORM_MAP = {
    "female": "f",
}

def split_pokemon_form(name_en: str, is_multi_form: bool) -> tuple:
    """拆分 name_en 为 (base_normalized, form_normalized)"""
    m = _FORME_PREFIX_RE.match(name_en)
    if m:
        base = m.group(1)
        prefix = m.group(2)
        suffix = m.group(3) or ""
        return normalize_name(f"{prefix}{base}{suffix}"), ""

    if is_multi_form and "-" in name_en:
        dash_idx = name_en.index("-")
        base = name_en[:dash_idx]
        form = name_en[dash_idx + 1:]
        if form in DEFAULT_FORMS:
            form_norm = ""
        elif form in FORM_MAP:
            form_norm = normalize_name(FORM_MAP[form])
        elif form.endswith("-breed"):
            form_norm = normalize_name(form[:-len("-breed")])
        else:
            form_norm = normalize_name(form)
        return normalize_name(base), form_norm
    return normalize_name(name_en), ""

def match_form_in_ncp(base: str, form: str, ncp_keys: dict) -> str:
    """用 base+form / form+base / base 三种方式匹配 NCP key"""
    if form:
        hit = ncp_keys.get(base + form) or ncp_keys.get(form + base) or ncp_keys.get(base)
    else:
        hit = ncp_keys.get(base)
    return hit

# ========== 天气/状态映射（与 cale_chinese_calculator.py 一致）==========

CALE_WEATHER_MAP = {
    "rain": "Rain",
    "sunny": "Sun",
    "sandstorm": "Sand",
    "hail": "Snow",
    "snow": "Snow",
    "extremely-harsh-sunlight": "Harsh Sun",
    "heavy-rain": "Heavy Rain",
    "strong-winds": "Strong Winds",
}

CALE_STATUS_MAP = {
    "Poison": "Poisoned",
    "Badly poisoned": "Badly Poisoned",
    "Burn": "Burned",
    "Freeze": "Frozen",
    "Paralysis": "Paralyzed",
    "Sleep": "Asleep",
}

TERRAIN_SUFFIX = " Terrain"


def main():
    # 1. 获取 JS 端所有 NCP keys
    print("=" * 70)
    print("加载 NCP (Gen 10 Champions) 数据...")
    result = subprocess.run(
        ["node", DUMP_JS],
        capture_output=True, text=True, cwd=os.path.dirname(DUMP_JS)
    )
    if result.returncode != 0:
        print(f"Node.js 错误: {result.stderr}")
        return

    ncp_data = json.loads(result.stdout)

    print(f"  NCP 宝可梦: {len(ncp_data['pokemon'])} 个")
    print(f"  NCP 招式:   {len(ncp_data['moves'])} 个")
    print(f"  NCP 特性:   {len(ncp_data['abilities'])} 个")
    print(f"  NCP 道具:   {len(ncp_data['items'])} 个")
    print(f"  NCP 性格:   {len(ncp_data['natures'])} 个")
    print(f"  NCP 天气:   {len(ncp_data['weather'])} 个")
    print(f"  NCP 场地:   {len(ncp_data['terrain'])} 个")
    print(f"  NCP 状态:   {len(ncp_data['status'])} 个")

    # 2. 从 DB 加载并 normalize（模拟 CaleChineseDamageCalculator 的行为）
    print("\n加载数据库映射...")
    conn = sqlite3.connect(DB_PATH)

    # 查询多形态 pokedex_id
    multi_form_ids = set()
    for row in conn.execute(
        "SELECT pokedex_id FROM pokemons "
        "WHERE name_en IS NOT NULL "
        "GROUP BY pokedex_id HAVING COUNT(*) > 1"
    ):
        multi_form_ids.add(row[0])

    categories = {}

    # 宝可梦（使用 form 拆分）
    db_pokemon = {}
    for row in conn.execute(
        "SELECT name_zh, name_en, pokedex_id FROM pokemons "
        "WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"
    ):
        name_zh, name_en, pokedex_id = row
        is_multi = pokedex_id in multi_form_ids
        base, form = split_pokemon_form(name_en, is_multi)
        db_pokemon[name_zh] = (name_en, base, form)
    categories["pokemon"] = db_pokemon

    # 招式
    db_moves = {}
    for row in conn.execute("SELECT name_zh, name_en FROM moves WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"):
        db_moves[row[0]] = (row[1], normalize_name(row[1]))
    categories["moves"] = db_moves

    # 特性
    db_abilities = {}
    for row in conn.execute("SELECT name_zh, name_en FROM abilities WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"):
        db_abilities[row[0]] = (row[1], normalize_name(row[1]))
    categories["abilities"] = db_abilities

    # 道具
    db_items = {}
    for row in conn.execute("SELECT name_zh, name_en FROM items WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"):
        db_items[row[0]] = (row[1], normalize_name(row[1]))
    categories["items"] = db_items

    # 性格
    db_natures = {}
    for row in conn.execute("SELECT name_zh, name_en FROM natures WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"):
        db_natures[row[0]] = (row[1], normalize_name(row[1]))
    categories["natures"] = db_natures

    # 天气
    db_weather = {}
    for row in conn.execute("SELECT name_zh, name_en FROM status WHERE category='weather' AND name_zh IS NOT NULL AND name_en IS NOT NULL"):
        ncp_val = CALE_WEATHER_MAP.get(row[1])
        if ncp_val:
            db_weather[row[0]] = (row[1], normalize_name(ncp_val))
    categories["weather"] = db_weather

    # 场地
    db_terrain = {}
    for row in conn.execute("SELECT name_zh, name_en FROM status WHERE category='terrain' AND name_zh IS NOT NULL AND name_en IS NOT NULL"):
        stripped = row[1].replace(TERRAIN_SUFFIX, "")
        db_terrain[row[0]] = (row[1], normalize_name(stripped))
    categories["terrain"] = db_terrain

    # 状态
    db_status = {}
    for row in conn.execute("SELECT name_zh, name_en FROM status WHERE name_zh IS NOT NULL AND name_en IS NOT NULL"):
        ncp_val = CALE_STATUS_MAP.get(row[1])
        if ncp_val:
            db_status[row[0]] = (row[1], normalize_name(ncp_val))
    categories["status"] = db_status

    conn.close()

    # 3. 交叉验证
    print("\n" + "=" * 70)
    print("交叉验证结果")
    print("=" * 70)

    category_labels = {
        "pokemon": "宝可梦",
        "moves": "招式",
        "abilities": "特性",
        "items": "道具",
        "natures": "性格",
        "weather": "天气",
        "terrain": "场地",
        "status": "状态",
    }

    total_matched = 0
    total_unmatched = 0
    total_db_only = 0
    all_mismatches = {}

    for cat_key, cat_label in category_labels.items():
        db_data = categories[cat_key]
        ncp_keys = ncp_data[cat_key]  # normalized_key -> original_key

        matched = []
        unmatched = []
        db_only = []

        checked = set()

        if cat_key == "pokemon":
            # 宝可梦使用 form 匹配
            for zh_name, (en_name, base, form) in db_data.items():
                check_key = (base, form)
                if check_key in checked:
                    continue
                checked.add(check_key)

                hit = match_form_in_ncp(base, form, ncp_keys)
                if hit:
                    matched.append((zh_name, en_name, f"base={base} form={form}", hit))
                else:
                    db_only.append((zh_name, en_name, f"base={base} form={form}"))
        else:
            for zh_name, (en_name, normalized) in db_data.items():
                if normalized in checked:
                    continue
                checked.add(normalized)

                if normalized in ncp_keys:
                    matched.append((zh_name, en_name, normalized, ncp_keys[normalized]))
                else:
                    db_only.append((zh_name, en_name, normalized))

        # 反向：NCP 中有但 DB 中没有的
        if cat_key == "pokemon":
            db_normalized_values = set()
            for _, (_, base, form) in db_data.items():
                if form:
                    db_normalized_values.add(base + form)
                    db_normalized_values.add(form + base)
                db_normalized_values.add(base)
            ncp_only = [(nk, ncp_keys[nk]) for nk in ncp_keys if nk not in db_normalized_values]
        else:
            db_normalized_values = set(n for _, (_, n) in db_data.items())
            ncp_only = [(nk, ncp_keys[nk]) for nk in ncp_keys if nk not in db_normalized_values]

        print(f"\n{'─' * 50}")
        print(f"【{cat_label}】")
        print(f"  DB 条目: {len(db_data)}, 去重后: {len(checked)}")
        print(f"  NCP 条目: {len(ncp_keys)}")
        print(f"  ✓ 匹配成功: {len(matched)}")

        if ncp_only:
            print(f"  ✗ NCP 有但 DB 无: {len(ncp_only)}")
            for nk, orig in sorted(ncp_only, key=lambda x: x[1]):
                print(f"      {orig} (normalized: {nk})")

        if db_only and cat_key in ("natures", "weather", "terrain", "status"):
            print(f"  ✗ DB 有但 NCP 无: {len(db_only)}")
            for zh, en, norm in db_only:
                print(f"      {zh} / {en} ({norm})")
        elif db_only:
            print(f"  - DB 有但 NCP 无: {len(db_only)} (正常，DB 包含所有世代)")

        total_matched += len(matched)
        total_unmatched += len(ncp_only)
        total_db_only += len(db_only)

        if ncp_only:
            all_mismatches[cat_key] = ncp_only

    # 4. 总结
    print(f"\n{'=' * 70}")
    print("总结")
    print(f"{'=' * 70}")
    print(f"  总匹配成功: {total_matched}")
    print(f"  NCP 有但 DB 无 (可能需要补数据): {total_unmatched}")
    print(f"  DB 有但 NCP 无 (正常，DB 包含所有世代): {total_db_only}")

    if all_mismatches:
        print(f"\n⚠ 有 {total_unmatched} 个 NCP 条目在 DB 中找不到匹配！")
        print("  这些是计算器支持但数据库缺失的，可能导致用户查询失败。")
    else:
        print("\n✓ 所有 NCP 条目都能在 DB 中找到匹配！Normalize 方案完全生效。")


if __name__ == "__main__":
    main()
