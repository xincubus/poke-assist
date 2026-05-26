"""
Wiki ↔ 数据库同步检测脚本

功能：
1. 检测 wiki 有但数据库没有的新条目
2. 检测 wiki 页面已更新但数据库未刷新的过期条目
3. 用 LLM 分两步分析：筛选是否需要更新 → 提取具体变化
4. 生成更新建议供用户审核
5. 用户确认后执行更新

用法：
    python sync_detector.py                      # 完整流程：检测 + LLM 分析
    python sync_detector.py --quick              # 只检测不调用 LLM
    python sync_detector.py --entity moves       # 只检查招式
    python sync_detector.py --since 2025-06-01   # 只检查此日期后更新的页面
    python sync_detector.py --file path/to/wiki.wiki  # 单文件模式（跳过全量扫描，输出 JSON 报告）
    python sync_detector.py --apply suggestions.json  # 执行更新
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import opencc
    _converter = opencc.OpenCC('t2s')  # 繁体转简体
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False
    print("警告: opencc 未安装，繁体字将不会自动转换为简体")

# Windows 终端 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 路径配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
POKEMON_DB = os.path.join(SCRIPT_DIR, "..", "pokemonData.db")
WIKI_META_DB = os.path.join(SCRIPT_DIR, "wiki_meta.db")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "sync_reports")

# 确保能 import api 模块
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, "api", ".env"))
except ImportError:
    pass

# 实体类型配置：(表名, 名称列, wiki后缀, 关键字段)
ENTITY_TYPES = {
    "moves": {
        "table": "moves",
        "name_col": "name_zh",
        "wiki_suffix": "（招式）",
        "fields": ["power", "accuracy", "pp", "type", "damage_class", "target",
                    "makes_contact", "can_protect", "can_magic_coat", "can_snatch"],
    },
    "abilities": {
        "table": "abilities",
        "name_col": "name_zh",
        "wiki_suffix": "（特性）",
        "fields": ["affected_by_mold_breaker", "affected_by_no_ability",
                    "triggers_on_entry", "can_be_traced",
                    "works_when_transformed", "can_be_swapped", "can_be_overridden"],
    },
    "items": {
        "table": "items",
        "name_col": "name_zh",
        "wiki_suffix": "（道具）",
        "fields": ["category", "fling_power", "fling_effect"],
    },
    "status": {
        "table": "status",
        "name_col": "name_zh",
        "wiki_suffix": "（状态）",
        "fields": ["category", "type_zh", "duration"],
    },
    "pokemons": {
        "table": "pokemons",
        "name_col": "name_zh",
        "wiki_suffix": "",  # 宝可梦 wiki 页面无后缀
        "fields": ["type1", "type2", "hp", "attack", "defense", "sp_attack", "sp_defense", "speed",
                    "ability1_name", "ability2_name", "hidden_ability_name"],
    },
}

# 手动映射（与 link_entities.py 一致）
MANUAL_OVERRIDES = {
    ("stats", "HP"): "HP",
    ("stats", "攻击"): "攻击",
    ("stats", "防御"): "防御",
    ("stats", "特攻"): "特攻",
    ("stats", "特防"): "特防",
    ("stats", "速度"): "速度",
    ("stats", "命中率"): "命中率",
    ("stats", "闪避率"): "闪避率",
}


# ============================================================
# 繁简转换
# ============================================================

def to_simplified(text: str) -> str:
    """将繁体字转换为简体字，同时将全角字母/数字转为半角"""
    if not text:
        return text
    # 全角字母(A-Z, a-z) → 半角，全角数字(0-9) → 半角
    result = []
    for ch in text:
        cp = ord(ch)
        if 0xFF21 <= cp <= 0xFF3A:  # Ａ-Ｚ
            result.append(chr(cp - 0xFEE0))
        elif 0xFF41 <= cp <= 0xFF5A:  # ａ-ｚ
            result.append(chr(cp - 0xFEE0))
        elif 0xFF10 <= cp <= 0xFF19:  # ０-９
            result.append(chr(cp - 0xFEE0))
        else:
            result.append(ch)
    text = ''.join(result)
    if not HAS_OPENCC:
        return text
    return _converter.convert(text)


def extract_name_from_wikitext(wikitext: str) -> Optional[str]:
    """从wikitext中提取name字段（官方名称）"""
    import re
    # 匹配 |name=xxx 模式
    match = re.search(r'\|name=([^|\n]+)', wikitext)
    if match:
        return match.group(1).strip()
    return None


def extract_move_info_from_wiki(wiki_title: str) -> Optional[dict]:
    """从wiki页面提取招式详细信息"""
    import re

    # 查找wiki页面文件路径
    conn = sqlite3.connect(WIKI_META_DB)
    row = conn.execute(
        "SELECT file_path FROM wiki_pages WHERE title = ? AND status = 'done'",
        (wiki_title,)
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    file_path = row[0]
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            wikitext = f.read()
    except Exception:
        return None

    info = {"file_path": file_path}

    # 提取各字段
    patterns = {
        "name_en": r'\|enname=([^|\n]+)',
        "name_ja": r'\|jname=([^|\n]+)',
        "name": r'\|name=([^|\n]+)',
        "type": r'\|type=([^|\n]+)',
        "damage_class": r'\|damagecategory=([^|\n]+)',
        "power": r'\|power=([^|\n]+)',
        "accuracy": r'\|accuracy=([^|\n]+)',
        "pp": r'\|basepp=([^|\n]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, wikitext)
        if match:
            value = match.group(1).strip()
            # 处理特殊值
            if value in ("—", "-", "N/A", ""):
                info[key] = None
            elif key in ("power", "accuracy", "pp"):
                # 提取数字
                num_match = re.search(r'\d+', value)
                if num_match:
                    info[key] = int(num_match.group())
                else:
                    info[key] = None
            elif key == "damage_class":
                # 转换为英文
                class_map = {"物理": "physical", "特殊": "special", "变化": "status"}
                info[key] = class_map.get(value, value.lower())
            elif key == "type":
                # 转换为英文
                type_map = {
                    "一般": "normal", "火": "fire", "水": "water", "草": "grass",
                    "电": "electric", "冰": "ice", "格斗": "fighting", "毒": "poison",
                    "地面": "ground", "飞行": "flying", "超能力": "psychic", "虫": "bug",
                    "岩石": "rock", "ghost": "ghost", "龙": "dragon", "恶": "dark",
                    "钢": "steel", "fairy": "fairy", "暗影": "shadow",
                }
                info[key] = type_map.get(value, value.lower())
            else:
                info[key] = value

    # 确保 name_en 存在
    if "name_en" not in info and "name" in info:
        info["name_en"] = info["name"]

    return info


def extract_ability_info_from_wiki(wiki_title: str) -> Optional[dict]:
    """从wiki页面提取特性详细信息"""
    import re

    conn = sqlite3.connect(WIKI_META_DB)
    row = conn.execute(
        "SELECT file_path FROM wiki_pages WHERE title = ? AND status = 'done'",
        (wiki_title,)
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    file_path = row[0]
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            wikitext = f.read()
    except Exception:
        return None

    info = {"file_path": file_path}

    # 提取 name_en
    match = re.search(r'\|enname=([^|\n]+)', wikitext)
    if match:
        info["name_en"] = match.group(1).strip()

    # 提取 name_ja
    match = re.search(r'\|jpname=([^|\n]+)', wikitext)
    if match:
        info["name_ja"] = match.group(1).strip()

    # 提取效果描述
    match = re.search(r'\|text=([^|\n]+)', wikitext)
    if match:
        info["description_ja"] = match.group(1).strip()

    return info


# ============================================================
# API 刷新 wiki 最新修改时间
# ============================================================

def refresh_wiki_timestamps(
    pages: Dict[str, dict],
    wiki_meta_db: str,
    batch_size: int = 50,
    delay: float = 0.3,
    limit: int = 0,
) -> int:
    """通过 MediaWiki API 批量查询页面最新版本时间，更新 wiki_meta.db 和内存 pages。

    Returns:
        更新的页面数
    """
    import urllib.request
    import urllib.parse

    WIKI_API = "https://wiki.52poke.com/api.php"
    USER_AGENT = "PokemonSyncDetector/1.0"
    REQUEST_TIMEOUT = 20

    conn = sqlite3.connect(wiki_meta_db)
    # 加载所有 done 页面的 page_id 和 title
    query = "SELECT page_id, title FROM wiki_pages WHERE status = 'done' AND file_path IS NOT NULL"
    if limit:
        query += f" LIMIT {limit}"
    page_list = []
    for row in conn.execute(query):
        page_list.append((row[0], row[1]))

    total = len(page_list)
    print(f"  [API] 刷新 {total} 个页面的最新修改时间...")

    updated = 0
    errors = 0

    for batch_start in range(0, total, batch_size):
        batch = page_list[batch_start : batch_start + batch_size]
        batch_ids = [str(pid) for pid, _ in batch]
        id_to_title = {pid: title for pid, title in batch}

        try:
            params = {
                "action": "query",
                "pageids": "|".join(batch_ids),
                "prop": "revisions",
                "rvprop": "timestamp",
                "format": "json",
            }
            url = WIKI_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            api_pages = data.get("query", {}).get("pages", {})
            for pid_str, pdata in api_pages.items():
                pid = int(pid_str)
                title = id_to_title.get(pid)
                if not title:
                    continue
                revisions = pdata.get("revisions", [])
                if not revisions:
                    continue
                api_ts = revisions[0].get("timestamp", "")
                if not api_ts:
                    continue

                # 更新内存
                if title in pages:
                    pages[title]["wiki_updated"] = api_ts
                # 更新数据库
                conn.execute(
                    "UPDATE wiki_pages SET wiki_updated = ? WHERE page_id = ?",
                    (api_ts, pid),
                )
                updated += 1

        except Exception as e:
            errors += 1
            print(f"    [API] 批次错误 (batch_start={batch_start}): {e}")

        # 进度
        processed = min(batch_start + batch_size, total)
        if processed % 1000 == 0 or processed >= total:
            print(f"    [API] {processed}/{total} 已查询")

        conn.commit()
        time.sleep(delay)

    conn.close()
    print(f"  [API] 完成: {updated} 页已更新, {errors} 个错误")
    return updated


# ============================================================
# 数据库加载
# ============================================================

def load_wiki_index(wiki_meta_db: str) -> Tuple[Dict[str, dict], Dict[str, str], Dict[str, List[str]]]:
    """加载 wiki_pages 和 wiki_redirects 映射

    Returns:
        pages: title -> {file_path, wiki_updated, local_downloaded, summary}
        redirects: source_title -> target_title
        reverse_redirects: target_title -> [source_title, ...] （反向映射）
    """
    conn = sqlite3.connect(wiki_meta_db)

    # title -> {file_path, wiki_updated, local_downloaded, summary}
    pages = {}
    for row in conn.execute(
        "SELECT title, file_path, wiki_updated, local_downloaded, summary "
        "FROM wiki_pages WHERE status = 'done' AND file_path IS NOT NULL"
    ):
        pages[row[0]] = {
            "file_path": row[1],
            "wiki_updated": row[2],
            "local_downloaded": row[3],
            "summary": row[4],
        }

    # source_title -> target_title
    redirects = {}
    for row in conn.execute(
        "SELECT r.source_title, wp.title "
        "FROM wiki_redirects r "
        "JOIN wiki_pages wp ON wp.page_id = r.target_page_id "
        "WHERE wp.status = 'done' AND wp.file_path IS NOT NULL"
    ):
        redirects[row[0]] = row[1]

    # 反向映射：target_title -> [source_title, ...]
    reverse_redirects = {}
    for source, target in redirects.items():
        if target not in reverse_redirects:
            reverse_redirects[target] = []
        reverse_redirects[target].append(source)

    conn.close()
    return pages, redirects, reverse_redirects


def load_db_entries(pokemon_db: str, table: str, name_col: str) -> List[dict]:
    """从数据库加载实体条目"""
    conn = sqlite3.connect(pokemon_db)
    conn.row_factory = sqlite3.Row

    # 获取所有列名
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()

    result = []
    for row in rows:
        entry = {col: row[col] for col in columns}
        result.append(entry)

    conn.close()
    return result


# ============================================================
# 匹配逻辑（复用 link_entities.py 的策略）
# ============================================================

def match_entity_to_wiki(
    name_zh: str,
    entity_type: str,
    pages: Dict[str, dict],
    redirects: Dict[str, str],
) -> Optional[str]:
    """将实体名称匹配到 wiki 页面标题，返回匹配的标题或 None"""
    if not name_zh:
        return None

    config = ENTITY_TYPES.get(entity_type, {})
    suffix = config.get("wiki_suffix", "")

    # 1. 精确匹配
    if name_zh in pages:
        return name_zh

    # 2. 通过重定向
    if name_zh in redirects:
        target = redirects[name_zh]
        if target in pages:
            return target

    # 3. 带消歧义后缀匹配
    if suffix:
        candidate = name_zh + suffix
        if candidate in pages:
            return candidate
        if candidate in redirects:
            target = redirects[candidate]
            if target in pages:
                return target

    # 4. types 表特殊处理
    if entity_type == "types" and name_zh.endswith("属性"):
        base = name_zh[:-2]
        candidate = f"{base}（属性）"
        if candidate in pages:
            return candidate
        if candidate in redirects:
            target = redirects[candidate]
            if target in pages:
                return target

    return None


# ============================================================
# Phase 1: 新条目检测
# ============================================================

def detect_new_entries(
    entity_type: str,
    pages: Dict[str, dict],
    redirects: Dict[str, str],
    reverse_redirects: Dict[str, List[str]],
    pokemon_db: str,
) -> List[dict]:
    """检测 wiki 有但数据库没有的条目

    会检查重定向关系：如果 wiki 条目有重定向指向它，且重定向的源名称在数据库中，
    则认为是"名称变更"而非"新条目"。
    会从wiki页面内容中提取name字段作为官方名称。
    """
    config = ENTITY_TYPES[entity_type]
    table = config["table"]
    name_col = config["name_col"]
    suffix = config["wiki_suffix"]

    # 加载数据库条目
    db_entries = load_db_entries(pokemon_db, table, name_col)
    db_names = {to_simplified(e[name_col]) for e in db_entries if e.get(name_col)}

    # 找出 wiki 中有该后缀的页面
    wiki_entries = []
    for title in pages:
        if suffix and title.endswith(suffix):
            base_name = title[: -len(suffix)]
            # 转换为简体用于比较
            base_name_simplified = to_simplified(base_name)
            wiki_entries.append((base_name, base_name_simplified, title))
        elif not suffix:
            # 没有后缀的类型（如 status），直接用标题
            title_simplified = to_simplified(title)
            wiki_entries.append((title, title_simplified, title))

    # 检测 wiki 有但 db 没有的
    new_entries = []
    renamed_entries = []
    for base_name, base_name_simplified, wiki_title in wiki_entries:
        # 从wiki页面提取官方名称
        page_info = pages.get(wiki_title, {})
        file_path = page_info.get("file_path")
        official_name = None
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    wikitext = f.read()[:2000]  # 只读前2000字符，足够找到name字段
                official_name = extract_name_from_wikitext(wikitext)
            except Exception:
                pass

        # 使用官方名称（如果有的话），否则使用页面标题
        if official_name:
            official_name_simplified = to_simplified(official_name)
        else:
            official_name_simplified = base_name_simplified

        # 尝试匹配（使用官方名称）
        matched = match_entity_to_wiki(official_name_simplified, entity_type, pages, redirects)
        if matched and matched in db_names:
            continue
        # 检查 db 中是否有这个名称（官方名称）
        if official_name_simplified in db_names:
            continue
        # 也检查 wiki 页面标题（去掉后缀）是否在 db 中
        if base_name_simplified in db_names:
            continue

        # 检查是否有重定向指向这个条目，且重定向的源名称在数据库中
        # 例如：wiki有"极落钳（招式）"，重定向"断头钳"指向它，且数据库中有"断头钳"
        redirect_sources = reverse_redirects.get(wiki_title, [])
        db_redirect_source = None
        for source in redirect_sources:
            # 去掉后缀检查
            if suffix and source.endswith(suffix):
                source_base = source[: -len(suffix)]
            else:
                source_base = source
            # 转换为简体比较
            source_base_simplified = to_simplified(source_base)
            if source_base_simplified in db_names:
                db_redirect_source = source_base_simplified
                break

        if db_redirect_source:
            # 这是名称变更，不是新条目
            renamed_entries.append({
                "entity_type": entity_type,
                "name_zh": official_name_simplified,
                "old_name": db_redirect_source,
                "wiki_title": wiki_title,
                "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
                "change_type": "renamed",
            })
        else:
            # 真正的新条目
            new_entries.append({
                "entity_type": entity_type,
                "name_zh": official_name_simplified,
                "wiki_title": wiki_title,
                "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
                "change_type": "new",
            })

    return new_entries, renamed_entries


# ============================================================
# Phase 2: 过期条目检测
# ============================================================

def _detect_stale_pokemons(
    pokemon_db: str,
    since_date: Optional[str] = None,
    until_date: Optional[str] = None,
) -> List[dict]:
    """pokemons 专用：用 wiki_file_path 的 page_id 查 wiki_updated，按 pokedex_id 分组，返回所有形态"""
    conn = sqlite3.connect(pokemon_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM pokemons WHERE wiki_file_path IS NOT NULL ORDER BY pokedex_id, is_default_form DESC"
    ).fetchall()
    conn.close()

    # 按 pokedex_id 分组
    from collections import OrderedDict
    groups = OrderedDict()
    for row in rows:
        entry = dict(row)
        pid = entry.get("pokedex_id")
        if pid not in groups:
            groups[pid] = []
        groups[pid].append(entry)

    # 从 wiki_file_path 提取 page_id，查 wiki_meta.db
    wiki_conn = sqlite3.connect(WIKI_META_DB)
    stale_entries = []
    for pokedex_id, entries in groups.items():
        file_path = entries[0].get("wiki_file_path", "")
        if not file_path:
            continue
        basename = os.path.basename(file_path)
        page_id = basename.split("_")[0] if "_" in basename else None
        if not page_id or not page_id.isdigit():
            continue

        wiki_row = wiki_conn.execute(
            "SELECT title, wiki_updated FROM wiki_pages WHERE CAST(page_id AS TEXT) = ? AND status='done'",
            (page_id,)
        ).fetchone()
        if not wiki_row:
            continue
        wiki_title, wiki_updated = wiki_row
        if not wiki_updated:
            continue
        if since_date and wiki_updated < since_date:
            continue
        if until_date and wiki_updated > until_date:
            continue

        # 默认形态作为代表名称
        default = next((e for e in entries if e.get("is_default_form")), entries[0])
        form_names = [e.get("name_zh", "") for e in entries]
        stale_entries.append({
            "entity_type": "pokemons",
            "name_zh": default.get("name_zh", ""),
            "name_en": default.get("name_en", ""),
            "wiki_title": wiki_title,
            "wiki_updated": wiki_updated,
            "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
            "summary": "",
            "db_entry": default,
            "db_entries": entries,  # 所有形态
            "form_count": len(entries),
        })
    wiki_conn.close()
    return stale_entries


def detect_stale_entries(
    entity_type: str,
    pages: Dict[str, dict],
    redirects: Dict[str, str],
    pokemon_db: str,
    since_date: Optional[str] = None,
    until_date: Optional[str] = None,
) -> List[dict]:
    """检测需要分析的条目：wiki 页面在 since_date 之后有更新的实体"""
    config = ENTITY_TYPES[entity_type]
    table = config["table"]
    name_col = config["name_col"]

    # pokemons 专用分支：用 wiki_file_path 直接匹配，按 pokedex_id 去重
    if entity_type == "pokemons":
        return _detect_stale_pokemons(pokemon_db, since_date, until_date)

    # 加载数据库条目
    db_entries = load_db_entries(pokemon_db, table, name_col)

    stale_entries = []
    for entry in db_entries:
        name_zh = entry.get(name_col)
        if not name_zh:
            continue

        # 匹配到 wiki 页面
        wiki_title = match_entity_to_wiki(name_zh, entity_type, pages, redirects)
        if not wiki_title or wiki_title not in pages:
            continue

        # 如果匹配到的是重定向源，用重定向目标的时间戳
        if wiki_title in redirects:
            target = redirects[wiki_title]
            if target in pages:
                wiki_title = target

        page_info = pages[wiki_title]
        wiki_updated = page_info.get("wiki_updated")

        if not wiki_updated:
            continue

        # 只要 wiki_updated >= since_date 就需要分析
        if since_date and wiki_updated < since_date:
            continue
        if until_date and wiki_updated > until_date:
            continue

        stale_entries.append({
            "entity_type": entity_type,
            "name_zh": name_zh,
            "name_en": entry.get("name_en", ""),
            "wiki_title": wiki_title,
            "wiki_updated": wiki_updated,
            "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
            "summary": page_info.get("summary", ""),
            "db_entry": entry,
        })

    return stale_entries


# ============================================================
# Phase 3: LLM 分析
# ============================================================

def llm_filter_stale(
    stale_entries: List[dict],
    entity_type: str,
) -> List[dict]:
    """第一步：用 LLM 筛选哪些过期条目需要更新"""
    try:
        from api.llm_service import LLMService
        llm = LLMService()
    except Exception as e:
        print(f"  [LLM] 无法初始化 LLM 服务: {e}")
        print(f"  [LLM] 跳过筛选，将所有 {len(stale_entries)} 个条目标记为需要更新")
        for entry in stale_entries:
            entry["needs_update"] = True
            entry["filter_reason"] = "LLM 不可用，默认需要更新"
        return stale_entries

    config = ENTITY_TYPES[entity_type]

    prompt_template = """你是一个 Pokemon 数据分析师。请快速判断以下 wiki 页面更新是否涉及数据库字段。

