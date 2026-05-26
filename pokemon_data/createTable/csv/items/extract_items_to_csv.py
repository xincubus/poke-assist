"""
将 heldItem/ 目录下的 JSON 文件转换为 items.csv

输出字段：
  id, name_ja, name_zh, name_en, category,
  fling_power, fling_effect,
  description_ja, description_zh, description_en,
  image_path

用法：
  python extract_items_to_csv.py
  python extract_items_to_csv.py --output my_items.csv
"""

import json
import csv
import argparse
import sys
from pathlib import Path

# Windows GBK 终端兼容
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 路径配置
SCRIPT_DIR = Path(__file__).parent
ITEMS_DIR     = SCRIPT_DIR.parent.parent.parent / "heldItem"
IMAGE_DIR     = SCRIPT_DIR.parent.parent.parent / "heldItemImage"
OUTPUT_CSV    = SCRIPT_DIR / "items.csv"

COLUMNS = [
    "id", "name_ja", "name_zh", "name_en",
    "category", "fling_power", "fling_effect",
    "description_ja", "description_zh", "description_en",
    "image_path",
]


def parse_item(data: dict) -> dict:
    item_id   = data["id"]
    name_en   = data["name"]
    category  = data["category"]["name"]
    fling_power  = data.get("fling_power") or ""
    fling_effect = (data["fling_effect"]["name"]
                    if data.get("fling_effect") else "")

    name_ja = name_zh = ""
    for entry in data.get("names", []):
        lang = entry["language"]["name"]
        if lang == "ja":
            name_ja = entry["name"]
        elif lang == "zh-hans":
            name_zh = entry["name"]

    def last_flavor(lang_code):
        texts = [f["text"] for f in data.get("flavor_text_entries", [])
                 if f["language"]["name"] == lang_code]
        return texts[-1].replace("\n", " ").replace("\f", " ") if texts else ""

    return {
        "id":             item_id,
        "name_ja":        name_ja,
        "name_zh":        name_zh,
        "name_en":        name_en,
        "category":       category,
        "fling_power":    fling_power,
        "fling_effect":   fling_effect,
        "description_ja": last_flavor("ja"),
        "description_zh": last_flavor("zh-hans"),
        "description_en": last_flavor("en"),
        "image_path":     f"heldItemImage/{name_en}.png" if (IMAGE_DIR / f"{name_en}.png").exists() else "",
    }


def convert(output_path: Path):
    if not ITEMS_DIR.exists():
        print(f"[ERROR] heldItem 目录不存在：{ITEMS_DIR}")
        return

    json_files = sorted(ITEMS_DIR.glob("*.json"))
    if not json_files:
        print(f"[ERROR] {ITEMS_DIR} 下没有 JSON 文件")
        return

    rows = []
    errors = []
    for f in json_files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            rows.append(parse_item(data))
        except Exception as e:
            errors.append((f.name, str(e)))

    # 按 id 排序
    rows.sort(key=lambda r: r["id"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✓ 已写入 {len(rows)} 条记录 → {output_path}")
    if errors:
        print(f"  跳过 {len(errors)} 个文件（解析失败）：")
        for name, err in errors[:10]:
            print(f"    {name}: {err}")

    # 统计缺中文名的条数
    missing_zh = sum(1 for r in rows if not r["name_zh"])
    print(f"  name_zh 为空：{missing_zh} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="heldItem JSON → items.csv")
    parser.add_argument("--output", default=str(OUTPUT_CSV),
                        help="输出 CSV 路径（默认：items.csv）")
    args = parser.parse_args()
    convert(Path(args.output))
