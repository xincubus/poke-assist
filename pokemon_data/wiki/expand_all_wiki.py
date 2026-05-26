"""
展开所有特性、招式、宝可梦的 wiki 页面，保存到新文件夹用于对比分析

用法：
    python expand_all_wiki.py [--output-dir OUTPUT_DIR] [--entity-type TYPE]

输出结构：
    output_dir/
        pokemons/
            妙蛙种子.txt        # 展开后的文本
            妙蛙种子.wiki       # 原始 wikitext
            ...
        moves/
            撞击.txt
            撞击.wiki
            ...
        abilities/
            茂盛.txt
            茂盛.wiki
            ...
        _stats.json             # 统计信息
        _unexpanded_templates.txt  # 未展开的模板汇总
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# 添加父目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))

from pokemon_data.wiki.template_expander import expand, ClassifierTable, SqliteTemplateLoader

# 数据库路径
WIKI_META_DB = SCRIPT_DIR / "wiki_meta.db"
POKEMON_DATA_DB = SCRIPT_DIR.parent / "pokemonData.db"
WIKITEXT_CACHE_DIR = SCRIPT_DIR / "wikitext_cache"


def cleanup_orphan_table_marks(text: str) -> str:
    """清理孤立的表格标记。

    模板展开后，原始 wikitext 中的表格标记（如 |}）可能变成孤立的。
    这个函数清理这些孤立的标记。

    规则：
    1. 移除孤立的 |}（前面没有对应的 {|）
    2. 移除空的 <div>...</div> 标签
    """
    # 移除孤立的 |}（前面没有对应的 {|）
    # 策略：检查每一行，如果只有 |} 且前面没有 {|，则移除
    lines = text.split('\n')
    result = []
    table_depth = 0

    for line in lines:
        stripped = line.strip()
        # 计算表格深度
        if stripped.startswith('{|'):
            table_depth += 1
            result.append(line)
        elif stripped == '|}':
            if table_depth > 0:
                table_depth -= 1
                result.append(line)
            # else: 孤立的 |}，跳过
        else:
            result.append(line)

    return '\n'.join(result)


def get_entities_from_db(entity_type: str) -> list:
    """从 pokemonData.db 获取实体列表"""
    conn = sqlite3.connect(str(POKEMON_DATA_DB))
    entities = []

    if entity_type == "pokemons":
        rows = conn.execute(
            "SELECT name_zh, name_en, id FROM pokemons WHERE name_zh IS NOT NULL"
        ).fetchall()
    elif entity_type == "moves":
        rows = conn.execute(
            "SELECT name_zh, name_en, id FROM moves WHERE name_zh IS NOT NULL"
        ).fetchall()
    elif entity_type == "abilities":
        rows = conn.execute(
            "SELECT name_zh, name_en, id FROM abilities WHERE name_zh IS NOT NULL"
        ).fetchall()
    else:
        rows = []

    conn.close()

    for name_zh, name_en, entity_id in rows:
        entities.append({
            "name_zh": name_zh,
            "name_en": name_en,
            "id": entity_id,
            "type": entity_type
        })

    return entities


def find_wiki_page(wiki_conn: sqlite3.Connection, entity: dict) -> Optional[dict]:
    """在 wiki_meta.db 中查找实体对应的 wiki 页面"""

    name_zh = entity["name_zh"]
    entity_type = entity["type"]

    # 构建可能的标题模式
    title_patterns = []

    if entity_type == "pokemons":
        # 宝可梦页面通常是：名称（宝可梦）
        title_patterns = [
            f"{name_zh}（宝可梦）",
            name_zh,
            f"{name_zh}（地区形态）",
        ]
    elif entity_type == "moves":
        # 招式页面通常是：名称（招式）
        title_patterns = [
            f"{name_zh}（招式）",
            name_zh,
        ]
    elif entity_type == "abilities":
        # 特性页面通常是：名称（特性）
        title_patterns = [
            f"{name_zh}（特性）",
            name_zh,
        ]

    # 尝试匹配
    for title in title_patterns:
        row = wiki_conn.execute(
            "SELECT page_id, title, file_path, status FROM wiki_pages WHERE title = ? AND status = 'done'",
            (title,)
        ).fetchone()

        if row:
            return {
                "page_id": row[0],
                "title": row[1],
                "file_path": row[2],
                "status": row[3]
            }

    # 尝试模糊匹配
    if entity_type == "pokemons":
        pattern = f"%{name_zh}%（宝可梦）%"
    elif entity_type == "moves":
        pattern = f"%{name_zh}%（招式）%"
    elif entity_type == "abilities":
        pattern = f"%{name_zh}%（特性）%"
    else:
        return None

    row = wiki_conn.execute(
        "SELECT page_id, title, file_path, status FROM wiki_pages WHERE title LIKE ? AND status = 'done' LIMIT 1",
        (pattern,)
    ).fetchone()

    if row:
        return {
            "page_id": row[0],
            "title": row[1],
            "file_path": row[2],
            "status": row[3]
        }

    return None


def load_wikitext(file_path: str) -> Optional[str]:
    """加载原始 wikitext"""
    if not file_path:
        return None

    # 处理相对路径
    if not os.path.isabs(file_path):
        file_path = WIKITEXT_CACHE_DIR / os.path.basename(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, FileNotFoundError):
        return None


def find_unexpanded_templates(text: str) -> list:
    """找出文本中未展开的模板调用"""
    # 先移除 HTML 注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # 匹配 {{模板名|...}} 格式
    pattern = r'\{\{([^|{}]+)(?:\|[^}]*)?\}\}'
    templates = re.findall(pattern, text)
    return list(set(templates))


def expand_entity(
    entity: dict,
    wiki_conn: sqlite3.Connection,
    loader: SqliteTemplateLoader,
    classifier: ClassifierTable,
    output_dir: Path
) -> dict:
    """展开单个实体的 wiki 页面，返回统计信息"""

    name_zh = entity["name_zh"]
    entity_type = entity["type"]

    # 查找 wiki 页面
    wiki_page = find_wiki_page(wiki_conn, entity)

    if not wiki_page:
        return {
            "entity": entity,
            "found": False,
            "reason": "wiki_page_not_found"
        }

    # 加载原始 wikitext
    wikitext = load_wikitext(wiki_page["file_path"])

    if not wikitext:
        return {
            "entity": entity,
            "found": True,
            "wiki_page": wiki_page,
            "expanded": False,
            "reason": "wikitext_load_failed"
        }

    # 展开模板
    try:
        expanded = expand(wikitext, loader=loader, classifier=classifier, page_title=wiki_page["title"])
        # 后处理：清理孤立的表格标记
        expanded = cleanup_orphan_table_marks(expanded)
    except Exception as e:
        return {
            "entity": entity,
            "found": True,
            "wiki_page": wiki_page,
            "expanded": False,
            "reason": f"expand_error: {str(e)}"
        }

    # 找出未展开的模板
    unexpanded = find_unexpanded_templates(expanded)

    # 保存文件
    entity_dir = output_dir / entity_type
    entity_dir.mkdir(parents=True, exist_ok=True)

    # 保存展开后的文本
    expanded_file = entity_dir / f"{name_zh}.txt"
    with open(expanded_file, "w", encoding="utf-8") as f:
        f.write(expanded)

    # 保存原始 wikitext
    wiki_file = entity_dir / f"{name_zh}.wiki"
    with open(wiki_file, "w", encoding="utf-8") as f:
        f.write(wikitext)

    return {
        "entity": entity,
        "found": True,
        "wiki_page": wiki_page,
        "expanded": True,
        "unexpanded_templates": unexpanded,
        "wikitext_len": len(wikitext),
        "expanded_len": len(expanded)
    }


def main():
    parser = argparse.ArgumentParser(description="展开所有特性、招式、宝可梦的 wiki 页面")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(SCRIPT_DIR / "expanded_pages"),
        help="输出目录路径"
    )
    parser.add_argument(
        "--entity-type",
        choices=["all", "pokemons", "moves", "abilities"],
        default="all",
        help="要展开的实体类型"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录: {output_dir}")

    # 初始化模板展开器
    loader = SqliteTemplateLoader(db_path=str(WIKI_META_DB), cache_dir=str(WIKITEXT_CACHE_DIR))
    classifier = ClassifierTable(db_path=str(WIKI_META_DB))

    # 连接 wiki_meta.db
    wiki_conn = sqlite3.connect(str(WIKI_META_DB))

    # 统计信息
    stats = {
        "total": 0,
        "found": 0,
        "expanded": 0,
        "not_found": 0,
        "expand_failed": 0,
        "by_type": {}
    }

    all_unexpanded = defaultdict(set)  # template_name -> set of entity names

    # 处理实体类型
    entity_types = ["pokemons", "moves", "abilities"] if args.entity_type == "all" else [args.entity_type]

    for entity_type in entity_types:
        print(f"\n{'='*60}")
        print(f"处理 {entity_type}...")
        print('='*60)

        entities = get_entities_from_db(entity_type)
        type_stats = {
            "total": len(entities),
            "found": 0,
            "expanded": 0,
            "not_found": 0,
            "expand_failed": 0
        }

        for i, entity in enumerate(entities, 1):
            if i % 100 == 0:
                print(f"  进度: {i}/{len(entities)}")

            result = expand_entity(entity, wiki_conn, loader, classifier, output_dir)

            if not result["found"]:
                type_stats["not_found"] += 1
            elif not result.get("expanded"):
                type_stats["expand_failed"] += 1
            else:
                type_stats["found"] += 1
                type_stats["expanded"] += 1

                # 收集未展开的模板
                for tpl in result.get("unexpanded_templates", []):
                    all_unexpanded[tpl].add(entity["name_zh"])

        stats["by_type"][entity_type] = type_stats
        stats["total"] += type_stats["total"]
        stats["found"] += type_stats["found"]
        stats["expanded"] += type_stats["expanded"]
        stats["not_found"] += type_stats["not_found"]
        stats["expand_failed"] += type_stats["expand_failed"]

        print(f"\n{entity_type} 统计:")
        print(f"  总数: {type_stats['total']}")
        print(f"  找到 wiki 页面: {type_stats['found']}")
        print(f"  成功展开: {type_stats['expanded']}")
        print(f"  未找到: {type_stats['not_found']}")
        print(f"  展开失败: {type_stats['expand_failed']}")

    wiki_conn.close()
    loader.close()

    # 保存统计信息
    stats_file = output_dir / "_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # 保存未展开模板汇总
    unexpanded_file = output_dir / "_unexpanded_templates.txt"
    with open(unexpanded_file, "w", encoding="utf-8") as f:
        f.write("未展开的模板汇总\n")
        f.write("="*60 + "\n\n")

        for tpl_name in sorted(all_unexpanded.keys()):
            entities = sorted(all_unexpanded[tpl_name])
            f.write(f"模板: {tpl_name}\n")
            f.write(f"  出现次数: {len(entities)}\n")
            f.write(f"  出现位置: {', '.join(entities[:10])}")
            if len(entities) > 10:
                f.write(f"... 等 {len(entities)} 个")
            f.write("\n\n")

    print(f"\n{'='*60}")
    print("完成!")
    print('='*60)
    print(f"\n总统计:")
    print(f"  总数: {stats['total']}")
    print(f"  找到 wiki 页面: {stats['found']}")
    print(f"  成功展开: {stats['expanded']}")
    print(f"  未找到: {stats['not_found']}")
    print(f"  展开失败: {stats['expand_failed']}")
    print(f"\n输出目录: {output_dir}")
    print(f"统计文件: {stats_file}")
    print(f"未展开模板汇总: {unexpanded_file}")
    print(f"未展开模板种类: {len(all_unexpanded)}")


if __name__ == "__main__":
    main()