数据库字段包括：
- 招式：威力、命中率、PP、属性、伤害类型、目标、附加效果、机制说明
- 特性：效果描述、机制属性（发动几率、是否可复制等）
- 道具：日文描述、分类、投掷威力、投掷效果
- 状态：分类、效果、持续时间

Wiki 页面标题：{title}
Wiki 更新时间：{wiki_updated}
页面摘要：
{summary}

请返回 JSON（不要包含其他文本）：
{{"needs_update": true/false, "reason": "简短理由（20字以内）"}}

只关注数值/机制变化，忽略格式调整、错别字修正、图片更新等。"""

    print(f"  [LLM Step 1] 筛选 {len(stale_entries)} 个过期条目...", flush=True)

    # 批量处理，每批 20 个
    batch_size = 20
    for i in range(0, len(stale_entries), batch_size):
        batch = stale_entries[i : i + batch_size]
        # 拆分静态规则和动态数据：模板中 "{summary}" 后为后续规则
        _tpl_split = prompt_template.index("{summary}")
        _tpl_rules_prefix = prompt_template[:_tpl_split]
        _tpl_rules_suffix = prompt_template[_tpl_split + len("{summary}"):]

        for entry in batch:
            _data = (
                f"Wiki 页面标题：{entry['wiki_title']}\n"
                f"Wiki 更新时间：{entry['wiki_updated']}\n"
                f"页面摘要：\n{entry.get('summary', '无摘要')}"
            )

            try:
                response = llm.sync_client.chat.completions.create(
                    model=llm.default_sync_model,
                    messages=[
                        {"role": "system", "content": _tpl_rules_prefix, "cache_control": {"type": "ephemeral"}},
                        {"role": "user", "content": _data},
                        {"role": "system", "content": _tpl_rules_suffix},
                    ],
                    max_tokens=16384,
                    temperature=0.1,
                    extra_body={"thinking": {"type": "enabled"}},
                )
                content = response.choices[0].message.content.strip()
                # 尝试解析 JSON
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                result = json.loads(content)
                entry["needs_update"] = result.get("needs_update", True)
                entry["filter_reason"] = result.get("reason", "")
            except Exception as e:
                # 解析失败，默认需要更新
                entry["needs_update"] = True
                entry["filter_reason"] = f"LLM 解析失败: {str(e)[:50]}"

        print(f"    已处理 {min(i + batch_size, len(stale_entries))}/{len(stale_entries)}", flush=True)

    # 统计结果
    needs_update = sum(1 for e in stale_entries if e.get("needs_update"))
    print(f"  [LLM Step 1] 结果: {needs_update} 个需要更新, {len(stale_entries) - needs_update} 个不需要", flush=True)

    return stale_entries


def llm_extract_changes(
    entries_to_analyze: List[dict],
    entity_type: str,
    pokemon_db: str,
) -> List[dict]:
    """第二步：用 LLM 提取具体变化"""
    try:
        from api.llm_service import LLMService
        llm = LLMService()
    except Exception as e:
        print(f"  [LLM] 无法初始化 LLM 服务: {e}")
        return []

    config = ENTITY_TYPES[entity_type]
    table = config["table"]
    fields = config["fields"]

    # 构建数据库当前值描述
    conn = sqlite3.connect(pokemon_db)
    conn.row_factory = sqlite3.Row

    fields_desc = ", ".join(fields)

    print(f"  [LLM Step 2] 分析 {len(entries_to_analyze)} 个条目的具体变化...", flush=True)

    suggestions = []
    for i, entry in enumerate(entries_to_analyze):
        name_zh = entry["name_zh"]

        # 从数据库读取当前值
        try:
            if entity_type == "pokemons" and "db_entries" in entry:
                # 多形态：列出所有形态的值
                forms_data = []
                for e in entry["db_entries"]:
                    form_name = e.get("name_zh", "")
                    form_vals = {f: e.get(f) for f in fields}
                    forms_data.append({"形态": form_name, **form_vals})
                db_values = json.dumps(forms_data, ensure_ascii=False, indent=2)
            else:
                row = conn.execute(
                    f"SELECT {', '.join(fields)} FROM {table} WHERE name_zh = ?",
                    (name_zh,),
                ).fetchone()
                if row:
                    db_values = json.dumps(
                        {f: row[f] for f in fields if row[f] is not None},
                        ensure_ascii=False,
                        indent=2,
                    )
                else:
                    db_values = "未找到"
        except Exception:
            db_values = "读取失败"

        # 读取 wiki 文件内容
        wiki_content = ""
        file_path = entry.get("file_path")
        if not file_path:
            wiki_title = entry.get("wiki_title", "")
            try:
                wiki_conn = sqlite3.connect(WIKI_META_DB)
                row = wiki_conn.execute(
                    "SELECT file_path FROM wiki_pages WHERE title = ?",
                    (wiki_title,),
                ).fetchone()
                if row:
                    file_path = row[0]
                wiki_conn.close()
            except Exception:
                pass

        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_wikitext = f.read()
                # 展开模板
                try:
                    from template_expander import expand
                    wiki_content = expand(raw_wikitext)[:8000]
                except Exception:
                    wiki_content = raw_wikitext[:8000]
            except Exception:
                wiki_content = "读取失败"

        if not wiki_content:
            wiki_content = "无法获取 wiki 内容"

        print(f"    [{i+1}] {name_zh}: file={file_path}, content_len={len(wiki_content)}", flush=True)

        # 调用 LLM
        title = entry.get("wiki_title", name_zh)
        extra_rules = ""
        if entity_type == "pokemons":
            extra_rules = (
                "\n宝可梦专用规则：\n"
                "a) 特性字段：info 框中 ability1 和 ability2 是两个普通特性，abilityd 是隐藏特性。多形态宝可梦用 ability1-2/ability2-2 等后缀区分各形态的特性，不要遗漏 ability2。\n"
                "b) 种族值：wiki 可能列出多个世代的种族值，以最新世代为准。注意「特殊」是 Gen1-2 的旧值（特攻+特防合一），不要与现代的 sp_attack/sp_defense 混淆。\n"
                "c) type2 为 NULL 表示单属性宝可梦，这是正常的，不要报告为需要更新。\n"
                "d) 数据库值包含该宝可梦的所有形态（默认形态、超级进化、地区形态等），请逐一核对每个形态的属性和种族值。多形态的数据通常在 wiki info 框的不同行或不同 form 区域。\n"
            )
        elif entity_type == "items":
            extra_rules = (
                "\n道具专用规则：\n"
                "a) category 必须从以下可选项中选择一个（这是 PokeAPI 英文分类，不是中文）：\n"
                "   all-machines, all-mail, apricorn-balls, apricorn-box, bad-held-items, baking-only,\n"
                "   catching-bonus, choice, collectibles, curry-ingredients, data-cards, dex-completion,\n"
                "   dynamax-crystals, effort-drop, effort-training, event-items, evolution, flutes,\n"
                "   gameplay, healing, held-items, in-a-pinch, jewels, loot, medicine, mega-stones,\n"
                "   memories, miracle-shooter, mulch, nature-mints, other, picky-healing, picnic,\n"
                "   plates, plot-advancement, pp-recovery, revival, sandwich-ingredients, scarves,\n"
                "   special-balls, species-candies, species-specific, spelunking, standard-balls,\n"
                "   stat-boosts, status-cures, tera-shard, tm-materials, training, type-enhancement,\n"
                "   type-protection, unused, vitamins, z-crystals\n"
                "   从 wiki 的 bag 字段映射到上述英文分类。如果无法确定就不报告 category 变更。\n"
                "b) fling_power：从道具信息框的 throw 字段提取数字。注意：树果类道具的 throw 字段通常是效果描述文本而非数字，此时 fling_power 应为 10（不要报告变更）。只有 throw 字段明确是纯数字时才报告。\n"
                "c) 如果有「效果变更」章节，注意最新版本的效果，但只关注当前字段范围内的变化。\n"
            )
        # 拆分静态规则和动态数据
        _rules = (
            "你是 Pokemon 数据分析师。分析 wiki 页面，判断数据库值是否需要更新。\n\n"
            "规则：\n"
            "1. 根据 info 框数值和「变更」「Champions」「招式变更」等所有和变更相关的章节，推算出各个参数的最新值。注意所有变更的章节，尤其是Champions（宝可梦冠军）的章节都需要特别关注。\n"
            "2. 检查各个参数的最新值与数据库中的值是否一致，如果不一致则需要更新。\n"
            "3. 只关注以下字段：" + fields_desc + "\n"
            + extra_rules
        )
        _data = (
            "数据库值：\n" + db_values + "\n\n"
            "Wiki：" + title + "\n" + wiki_content + "\n\n"
            "严格按此 JSON 格式返回，不要有其他文本：\n"
            '{"name_zh":"名称","changes":[{"field":"字段","current_value":"旧值","new_value":"新值","reason":"原因"}],"confidence":"high"}\n'
            "无变化时 changes 为空数组 []"
        )

        try:
            response = llm.sync_client.chat.completions.create(
                model=llm.default_sync_model,
                messages=[
                    {"role": "system", "content": _rules, "cache_control": {"type": "ephemeral"}},
                    {"role": "user", "content": _data},
                ],
                max_tokens=16384,
                temperature=0.1,
                extra_body={"thinking": {"type": "enabled"}},
            )
            content = response.choices[0].message.content
            if not content:
                print(f"    [{i+1}] {name_zh}: LLM 返回空响应 (finish={response.choices[0].finish_reason}, usage={response.usage})", flush=True)
                continue
            content = content.strip()
            # 清理 markdown 代码块
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            # 尝试修复常见 JSON 问题：移除尾部多余逗号
            content = re.sub(r',\s*}', '}', content)
            content = re.sub(r',\s*]', ']', content)
            # 提取第一个完整 JSON 对象（处理 LLM 在 JSON 后附加文本的情况）
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    raise

            if result.get("changes"):
                suggestions.append({
                    "entity_type": entity_type,
                    "name_zh": result.get("name_zh", name_zh),
                    "name_en": result.get("name_en", entry.get("name_en", "")),
                    "change_type": "value_changed",
                    "changes": result["changes"],
                    "confidence": result.get("confidence", "medium"),
                    "wiki_url": entry.get("wiki_url", ""),
                    "wiki_title": entry.get("wiki_title", ""),
                })
        except Exception as e:
            print(f"    [{i+1}] {name_zh}: LLM 分析失败 - {str(e)[:80]}", flush=True)

        if (i + 1) % 10 == 0:
            print(f"    已处理 {i+1}/{len(entries_to_analyze)}", flush=True)

    conn.close()
    print(f"  [LLM Step 2] 结果: {len(suggestions)} 个条目有具体变化", flush=True)
    return suggestions


def llm_extract_entity_info(
    wiki_title: str,
    entity_type: str,
) -> Optional[dict]:
    """用 LLM 从 wiki 页面提取实体完整信息（用于新条目插入）"""
    try:
        from api.llm_service import LLMService
        llm = LLMService()
    except Exception as e:
        print(f"  [LLM] 无法初始化 LLM 服务: {e}")
        return None

    # 读取 wiki 文件内容
    conn = sqlite3.connect(WIKI_META_DB)
    row = conn.execute(
        "SELECT file_path FROM wiki_pages WHERE title = ? AND status = 'done'",
        (wiki_title,)
    ).fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    file_path = row[0]
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            wiki_content = f.read()
    except Exception:
        return None

    # 根据实体类型构建不同的 prompt
    if entity_type == "moves":
        prompt = """你是一个 Pokemon 数据分析师。请从以下 wiki 页面中提取招式的完整信息。

