#!/usr/bin/env python3
"""
检查 weather.csv 中的缺失字段，支持手动补录
用法：
  python supplement_weather_csv.py           # 检查缺失情况
  python supplement_weather_csv.py --check   # 仅检查，不修改
  python supplement_weather_csv.py --reparse # 重新从 HTML 解析（覆盖已有数据）

如果 HTML 已下载但 extract 结果有缺失，可以：
1. 先运行 --check 查看哪些字段缺失
2. 手动编辑 weather.csv 补录
3. 或修改 extract_weather_to_csv.py 的解析逻辑后重新运行

输出：weather_updated.csv（与 weather.csv 相同格式，作为导入源）
"""

import os
import sys
import csv
import shutil
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CSV_DIR = Path(__file__).parent
INPUT_CSV = CSV_DIR / "weather.csv"
OUTPUT_CSV = CSV_DIR / "weather_updated.csv"

EFFECT_FIELDS = [
    "type_effect_zh", "type_effect_en", "type_effect_ja",
    "move_effect_zh", "move_effect_en", "move_effect_ja",
    "ability_effect_zh", "ability_effect_en", "ability_effect_ja",
]
ALL_FIELDS = [
    "id", "name_en", "name_zh", "name_ja",
    "description_zh", "description_en", "description_ja",
] + EFFECT_FIELDS


def load_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def check_missing(rows):
    """打印缺失字段统计"""
    print(f"\n{'='*60}")
    print(f"{'天气':<12} {'缺失字段'}")
    print(f"{'='*60}")
    total_missing = 0
    for row in rows:
        missing = [f for f in ALL_FIELDS if not row.get(f, "").strip()]
        if missing:
            print(f"  {row.get('name_zh', row.get('name_en', '?')):<10} {', '.join(missing)}")
            total_missing += len(missing)
    if total_missing == 0:
        print("  ✓ 所有字段均已填写")
    else:
        print(f"\n共缺失 {total_missing} 个字段")
    print(f"{'='*60}\n")
    return total_missing


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="仅检查缺失，不生成输出文件")
    parser.add_argument("--reparse", action="store_true", help="重新从 HTML 解析（调用 extract 脚本）")
    args = parser.parse_args()

    if args.reparse:
        print("重新运行 extract_weather_to_csv.py...")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(CSV_DIR / "extract_weather_to_csv.py")],
            capture_output=False
        )
        if result.returncode != 0:
            print("❌ extract 脚本运行失败")
            return

    if not INPUT_CSV.exists():
        print(f"❌ 找不到 {INPUT_CSV}")
        print("请先运行 extract_weather_to_csv.py")
        return

    rows = load_csv(INPUT_CSV)
    print(f"读取 {len(rows)} 条记录")

    missing_count = check_missing(rows)

    if args.check:
        return

    # 生成 weather_updated.csv（直接复制，手动补录后再运行即可）
    shutil.copy2(INPUT_CSV, OUTPUT_CSV)
    print(f"✓ 已生成 {OUTPUT_CSV}")

    if missing_count > 0:
        print(f"\n提示：有 {missing_count} 个字段缺失。")
        print("可以：")
        print("  1. 手动编辑 weather_updated.csv 补录缺失数据")
        print("  2. 或修改 extract_weather_to_csv.py 的解析逻辑后运行 --reparse")
    else:
        print("✓ 数据完整，可直接运行 import_weather_csv.py 导入数据库")


if __name__ == "__main__":
    main()
