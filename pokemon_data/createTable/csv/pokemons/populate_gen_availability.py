"""
为 pokemons 表填充世代可用性字段：first_gen, in_sv, in_champions。

用法：
    python populate_gen_availability.py              # 执行填充
    python populate_gen_availability.py --dry-run    # 仅预览，不写入数据库

工作流程：
1. 用 Node.js 从 pokedex.js 提取各世代 pokedex key 列表
2. 匹配 DB 记录 → NCP key（复用 populate_name_ncp 的匹配逻辑）
3. 确定 first_gen（首次出现世代 1-9）
4. 确定 in_sv / in_champions
5. ALTER TABLE 加列 + UPDATE 填值
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")
CALE_DIR = os.path.join(PROJECT_ROOT, "damage_calculator", "cale")

# DB name_en → NCP key（与 populate_name_ncp.py 一致）
MANUAL_OVERRIDES = {
    "deoxys-normal": "Deoxys",
    "wormadam-plant": "Wormadam",
    "giratina-altered": "Giratina",
    "shaymin-land": "Shaymin",
    "basculin-red-striped": "Basculin",
    "darmanitan-standard": "Darmanitan",
    "darmanitan-galar-standard": "Darmanitan-Galar",
    "tornadus-incarnate": "Tornadus",
    "thundurus-incarnate": "Thundurus",
    "landorus-incarnate": "Landorus",
    "keldeo-ordinary": "Keldeo",
    "meloetta-aria": "Meloetta",
    "enamorus-incarnate": "Enamorus",
    "toxtricity-amped": "Toxtricity",
    "eiscue-ice": "Eiscue",
    "morpeko-full-belly": "Morpeko",
    "mimikyu-disguised": "Mimikyu",
    "palafin-zero": "Palafin",
    "tatsugiri-curly": "Tatsugiri",
    "dudunsparce-two-segment": "Dudunsparce",
    "magearna-original": "Magearna",
    "necrozma-dusk": "Necrozma-Dusk-Mane",
    "necrozma-dawn": "Necrozma-Dawn-Wings",
    "necrozma-ultra": "Ultra Necrozma",
    "calyrex-ice": "Calyrex-Ice Rider",
    "calyrex-shadow": "Calyrex-Shadow Rider",
    "maushold-family-of-four": "Maushold-Four",
    "maushold-family-of-three": "Maushold",
    "magearna-original-mega": "Mega Magearna",
    "greninja-ash": "Ash-Greninja",
    "keldeo-resolute": "Keldeo",
    "ogerpon-wellspring-mask": "Ogerpon-Wellspring",
    "ogerpon-hearthflame-mask": "Ogerpon-Hearthflame",
    "ogerpon-cornerstone-mask": "Ogerpon-Cornerstone",
    "zygarde-10-power-construct": "Zygarde-10%",
    "zygarde-50-power-construct": "Zygarde",
}

MEGA_RE = re.compile(r"^(.+)-(mega|primal)(?:-(x|y|z))?$", re.IGNORECASE)

# 世代 pokedex 变量名 → first_gen 值（按时间顺序排列）
NATDEX_CHAIN = [
    ("POKEDEX_RBY", 1),
    ("POKEDEX_GSC", 2),
    ("POKEDEX_ADV", 3),
    ("POKEDEX_DPP", 4),
    ("POKEDEX_BW", 5),
    ("POKEDEX_XY", 6),
    ("POKEDEX_SM", 7),
    ("POKEDEX_SS_NATDEX", 8),
    ("POKEDEX_SV_NATDEX", 9),
]


def normalize(s: str) -> str:
    return re.sub(r"[^a-zA-Z]", "", s).lower()


def extract_pokedex_data() -> dict:
    """用 Node.js 从 pokedex.js 提取各世代 pokedex 的 key 列表。

    Returns:
        dict: {
            "natdex": {"POKEDEX_RBY": [...], "POKEDEX_GSC": [...], ...},
            "restricted": {"POKEDEX_SV": [...], "POKEDEX_CHAMPIONS": [...]},
        }
    """
    js_code = """