Wiki 页面标题：{title}
Wiki 页面内容：
{wiki_content}

请返回 JSON 格式（不要包含其他文本）：
{{
  "name_zh": "中文名",
  "name_en": "英文名",
  "name_ja": "日文名",
  "type": "属性（英文小写，如 normal/fire/water）",
  "damage_class": "伤害类别（physical/special/status）",
  "power": 威力（数字或null），
  "accuracy": 命中率（数字或null），
  "pp": PP值（数字或null），
  "target": 目标（数字代码或null），
  "makes_contact": 是否接触招式（0或1或null），
  "can_protect": 是否可守住（0或1或null），
  "effect_zh": "招式效果的中文描述（从招式附加效果部分提取完整描述）"
}}

注意：
1. 优先从 info 框提取基础数值，但也要查看"招式变更"部分，如果有最新版本的数值变更（如冠军版本），以最新版本为准
2. effect_zh 从"招式附加效果"部分提取完整的对战效果描述
3. type 必须是英文小写（一般=normal, 火=fire, 水=water, 草=grass, 电=electric, 冰=ice, 格斗=fighting, 毒=poison, 地面=ground, 飞行=flying, 超能力=psychic, 虫=bug, 岩石=rock, 幽灵=ghost, 龙=dragon, 恶=dark, 钢=steel, 妖精=fairy, 暗影=shadow）
4. damage_class 必须是英文（物理=physical, 特殊=special, 变化=status）"""

    elif entity_type == "abilities":
        prompt = """你是一个 Pokemon 数据分析师。请从以下 wiki 页面中提取特性的完整信息。

