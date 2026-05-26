"""
为 items 表填充世代可用性字段：name_ncp, first_gen, in_sv, in_champions。

用法：
    python populate_item_gen_availability.py              # 执行填充
    python populate_item_gen_availability.py --dry-run    # 仅预览，不写入数据库

工作流程：
1. 用 Node.js 从 item_data.js 提取各世代道具列表
2. 匹配 DB 中的 name_en（kebab-case）→ NCP 中的 Title Case 道具名
3. 确定 first_gen（首次出现世代 2-9）、in_sv、in_champions
4. UPDATE 填值
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "pokemon_data", "pokemonData.db")
CALE_DIR = os.path.join(PROJECT_ROOT, "damage_calculator", "cale")

# 世代道具变量名 → first_gen 值（按时间顺序排列）
# 使用非 natdex 的游戏内列表来确定首次出现世代
ITEM_GEN_CHAIN = [
    ("ITEMS_GSC", 2),
    ("ITEMS_ADV", 3),
    ("ITEMS_DPP", 4),
    ("ITEMS_BW", 5),
    ("ITEMS_XY", 6),
    ("ITEMS_SM", 7),
    ("ITEMS_SS", 8),
    ("ITEMS_SV", 9),
]


def extract_item_data() -> dict:
    """用 Node.js 从 item_data.js 提取各世代道具列表。

    Returns:
        dict: 各 ITEMS_* 变量名 → 道具名列表（Title Case）
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
loadGlobal('item_data.js');

var result = {};
var itemVars = ['ITEMS_GSC','ITEMS_ADV','ITEMS_DPP','ITEMS_BW','ITEMS_XY',
  'ITEMS_SM','ITEMS_SS','ITEMS_SV','ITEMS_CHAMPIONS'];
itemVars.forEach(function(v){
  if(global[v]) result[v] = Array.isArray(global[v]) ? global[v] : Object.values(global[v]);
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


def normalize_item_name(name_en: str) -> str:
    """将 DB 的 kebab-case name_en 转为 Title Case（与 NCP 道具名一致）"""
    return name_en.replace("-", " ").title()


def main():
    parser = argparse.ArgumentParser(description="填充 items 表的世代可用性字段")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    args = parser.parse_args()

    print("提取道具数据...")
    item_data = extract_item_data()

    for var_name, items in item_data.items():
        print(f"  {var_name}: {len(items)} 道具")

    # 构建 NCP 道具名集合（用于匹配）
    all_ncp_items = set()
    for items in item_data.values():
        all_ncp_items.update(items)

    # 构建 first_gen 查找：NCP 道具名(Title Case) → 最早世代
    ncp_first_gen = {}
    for var_name, gen in ITEM_GEN_CHAIN:
        if var_name in item_data:
            for item_name in item_data[var_name]:
                if item_name not in ncp_first_gen:
                    ncp_first_gen[item_name] = gen

    # 限定图鉴集合
    sv_items = set(item_data.get("ITEMS_SV", []))
    champions_items = set(item_data.get("ITEMS_CHAMPIONS", []))

    print(f"\n  NCP 道具总数: {len(all_ncp_items)}")
    print(f"  ITEMS_SV: {len(sv_items)}")
    print(f"  ITEMS_CHAMPIONS: {len(champions_items)}")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, name_en, name_ncp FROM items WHERE name_en IS NOT NULL"
    ).fetchall()
    print(f"  DB 共 {len(rows)} 条 item\n")

    # 计算每个 item 的世代信息
    results = {}  # id → (name_ncp, first_gen, in_sv, in_champions)
    stats = {"matched": 0, "unmatched": 0, "first_gen_dist": {}}

    for db_id, name_en, existing_ncp in rows:
        # 尝试匹配：优先用已有 name_ncp，否则 normalize name_en
        ncp_key = existing_ncp
        if not ncp_key:
            title = normalize_item_name(name_en)
            if title in all_ncp_items:
                ncp_key = title

        if not ncp_key or ncp_key not in all_ncp_items:
            stats["unmatched"] += 1
            results[db_id] = (None, None, 0, 0)
            continue

        stats["matched"] += 1

        first_gen = ncp_first_gen.get(ncp_key)
        in_sv = 1 if ncp_key in sv_items else 0
        in_champions = 1 if ncp_key in champions_items else 0

        results[db_id] = (ncp_key, first_gen, in_sv, in_champions)

        gen_key = str(first_gen) if first_gen else "None"
        stats["first_gen_dist"][gen_key] = stats["first_gen_dist"].get(gen_key, 0) + 1

    # 打印统计
    print(f"匹配结果:")
    print(f"  已匹配: {stats['matched']}")
    print(f"  未匹配: {stats['unmatched']}")
    print(f"\nfirst_gen 分布:")
    for gen in sorted(stats["first_gen_dist"].keys()):
        print(f"  Gen {gen}: {stats['first_gen_dist'][gen]}")

    sv_count = sum(1 for r in results.values() if r[2])
    champ_count = sum(1 for r in results.values() if r[3])
    print(f"\n限定图鉴:")
    print(f"  in_sv: {sv_count}")
    print(f"  in_champions: {champ_count}")

    if args.dry_run:
        print("\n[DRY RUN] 抽样展示:")
        samples = ["choice-scarf", "choice-specs", "life-orb", "focus-sash",
                    "assault-vest", "leftovers", "safety-goggles", "booster-energy"]
        for name_en in samples:
            row = conn.execute(
                "SELECT id, name_ncp FROM items WHERE name_en = ?", (name_en,)
            ).fetchone()
            if row:
                r = results.get(row[0], (None, None, 0, 0))
                ncp = r[0] or "NULL"
                print(f"  {name_en:25s} ncp={ncp:25s} fg={r[1]} sv={r[2]} ch={r[3]}")
        conn.close()
        return

    # 批量更新
    for db_id, (ncp_key, first_gen, in_sv, in_champions) in results.items():
        conn.execute(
            "UPDATE items SET name_ncp = ?, first_gen = ?, in_sv = ?, in_champions = ? WHERE id = ?",
            (ncp_key, first_gen, in_sv, in_champions, db_id),
        )

    conn.commit()

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_first_gen ON items(first_gen)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_in_sv ON items(in_sv)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_in_champions ON items(in_champions)")
    conn.commit()
    conn.close()

    print(f"\n完成！已填充 {stats['matched']} 条记录的世代可用性字段。")


if __name__ == "__main__":
    main()
