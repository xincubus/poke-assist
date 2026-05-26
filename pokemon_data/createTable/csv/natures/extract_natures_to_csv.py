#!/usr/bin/env python3
"""
从 pokemon_data/nature 目录下的 JSON 文件提取性格数据，导出为 CSV
CSV 输出到 pokemon_data/createTable/csv/natures/natures.csv，方便手动修正后再导入数据库

数据来源：PokeAPI JSON（由 download/download_natures_json.py 下载）
"""

import csv
import json
import sys
import io
import os
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent.parent.parent
NATURE_DIR = BASE_DIR / "nature"
OUTPUT_CSV = Path(__file__).parent / "natures.csv"

CSV_HEADERS = [
    'id', 'name_ja', 'name_en', 'name_zh',
    'decreased_stat_id', 'increased_stat_id',
    'decreased_stat_en', 'increased_stat_en',
    'decreased_stat_zh', 'increased_stat_zh',
    'decreased_stat_ja', 'increased_stat_ja',
]

# stat_id → 三语名称（与 stats 表一致）
STAT_NAMES = {
    1: {'en': 'HP',             'zh': 'HP',   'ja': 'HP'},
    2: {'en': 'Attack',         'zh': '攻击', 'ja': 'こうげき'},
    3: {'en': 'Defense',        'zh': '防御', 'ja': 'ぼうぎょ'},
    4: {'en': 'Special Attack', 'zh': '特攻', 'ja': 'とくこう'},
    5: {'en': 'Special Defense','zh': '特防', 'ja': 'とくぼう'},
    6: {'en': 'Speed',          'zh': '速度', 'ja': 'すばやさ'},
}


def parse_nature(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    nature_id = data['id']

    name_ja = name_zh = name_en = ''
    for entry in data.get('names', []):
        lang = entry['language']['name']
        if lang == 'ja':
            name_ja = entry['name']
        elif lang == 'ja-hrkt' and not name_ja:
            name_ja = entry['name']
        elif lang == 'zh-hans':
            name_zh = entry['name']
        elif lang == 'en':
            name_en = entry['name']

    def parse_stat(stat_field):
        if not data.get(stat_field):
            return None, '', '', ''
        url = data[stat_field]['url']
        stat_id = int(url.rstrip('/').split('/')[-1])
        names = STAT_NAMES.get(stat_id, {'en': '', 'zh': '', 'ja': ''})
        return stat_id, names['en'], names['zh'], names['ja']

    dec_id, dec_en, dec_zh, dec_ja = parse_stat('decreased_stat')
    inc_id, inc_en, inc_zh, inc_ja = parse_stat('increased_stat')

    return {
        'id': nature_id,
        'name_ja': name_ja,
        'name_en': name_en,
        'name_zh': name_zh,
        'decreased_stat_id': dec_id if dec_id is not None else '',
        'increased_stat_id': inc_id if inc_id is not None else '',
        'decreased_stat_en': dec_en,
        'increased_stat_en': inc_en,
        'decreased_stat_zh': dec_zh,
        'increased_stat_zh': inc_zh,
        'decreased_stat_ja': dec_ja,
        'increased_stat_ja': inc_ja,
    }


def main():
    print('=' * 60)
    print('从 nature JSON 提取性格数据 → CSV')
    print('=' * 60)
    print(f'JSON 目录: {NATURE_DIR}')
    print(f'输出文件: {OUTPUT_CSV}\n')

    if not NATURE_DIR.exists():
        print(f'✗ JSON 目录不存在: {NATURE_DIR}')
        print('  请先运行 download/download_natures_json.py 下载数据')
        sys.exit(1)

    json_files = sorted(NATURE_DIR.glob('*.json'))
    if not json_files:
        print(f'✗ 未找到 JSON 文件: {NATURE_DIR}')
        sys.exit(1)

    rows = []
    for filepath in json_files:
        row = parse_nature(filepath)
        rows.append(row)
        inc_label = row['increased_stat_zh'] or '无'
        dec_label = row['decreased_stat_zh'] or '无'
        print(f"  [{row['id']:2d}] {row['name_en']:<12} ({row['name_zh']}/{row['name_ja']}): +{inc_label} / -{dec_label}")

    rows.sort(key=lambda r: int(r['id']))

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, delimiter=',')
        writer.writeheader()
        writer.writerows(rows)

    print(f'\n{"=" * 60}')
    print(f'✓ 已导出 {len(rows)} 条记录到 {OUTPUT_CSV}')
    print(f'  请检查并手动修正后，运行 import_natures_csv.py 导入数据库')
    print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
