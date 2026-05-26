"""
从 pokemon_data/pokemon/*.json 提取招式学习记录，生成 pokemon_moves.csv

输出字段（与 pokemon_moves 表一致）：
  pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_ja, pokemon_name_en,
  move_id, move_name_zh, move_name_en, move_name_ja,
  learn_method, level, version_group, generation

用法：
  python extract_pokemon_moves_csv.py
  python extract_pokemon_moves_csv.py --output my_output.csv
"""

import json
import csv
import sqlite3
import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR  = Path(__file__).parent
POKEMON_DIR = SCRIPT_DIR.parent.parent.parent / "pokemon"
DB_FILE     = SCRIPT_DIR.parent.parent.parent / "pokemonData.db"
OUTPUT_CSV  = SCRIPT_DIR / "pokemon_moves.csv"

COLUMNS = [
    "pokedex_id", "pokeapi_id", "pokemon_name_zh", "pokemon_name_ja", "pokemon_name_en",
    "move_id", "move_name_zh", "move_name_en", "move_name_ja",
    "learn_method", "level", "version_group", "generation",
]

VERSION_GROUP_TO_GENERATION = {
    "red-blue": 1, "yellow": 1, "red-green-japan": 1, "blue-japan": 1,
    "gold-silver": 2, "crystal": 2,
    "ruby-sapphire": 3, "emerald": 3, "firered-leafgreen": 3, "colosseum": 3, "xd": 3,
    "diamond-pearl": 4, "platinum": 4, "heartgold-soulsilver": 4,
    "black-white": 5, "black-2-white-2": 5,
    "x-y": 6, "omega-ruby-alpha-sapphire": 6,
    "sun-moon": 7, "ultra-sun-ultra-moon": 7, "lets-go-pikachu-lets-go-eevee": 7,
    "sword-shield": 8, "brilliant-diamond-shining-pearl": 8, "legends-arceus": 8,
    "scarlet-violet": 9,
}

LEARN_METHOD_MAP = {
    "level-up": "等级提升",
    "egg": "蛋招式",
    "tutor": "教学招式",
    "machine": "招式机",
    "stadium-surfing-pikachu": "特殊",
    "light-ball-egg": "特殊",
    "colosseum-purification": "特殊",
    "xd-shadow": "特殊",
    "xd-purification": "特殊",
    "form-change": "形态变化",
}


def build_lookup_tables(conn):
    """从数据库构建 pokeapi_id → pokemon 信息 和 move_name_en → move 信息 的映射"""
    cur = conn.cursor()

    cur.execute("SELECT pokeapi_id, pokedex_id, name_zh, name_ja, name_en FROM pokemons")
    pokemon_map = {row[0]: row for row in cur.fetchall()}

    cur.execute("SELECT id, name_zh, name_en, name_ja FROM moves")
    move_rows = cur.fetchall()
    move_map = {}
    for row in move_rows:
        move_id, name_zh, name_en, name_ja = row
        if name_en:
            move_map[name_en.lower()] = row
            move_map[name_en.lower().replace(" ", "-")] = row

    return pokemon_map, move_map


def extract_move_id_from_url(url):
    return int(url.rstrip("/").split("/")[-1])


def process_json(json_path, pokemon_map, move_map):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    pokeapi_id = data["id"]
    pokemon_info = pokemon_map.get(pokeapi_id)
    if pokemon_info:
        _, pokedex_id, name_zh, name_ja, name_en = pokemon_info
    else:
        pokedex_id = pokeapi_id
        name_zh = name_ja = ""
        name_en = data["name"]

    rows = []
    for move_entry in data.get("moves", []):
        move_name_en = move_entry["move"]["name"]
        move_api_id  = extract_move_id_from_url(move_entry["move"]["url"])

        move_info = (
            move_map.get(move_name_en.lower()) or
            move_map.get(move_name_en.lower().replace("-", " "))
        )
        if move_info:
            move_id, move_name_zh, _, move_name_ja = move_info
        else:
            move_id      = move_api_id
            move_name_zh = ""
            move_name_ja = ""

        for detail in move_entry["version_group_details"]:
            vg         = detail["version_group"]["name"]
            generation = VERSION_GROUP_TO_GENERATION.get(vg, 0)
            if generation == 0:
                continue

            method_en   = detail["move_learn_method"]["name"]
            learn_method = LEARN_METHOD_MAP.get(method_en, method_en)
            level        = detail["level_learned_at"] or ""

            rows.append({
                "pokedex_id":      pokedex_id,
                "pokeapi_id":      pokeapi_id,
                "pokemon_name_zh": name_zh or "",
                "pokemon_name_ja": name_ja or "",
                "pokemon_name_en": name_en,
                "move_id":         move_id,
                "move_name_zh":    move_name_zh or "",
                "move_name_en":    move_name_en,
                "move_name_ja":    move_name_ja or "",
                "learn_method":    learn_method,
                "level":           level,
                "version_group":   vg,
                "generation":      generation,
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description="pokemon JSON → pokemon_moves.csv")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="输出 CSV 路径")
    args = parser.parse_args()
    output_path = Path(args.output)

    if not POKEMON_DIR.exists():
        print(f"[ERROR] pokemon 目录不存在：{POKEMON_DIR}")
        return
    if not DB_FILE.exists():
        print(f"[ERROR] 数据库不存在：{DB_FILE}")
        return

    conn = sqlite3.connect(DB_FILE)
    pokemon_map, move_map = build_lookup_tables(conn)
    conn.close()
    print(f"已加载 {len(pokemon_map)} 个宝可梦，{len(move_map)//2} 个招式")

    json_files = sorted(
        f for f in POKEMON_DIR.glob("*.json")
        if not f.name.endswith("_species.json")
    )
    print(f"找到 {len(json_files)} 个宝可梦 JSON 文件，开始提取...")

    all_rows = []
    errors   = []
    for i, jf in enumerate(json_files, 1):
        try:
            all_rows.extend(process_json(jf, pokemon_map, move_map))
        except Exception as e:
            errors.append((jf.name, str(e)))
        if i % 200 == 0:
            print(f"  已处理 {i}/{len(json_files)}...")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✓ 已写入 {len(all_rows):,} 条记录 → {output_path}")
    if errors:
        print(f"  跳过 {len(errors)} 个文件（解析失败）：")
        for name, err in errors[:10]:
            print(f"    {name}: {err}")

    missing_zh = sum(1 for r in all_rows if not r["move_name_zh"])
    print(f"  move_name_zh 为空：{missing_zh:,} 条（对应招式在 moves 表中无中文名）")


if __name__ == "__main__":
    main()
