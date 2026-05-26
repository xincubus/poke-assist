"""
批量给 wiki_templates 打分类标签。

两种用法：

1) 应用内置默认规则（最常见，一次性初始化时跑一次）
    python classify_templates.py --apply-defaults

2) 按前缀 / 精确名 批量打标
    python classify_templates.py --prefix "招式效果/" --category semantic
    python classify_templates.py --names "m,s,i,a,p" --category inline --param-fmt "$last"
    python classify_templates.py --names "招式信息框" --category infobox --param-fmt key_value

3) 查看未分类或某类的清单
    python classify_templates.py --list unknown --limit 50
    python classify_templates.py --list semantic
"""

import argparse
import os
import sqlite3
from datetime import datetime


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")


# ============================================================
# 内置默认规则
# ============================================================
# 顺序重要：从精确到前缀，先命中的先处理
# 注意：MediaWiki Template namespace 是 first-letter case，ASCII 首字母自动大写
# （wiki 里存 `Template:M`、不是 `Template:m`）。所以这里全用大写开头。
DEFAULT_RULES = [
    # ─── INLINE：单字母 / 短名引用 ─────────────────
    {"names": ["M", "S", "I", "A", "P"], "category": "inline", "param_fmt": "$last"},
    {"names": ["M2"], "category": "inline", "param_fmt": "$2"},
    {"names": ["Tt"], "category": "inline", "param_fmt": "$1"},
    {"names": ["Lang", "Langtt"], "category": "inline", "param_fmt": "$last"},
    {"names": ["Game", "Game2"], "category": "inline", "param_fmt": "$1"},
    # 语言链接 / 页面跳转类短名
    {"names": ["Wp", "Main", "N", "Type", "Cat"], "category": "inline", "param_fmt": "$1"},
    # 动画 / 漫画 / 游戏 / 地点引用
    {"names": ["An", "PS", "TP1", "TP2", "Gen", "Pkm", "Rt", "Par"],
     "category": "inline", "param_fmt": "$last"},
    {"names": ["E", "C", "JP"], "category": "inline", "param_fmt": "$last"},
    # 动画季号 / 漫画卷号 缩写
    {"names": ["EP", "DP", "AG", "Adv", "Chap", "XY", "BW", "SM", "DL", "Side", "Mov", "Sup"],
     "category": "inline", "param_fmt": "$last"},
    {"names": ["PokémonPrevNext", "PokemonPrevNext"], "category": "drop"},

    # ─── INFOBOX：信息框 / 表格容器 ────────────────
    {
        "names": [
            "招式信息框", "特性信息框", "道具信息框", "宝可梦信息框",
            "能力信息框", "地点信息框", "剧情信息框", "对战信息框",
            "包包信息框", "道具地点", "Bag",
        ],
        "category": "infobox", "param_fmt": "key_value",
    },
    {"prefix": "Movelist/", "category": "infobox", "param_fmt": "title_only"},
    {"names": ["Movelistheader", "Movelistend"], "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "Learnlist/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "MSP/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "名字/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "图鉴条目/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "携带物品/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "招待方式/", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "动画招式", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "招式范围图示", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "状态说明框", "category": "infobox", "param_fmt": "title_only"},
    {"prefix": "Animedex", "category": "drop"},   # 动画图鉴表格，对战语义无价值
    {"prefix": "训练家卡信息", "category": "infobox", "param_fmt": "title_only"},
    # 信息框子模板（如 `招式信息框/game`）一律 drop —— 它们是父 infobox 的展开件，
    # 单独出现时会渲染成表格片段
    {"prefix": "招式信息框/", "category": "drop"},
    {"prefix": "特性信息框/", "category": "drop"},
    {"prefix": "道具信息框/", "category": "drop"},
    {"prefix": "宝可梦信息框/", "category": "drop"},
    {"prefix": "能力信息框/", "category": "drop"},
    {"prefix": "地点信息框/", "category": "drop"},
    {"prefix": "剧情信息框/", "category": "drop"},
    {"prefix": "对战信息框/", "category": "drop"},
    {"names": ["包包信息框/h"], "category": "drop"},

    # ─── SEMANTIC：对战规则文本 ────────────────────
    {"prefix": "招式效果/", "category": "semantic"},
    {"prefix": "特性效果/", "category": "semantic"},
    {"prefix": "状态效果/", "category": "semantic"},
    {"prefix": "招式说明/", "category": "semantic"},
    {"prefix": "道具效果/", "category": "semantic"},
    {"prefix": "形态变化", "category": "semantic"},

    # ─── DROP：工程模板 / 分类 / 版权声明 ──────────
    {"names": ["模板文档", "神奇宝贝百科招式工程"], "category": "drop"},
    {"prefix": "神奇宝贝百科", "category": "drop"},
    {"prefix": "神奇寶貝百科", "category": "drop"},     # 繁体变体
    {"prefix": "图鉴", "category": "drop"},             # 各类图鉴横幅
    # TCG 卡牌家族 —— 对战语义零价值，总页引用 50K+
    {"prefix": "TCG", "category": "drop"},
    {"prefix": "卡牌信息", "category": "drop"},
    {"prefix": "ExpansionList", "category": "drop"},
    # 精灵图标 / 动图 —— 纯图片引用
    {"names": ["MSP", "MSPN", "Anigif", "Anipng"], "category": "drop"},
    # 导航 / 表格框架 —— 无文本内容
    {"names": ["招式表间链接"], "category": "drop"},
    # wiki 语法 magic helper：`{{!}}` = `|`，`{{-}}` = `<br clear>` 等；表格被 drop 后这些残留也无意义
    {"names": ["-", "!", "=", "!!", "(", ")", "$"], "category": "drop"},
    # 文章状态 stub
    {"names": ["暂译", "未完成", "小作品", "Reflist", "Cite", "Cite web", "Cite book"], "category": "drop"},
    # 剧透 / 透视显示框
    {"names": ["剧透提示", "劇透提示", "透视提示", "穿透显示"], "category": "drop"},
]


