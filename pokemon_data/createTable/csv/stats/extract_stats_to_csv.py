#!/usr/bin/env python3
"""
从 pokemon_data/stat 目录下的 HTML 文件中提取 8 种能力信息，导出为 CSV
CSV 输出到 pokemon_data/stat/stats.csv，方便手动修正后再导入数据库
"""

import csv
import sys
import io
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup, NavigableString
except ImportError:
    print("需要安装 beautifulsoup4: pip install beautifulsoup4")
    sys.exit(1)

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent.parent  # createTable/
STAT_DIR = BASE_DIR.parent / "stat"             # pokemon_data/stat/
OUTPUT_CSV = Path(__file__).parent / "stats.csv"  # csv/stats/stats.csv

# 8 种能力配置（简称为游戏标准术语，硬编码）
STATS_CONFIG = [
    {'id': 1, 'file_prefix': 'hp',              'abbr_en': 'HP',      'abbr_zh': 'HP',   'abbr_ja': 'HP'},
    {'id': 2, 'file_prefix': 'attack',           'abbr_en': 'Atk',    'abbr_zh': '攻击', 'abbr_ja': 'こうげき'},
    {'id': 3, 'file_prefix': 'defense',          'abbr_en': 'Def',    'abbr_zh': '防御', 'abbr_ja': 'ぼうぎょ'},
    {'id': 4, 'file_prefix': 'special-attack',   'abbr_en': 'Sp.Atk', 'abbr_zh': '特攻', 'abbr_ja': 'とくこう'},
    {'id': 5, 'file_prefix': 'special-defense',  'abbr_en': 'Sp.Def', 'abbr_zh': '特防', 'abbr_ja': 'とくぼう'},
    {'id': 6, 'file_prefix': 'speed',            'abbr_en': 'Spe',    'abbr_zh': '速度', 'abbr_ja': 'すばやさ'},
    {'id': 7, 'file_prefix': 'accuracy',         'abbr_en': 'Acc',    'abbr_zh': '命中', 'abbr_ja': '命中'},
    {'id': 8, 'file_prefix': 'evasion',          'abbr_en': 'Eva',    'abbr_zh': '闪避', 'abbr_ja': '回避'},
]

CSV_HEADERS = [
    'id', 'name_en', 'name_zh', 'abbr_zh', 'abbr_ja', 'abbr_en',
    'name_ja', 'description_zh', 'description_en', 'description_ja'
]


def parse_html(file_path):
    """解析 HTML 文件，以二进制读取并指定 utf-8 编码"""
    with open(file_path, 'rb') as f:
        soup = BeautifulSoup(f.read(), 'html.parser', from_encoding='utf-8')
    return soup.find('div', class_='mw-parser-output')


def get_text_before_h2(parser_output, skip_disambig_fn=None):
    """获取第一个 <h2> 之前的有效 <p> 标签列表"""
    result = []
    for child in parser_output.children:
        if not hasattr(child, 'name') or child.name is None:
            continue
        if child.name == 'h2':
            break
        if child.name == 'p':
            if skip_disambig_fn and skip_disambig_fn(child):
                continue
            result.append(child)
    return result


def extract_ruby_base(element):
    """从含 ruby 注音的元素中提取基础文本（去除 rt/rp）"""
    ruby = element.find('ruby')
    if ruby:
        inner_span = ruby.find('span', {'lang': 'ja'})
        if inner_span:
            return inner_span.get_text()
        parts = []
        for child in ruby.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif hasattr(child, 'name') and child.name not in ('rt', 'rp', 'small'):
                parts.append(child.get_text())
        return ''.join(parts).strip()
    return element.get_text()


def skip_zh_disambig(p):
    """判断中文 wiki 的消歧义段落"""
    return bool(p.find('img')) or '这篇文章讲述' in p.get_text()


