#!/usr/bin/env python3
"""
从 Excel 文件导入 battle_terms 表数据
支持新增、更新、删除操作
"""

import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd
import argparse

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置路径
BASE_DIR = Path(__file__).parent.parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"
EXPORT_DIR = BASE_DIR / "exports"


def validate_data(df):
    """验证数据格式"""
    print("\n" + "=" * 60)
    print("验证数据格式")
    print("=" * 60)

    errors = []

    # 检查必填字段
    required_fields = ['term', 'category']
    optional_with_check = []  # definition 改为选填
    for field in required_fields:
        if field not in df.columns:
            errors.append(f"缺少必填列: {field}")
        elif df[field].isna().any():
            null_rows = df[df[field].isna()].index.tolist()
            errors.append(f"列 {field} 存在空值，行号: {null_rows}")

    # 检查 category 值是否合法
    valid_categories = ['stat_spread', 'item_alias', 'role', 'mechanic', 'calc_concept', 'ev_nature', 'pokemon_alias']
    if 'category' in df.columns:
        invalid_categories = df[~df['category'].isin(valid_categories)]['category'].unique()
        if len(invalid_categories) > 0:
            errors.append(f"无效的 category 值: {invalid_categories.tolist()}")

    if errors:
        print("✗ 数据验证失败:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("✓ 数据验证通过")
    return True


def import_from_excel(excel_file, mode='replace'):
    """
    从 Excel 导入数据
    mode: 'replace' 完全替换, 'append' 追加, 'update' 更新
    """
    print("\n" + "=" * 60)
    print(f"从 Excel 导入 battle_terms 数据 (模式: {mode})")
    print("=" * 60)

    # 读取 Excel
    if not Path(excel_file).exists():
        print(f"✗ 文件不存在: {excel_file}")
        return False

    df = pd.read_excel(excel_file, sheet_name='battle_terms')
    # 跳过 term 和 category 都为空的行
    df = df.dropna(subset=['term', 'category'], how='all')
    print(f"✓ 读取到 {len(df)} 条记录")

    # 验证数据
    if not validate_data(df):
        return False

    # 处理 NaN 值
    df = df.where(pd.notna(df), None)

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        if mode == 'replace':
            # 完全替换：清空表后插入
            print("\n清空现有数据...")
            cursor.execute('DELETE FROM battle_terms')
            print("✓ 已清空")

            # 插入新数据（忽略 id 列，让数据库自动生成）
            print("\n插入新数据...")
            for idx, row in df.iterrows():
                cursor.execute('''
                    INSERT INTO battle_terms (term, aliases, category, definition,
                                            formula, related_field, related_value, language)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['term'],
                    row.get('aliases'),
                    row['category'],
                    row['definition'],
                    row.get('formula'),
                    row.get('related_field'),
                    row.get('related_value'),
                    row.get('language', 'zh')
                ))
            print(f"✓ 已插入 {len(df)} 条记录")

        elif mode == 'append':
            # 追加模式：只插入新记录
            print("\n追加新数据...")
            inserted = 0
            for idx, row in df.iterrows():
                # 检查是否已存在（根据 term 和 category）
                cursor.execute('''
                    SELECT id FROM battle_terms
                    WHERE term = ? AND category = ?
                ''', (row['term'], row['category']))

                if cursor.fetchone() is None:
                    cursor.execute('''
                        INSERT INTO battle_terms (term, aliases, category, definition,
                                                formula, related_field, related_value, language)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row['term'],
                        row.get('aliases'),
                        row['category'],
                        row['definition'],
                        row.get('formula'),
                        row.get('related_field'),
                        row.get('related_value'),
                        row.get('language', 'zh')
                    ))
                    inserted += 1
            print(f"✓ 已追加 {inserted} 条新记录")

        elif mode == 'update':
            # 更新模式：根据 id 更新，无 id 则插入
            print("\n更新数据...")
            updated = 0
            inserted = 0

            for idx, row in df.iterrows():
                if pd.notna(row.get('id')):
                    # 有 id，执行更新
                    cursor.execute('''
                        UPDATE battle_terms
                        SET term = ?, aliases = ?, category = ?, definition = ?,
                            formula = ?, related_field = ?, related_value = ?, language = ?
                        WHERE id = ?
                    ''', (
                        row['term'],
                        row.get('aliases'),
                        row['category'],
                        row['definition'],
                        row.get('formula'),
                        row.get('related_field'),
                        row.get('related_value'),
                        row.get('language', 'zh'),
                        int(row['id'])
                    ))
                    if cursor.rowcount > 0:
                        updated += 1
                else:
                    # 无 id，执行插入
                    cursor.execute('''
                        INSERT INTO battle_terms (term, aliases, category, definition,
                                                formula, related_field, related_value, language)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row['term'],
                        row.get('aliases'),
                        row['category'],
                        row['definition'],
                        row.get('formula'),
                        row.get('related_field'),
                        row.get('related_value'),
                        row.get('language', 'zh')
                    ))
                    inserted += 1

            print(f"✓ 已更新 {updated} 条记录")
            print(f"✓ 已插入 {inserted} 条新记录")

        conn.commit()

        # 显示最终统计
        cursor.execute('SELECT COUNT(*) FROM battle_terms')
        total = cursor.fetchone()[0]
        cursor.execute('''
            SELECT category, COUNT(*) as count
            FROM battle_terms
            GROUP BY category
            ORDER BY category
        ''')
        categories = cursor.fetchall()

        print("\n" + "=" * 60)
        print(f"导入完成！当前共 {total} 条记录")
        print("=" * 60)
        print("\n分类统计:")
        for category, count in categories:
            print(f"  {category}: {count} 条")

        conn.close()
        return True

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"\n✗ 导入失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='从 Excel 导入 battle_terms 数据')
    parser.add_argument('excel_file', help='Excel 文件路径')
    parser.add_argument('--mode', choices=['replace', 'append', 'update'],
                       default='replace',
                       help='导入模式: replace(替换), append(追加), update(更新)')

    args = parser.parse_args()

    print("=" * 60)
    print("宝可梦对战术语表导入工具")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    print(f"Excel 文件: {args.excel_file}")
    print(f"导入模式: {args.mode}")

    success = import_from_excel(args.excel_file, args.mode)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
