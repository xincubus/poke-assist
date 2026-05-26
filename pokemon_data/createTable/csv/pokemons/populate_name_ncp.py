"""
为 pokemons 表填充 name_ncp 列（NCP 计算器的 pokedex key）。

用法：
    python populate_name_ncp.py              # 执行填充
    python populate_name_ncp.py --dry-run    # 仅预览，不写入

工作流程：
1. 用 Node.js 从 cale/pokedex.js 提取所有世代的 pokedex key
2. 建 normalize 索引（去非字母、小写）
3. 按优先级匹配：手动覆盖 → normalize 直接匹配 → mega/primal 翻转 → 去后缀
4. ALTER TABLE 加列 + UPDATE 填值
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

# DB name_en → NCP key（自动策略无法覆盖的特殊映射）
MANUAL_OVERRIDES = {
    # 默认形态（NCP 用 base name 表示）
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
    # 名称不同（DB 缩写 vs NCP 全称）
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
    # power-construct 和 base 共享同一 NCP key
    "zygarde-10-power-construct": "Zygarde-10%",
    "zygarde-50-power-construct": "Zygarde",
}

MEGA_RE = re.compile(r"^(.+)-(mega|primal)(?:-(x|y|z))?$", re.IGNORECASE)


def normalize(s: str) -> str:
    return re.sub(r"[^a-zA-Z]", "", s).lower()


def extract_ncp_keys() -> list:
    """用 Node.js 从 pokedex.js 提取所有世代的 pokedex key"""
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
loadGlobal('move_data.js');loadGlobal('cooldown_za.js');
var all = new Set();
var vars = ['POKEDEX_RBY','POKEDEX_GSC','POKEDEX_ADV','POKEDEX_DPP','POKEDEX_BW',
  'POKEDEX_XY','POKEDEX_SM','POKEDEX_SS','POKEDEX_SS_NATDEX','POKEDEX_SV',
  'POKEDEX_SV_NATDEX','POKEDEX_ZA_NATDEX','POKEDEX_CHAMPIONS'];
vars.forEach(function(v){
  var p = global[v];
  if(p) Object.keys(p).forEach(function(k){ all.add(k); });
});
console.log(JSON.stringify(Array.from(all).sort()));
"""
    result = subprocess.run(
        ["node", "-e", js_code, CALE_DIR],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print(f"Node.js error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def build_mapping(db_rows, ncp_keys):
    """为每条 DB 记录匹配 NCP key，返回 {id: ncp_key} 和统计"""
    ncp_set = set(ncp_keys)
    ncp_lookup = {}
    for k in ncp_keys:
        n = normalize(k)
        if n not in ncp_lookup:
            ncp_lookup[n] = k

    mapping = {}
    stats = {"manual": 0, "normalize": 0, "mega_flip": 0,
             "strip_breed": 0, "strip_male": 0, "female_f": 0, "null": 0}

    for db_id, name_en in db_rows:
        # 1. 手动覆盖
        if name_en in MANUAL_OVERRIDES:
            ncp = MANUAL_OVERRIDES[name_en]
            if ncp in ncp_set:
                mapping[db_id] = ncp
                stats["manual"] += 1
                continue

        # 2. 直接 normalize 匹配
        n = normalize(name_en)
        if n in ncp_lookup:
            mapping[db_id] = ncp_lookup[n]
            stats["normalize"] += 1
            continue

        # 3. mega/primal 前缀翻转
        m = MEGA_RE.match(name_en)
        if m:
            flipped = normalize(m.group(2) + m.group(1) + (m.group(3) or ""))
            if flipped in ncp_lookup:
                mapping[db_id] = ncp_lookup[flipped]
                stats["mega_flip"] += 1
                continue

        # 4. 去 -breed 后缀
        if name_en.endswith("-breed"):
            stripped = normalize(name_en[:-6])
            if stripped in ncp_lookup:
                mapping[db_id] = ncp_lookup[stripped]
                stats["strip_breed"] += 1
                continue

        # 5. 去 -male 后缀（默认形态）
        if name_en.endswith("-male"):
            stripped = normalize(name_en[:-5])
            if stripped in ncp_lookup:
                mapping[db_id] = ncp_lookup[stripped]
                stats["strip_male"] += 1
                continue

        # 6. -female → -F
        if name_en.endswith("-female"):
            converted = normalize(name_en[:-7] + "f")
            if converted in ncp_lookup:
                mapping[db_id] = ncp_lookup[converted]
                stats["female_f"] += 1
                continue

        stats["null"] += 1

    return mapping, stats


def main():
    parser = argparse.ArgumentParser(description="填充 pokemons.name_ncp 列")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    args = parser.parse_args()

    print("提取 NCP pokedex keys...")
    ncp_keys = extract_ncp_keys()
    print(f"  共 {len(ncp_keys)} 个 NCP key")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name_en FROM pokemons WHERE name_en IS NOT NULL").fetchall()
    print(f"  DB 共 {len(rows)} 条 pokemon")

    print("匹配中...")
    mapping, stats = build_mapping(rows, ncp_keys)

    print(f"\n匹配结果:")
    print(f"  手动覆盖:     {stats['manual']}")
    print(f"  normalize:    {stats['normalize']}")
    print(f"  mega/primal:  {stats['mega_flip']}")
    print(f"  去 -breed:    {stats['strip_breed']}")
    print(f"  去 -male:     {stats['strip_male']}")
    print(f"  -female→-F:   {stats['female_f']}")
    print(f"  NULL（无匹配）: {stats['null']}")
    print(f"  总匹配: {len(mapping)} / {len(rows)}")

    if args.dry_run:
        print("\n[DRY RUN] 抽样展示:")
        samples = ["basculegion-male", "charizard-mega-x", "ho-oh", "mr-rime",
                   "calyrex-ice", "maushold-family-of-three", "tauros-paldea-combat-breed",
                   "basculegion-female", "indeedee-female", "necrozma-dawn"]
        for name_en in samples:
            row = conn.execute("SELECT id FROM pokemons WHERE name_en = ?", (name_en,)).fetchone()
            if row:
                ncp = mapping.get(row[0], "NULL")
                print(f"  {name_en:40s} → {ncp}")
        conn.close()
        return

    # 添加列（如果不存在）
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pokemons)").fetchall()]
    if "name_ncp" not in cols:
        conn.execute("ALTER TABLE pokemons ADD COLUMN name_ncp TEXT")
        print("\n已添加 name_ncp 列")

    # 清空旧值
    conn.execute("UPDATE pokemons SET name_ncp = NULL")

    # 批量更新
    for db_id, ncp_key in mapping.items():
        conn.execute("UPDATE pokemons SET name_ncp = ? WHERE id = ?", (ncp_key, db_id))

    conn.commit()

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pokemons_name_ncp ON pokemons(name_ncp)")
    conn.commit()
    conn.close()

    print(f"\n完成！已填充 {len(mapping)} 条 name_ncp 值。")


if __name__ == "__main__":
    main()
