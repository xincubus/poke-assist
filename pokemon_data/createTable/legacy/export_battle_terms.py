#!/usr/bin/env python3
"""
导出 battle_terms 表到 Excel 文件
支持手动编辑后再导入
"""

import sqlite3
import sys
import io
from pathlib import Path
import pandas as pd
from datetime import datetime

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置路径
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "pokemonData.db"
EXPORT_DIR = BASE_DIR / "exports"


def export_to_excel():
    """导出 battle_terms 表到 Excel"""
    print("\n" + "=" * 60)
    print("导出 battle_terms 表到 Excel")
    print("=" * 60)

    # 确保导出目录存在
    EXPORT_DIR.mkdir(exist_ok=True)

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)

    # 读取数据
    query = """
        SELECT id, term, aliases, category, definition,
               formula, related_field, related_value, language
        FROM battle_terms
        ORDER BY category, id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 生成文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_file = EXPORT_DIR / f"battle_terms_{timestamp}.xlsx"

    # 导出到 Excel
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='battle_terms', index=False)

        # 获取工作表并设置列宽
        worksheet = writer.sheets['battle_terms']
        worksheet.column_dimensions['A'].width = 8   # id
        worksheet.column_dimensions['B'].width = 20  # term
        worksheet.column_dimensions['C'].width = 25  # aliases
        worksheet.column_dimensions['D'].width = 18  # category
        worksheet.column_dimensions['E'].width = 40  # definition
        worksheet.column_dimensions['F'].width = 50  # formula
        worksheet.column_dimensions['G'].width = 25  # related_field
        worksheet.column_dimensions['H'].width = 20  # related_value
        worksheet.column_dimensions['I'].width = 10  # language

    print(f"✓ 已导出 {len(df)} 条记录")
    print(f"✓ 文件路径: {excel_file}")
    print("\n分类统计:")
    category_counts = df['category'].value_counts()
    for category, count in category_counts.items():
        print(f"  {category}: {count} 条")

    print("\n" + "=" * 60)
    print("导出完成！")
    print("=" * 60)
    print("\n使用说明:")
    print("1. 在 Excel 中编辑数据（可新增、修改、删除行）")
    print("2. 新增行时 id 列留空（导入时自动生成）")
    print("3. 保存后使用 import_battle_terms.py 导入")
    print("=" * 60)

    return excel_file


def main():
    print("=" * 60)
    print("宝可梦对战术语表导出工具")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")

    try:
        excel_file = export_to_excel()
    except Exception as e:
        print(f"\n✗ 导出失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