def extract_zh_info(file_path):
    """从中文 HTML 提取：(name_zh, name_en, name_ja, desc_zh)"""
    parser_output = parse_html(file_path)
    if not parser_output:
        return '', '', '', ''

    paragraphs = get_text_before_h2(parser_output, skip_zh_disambig)
    if not paragraphs:
        return '', '', '', ''

    def_p = paragraphs[0]
    def_text = def_p.get_text()

    # 1. 中文名：第一个 <b> 标签
    first_b = def_p.find('b')
    name_zh = first_b.get_text() if first_b else ''

    # 2. 英文名：找到内容全为 ASCII 字母/空格的 <b> 标签
    name_en = ''
    for b in def_p.find_all('b'):
        candidate = b.get_text().strip()
        if candidate and re.match(r'^[A-Za-z][A-Za-z\s.]+$', candidate):
            name_en = candidate
            break

    # 3. 日文名：优先从"日文汉字"字段取汉字形式，否则从 <span lang="ja"> 取
    name_ja = ''
    if '日文汉字' in def_text:
        ja_spans = def_p.find_all('span', {'lang': 'ja'})
        if len(ja_spans) >= 2:
            name_ja = extract_ruby_base(ja_spans[1])
        elif ja_spans:
            name_ja = extract_ruby_base(ja_spans[0])
    else:
        ja_span = def_p.find('span', {'lang': 'ja'})
        if ja_span:
            name_ja = extract_ruby_base(ja_span)

    # 4. 中文描述：定义句之后的内容 + 后续段落
    desc_parts = []
    # 尝试匹配 "能力的一种。" 或 "能力之一，" 之后的内容
    desc_match = re.search(r'(?:能力的一种|能力之一)[。，.]\s*(.+)', def_text, re.DOTALL)
    if desc_match:
        remaining = desc_match.group(1).strip()
        if remaining:
            desc_parts.append(remaining)
    else:
        # 匹配右括号后第一个句号之后的内容
        paren_match = re.search(r'[）)][^。]*。\s*(.+)', def_text, re.DOTALL)
        if paren_match:
            remaining = paren_match.group(1).strip()
            if remaining:
                desc_parts.append(remaining)

    for p in paragraphs[1:]:
        text = p.get_text().strip()
        if text:
            desc_parts.append(text)

    desc_zh = '\n'.join(desc_parts)
    return name_zh, name_en, name_ja, desc_zh


def extract_ja_description(file_path):
    """从日文 HTML 提取日文描述"""
    parser_output = parse_html(file_path)
    if not parser_output:
        return ''

    desc_parts = []
    for child in parser_output.children:
        if not hasattr(child, 'name') or child.name is None:
            continue
        if child.name == 'h2':
            break
        if child.name == 'div':
            div_text = child.get_text()
            if 'このページでは' in div_text or '曖昧さ回避' in div_text:
                continue
        if child.name == 'p':
            text = child.get_text().strip()
            if text and 'このページでは' not in text:
                desc_parts.append(text)

    return '\n'.join(desc_parts)


def extract_en_description(file_path):
    """从英文 HTML 提取英文描述"""
    parser_output = parse_html(file_path)
    if not parser_output:
        return ''

    def skip_en_disambig(p):
        return 'If you were looking for' in p.get_text()

    paragraphs = get_text_before_h2(parser_output, skip_en_disambig)
    desc_parts = [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
    return '\n'.join(desc_parts)


def main():
    print("=" * 60)
    print("从 stat HTML 提取能力数据 → CSV")
    print("=" * 60)
    print(f"HTML 目录: {STAT_DIR}")
    print(f"输出文件: {OUTPUT_CSV}\n")

    rows = []
    for stat in STATS_CONFIG:
        stat_id = stat['id']
        prefix = stat['file_prefix']

        zh_file = STAT_DIR / f"{prefix}-zh.html"
        en_file = STAT_DIR / f"{prefix}-en.html"
        ja_file = STAT_DIR / f"{prefix}-ja.html"

        print(f"  [{stat_id}] {prefix}")

        # 中文 HTML → 名称 + 中文描述
        if zh_file.exists():
            name_zh, name_en, name_ja, desc_zh = extract_zh_info(zh_file)
        else:
            name_zh = name_en = name_ja = desc_zh = ''
            print(f"      ⚠ 缺少: {zh_file.name}")

        # 日文描述
        desc_ja = extract_ja_description(ja_file) if ja_file.exists() else ''

        # 英文描述
        desc_en = extract_en_description(en_file) if en_file.exists() else ''

        row = {
            'id': stat_id,
            'name_en': name_en,
            'name_zh': name_zh,
            'abbr_zh': stat['abbr_zh'],
            'abbr_ja': stat['abbr_ja'],
            'abbr_en': stat['abbr_en'],
            'name_ja': name_ja,
            'description_zh': desc_zh,
            'description_en': desc_en,
            'description_ja': desc_ja,
        }
        rows.append(row)

        print(f"      名称: {name_zh} / {name_en} / {name_ja}")
        print(f"      简称: {stat['abbr_zh']} / {stat['abbr_en']} / {stat['abbr_ja']}")
        desc_preview = (desc_zh[:50] + '...') if len(desc_zh) > 50 else (desc_zh or '(空)')
        print(f"      描述zh: {desc_preview}")

    # 写入 CSV（tab 分隔，UTF-8 with BOM 方便 Excel 打开）
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, delimiter=',')
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'=' * 60}")
    print(f"✓ 已导出 {len(rows)} 条记录到 {OUTPUT_CSV}")
    print(f"  请检查并手动修正后，运行 import_stats_csv.py 导入数据库")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