Wiki 页面标题：{title}
Wiki 页面内容：
{wiki_content}

请返回 JSON 格式（不要包含其他文本）：
{{
  "name_zh": "中文名",
  "name_en": "英文名",
  "name_ja": "日文名（片假名/平假名）",
  "effect_battle": "对战中的效果描述（中文，完整描述）",
  "effect_overworld": "对战外的效果描述（中文，如果有的话）"
}}

注意：
1. effect_battle 从"特性效果"的"对战中"部分提取完整描述
2. effect_overworld 从"特性效果"的"对战外"部分提取（如果有的话）
3. 如果有多个世代的效果变化，提取最新版本的效果"""

    elif entity_type == "items":
        prompt = """你是一个 Pokemon 数据分析师。请从以下 wiki 页面中提取道具的完整信息。

Wiki 页面标题：{title}
Wiki 页面内容：
{wiki_content}

请返回 JSON 格式（不要包含其他文本）：
{{
  "name_zh": "中文名",
  "name_en": "英文名",
  "name_ja": "日文名（片假名/平假名）",
  "category": "道具分类（PokeAPI 英文 slug，见下方映射表）",
  "fling_power": 投掷威力（数字，如果wiki没有明确标注则为null），
  "fling_effect": "投掷效果（如果有特殊效果则描述，否则为null）"
}}

