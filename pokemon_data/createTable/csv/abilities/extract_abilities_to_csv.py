"""
从 pokemon_data/ability/ 目录下的 JSON 文件提取特性数据，生成 abilities.csv
输出字段：id, name_en, name_zh, name_ja, description_zh, description_en, description_ja
"""

import json
import csv
import os

ABILITY_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ability')
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), 'abilities.csv')


def get_name(names, lang):
    for entry in names:
        if entry['language']['name'] == lang:
            return entry['name']
    return ''


def get_effect(effect_entries, lang):
    """从 effect_entries 取 short_effect（简短说明）"""
    for entry in effect_entries:
        if entry['language']['name'] == lang:
            return entry.get('short_effect', entry.get('effect', ''))
    return ''


def get_flavor_text(flavor_text_entries, lang):
    """取该语言最后一条 flavor_text（最新版本）"""
    result = ''
    for entry in flavor_text_entries:
        if entry['language']['name'] == lang:
            result = entry['flavor_text'].replace('\n', ' ')
    return result


def extract():
    rows = []

    json_files = sorted(
        [f for f in os.listdir(ABILITY_DIR) if f.endswith('.json')],
        key=lambda f: json.load(open(os.path.join(ABILITY_DIR, f), encoding='utf-8')).get('id', 0)
    )

    for filename in json_files:
        path = os.path.join(ABILITY_DIR, filename)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        ability_id = data.get('id', '')
        name_en = get_name(data.get('names', []), 'en') or data.get('name', '')
        name_zh = get_name(data.get('names', []), 'zh-hans')
        name_ja = get_name(data.get('names', []), 'ja')

        effect_entries = data.get('effect_entries', [])
        flavor_entries = data.get('flavor_text_entries', [])

        # 优先用 effect_entries short_effect，没有则用 flavor_text
        desc_en = get_effect(effect_entries, 'en') or get_flavor_text(flavor_entries, 'en')
        desc_zh = get_flavor_text(flavor_entries, 'zh-hans')
        desc_ja = get_flavor_text(flavor_entries, 'ja')

        rows.append({
            'id': ability_id,
            'name_en': name_en,
            'name_zh': name_zh,
            'name_ja': name_ja,
            'description_zh': desc_zh,
            'description_en': desc_en,
            'description_ja': desc_ja,
        })

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'id', 'name_en', 'name_zh', 'name_ja',
            'description_zh', 'description_en', 'description_ja'
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"已导出 {len(rows)} 条特性数据到 {OUTPUT_CSV}")

    # 统计缺失
    missing_zh = sum(1 for r in rows if not r['name_zh'])
    missing_desc_zh = sum(1 for r in rows if not r['description_zh'])
    print(f"name_zh 缺失：{missing_zh} 条")
    print(f"description_zh 缺失：{missing_desc_zh} 条")


if __name__ == '__main__':
    extract()
