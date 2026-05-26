"""
从 wiki 文件构建 pokemon_moves_champions 表
数据源：pokemon_data/wiki/wikitext_cache/*Champions招式表.wiki
支持增量更新：按宝可梦维度删除旧记录后重新写入
"""

import os
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
from typing import Optional

DB_PATH = Path(__file__).resolve().parents[3] / "pokemonData.db"
WIKI_CACHE = Path(__file__).resolve().parents[3] / "wiki" / "wikitext_cache"

# learnlist/level/champ 模板正则
# 格式：{{learnlist/level/champ|招式名|属性|分类|威力|命中|pp|8='''}}
CHAMP_RE = re.compile(
    r"\{\{learnlist/level/champ\|"
    r"([^|]+)\|"    # 招式名
    r"([^|]+)\|"    # 属性
    r"([^|]+)\|"    # 分类
    r"([^|]+)\|"    # 威力
    r"([^|]+)\|"    # 命中
    r"([^|}|]+)"    # pp
)

# Toggle Header 正则
TOGGLE_HEADER_RE = re.compile(r"\{\{Toggle/Header\|([^}]+)\}\}")
# Toggle Content 分隔 - 需要处理嵌套模板
def extract_toggle_contents(content: str) -> list[str]:
    """提取所有 Toggle/Content 块的内容，正确处理嵌套的 {{ }}"""
    blocks = []
    pattern = "{{Toggle/Content|"
    start = 0
    while True:
        idx = content.find(pattern, start)
        if idx == -1:
            break
        # 从 pattern 之后开始计数括号
        pos = idx + len(pattern)
        depth = 2  # 已经有 {{Toggle/Content|，所以 depth=2
        while pos < len(content) and depth > 0:
            if content[pos:pos+2] == "{{":
                depth += 1
                pos += 2
            elif content[pos:pos+2] == "}}":
                depth -= 1
                pos += 2
            else:
                pos += 1
        # 提取内容（去掉最后的 }}）
        block = content[idx + len(pattern):pos - 2]
        blocks.append(block)
        start = pos
    return blocks


# wiki 文件名 → 数据库标准名 映射（解决命名不一致）
_WIKI_NAME_MAP = {
    "谜拟Q": "谜拟丘",  # wiki 用全角Ｑ，半角化后为 Q
    "死神棺": "迭失棺",
    "死神板": "迭失板",
    "電飛鼠": "电飞鼠",
    "流氓熊猫": "霸道熊猫",
}


def _normalize_wiki_name(name: str) -> str:
    """标准化 wiki 文件名：全角→半角 + 已知映射"""
    # 全角字母/数字转半角
    result = []
    for c in name:
        cp = ord(c)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        else:
            result.append(c)
    name = "".join(result)
    # 已知映射
    return _WIKI_NAME_MAP.get(name, name)


def parse_filename(filename: str) -> Optional[str]:
    """从文件名提取宝可梦中文名，如 326939_皮卡丘_Champions招式表.wiki → 皮卡丘"""
    m = re.match(r"\d+_(.+?)_Champions招式表\.wiki$", filename)
    return _normalize_wiki_name(m.group(1)) if m else None


def parse_moves_from_text(text: str) -> list[dict]:
    """从 wikitext 中提取所有 learnlist/level/champ 招式"""
    moves = []
    for m in CHAMP_RE.finditer(text):
        move_name_zh = m.group(1).strip()
        type_name = m.group(2).strip()
        category = m.group(3).strip()
        power = m.group(4).strip()
        accuracy = m.group(5).strip()
        pp = m.group(6).strip()
        # 跳过空招式名
        if not move_name_zh:
            continue
        moves.append({
            "move_name_zh": move_name_zh,
            "type": type_name,
            "category": category,
            "power": power,
            "accuracy": accuracy,
            "pp": pp,
        })
    return moves