注意：
1. category 必须从以下可选项中选择一个（这是 PokeAPI 英文分类，不是中文）：
   all-machines, all-mail, apricorn-balls, apricorn-box, bad-held-items, baking-only,
   catching-bonus, choice, collectibles, curry-ingredients, data-cards, dex-completion,
   dynamax-crystals, effort-drop, effort-training, event-items, evolution, flutes,
   gameplay, healing, held-items, in-a-pinch, jewels, loot, medicine, mega-stones,
   memories, miracle-shooter, mulch, nature-mints, other, picky-healing, picnic,
   plates, plot-advancement, pp-recovery, revival, sandwich-ingredients, scarves,
   special-balls, species-candies, species-specific, spelunking, standard-balls,
   stat-boosts, status-cures, tera-shard, tm-materials, training, type-enhancement,
   type-protection, unused, vitamins, z-crystals
   从 wiki 的 bag 字段映射到上述英文分类。常见映射：
   - 精灵球 → standard-balls 或 special-balls（公园球等特殊球用 special-balls）
   - 药品 → medicine 或 healing
   - 树果 → berries（但 PokeAPI 没有 berries，用 held-items 或 other）
   - 进化道具 → evolution
   - 战斗道具 → held-items 或 stat-boosts
   - 重要物品 → plot-advancement 或 event-items
   - Ｚ纯晶 → z-crystals
   - 超级石 → mega-stones
   - 糖果 → species-candies 或 vitamins
   如果无法确定就不报告 category（设为 null）。
