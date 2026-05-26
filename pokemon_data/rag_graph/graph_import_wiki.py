"""Wiki 全量页面导入：wiki_meta.db + wikitext_cache → graph.db"""
import os
import re
import sqlite3
import sys
import time
import urllib.parse

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pokemon_data.rag_graph.graph_db import GraphDB

# ── 路径 ─────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_META_DB = os.path.join(_BASE, "wiki", "wiki_meta.db")
GRAPH_DB_PATH = os.path.join(_BASE, "rag_graph", "graph.db")
WIKITEXT_DIR = os.path.join(_BASE, "wiki", "wikitext_cache")

# ── Aho-Corasick（可选） ──────────────────────────────────────────────
try:
    import ahocorasick
    USE_AC = True
except ImportError:
    USE_AC = False

# ── 停用词 ────────────────────────────────────────────────────────────
STOPWORDS = {
    'hp', '攻击', '防御', '特攻', '特防', '速度', '命中', '回避',
    '一般', '格斗', '飞行', '毒', '地面', '岩石', '虫', '幽灵',
    '钢', '火', '水', '草', '电', '超能力', '冰', '龙', '恶', '妖精',
    '招式', '特性', '道具', '属性', '宝可梦', '状态', '天气', '场地',
    '对战', '伤害', '效果', '倍率', '命中率', '暴击',
    '使用', '造成', '降低', '提升', '变化', '回合',
}

# ── 排除的 node_type ─────────────────────────────────────────────────
EXCLUDE_TYPES = ('generation', 'game', 'wiki_page', 'wiki_section')

# ── 正则（编译一次） ─────────────────────────────────────────────────
_RE_REF = re.compile(r'<ref[^>]*>.*?</ref>', re.DOTALL)
_RE_REF_SELF = re.compile(r'<ref[^>]*/>')
_RE_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)
_RE_HTML = re.compile(r'<[^>]+>')
_RE_TEMPLATE = re.compile(r'\{\{[^{}]*\}\}')
_RE_TABLE = re.compile(r'\{\|.*?\|\}', re.DOTALL)
_RE_FILE = re.compile(
    r'\[\[(?:File|Image|文件):(?:[^\]]*(?:\[\[.*?\]\])?[^\]]*)\]\]',
    re.IGNORECASE)
_RE_LINK_ALT = re.compile(r'\[\[([^\]|]+)\|([^\]]+)\]\]')
_RE_LINK = re.compile(r'\[\[([^\]]+)\]\]')
_RE_EXT_LINK = re.compile(r'\[https?://[^\s\]]+\s*([^\]]*)\]')
_RE_BOLD = re.compile(r"'{2,3}")
_RE_LIST = re.compile(r'^[\*#;:]+\s*', re.MULTILINE)

_H4_RE = re.compile(r'^====\s*(.+?)\s*====\s*$')
_H3_RE = re.compile(r'^===\s*(.+?)\s*===\s*$')
_H2_RE = re.compile(r'^==\s*([^=]+?)\s*==\s*$')


# ── wikitext 解析 ────────────────────────────────────────────────────
def clean_wikitext(text):
    """清洗 wikitext 标记，返回纯文本"""
    text = _RE_REF.sub('', text)
    text = _RE_REF_SELF.sub('', text)
    text = _RE_COMMENT.sub('', text)
    text = _RE_HTML.sub('', text)
    for _ in range(5):
        prev = text
        text = _RE_TEMPLATE.sub('', text)
        if text == prev:
            break
    text = _RE_TABLE.sub('', text)
    text = _RE_FILE.sub('', text)
    text = _RE_LINK_ALT.sub(r'\2', text)
    text = _RE_LINK.sub(r'\1', text)
    text = _RE_EXT_LINK.sub(r'\1', text)
    text = _RE_BOLD.sub('', text)
    text = _RE_LIST.sub('', text)
    return text


def parse_wikitext(text):
    """解析 wikitext → (summary, sections)"""
    text = clean_wikitext(text)
    lines = text.split('\n')
    sections = []
    current_heading = ""
    current_level = 0
    current_lines = []
    summary_lines = []
    in_summary = True

    for line in lines:
        h4_match = _H4_RE.match(line)
        h3_match = _H3_RE.match(line) if not h4_match else None
        h2_match = _H2_RE.match(line) if not h3_match and not h4_match else None

        matched = h4_match or h3_match or h2_match
        if matched:
            new_level = 4 if h4_match else (3 if h3_match else 2)
            if in_summary:
                summary_lines = current_lines
                in_summary = False
            elif current_lines:
                sections.append({
                    'heading': current_heading,
                    'level': current_level,
                    'text': '\n'.join(current_lines).strip()
                })
            current_heading = matched.group(1)
            current_level = new_level
            current_lines = []
        else:
            current_lines.append(line)

    if in_summary:
        summary_lines = current_lines
    elif current_lines:
        sections.append({
            'heading': current_heading,
            'level': current_level,
            'text': '\n'.join(current_lines).strip()
        })

    summary = '\n'.join(summary_lines).strip()
    return summary, sections


