#!/usr/bin/env python3
"""
从 pokemon_data/status 目录下的 HTML 文件中提取异常状态信息，导出为 CSV
CSV 输出到 pokemon_data/createTable/csv/status/status.csv，方便手动修正后再导入数据库
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

BASE_DIR = Path(__file__).parent.parent.parent.parent
STATUS_DIR = BASE_DIR / "status"
OUTPUT_CSV = Path(__file__).parent / "status.csv"

# 8 种状态配置（与 download_status_html.py 对应，排除主页面）
STATUS_CONFIG = [
    {'id': 1, 'file_prefix': 'poison'},
    {'id': 2, 'file_prefix': 'bad-poison'},
    {'id': 3, 'file_prefix': 'burn'},
    {'id': 4, 'file_prefix': 'freeze'},
    {'id': 5, 'file_prefix': 'paralysis'},
    {'id': 6, 'file_prefix': 'sleep'},
    {'id': 7, 'file_prefix': 'drowsy'},
    {'id': 8, 'file_prefix': 'faint'},
]

CSV_HEADERS = [
    'id', 'name_en', 'name_ja', 'name_zh',
    'description_zh', 'description_en', 'description_ja'
]


def parse_html(file_path):
    """解析 HTML 文件，以二进制读取并指定 utf-8 编码"""
    with open(file_path, 'rb') as f:
        soup = BeautifulSoup(f.read(), 'html.parser', from_encoding='utf-8')
    return soup.find('div', class_='mw-parser-output')


def extract_zh_info(file_path):
    """从中文 HTML 提取：(name_zh, name_en, name_ja, desc_zh)

    中文 wiki 的状态页面通常有一个信息表格，包含：
    - <font size="4px">灼伤</font> → 中文名
    - <span lang="ja">やけど</span> → 日文名
    - <span lang="en">Burn</span> → 英文名
    - <td class="roundy b-..."> → 简短描述
    """
    parser_output = parse_html(file_path)
    if not parser_output:
        return '', '', '', ''

    name_zh = ''
    name_en = ''
    name_ja = ''
    desc_zh = ''

    # 1. 从信息表格中提取名称
    # 查找包含 <font size="4px"> 的 th（状态名称所在行）
    font_tag = parser_output.find('font', attrs={'size': '4px'})
    if font_tag:
        name_zh = font_tag.get_text().strip()
        # 同行的 <span lang="ja"> 和 <span lang="en">
        parent_th = font_tag.find_parent('th')
        if parent_th:
            ja_span = parent_th.find('span', {'lang': 'ja'})
            en_span = parent_th.find('span', {'lang': 'en'})
            if ja_span:
                name_ja = ja_span.get_text().strip()
            if en_span:
                name_en = en_span.get_text().strip()

    # 2. 如果表格没找到名称，从第一个 <p> 的 <b> 标签中尝试
    if not name_zh:
        first_p = parser_output.find('p')
        if first_p:
            first_b = first_p.find('b')
            if first_b:
                name_zh = first_b.get_text().strip()

    if not name_en:
        for b in parser_output.find_all('b'):
            candidate = b.get_text().strip()
            if candidate and re.match(r'^[A-Za-z][A-Za-z\s.\-]+$', candidate):
                name_en = candidate
                break

    if not name_ja:
        ja_span = parser_output.find('span', {'lang': 'ja'})
        if ja_span:
            name_ja = ja_span.get_text().strip()

    # 3. 中文描述：从第一个 <p> 标签中获取
    desc_parts = []
    for child in parser_output.children:
        if not hasattr(child, 'name') or child.name is None:
            continue
        if child.name == 'h2':
            break
        if child.name == 'p':
            text = child.get_text().strip()
            # 跳过消歧义段落
            if text and '这篇文章讲述' not in text and not child.find('img'):
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
        text = p.get_text()
        return 'redirects here' in text or 'If you were looking for' in text

    desc_parts = []
    for child in parser_output.children:
        if not hasattr(child, 'name') or child.name is None:
            continue
        if child.name == 'h2':
            break
        if child.name in ('dl',):
            # 跳过消歧义的 <dl> 段落
            continue
        if child.name == 'p':
            if skip_en_disambig(child):
                continue
            text = child.get_text().strip()
            if text:
                desc_parts.append(text)

    return '\n'.join(desc_parts)


def main():
    print("=" * 60)
    print("从 status HTML 提取异常状态数据 → CSV")
    print("=" * 60)
    print(f"HTML 目录: {STATUS_DIR}")
    print(f"输出文件: {OUTPUT_CSV}\n")

    rows = []
    for status in STATUS_CONFIG:
        status_id = status['id']
        prefix = status['file_prefix']

        zh_file = STATUS_DIR / f"{prefix}-zh.html"
        en_file = STATUS_DIR / f"{prefix}-en.html"
        ja_file = STATUS_DIR / f"{prefix}-ja.html"

        print(f"  [{status_id}] {prefix}")

        # 中文 HTML → 名称 + 中文描述
        if zh_file.exists():
            name_zh, name_en, name_ja, desc_zh = extract_zh_info(zh_file)
        else:
            name_zh = name_en = name_ja = desc_zh = ''
            print(f"      ⚠ 缺少: {zh_file.name}")

        # 日文描述
        if ja_file.exists():
            desc_ja = extract_ja_description(ja_file)
        else:
            desc_ja = ''
            print(f"      ⚠ 缺少: {ja_file.name}")

        # 英文描述
        if en_file.exists():
            desc_en = extract_en_description(en_file)
        else:
            desc_en = ''
            print(f"      ⚠ 缺少: {en_file.name}")

        row = {
            'id': status_id,
            'name_en': name_en,
            'name_ja': name_ja,
            'name_zh': name_zh,
            'description_zh': desc_zh,
            'description_en': desc_en,
            'description_ja': desc_ja,
        }
        rows.append(row)

        print(f"      名称: {name_zh} / {name_en} / {name_ja}")
        desc_preview = (desc_zh[:50] + '...') if len(desc_zh) > 50 else (desc_zh or '(空)')
        print(f"      描述zh: {desc_preview}")

    # 写入 CSV（UTF-8 with BOM 方便 Excel 打开，逗号分隔）
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'=' * 60}")
    print(f"✓ 已导出 {len(rows)} 条记录到 {OUTPUT_CSV}")
    print(f"  请检查并手动修正后，运行 import_status_csv.py 导入数据库")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