def parse_wiki_file(filepath: str) -> dict[str, list[dict]]:
    """
    解析一个 Champions 招式表 wiki 文件
    返回 {form_name: [moves]} 字典
    无形态切换时 form_name 为 '_default'
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否有 Toggle 形态切换
    header_match = TOGGLE_HEADER_RE.search(content)
    if header_match:
        # 有形态切换
        forms = [f.strip() for f in header_match.group(1).split("|")]
        # 提取所有 Toggle/Content 块
        content_blocks = extract_toggle_contents(content)
        result = {}
        for i, block in enumerate(content_blocks):
            # 按行首的 | 分割不同形态
            form_blocks = re.split(r'\n\|\n', block)
            for j, form_block in enumerate(form_blocks):
                form_name = forms[j] if j < len(forms) else f"_form_{j}"
                moves = parse_moves_from_text(form_block)
                if moves:
                    result[form_name] = moves
        return result
    else:
        # 无形态切换
        moves = parse_moves_from_text(content)
        return {"_default": moves} if moves else {}


def load_move_map(conn: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    """加载 招式中文名 → (move_id, move_name_en) 映射"""
    cur = conn.execute("SELECT id, name_zh, name_en FROM moves WHERE name_zh IS NOT NULL")
    result = {}
    for row in cur:
        result[row[1]] = (row[0], row[2])
    return result


def load_pokemon_map(conn: sqlite3.Connection) -> dict[str, list[tuple[int, int, str, str]]]:
    """
    加载宝可梦映射：base_name → [(pokedex_id, pokeapi_id, name_zh, name_en), ...]
    base_name 是去掉括号形式说明的基础名，如 "花叶蒂" 匹配 "花叶蒂" 和 "花叶蒂（永恒之花的样子）"
    """
    cur = conn.execute("SELECT pokedex_id, pokeapi_id, name_zh, name_en FROM pokemons")
    result = defaultdict(list)
    for row in cur:
        name_zh = row[2]
        # 提取基础名（去掉括号内容）
        base = re.sub(r"[（(].+[）)]", "", name_zh).strip()
        result[base].append((row[0], row[1], name_zh, row[3]))
    return result


def match_pokemon(base_name: str, form_name: str, pokemon_map: dict) -> Optional[tuple]:
    """
    匹配宝可梦：优先匹配形态，再匹配默认形态
    返回 (pokedex_id, pokeapi_id, name_zh, name_en)
    """
    candidates = pokemon_map.get(base_name, [])
    if not candidates:
        return None

    if form_name == "_default":
        # 无形态切换，返回默认形态（pokeapi_id 最小的）
        return min(candidates, key=lambda x: x[1])

    # 有形态切换，尝试匹配
    for cand in candidates:
        name_zh = cand[2]
        # 检查形态名是否在宝可梦中文名中
        if form_name in name_zh:
            return cand

    # 匹配不到，返回默认形态
    return min(candidates, key=lambda x: x[1])


def main():
    if not DB_PATH.exists():
        print(f"错误：数据库不存在 {DB_PATH}")
        sys.exit(1)

    if not WIKI_CACHE.exists():
        print(f"错误：wiki 缓存目录不存在 {WIKI_CACHE}")
        sys.exit(1)

    # 查找所有 Champions 招式表文件
    files = sorted(WIKI_CACHE.glob("*Champions招式表.wiki"))
    print(f"找到 {len(files)} 个 Champions 招式表文件")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # 建表（如果不存在）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pokemon_moves_champions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pokedex_id       INTEGER NOT NULL,
            pokeapi_id       INTEGER NOT NULL,
            pokemon_name_zh  TEXT,
            pokemon_name_en  TEXT NOT NULL,
            move_id          INTEGER NOT NULL,
            move_name_zh     TEXT,
            move_name_en     TEXT NOT NULL,
            learn_method     TEXT NOT NULL,
            level            INTEGER,
            version_group    TEXT NOT NULL,
            generation       INTEGER NOT NULL
        )
    """)
    conn.commit()

    # 加载映射
    move_map = load_move_map(conn)
    pokemon_map = load_pokemon_map(conn)
    print(f"已加载 {len(move_map)} 条招式映射，{len(pokemon_map)} 个宝可梦基础名")

    # 统计
    total_files = 0
    success_files = 0
    total_moves = 0
    skipped_moves = 0
    skipped_pokemon = set()
    unmatched_moves = set()

    # 按宝可梦分组处理
    pokemon_moves_data = defaultdict(list)  # pokeapi_id -> [rows]

    for filepath in files:
        total_files += 1
        base_name = parse_filename(filepath.name)
        if not base_name:
            print(f"  跳过：无法解析文件名 {filepath.name}")
            continue

        forms = parse_wiki_file(str(filepath))
        if not forms:
            print(f"  跳过：无招式数据 {filepath.name}")
            continue

        success_files += 1

        for form_name, moves in forms.items():
            pokemon_info = match_pokemon(base_name, form_name, pokemon_map)
            if not pokemon_info:
                skipped_pokemon.add(base_name)
                continue

            pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_en = pokemon_info

            for move in moves:
                move_name_zh = _normalize_wiki_name(move["move_name_zh"])
                if move_name_zh not in move_map:
                    unmatched_moves.add(move_name_zh)
                    skipped_moves += 1
                    continue

                move_id, move_name_en = move_map[move_name_zh]
                pokemon_moves_data[pokeapi_id].append((
                    pokedex_id, pokeapi_id,
                    pokemon_name_zh, pokemon_name_en,
                    move_id, move_name_zh, move_name_en,
                    "Champions", None, "pokemon-champions", 10
                ))
                total_moves += 1

    # 写入数据库（增量更新）
    inserted = 0
    updated_pokemon = 0
    new_pokemon = 0

    conn.execute("BEGIN TRANSACTION")
    try:
        for pokeapi_id, rows in pokemon_moves_data.items():
            # 检查是否已有记录
            existing = conn.execute(
                "SELECT COUNT(*) FROM pokemon_moves_champions WHERE pokeapi_id = ?",
                (pokeapi_id,)
            ).fetchone()[0]

            # 删除旧记录
            conn.execute(
                "DELETE FROM pokemon_moves_champions WHERE pokeapi_id = ?",
                (pokeapi_id,)
            )

            # 插入新记录
            conn.executemany(
                """INSERT INTO pokemon_moves_champions
                   (pokedex_id, pokeapi_id, pokemon_name_zh, pokemon_name_en,
                    move_id, move_name_zh, move_name_en,
                    learn_method, level, version_group, generation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows
            )
            inserted += len(rows)

            if existing > 0:
                updated_pokemon += 1
            else:
                new_pokemon += 1

        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"错误：{e}")
        sys.exit(1)

    # 输出统计
    print(f"\n=== 构建完成 ===")
    print(f"文件总数：{total_files}")
    print(f"成功解析：{success_files}")
    print(f"新增宝可梦：{new_pokemon}")
    print(f"更新宝可梦：{updated_pokemon}")
    print(f"总招式数：{inserted}")
    print(f"跳过招式（未匹配）：{skipped_moves}")

    if skipped_pokemon:
        print(f"\n未匹配宝可梦（{len(skipped_pokemon)}）：")
        for name in sorted(skipped_pokemon):
            print(f"  - {name}")

    if unmatched_moves:
        print(f"\n未匹配招式（{len(unmatched_moves)}）：")
        for name in sorted(unmatched_moves):
            print(f"  - {name}")

    # 验证
    count = conn.execute("SELECT COUNT(*) FROM pokemon_moves_champions").fetchone()[0]
    pokemon_count = conn.execute("SELECT COUNT(DISTINCT pokeapi_id) FROM pokemon_moves_champions").fetchone()[0]
    print(f"\n表中记录数：{count}，覆盖宝可梦：{pokemon_count}")

    conn.close()


if __name__ == "__main__":
    main()