# ── 实体匹配 ─────────────────────────────────────────────────────────
def build_automaton(entity_names):
    """构建 Aho-Corasick 自动机或 dict fallback"""
    filtered = {n: ids for n, ids in entity_names.items() if n not in STOPWORDS}
    if USE_AC:
        A = ahocorasick.Automaton()
        for name, node_ids in filtered.items():
            A.add_word(name, (name, node_ids))
        A.make_automaton()
        return A
    return filtered


def find_mentions(matcher, text, max_entities=20):
    """返回命中实体的 {name: (node_ids, count)}，最多 max_entities 个不同实体"""
    if USE_AC:
        found = {}
        for end_idx, (name, node_ids) in matcher.iter(text):
            if name in found:
                prev_ids, cnt = found[name]
                found[name] = (prev_ids, cnt + 1)
            elif len(found) < max_entities:
                found[name] = (node_ids, 1)
        return found
    else:
        found = {}
        for name, node_ids in matcher.items():
            count = text.count(name)
            if count == 0:
                continue
            if len(found) < max_entities:
                found[name] = (node_ids, count)
        return found


# ── 幂等清理 ─────────────────────────────────────────────────────────
def _cleanup_existing(graph):
    """清除已有的 wiki 节点和边（幂等重跑）"""
    c = graph.conn
    c.execute("""
        DELETE FROM graph_edges WHERE source_id LIKE 'wiki_page:%'
        OR source_id LIKE 'wiki_section:%'
        OR target_id LIKE 'wiki_page:%'
        OR target_id LIKE 'wiki_section:%'
    """)
    c.execute("DELETE FROM graph_nodes WHERE node_type IN ('wiki_page','wiki_section')")
    c.execute("DELETE FROM graph_entity_aliases WHERE alias_type = 'redirect'")
    graph.commit()