def _touch_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# 批量打标
# ============================================================
def classify_by_prefix(conn, prefix: str, category: str, param_fmt: str = None) -> int:
    cur = conn.execute(
        """UPDATE wiki_templates
              SET category = ?, param_fmt = ?, updated_at = ?
            WHERE name LIKE ? AND category = 'unknown'""",
        (category, param_fmt, _touch_now(), prefix + "%"),
    )
    conn.commit()
    return cur.rowcount


def classify_by_names(conn, names: list, category: str, param_fmt: str = None) -> int:
    if not names:
        return 0
    placeholders = ",".join(["?"] * len(names))
    cur = conn.execute(
        f"""UPDATE wiki_templates
               SET category = ?, param_fmt = ?, updated_at = ?
             WHERE name IN ({placeholders}) AND category = 'unknown'""",
        (category, param_fmt, _touch_now(), *names),
    )
    conn.commit()
    return cur.rowcount


def apply_defaults(conn) -> dict:
    totals = {"semantic": 0, "infobox": 0, "inline": 0, "drop": 0}
    for rule in DEFAULT_RULES:
        cat = rule["category"]
        fmt = rule.get("param_fmt")
        if "names" in rule:
            n = classify_by_names(conn, rule["names"], cat, fmt)
        elif "prefix" in rule:
            n = classify_by_prefix(conn, rule["prefix"], cat, fmt)
        else:
            continue
        totals[cat] = totals.get(cat, 0) + n
    return totals


# ============================================================
# 列表查询
# ============================================================
def list_category(conn, category: str, limit: int = 50) -> None:
    print(f"-- category='{category}' 的模板 (最多 {limit} 条) --")
    rows = conn.execute(
        """SELECT name, param_fmt, note
             FROM wiki_templates
            WHERE category = ?
            ORDER BY name
            LIMIT ?""",
        (category, limit),
    ).fetchall()
    for name, fmt, note in rows:
        parts = [name]
        if fmt:
            parts.append(f"[{fmt}]")
        if note:
            parts.append(f"// {note}")
        print(" ".join(parts))


def show_stats(conn) -> None:
    rows = conn.execute(
        "SELECT category, COUNT(*) FROM wiki_templates GROUP BY category ORDER BY 2 DESC"
    ).fetchall()
    total = sum(n for _, n in rows)
    print(f"wiki_templates 总计: {total}")
    for cat, n in rows:
        print(f"  {cat:<10} {n}")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="批量给 wiki_templates 打分类标签")
    parser.add_argument("--db", default=DB_PATH)

    g = parser.add_mutually_exclusive_group()
    g.add_argument("--apply-defaults", action="store_true", help="应用内置默认规则")
    g.add_argument("--prefix", help="按前缀批量打标")
    g.add_argument("--names", help="按精确名批量打标，逗号分隔")
    g.add_argument("--list", dest="list_cat", help="列出某 category 的模板")
    g.add_argument("--stats", action="store_true", help="只显示分类统计")

    parser.add_argument("--category", choices=["semantic", "infobox", "inline", "drop", "unknown"])
    parser.add_argument("--param-fmt", default=None)
    parser.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    conn = sqlite3.connect(args.db)

    if args.stats:
        show_stats(conn)
    elif args.list_cat:
        list_category(conn, args.list_cat, args.limit)
    elif args.apply_defaults:
        totals = apply_defaults(conn)
        print("已应用默认规则：")
        for cat, n in totals.items():
            print(f"  {cat:<10} 新标记 {n}")
        print()
        show_stats(conn)
    elif args.prefix or args.names:
        if not args.category:
            parser.error("--prefix / --names 必须配合 --category 使用")
        if args.prefix:
            n = classify_by_prefix(conn, args.prefix, args.category, args.param_fmt)
            print(f"前缀 '{args.prefix}' → {args.category}：更新 {n} 条")
        else:
            names = [x.strip() for x in args.names.split(",") if x.strip()]
            n = classify_by_names(conn, names, args.category, args.param_fmt)
            print(f"精确名 {names} → {args.category}：更新 {n} 条")
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