2. fling_power：从道具信息框的 throw 字段提取数字。注意：树果类道具的 throw 字段通常是效果描述文本而非数字，此时 fling_power 应为 null。只有 throw 字段明确是纯数字时才提取。
3. 如果有"效果变更"章节，注意最新版本的效果"""

    else:
        return None

    # 拆分静态规则和动态数据：模板中 "{title}" 前为规则
    _split_idx = prompt.index("{title}")
    _rules = prompt[:_split_idx]
    _data = prompt[_split_idx:].format(title=wiki_title, wiki_content=wiki_content[:10000])

    try:
        response = llm.sync_client.chat.completions.create(
            model=llm.default_sync_model,
            messages=[
                {"role": "system", "content": _rules, "cache_control": {"type": "ephemeral"}},
                {"role": "user", "content": _data},
            ],
            max_tokens=16384,
            temperature=0.1,
            extra_body={"thinking": {"type": "enabled"}},
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content)
        result["file_path"] = file_path
        return result
    except Exception as e:
        print(f"  [LLM] 提取失败: {str(e)[:80]}")
        return None


# ============================================================
# 报告生成
# ============================================================

def generate_report(
    new_entries: List[dict],
    renamed_entries: List[dict],
    stale_entries: List[dict],
    suggestions: List[dict],
    output_path: str,
):
    """生成同步报告"""
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "new_entries": len(new_entries),
            "renamed_entries": len(renamed_entries),
            "stale_entries": len(stale_entries),
            "suggested_updates": len(suggestions),
        },
        "new_entries": new_entries,
        "renamed_entries": renamed_entries,
        "stale_entries": [
            {
                "entity_type": e["entity_type"],
                "name_zh": e["name_zh"],
                "wiki_updated": e["wiki_updated"],
                "needs_update": e.get("needs_update", True),
                "filter_reason": e.get("filter_reason", ""),
                "wiki_url": e.get("wiki_url", ""),
            }
            for e in stale_entries
        ],
        "changes": suggestions,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def print_summary(report: dict):
    """打印控制台摘要"""
    print("\n" + "=" * 60)
    print(f"Pokemon 数据同步报告")
    print("=" * 60)

    summary = report["summary"]
    print(f"\n[新条目 - Wiki 有，数据库没有]")
    print(f"  共 {summary['new_entries']} 个")
    for entry in report["new_entries"][:10]:
        print(f"    - {entry['entity_type']}: {entry['name_zh']}")
    if summary["new_entries"] > 10:
        print(f"    ... 还有 {summary['new_entries'] - 10} 个")

    print(f"\n[名称变更 - Wiki 使用新名称]")
    print(f"  共 {summary['renamed_entries']} 个")
    for entry in report["renamed_entries"][:10]:
        print(f"    - {entry['entity_type']}: {entry['old_name']} → {entry['name_zh']}")
    if summary["renamed_entries"] > 10:
        print(f"    ... 还有 {summary['renamed_entries'] - 10} 个")

    print(f"\n[过期条目 - Wiki 页面已更新]")
    print(f"  共 {summary['stale_entries']} 个")

    needs_update = sum(
        1 for e in report["stale_entries"] if e.get("needs_update")
    )
    print(f"  其中 {needs_update} 个需要更新（LLM 筛选）")

    print(f"\n[更新建议]")
    print(f"  共 {summary['suggested_updates']} 个条目有具体变化")
    for change in report["changes"][:10]:
        print(f"    - {change['entity_type']}: {change['name_zh']}")
        for c in change.get("changes", []):
            print(f"      {c['field']}: {c['current_value']} → {c['new_value']}")
    if summary["suggested_updates"] > 10:
        print(f"    ... 还有 {summary['suggested_updates'] - 10} 个")

    print(f"\n报告已保存到: {OUTPUT_DIR}")


# ============================================================
# 执行更新
# ============================================================

def apply_changes(suggestions_path: str, pokemon_db: str):
    """执行更新建议"""
    with open(suggestions_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    changes = report.get("changes", [])
    renamed_entries = report.get("renamed_entries", [])
    new_entries = report.get("new_entries", [])

    if not changes and not renamed_entries and not new_entries:
        print("没有需要更新的条目")
        return

    print(f"\n将要执行的更新：")
    print(f"  - 更新 {len(changes)} 个现有条目（值变更）")
    print(f"  - 重命名 {len(renamed_entries)} 个条目（名称变更）")
    print(f"  - 新增 {len(new_entries)} 个条目（需要手动补充信息）")

    # 显示详细信息
    if changes:
        print(f"\n[值变更]")
        for change in changes[:20]:
            print(f"  [{change['entity_type']}] {change['name_zh']}:")
            for c in change.get("changes", []):
                print(f"    {c['field']}: {c['current_value']} -> {c['new_value']}")

    if renamed_entries:
        print(f"\n[名称变更]")
        for entry in renamed_entries:
            print(f"  [{entry['entity_type']}] {entry['old_name']} -> {entry['name_zh']}")

    if new_entries:
        print(f"\n[新条目]（需要手动补充信息）")
        for entry in new_entries:
            print(f"  [{entry['entity_type']}] {entry['name_zh']} ({entry.get('wiki_url', '')})")

    # 确认
    confirm = input("\n确认执行更新？(yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("已取消")
        return

    conn = sqlite3.connect(pokemon_db)
    updated = 0
    errors = 0

    # 1. 处理值变更
    for change in changes:
        entity_type = change.get("entity_type", "moves")
        config = ENTITY_TYPES.get(entity_type, ENTITY_TYPES["moves"])
        table = config["table"]
        name_zh = change["name_zh"]

        set_clauses = []
        values = []
        for c in change.get("changes", []):
            field = c["field"]
            new_value = c["new_value"]
            set_clauses.append(f"{field} = ?")
            values.append(new_value)

        if not set_clauses:
            continue

        values.append(name_zh)
        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE name_zh = ?"

        try:
            conn.execute(sql, values)
            updated += 1
        except Exception as e:
            print(f"  更新失败 [{name_zh}]: {e}")
            errors += 1

    # 2. 处理名称变更
    for entry in renamed_entries:
        entity_type = entry.get("entity_type", "moves")
        config = ENTITY_TYPES.get(entity_type, ENTITY_TYPES["moves"])
        table = config["table"]
        old_name = entry["old_name"]
        new_name = entry["name_zh"]

        sql = f"UPDATE {table} SET name_zh = ? WHERE name_zh = ?"
        try:
            conn.execute(sql, (new_name, old_name))
            updated += 1
            print(f"  重命名: {old_name} -> {new_name}")
        except Exception as e:
            print(f"  重命名失败 [{old_name}]: {e}")
            errors += 1

    # 3. 处理新条目
    if new_entries:
        print(f"\n[处理新条目]")
        for entry in new_entries:
            entity_type = entry.get("entity_type", "moves")
            wiki_title = entry.get("wiki_title", "")
            name_zh = entry["name_zh"]

            # 用 LLM 提取信息（替代正则）
            wiki_info = llm_extract_entity_info(wiki_title, entity_type)
            if not wiki_info:
                print(f"  跳过 {name_zh}: LLM 无法提取信息")
                errors += 1
                continue

            # 插入新条目
            try:
                if entity_type == "moves":
                    max_id = conn.execute("SELECT MAX(id) FROM moves").fetchone()[0] or 0
                    new_id = max_id + 1
                    conn.execute("""
                        INSERT INTO moves (id, name_zh, name_en, name_ja, type, damage_class, power, accuracy, pp, wiki_file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        new_id, name_zh,
                        wiki_info.get("name_en", ""),
                        wiki_info.get("name_ja", ""),
                        wiki_info.get("type", ""),
                        wiki_info.get("damage_class", ""),
                        wiki_info.get("power"),
                        wiki_info.get("accuracy"),
                        wiki_info.get("pp"),
                        wiki_info.get("file_path"),
                    ))
                    updated += 1
                    print(f"  新增: {name_zh} (id={new_id})")

                elif entity_type == "abilities":
                    max_id = conn.execute("SELECT MAX(id) FROM abilities").fetchone()[0] or 0
                    new_id = max_id + 1
                    conn.execute("""
                        INSERT INTO abilities (id, name_zh, name_en, name_ja, wiki_file_path)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        new_id, name_zh,
                        wiki_info.get("name_en", ""),
                        wiki_info.get("name_ja", ""),
                        wiki_info.get("file_path"),
                    ))
                    updated += 1
                    print(f"  新增: {name_zh} (id={new_id})")

                elif entity_type == "items":
                    max_id = conn.execute("SELECT MAX(id) FROM items").fetchone()[0] or 0
                    new_id = max_id + 1
                    conn.execute("""
                        INSERT INTO items (id, name_zh, name_en, name_ja, category,
                            fling_power, fling_effect, wiki_file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        new_id, name_zh,
                        wiki_info.get("name_en", ""),
                        wiki_info.get("name_ja", ""),
                        wiki_info.get("category", ""),
                        wiki_info.get("fling_power"),
                        wiki_info.get("fling_effect"),
                        wiki_info.get("file_path"),
                    ))
                    updated += 1
                    print(f"  新增: {name_zh} (id={new_id})")

            except Exception as e:
                print(f"  新增失败 [{name_zh}]: {e}")
                errors += 1

    conn.commit()
    conn.close()

    print(f"\n更新完成: {updated} 成功, {errors} 失败")


