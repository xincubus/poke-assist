"""
为 pokemonData.db 中所有含 name_zh 的表添加拼音列。
- 普通表：name_zh → name_pinyin (全拼) + name_pinyin_abbr (首字母)
- battle_terms：term → term_pinyin + term_pinyin_abbr
                aliases (逗号分隔) → aliases_pinyin + aliases_pinyin_abbr

用法：python add_pinyin.py [--dry-run]
"""

import argparse
import sqlite3
import os
from pypinyin import pinyin, Style

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pokemonData.db')

# 普通表：都用 name_zh 列
NORMAL_TABLES = [
    'pokemons', 'moves', 'abilities', 'items', 'types',
    'natures', 'status', 'stats',
]

def to_pinyin(text):
    """中文 → 全拼，空格分隔。非中文字符原样保留。"""
    if not text or not text.strip():
        return '', ''
    result = pinyin(text, style=Style.NORMAL, errors='default')
    full = ' '.join([seg[0] for seg in result])
    abbr = ''.join([seg[0][0] for seg in result])
    return full, abbr


def ensure_column(cur, table, col_name, col_type='TEXT'):
    """如果列不存在则添加。"""
    cur.execute(f"PRAGMA table_info({table})")
    existing = [row[1] for row in cur.fetchall()]
    if col_name not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
        return True
    return False


def process_normal_table(cur, table, dry_run=False):
    """处理普通表：name_zh → name_pinyin + name_pinyin_abbr"""
    ensure_column(cur, table, 'name_pinyin')
    ensure_column(cur, table, 'name_pinyin_abbr')

    cur.execute(f"SELECT id, name_zh FROM {table} WHERE name_zh IS NOT NULL AND name_zh != ''")
    rows = cur.fetchall()
    updated = 0
    for row_id, name_zh in rows:
        full, abbr = to_pinyin(name_zh)
        if not dry_run:
            cur.execute(
                f"UPDATE {table} SET name_pinyin = ?, name_pinyin_abbr = ? WHERE id = ?",
                (full, abbr, row_id)
            )
        updated += 1
    return updated


def process_battle_terms(cur, dry_run=False):
    """处理 battle_terms：term → term_pinyin + term_pinyin_abbr, aliases → aliases_pinyin + aliases_pinyin_abbr"""
    ensure_column(cur, 'battle_terms', 'term_pinyin')
    ensure_column(cur, 'battle_terms', 'term_pinyin_abbr')
    ensure_column(cur, 'battle_terms', 'aliases_pinyin')
    ensure_column(cur, 'battle_terms', 'aliases_pinyin_abbr')

    cur.execute("SELECT id, term, aliases FROM battle_terms")
    rows = cur.fetchall()
    updated = 0
    for row_id, term, aliases in rows:
        # term 拼音
        term_full, term_abbr = to_pinyin(term) if term and term.strip() else ('', '')

        # aliases 拼音
        aliases_full_str, aliases_abbr_str = '', ''
        if aliases and aliases.strip():
            parts = [a.strip() for a in aliases.split(',') if a.strip()]
            fulls, abbrs = [], []
            for part in parts:
                f, a = to_pinyin(part)
                fulls.append(f)
                abbrs.append(a)
            aliases_full_str = ','.join(fulls)
            aliases_abbr_str = ','.join(abbrs)

        if not dry_run:
            cur.execute(
                "UPDATE battle_terms SET term_pinyin = ?, term_pinyin_abbr = ?, aliases_pinyin = ?, aliases_pinyin_abbr = ? WHERE id = ?",
                (term_full, term_abbr, aliases_full_str, aliases_abbr_str, row_id)
            )
        updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser(description='为 pokemonData.db 添加拼音列')
    parser.add_argument('--dry-run', action='store_true', help='只统计，不写入')
    args = parser.parse_args()

    db_path = os.path.normpath(DB_PATH)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print(f"数据库: {db_path}")
    if args.dry_run:
        print("(dry-run 模式，不写入)\n")

    total = 0
    for table in NORMAL_TABLES:
        count = process_normal_table(cur, table, args.dry_run)
        print(f"  {table}: {count} 条")
        total += count

    count = process_battle_terms(cur, args.dry_run)
    print(f"  battle_terms (aliases): {count} 条")
    total += count

    if not args.dry_run:
        conn.commit()
        print(f"\n完成，共更新 {total} 条记录")
    else:
        print(f"\n(dry-run) 共 {total} 条待更新")

    conn.close()


if __name__ == '__main__':
    main()