var path = require('path');
var fs = require('fs');
var vm = require('vm');
var caleDir = process.argv[1];
function deepExtend(deep,t){var a,i;if(typeof deep!=='boolean'){t=deep;deep=false;a=Array.prototype.slice.call(arguments,1)}else{a=Array.prototype.slice.call(arguments,2)}if(!t)t={};for(i=0;i<a.length;i++){var o=a[i];if(!o)continue;for(var n in o){var c=o[n];if(t===c)continue;if(deep&&c&&typeof c==='object'){t[n]=deepExtend(deep,Array.isArray(c)?[]:{},c)}else if(c!==undefined){t[n]=c}}}return t}
global.$ = function(){return {val:function(){},is:function(){return false},prop:function(){return false},find:function(){return global.$()},text:function(){return global.$()}}};
$.extend = deepExtend;
global.setHasTypeFunc = function(){};
function loadGlobal(f){vm.runInThisContext(fs.readFileSync(path.join(caleDir,f),'utf-8'),{filename:f})}
loadGlobal('stat_data.js');loadGlobal('nature_data.js');loadGlobal('type_data.js');
loadGlobal('item_data.js');loadGlobal('ability_data.js');loadGlobal('pokedex.js');

var result = {};
// 全国图鉴继承链
var natdexVars = ['POKEDEX_RBY','POKEDEX_GSC','POKEDEX_ADV','POKEDEX_DPP','POKEDEX_BW',
  'POKEDEX_XY','POKEDEX_SM','POKEDEX_SS_NATDEX','POKEDEX_SV_NATDEX'];
result.natdex = {};
natdexVars.forEach(function(v){
  if(global[v]) result.natdex[v] = Object.keys(global[v]);
});
// 限定图鉴
var restrictedVars = ['POKEDEX_SV','POKEDEX_CHAMPIONS'];
result.restricted = {};
restrictedVars.forEach(function(v){
  if(global[v]) result.restricted[v] = Object.keys(global[v]);
});
console.log(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "-e", js_code, CALE_DIR],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"Node.js error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def build_ncp_lookup(ncp_keys: list) -> dict:
    """构建 normalize(name) → ncp_key 的查找表"""
    lookup = {}
    for k in ncp_keys:
        n = normalize(k)
        if n not in lookup:
            lookup[n] = k
    return lookup


def match_name_to_ncp(name_en: str, ncp_lookup: dict, ncp_set: set) -> str:
    """将 DB 的 name_en 匹配到 NCP key，复用 populate_name_ncp 的逻辑"""
    # 1. 手动覆盖
    if name_en in MANUAL_OVERRIDES:
        ncp = MANUAL_OVERRIDES[name_en]
        if ncp in ncp_set:
            return ncp

    # 2. 直接 normalize 匹配
    n = normalize(name_en)
    if n in ncp_lookup:
        return ncp_lookup[n]

    # 3. mega/primal 前缀翻转
    m = MEGA_RE.match(name_en)
    if m:
        flipped = normalize(m.group(2) + m.group(1) + (m.group(3) or ""))
        if flipped in ncp_lookup:
            return ncp_lookup[flipped]

    # 4. 去 -breed 后缀
    if name_en.endswith("-breed"):
        stripped = normalize(name_en[:-6])
        if stripped in ncp_lookup:
            return ncp_lookup[stripped]

    # 5. 去 -male 后缀
    if name_en.endswith("-male"):
        stripped = normalize(name_en[:-5])
        if stripped in ncp_lookup:
            return ncp_lookup[stripped]

    # 6. -female → -F
    if name_en.endswith("-female"):
        converted = normalize(name_en[:-7] + "f")
        if converted in ncp_lookup:
            return ncp_lookup[converted]

    return None