# ── 主流程 ───────────────────────────────────────────────────────────
def import_wiki(wiki_meta_path=None, graph_path=None, verbose=True):
    wiki_meta_path = wiki_meta_path or WIKI_META_DB
    graph_path = graph_path or GRAPH_DB_PATH

    if not os.path.exists(wiki_meta_path):
        print(f"ERROR: wiki_meta.db not found: {wiki_meta_path}")
        return
    if not os.path.exists(graph_path):
        print(f"ERROR: graph.db not found: {graph_path}")
        return

    wiki_db = sqlite3.connect(wiki_meta_path)
    graph = GraphDB(graph_path)
    t0 = time.time()

    counts = {
        "wiki_pages": 0, "wiki_sections": 0,
        "section_of": 0, "page_mentions": 0, "section_mentions": 0,
        "redirect_aliases": 0, "redirect_entity_aliases": 0,
    }

    # ── 1. 幂等清理 ──────────────────────────────────────────────────
    if verbose:
        print("清除已有 wiki 节点/边/redirect 别名...")
    _cleanup_existing(graph)

    # ── 2. 预加载 done 页面 ID 集合 ──────────────────────────────────
    done_ids = set()
    for row in wiki_db.execute("SELECT page_id FROM wiki_pages WHERE status = 'done'"):
        done_ids.add(row[0])
    if verbose:
        print(f"done 页面: {len(done_ids)}")

    # ── 3. 加载实体集 + redirect 重映射缓存 ──────────────────────────
    entity_names = {}  # {name: [node_id, ...]}

    # 节点 name_zh（排除 wiki 类型和通用类型）
    for row in graph.conn.execute(
        "SELECT node_id, name_zh FROM graph_nodes WHERE length(name_zh) >= 2 "
        "AND node_type NOT IN ('generation','game','wiki_page','wiki_section')"
    ):
        entity_names.setdefault(row[1], []).append(row[0])

    # 别名（排除 redirect 类型）
    for row in graph.conn.execute(
        "SELECT alias, node_id FROM graph_entity_aliases "
        "WHERE length(alias) >= 2 AND alias_type != 'redirect'"
    ):
        entity_names.setdefault(row[0], []).append(row[1])

    # redirect 重映射 + 别名注册
    redirect_entity_map = {}  # source_title → [real_entity_node_ids]
    for row in wiki_db.execute(
        "SELECT source_title, target_page_id, target_title FROM wiki_redirects"
    ):
        source_title, target_pid, target_title = row
        if target_pid not in done_ids:
            continue

        # 注册为 wiki_page 别名
        graph.add_alias(source_title, f"wiki_page:{target_pid}", alias_type='redirect')
        counts["redirect_aliases"] += 1

        # 重映射到实体节点
        base_name = re.sub(r'[（(][^）)]+[）)]$', '', target_title).strip()
        entity_rows = graph.conn.execute(
            "SELECT node_id FROM graph_nodes "
            "WHERE name_zh = ? AND node_type NOT IN "
            "('generation','game','wiki_page','wiki_section')",
            (base_name,)
        ).fetchall()

        if entity_rows:
            real_ids = [r[0] for r in entity_rows]
            for node_id in real_ids:
                graph.add_alias(source_title, node_id, alias_type='redirect')
                counts["redirect_entity_aliases"] += 1
            redirect_entity_map[source_title] = real_ids
            # 注册到 matcher
            entity_names.setdefault(source_title, []).extend(real_ids)

    if verbose:
        print(f"redirect 别名: {counts['redirect_aliases']}, "
              f"实体重映射: {counts['redirect_entity_aliases']}, "
              f"matcher 实体词: {len(entity_names)}")

    # ── 4. 构建匹配器 ────────────────────────────────────────────────
    matcher = build_automaton(entity_names)
    if verbose:
        mode = "Aho-Corasick" if USE_AC else "naive (pip install pyahocorasick)"
        print(f"匹配器: {mode}")

    # ── 5. 遍历 wikitext 文件 ────────────────────────────────────────
    rows = wiki_db.execute(
        "SELECT page_id, title, file_path FROM wiki_pages WHERE status = 'done'"
    ).fetchall()

    project_root = os.path.dirname(_BASE)

    for i, (page_id, title, file_path) in enumerate(rows):
        # 规范化 file_path（相对于项目根目录）
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_root, file_path)

        if not os.path.exists(file_path):
            if verbose and i < 5:
                print(f"  SKIP missing: {file_path}")
            continue

        # 读取 + 解析
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                wikitext = f.read()
        except Exception:
            continue

        summary, sections = parse_wikitext(wikitext)

        # wiki_page 节点
        node_id = f"wiki_page:{page_id}"
        source_page = f"https://wiki.52poke.com/wiki/{urllib.parse.quote(title)}"
        graph.add_node(node_id, "wiki_page", name_zh=title,
                       source="wiki", source_page=source_page,
                       properties={"file_path": file_path})
        counts["wiki_pages"] += 1

        # page_mentions（摘要匹配）
        if summary:
            mentions = find_mentions(matcher, summary)
            for name, (node_ids, cnt) in mentions.items():
                weight = 1.0 / len(node_ids)
                for nid in node_ids:
                    graph.add_edge(node_id, nid, "page_mentions",
                                   weight=weight,
                                   properties={"match_type": "summary",
                                               "match_count": cnt},
                                   source="wiki")
                    counts["page_mentions"] += 1

        # wiki_section 节点 + section_of + section_mentions
        for idx, sec in enumerate(sections):
            sec_node_id = f"wiki_section:{page_id}_{idx}"
            sec_name = f"{title} / {sec['heading']}" if sec['heading'] else title
            graph.add_node(sec_node_id, "wiki_section", name_zh=sec_name,
                           source="wiki",
                           properties={"page_id": page_id,
                                       "heading": sec['heading'],
                                       "level": sec['level'],
                                       "section_idx": idx})
            counts["wiki_sections"] += 1

            # section_of 边
            graph.add_edge(sec_node_id, node_id, "section_of", source="wiki")
            counts["section_of"] += 1

            # section_mentions
            if sec['text']:
                mentions = find_mentions(matcher, sec['text'])
                for name, (node_ids, cnt) in mentions.items():
                    weight = 1.0 / len(node_ids)
                    for nid in node_ids:
                        graph.add_edge(sec_node_id, nid, "section_mentions",
                                       weight=weight,
                                       properties={"match_type": "text",
                                                   "match_count": cnt},
                                       source="wiki")
                        counts["section_mentions"] += 1

        # 每 1000 页 commit + 进度
        if (i + 1) % 1000 == 0:
            graph.commit()
            if verbose:
                elapsed = time.time() - t0
                print(f"  [{i+1}/{len(rows)}] pages={counts['wiki_pages']} "
                      f"sections={counts['wiki_sections']} "
                      f"edges={counts['section_of'] + counts['page_mentions'] + counts['section_mentions']} "
                      f"({elapsed:.0f}s)")

    # 最终 commit
    graph.commit()

    # ── 6. 统计 ──────────────────────────────────────────────────────
    elapsed = time.time() - t0
    if verbose:
        total_edges = counts['section_of'] + counts['page_mentions'] + counts['section_mentions']
        print(f"\n导入完成 ({elapsed:.1f}s)")
        print(f"  wiki_page: {counts['wiki_pages']}")
        print(f"  wiki_section: {counts['wiki_sections']}")
        print(f"  section_of 边: {counts['section_of']}")
        print(f"  page_mentions 边: {counts['page_mentions']}")
        print(f"  section_mentions 边: {counts['section_mentions']}")
        print(f"  总边数: {total_edges}")
        print(f"  redirect 别名: {counts['redirect_aliases']}")
        print(f"  redirect 实体别名: {counts['redirect_entity_aliases']}")

    graph.close()
    wiki_db.close()
    return counts


if __name__ == "__main__":
    import_wiki()