# ============================================================
# 单文件模式
# ============================================================

def find_stale_by_file(file_path: str, entity_type: Optional[str] = None) -> Optional[dict]:
    """单文件模式：直接从 wiki_meta.db 查 title，再从 pokemonData.db 查条目，跳过全量扫描"""
    basename = os.path.basename(file_path)
    # 用 page_id 前缀匹配（文件名格式：{page_id}_{name}.wiki，数据库中 file_path 可能名字不同）
    page_id = basename.split('_')[0] if '_' in basename else None
    conn = sqlite3.connect(WIKI_META_DB)
    if page_id and page_id.isdigit():
        row = conn.execute(
            "SELECT title, wiki_updated FROM wiki_pages WHERE CAST(page_id AS TEXT) = ? AND status='done'",
            (page_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT title, wiki_updated FROM wiki_pages WHERE file_path LIKE ? AND status='done'",
            (f'%{basename}',)
        ).fetchone()
    conn.close()
    if not row:
        return None
    wiki_title, wiki_updated = row

    # 自动推断 entity_type
    if not entity_type:
        for etype, config in ENTITY_TYPES.items():
            suffix = config.get("wiki_suffix", "")
            if suffix and wiki_title.endswith(suffix):
                entity_type = etype
                break
        if not entity_type:
            # 默认当 moves 处理
            entity_type = "moves"

    config = ENTITY_TYPES[entity_type]
    table = config["table"]
    name_col = config["name_col"]
    suffix = config.get("wiki_suffix", "")

    conn = sqlite3.connect(POKEMON_DB)
    conn.row_factory = sqlite3.Row
    # 尝试 name_zh 匹配
    db_row = conn.execute(
        f"SELECT * FROM {table} WHERE {name_col} = ? OR {name_col} = ?",
        (wiki_title, wiki_title.replace(suffix, '') if suffix else wiki_title)
    ).fetchone()
    if not db_row:
        # 尝试 wiki_file_path 匹配
        try:
            db_row = conn.execute(
                f"SELECT * FROM {table} WHERE wiki_file_path LIKE ?", (f'%{basename}',)
            ).fetchone()
        except Exception:
            pass
    if not db_row:
        # 从 wikitext 提取 name 字段匹配
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()[:2000]
                m = re.search(r'\|name=([^|\n]+)', text)
                if m:
                    name = m.group(1).strip()
                    db_row = conn.execute(
                        f"SELECT * FROM {table} WHERE {name_col} = ?", (name,)
                    ).fetchone()
            except Exception:
                pass
    if not db_row:
        conn.close()
        return None

    columns = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    entry = {col: db_row[col] for col in columns}
    conn.close()
    return {
        "entity_type": entity_type,
        "name_zh": entry.get(name_col, ""),
        "name_en": entry.get("name_en", ""),
        "wiki_title": wiki_title,
        "wiki_updated": wiki_updated,
        "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
        "summary": "",
        "db_entry": entry,
        "file_path": file_path,
    }


# ============================================================
# 摘要生成
# ============================================================

def generate_summary_md(report: dict, output_path: str) -> str:
    """从同步报告 JSON 生成可读的 .md 摘要文件，返回文件路径"""
    from collections import defaultdict

    lines = []
    entity_type = report.get("entity_type", "unknown")
    lines.append(f"# {entity_type.title()} 同步报告摘要")
    lines.append(f"生成时间: {report.get('generated_at', '')}")
    lines.append(f"since: {report.get('since', '')}  until: {report.get('until', '') or '不限'}")
    lines.append(f"模型: {report.get('model', '')}")

    changes = report.get("changes", [])
    new_entries = report.get("new_entries", [])
    renamed_entries = report.get("renamed_entries", [])
    total_stale = report.get("total_stale", 0)
    lines.append(f"过期条目: {total_stale}  有变更: {len(changes)}")
    lines.append(f"新条目: {len(new_entries)}  重命名: {len(renamed_entries)}")
    lines.append("")

    # 新条目
    if new_entries:
        lines.append(f"## 新条目 ({len(new_entries)} 个)")
        lines.append("")
        for entry in new_entries:
            info = entry.get("wiki_info", {})
            name_en = info.get("name_en", "")
            lines.append(f"- {entry['name_zh']} ({name_en}) — {entry.get('wiki_url', '')}")
        lines.append("")

    # 重命名
    if renamed_entries:
        lines.append(f"## 名称变更 ({len(renamed_entries)} 个)")
        lines.append("")
        for entry in renamed_entries:
            lines.append(f"- {entry.get('old_name', '')} → {entry['name_zh']}")
        lines.append("")

    if not changes:
        lines.append("## 值变更：无")
    else:
        # 按字段分组统计
        field_groups = defaultdict(list)
        for entry in changes:
            for c in entry.get("changes", []):
                field_groups[c["field"]].append({
                    "name_zh": entry["name_zh"],
                    "name_en": entry.get("name_en", ""),
                    "old": c["current_value"],
                    "new": c["new_value"],
                    "reason": c.get("reason", ""),
                })

        for field, items in field_groups.items():
            lines.append(f"## {field} ({len(items)} 条)")
            lines.append("")
            for item in items:
                old = repr(item["old"]) if item["old"] is not None else "NULL"
                reason = f"  ({item['reason']})" if item["reason"] else ""
                lines.append(f"- {item['name_zh']} ({item['name_en']}): {old} -> {item['new']}{reason}")
            lines.append("")

    md_path = output_path.replace(".json", "_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Wiki ↔ 数据库同步检测")
    parser.add_argument("--quick", action="store_true", help="只检测，不调用 LLM")
    parser.add_argument("--entity", choices=list(ENTITY_TYPES.keys()), help="只检查指定实体类型")
    parser.add_argument("--since", default="2026-04-01", help="只检查此日期后更新的页面 (YYYY-MM-DD，默认 2026-04-01)")
    parser.add_argument("--until", default=None, help="只检查此日期前更新的页面 (YYYY-MM-DD，默认不限)")
    parser.add_argument("--file", help="只分析指定的 wikitext 文件路径（跳过全量扫描，输出 JSON 报告）")
    parser.add_argument("--apply", metavar="FILE", help="执行更新建议")
    parser.add_argument("--output", help="自定义输出路径")
    parser.add_argument("--skip-api", action="store_true", help="跳过 API 查询，使用本地缓存的时间戳（快速模式）")
    parser.add_argument("--api-limit", type=int, default=0, help="限制 API 查询的页面数（0=全部，测试用）")
    args = parser.parse_args()

    # 执行更新模式
    if args.apply:
        apply_changes(args.apply, POKEMON_DB)
        return

    # 单文件模式：短路，不加载 wiki 索引
    if args.file:
        file_path = args.file
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__), ), '..', '..', file_path)
            file_path = os.path.normpath(file_path)
        print("=" * 60)
        print("Pokemon Wiki ↔ 数据库同步检测（单文件模式）")
        print("=" * 60)
        print(f"\n文件: {os.path.basename(file_path)}")
        stale = find_stale_by_file(file_path, args.entity)
        if not stale:
            print("  未找到匹配的条目")
            return
        entity_type = stale["entity_type"]
        print(f"  匹配: {stale['name_zh']} (entity={entity_type}, wiki={stale['wiki_title']})")

        suggestions = []
        if not args.quick:
            print("\nLLM analysis...")
            suggestions = llm_extract_changes([stale], entity_type, POKEMON_DB)
            for s in suggestions:
                for c in s.get('changes', []):
                    print(f'  {s["name_zh"]}: {c["field"]}: {c["current_value"]} -> {c["new_value"]}')
            if not suggestions:
                print("  无变化")

        # 生成 JSON 报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or os.path.join(OUTPUT_DIR, f"sync_report_{entity_type}_{timestamp}.json")
        report = {
            "generated_at": datetime.now().isoformat(),
            "entity_type": entity_type,
            "since": args.since,
            "model": os.getenv("LLM_MODEL_SYNC", "mimo-v2.5"),
            "total_stale": 1,
            "total_changes": len(suggestions),
            "changes": suggestions,
            "file_mode": True,
            "file_path": file_path,
        }
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {output_path}")
        return

    print("=" * 60)
    print("Pokemon Wiki ↔ 数据库同步检测")
    print("=" * 60)

    # 加载 wiki 索引
    print("\n[1] 加载 wiki 索引...")
    pages, redirects, reverse_redirects = load_wiki_index(WIKI_META_DB)
    print(f"  wiki_pages: {len(pages)} 条")
    print(f"  wiki_redirects: {len(redirects)} 条")

    # 通过 API 刷新 wiki 最新修改时间
    if not args.skip_api:
        print("\n[1.5] 查询 wiki API 获取最新修改时间...")
        refresh_wiki_timestamps(pages, WIKI_META_DB, limit=args.api_limit)
    else:
        print("\n[1.5] 跳过 API 查询（--skip-api）")

    # 确定要检查的实体类型
    entity_types = [args.entity] if args.entity else list(ENTITY_TYPES.keys())

    all_new_entries = []
    all_renamed_entries = []
    all_stale_entries = []
    all_suggestions = []

    for entity_type in entity_types:
        print(f"\n[2] 检测 {entity_type}...", flush=True)

        # Phase 1: 新条目检测（包含重命名检测）
        new_entries, renamed_entries = detect_new_entries(
            entity_type, pages, redirects, reverse_redirects, POKEMON_DB
        )
        print(f"  新条目: {len(new_entries)} 个")
        print(f"  名称变更: {len(renamed_entries)} 个")
        all_new_entries.extend(new_entries)
        all_renamed_entries.extend(renamed_entries)

        # Phase 2: 过期条目检测
        stale_entries = detect_stale_entries(
            entity_type, pages, redirects, POKEMON_DB, args.since, args.until
        )
        print(f"  过期条目: {len(stale_entries)} 个")
        all_stale_entries.extend(stale_entries)

        # Phase 3: LLM 分析（如果不是 --quick 模式）
        if not args.quick:
            # 直接用完整 wiki 内容分析（跳过 summary 筛选）
            if stale_entries:
                print(f"\n[3] LLM 分析过期条目 {entity_type} ({len(stale_entries)} 个)...", flush=True)
                suggestions = llm_extract_changes(stale_entries, entity_type, POKEMON_DB)
                all_suggestions.extend(suggestions)

            # 分析新条目（用 LLM 提取完整信息）
            if new_entries:
                print(f"\n[3] LLM 分析新条目 {entity_type}...")
                filtered_entries = new_entries
                if args.since:
                    filtered_entries = [
                        e for e in new_entries
                        if pages.get(e.get("wiki_title", ""), {}).get("wiki_updated", "9999") >= args.since
                    ]
                    print(f"  --since {args.since} 过滤后: {len(filtered_entries)}/{len(new_entries)} 个")
                for entry in filtered_entries:
                    wiki_title = entry.get("wiki_title", "")
                    name_zh = entry["name_zh"]
                    print(f"  提取: {name_zh}...")
                    wiki_info = llm_extract_entity_info(wiki_title, entity_type)
                    if wiki_info:
                        entry["wiki_info"] = wiki_info
                        print(f"    完成: {wiki_info.get('name_en', '')}")
                    else:
                        print(f"    失败")

    # 生成报告
    print(f"\n[4] 生成报告...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(OUTPUT_DIR, f"sync_report_{timestamp}.json")

    report = generate_report(
        all_new_entries, all_renamed_entries, all_stale_entries,
        all_suggestions, output_path
    )
    print_summary(report)

    print(f"\n下一步：")
    print(f"  1. 查看报告: {output_path}")
    print(f"  2. 审核更新建议")
    print(f"  3. 执行更新: python sync_detector.py --apply {output_path}")


if __name__ == "__main__":
    main()