def main():
    parser = argparse.ArgumentParser(description="填充 pokemons 表的世代可用性字段")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    args = parser.parse_args()

    print("提取 pokedex 数据...")
    pokedex_data = extract_pokedex_data()
    natdex = pokedex_data["natdex"]
    restricted = pokedex_data["restricted"]

    print(f"  全国图鉴: {', '.join(f'{k}({len(v)})' for k, v in natdex.items())}")
    print(f"  限定图鉴: {', '.join(f'{k}({len(v)})' for k, v in restricted.items())}")

    # 收集所有 NCP key 构建查找表
    all_ncp_keys = set()
    for keys in natdex.values():
        all_ncp_keys.update(keys)
    for keys in restricted.values():
        all_ncp_keys.update(keys)
    ncp_lookup = build_ncp_lookup(list(all_ncp_keys))
    print(f"  共 {len(all_ncp_keys)} 个 NCP key")

    # 为每个 NCP key 构建限定图鉴查找集合
    restricted_sets = {k: set(v) for k, v in restricted.items()}

    # 为每个 NCP key 构建全国图鉴查找集合（用于确定 first_gen）
    natdex_sets = {}
    for var_name, gen in NATDEX_CHAIN:
        if var_name in natdex:
            natdex_sets[var_name] = set(natdex[var_name])

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, name_en, name_ncp FROM pokemons WHERE name_en IS NOT NULL"
    ).fetchall()
    print(f"  DB 共 {len(rows)} 条 pokemon\n")

    # 计算每个 pokemon 的世代信息
    results = {}  # id → (first_gen, in_sv, in_champions)
    stats = {"matched": 0, "unmatched": 0, "first_gen_dist": {}}

    for db_id, name_en, name_ncp in rows:
        # 优先用已有的 name_ncp，否则尝试匹配
        ncp_key = name_ncp
        if not ncp_key:
            ncp_key = match_name_to_ncp(name_en, ncp_lookup, all_ncp_keys)

        if not ncp_key:
            stats["unmatched"] += 1
            results[db_id] = (None, 0, 0)
            continue

        stats["matched"] += 1

        # 确定 first_gen（从最早世代开始检查）
        first_gen = None
        for var_name, gen in NATDEX_CHAIN:
            if var_name in natdex_sets and ncp_key in natdex_sets[var_name]:
                first_gen = gen
                break

        # 确定限定图鉴可用性
        in_sv = 1 if ncp_key in restricted_sets.get("POKEDEX_SV", set()) else 0
        in_champions = 1 if ncp_key in restricted_sets.get("POKEDEX_CHAMPIONS", set()) else 0

        results[db_id] = (first_gen, in_sv, in_champions)

        gen_key = str(first_gen) if first_gen else "None"
        stats["first_gen_dist"][gen_key] = stats["first_gen_dist"].get(gen_key, 0) + 1

    # 打印统计
    print(f"匹配结果:")
    print(f"  已匹配: {stats['matched']}")
    print(f"  未匹配: {stats['unmatched']}")
    print(f"\nfirst_gen 分布:")
    for gen in sorted(stats["first_gen_dist"].keys()):
        print(f"  Gen {gen}: {stats['first_gen_dist'][gen]}")

    sv_count = sum(1 for r in results.values() if r[1])
    champ_count = sum(1 for r in results.values() if r[2])
    print(f"\n限定图鉴:")
    print(f"  in_sv: {sv_count}")
    print(f"  in_champions: {champ_count}")

    if args.dry_run:
        print("\n[DRY RUN] 抽样展示:")
        samples = ["charizard", "pikachu", "mewtwo", "rayquaza", "zacian",
                    "koraidon", "miraidon", "archaludon", "pecharunt"]
        for name_en in samples:
            row = conn.execute(
                "SELECT id, name_ncp FROM pokemons WHERE name_en = ?", (name_en,)
            ).fetchone()
            if row:
                r = results.get(row[0], (None, 0, 0))
                ncp = row[1] or "NULL"
                print(f"  {name_en:20s} ncp={ncp:25s} fg={r[0]} sv={r[1]} ch={r[2]}")
        conn.close()
        return

    # 批量更新
    for db_id, (first_gen, in_sv, in_champions) in results.items():
        conn.execute(
            "UPDATE pokemons SET first_gen = ?, in_sv = ?, in_champions = ? WHERE id = ?",
            (first_gen, in_sv, in_champions, db_id),
        )

    conn.commit()

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pokemons_first_gen ON pokemons(first_gen)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pokemons_in_sv ON pokemons(in_sv)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pokemons_in_champions ON pokemons(in_champions)")
    conn.commit()
    conn.close()

    print(f"\n完成！已填充 {stats['matched']} 条记录的世代可用性字段。")


if __name__ == "__main__":
    main()
