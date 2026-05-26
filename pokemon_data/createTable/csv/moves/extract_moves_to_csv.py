"""
将 moves/ 目录下的 JSON 文件转换为 moves.csv

输出字段（与 moves 表一致）：
  id, name_ja, name_zh, name_en,
  type, damage_class, power, accuracy, priority, pp,
  description_ja, description_zh, description_en,
  effect_ja, effect_zh, effect_en,
  learned_by_pokemon, type_id

说明：
  description_* — 游戏内 flavor text（最新版本）
  effect_*      — 机制效果描述；effect_en 从 JSON effect_entries 提取，
                  effect_ja / effect_zh 留空，待爬虫补全

用法：
  python download_moves_csv.py
  python download_moves_csv.py --output my_moves.csv
"""

import json
import csv
import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
MOVES_DIR = SCRIPT_DIR.parent.parent.parent / "moves"
OUTPUT_CSV = SCRIPT_DIR / "moves.csv"

COLUMNS = [
    "id", "name_ja", "name_zh", "name_en",
    "type", "damage_class", "power", "accuracy", "priority", "pp",
    "description_ja", "description_zh", "description_en",
    "effect_ja", "effect_zh", "effect_en",
    "learned_by_pokemon", "type_id",
]

# type 名称 → type_id（与 types 表一致）
TYPE_ID_MAP = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10,
    "water": 11, "grass": 12, "electric": 13, "psychic": 14, "ice": 15,
    "dragon": 16, "dark": 17, "fairy": 18, "stellar": 19, "unknown": 10001,
    "shadow": 10002,
}


def last_flavor(data: dict, lang: str) -> str:
    texts = [
        e["flavor_text"]
        for e in data.get("flavor_text_entries", [])
        if e["language"]["name"] == lang
    ]
    return texts[-1].replace("\n", " ").replace("\f", " ") if texts else ""


def effect_en(data: dict) -> str:
    for e in data.get("effect_entries", []):
        if e["language"]["name"] == "en":
            text = e["effect"]
            chance = data.get("effect_chance")
            if chance is not None:
                text = text.replace("$effect_chance", str(chance))
            return text.replace("\n", " ").replace("\f", " ")
    return ""


def parse_move(data: dict) -> dict:
    names = {e["language"]["name"]: e["name"] for e in data.get("names", [])}

    type_name = data["type"]["name"]
    learned_by = len(data.get("learned_by_pokemon", []))

    return {
        "id":               data["id"],
        "name_ja":          names.get("ja", ""),
        "name_zh":          names.get("zh-hans", ""),
        "name_en":          data["name"],
        "type":             type_name,
        "damage_class":     data["damage_class"]["name"],
        "power":            data["power"] if data["power"] is not None else "",
        "accuracy":         data["accuracy"] if data["accuracy"] is not None else "",
        "priority":         data["priority"],
        "pp":               data["pp"] if data["pp"] is not None else "",
        "description_ja":   last_flavor(data, "ja"),
        "description_zh":   last_flavor(data, "zh-hans"),
        "description_en":   last_flavor(data, "en"),
        "effect_ja":        "",
        "effect_zh":        "",
        "effect_en":        effect_en(data),
        "learned_by_pokemon": learned_by,
        "type_id":          TYPE_ID_MAP.get(type_name, ""),
    }


def convert(output_path: Path):
    if not MOVES_DIR.exists():
        print(f"[ERROR] moves 目录不存在：{MOVES_DIR}")
        return

    json_files = sorted(MOVES_DIR.glob("*.json"))
    if not json_files:
        print(f"[ERROR] {MOVES_DIR} 下没有 JSON 文件")
        return

    rows = []
    errors = []
    for f in json_files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            rows.append(parse_move(data))
        except Exception as e:
            errors.append((f.name, str(e)))

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

    missing_zh = sum(1 for r in rows if not r["name_zh"])
    missing_effect_en = sum(1 for r in rows if not r["effect_en"])
    print(f"  name_zh 为空：{missing_zh} 条")
    print(f"  effect_en 为空：{missing_effect_en} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="moves JSON → moves.csv")
    parser.add_argument("--output", default=str(OUTPUT_CSV),
                        help="输出 CSV 路径（默认：moves.csv）")
    args = parser.parse_args()
    convert(Path(args.output))
