"""Step 5：LLM 抽取 wiki 页面的语义关系到 graph_edges（source='llm_extracted'）

用法：
  python graph_extract.py --limit 100 --dry-run            # 试跑不写库
  python graph_extract.py --limit 100 --shuffle             # 第一轮 100 页
  python graph_extract.py --limit 500 --concurrency 5      # 第二轮 500 页
  python graph_extract.py --concurrency 5                  # 全量
  python graph_extract.py --retry-errors                   # 重试 error 页

依赖：
  pip install mwparserfromhell openai

自动从 api/.env 读取 LLM_TOOL_USE_API_KEY / LLM_TOOL_USE_BASE_URL / LLM_MODEL_TOOL_USE
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import mwparserfromhell
from openai import OpenAI

from pokemon_data.rag_graph.graph_db import GraphDB

# ── 路径 ─────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_BASE)
WIKI_META_DB = os.path.join(_BASE, "wiki", "wiki_meta.db")
GRAPH_DB_PATH = os.path.join(_BASE, "rag_graph", "graph.db")
POKEMON_DB = os.path.join(_BASE, "pokemonData.db")
PROMPT_FILE = os.path.join(_PROJECT_ROOT, "api", "prompt", "graph_extract_prompt.txt")
ENV_FILE = os.path.join(_PROJECT_ROOT, "api", ".env")
DRY_RUN_OUTPUT = os.path.join(_BASE, "rag_graph", "dry_run_results.jsonl")


# ── 自动加载 .env ────────────────────────────────────────────────────
def _load_dotenv(path: str = ENV_FILE):
    """从 .env 文件加载 KEY=VALUE 到 os.environ（不覆盖已有变量）"""
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k and k not in os.environ:
                os.environ[k] = v


# ── 模板白名单（预处理用）────────────────────────────────────────────
# 删除：导航/分类/跨语言/内嵌控制模板（无语义）
TEMPLATE_DELETE_PATTERNS = {
    "navigation", "navbox", "defaultsort", "disambig", "stub", "portal",
    "authority control", "外部链接", "相关页面", "languages", "顶部",
    "消歧义", "noinclude", "导航", "地区导航", "世代", "游戏导航",
}
# 展开为 key: value 文本（含机制信息，不删）
TEMPLATE_EXPAND_PATTERNS = {
    "招式信息框", "特性信息框", "道具信息框", "宝可梦信息框", "状态信息框",
    "寶可夢信息框", "招式信息", "特性信息", "道具信息", "精灵信息",
    "神奇宝贝信息框", "神奇寶貝信息框",
}
# 纯列表/导航页模板（命中即整页跳过，不送 LLM）
TEMPLATE_LIST_PATTERNS = {
    "招式列表", "道具列表", "宝可梦列表", "特性列表", "服装列表",
    "全国图鉴", "地区图鉴", "分级列表",
}

# ── 限制 ─────────────────────────────────────────────────────────────
MAX_CONTENT_CHARS = 80_000            # 超过走 fallback（按 section 拆）
SECTION_MAX_CHARS = 60_000
TOP_ENTITIES = 50
LLM_MAX_RETRIES = 3
MIN_CLEANED_LEN = 50                  # 预处理后少于此字符数直接跳过

# ── 跳过条件 ──────────────────────────────────────────────────────────
# 标题含这些关键词的页面：纯列表/消歧义/索引/年表等，无实质语义内容
_SKIP_TITLE_KEYWORDS = {
    "列表", "招式表", "年表", "索引", "目录", "一览",
    "消歧义", "消歧", "disambig",
    "设定", "简介", "公式",
}
# 由纯数字 + 可选括号注释组成的标题（如 "293"、"161"），多为编号页
_RE_TITLE_NUM = re.compile(r'^[\d\s]+$')


# ══════════════════════════════════════════════════════════════════════
# MiMo 客户端
# ══════════════════════════════════════════════════════════════════════
def _make_client(require_key: bool = True) -> Tuple[Optional[OpenAI], str]:
    """自动读取 api/.env，按以下优先级找 key：
    MIMO_API_KEY → LLM_TOOL_USE_API_KEY → LLM_API_KEY → DEEPSEEK_API_KEY
    """
    _load_dotenv(ENV_FILE)

    api_key = (os.getenv("MIMO_API_KEY")
               or os.getenv("LLM_TOOL_USE_API_KEY")
               or os.getenv("LLM_API_KEY")
               or os.getenv("DEEPSEEK_API_KEY"))
    base_url = (os.getenv("MIMO_API_BASE")
                or os.getenv("LLM_TOOL_USE_BASE_URL")
                or os.getenv("LLM_BASE_URL")
                or os.getenv("DEEPSEEK_BASE_URL")
                or "https://token-plan-cn.xiaomimimo.com/v1")
    model = (os.getenv("MIMO_MODEL")
             or os.getenv("LLM_MODEL_TOOL_USE")
             or os.getenv("LLM_MODEL_EXTRACT")
             or "mimo-v2.5")

    if not api_key:
        if require_key:
            raise RuntimeError(
                "未设置 API Key。检查 api/.env 中是否有 LLM_TOOL_USE_API_KEY")
        return None, model
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0), model


# ══════════════════════════════════════════════════════════════════════
# 统一 Prompt
# ══════════════════════════════════════════════════════════════════════
def load_prompt() -> str:
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def get_existing_relations(graph: GraphDB, limit: int = 80) -> str:
    """从 graph_edges 表查询已有的 llm_extracted 关系类型，按频次排序"""
    rows = graph.conn.execute("""
        SELECT edge_type, COUNT(*) AS cnt
        FROM graph_edges
        WHERE source = 'llm_extracted'
        GROUP BY edge_type
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,)).fetchall()
    if rows:
        return ", ".join(f"{r[0]}({r[1]})" for r in rows)
    return "（暂无，从种子列表选用或自行命名）"


def build_prompt(template: str, content: str, entities: List[Tuple[str, str]],
                 existing_relations: str = "") -> str:
    if entities:
        lines = [f"- {name}" for name, _ in entities]
        entity_list_str = "\n".join(lines)
    else:
        entity_list_str = "（该页面暂无预识别实体，可直接用中文原名输出）"
    return (template
            .replace("{entity_list}", entity_list_str)
            .replace("{existing_relations}", existing_relations)
            .replace("{content}", content))


# ══════════════════════════════════════════════════════════════════════
# wikitext 预处理
# ══════════════════════════════════════════════════════════════════════
_RE_LINK_ALT = re.compile(r'\[\[([^\]|]+)\|([^\]]+)\]\]')
_RE_LINK = re.compile(r'\[\[([^\]]+)\]\]')
_RE_REF = re.compile(r'<ref[^>]*>.*?</ref>', re.DOTALL)
_RE_REF_SELF = re.compile(r'<ref[^>]*/>')
_RE_HTML = re.compile(r'<[^>]+>')
_RE_EMPTY_LINES = re.compile(r'\n{3,}')
_H2_RE = re.compile(r'^==\s*([^=]+?)\s*==\s*$', re.MULTILINE)


def _template_name(tpl) -> str:
    try:
        return str(tpl.name).strip().lower()
    except Exception:
        return ""


def _matches(name: str, patterns: set) -> bool:
    return any(p in name for p in patterns)


def preprocess_wikitext(wikitext: str) -> str:
    """用 mwparserfromhell 处理嵌套模板 + 清洗 wikimarkup"""
    try:
        code = mwparserfromhell.parse(wikitext)
    except Exception:
        return wikitext

    for tpl in code.filter_templates(recursive=True):
        name = _template_name(tpl)
        if not name:
            continue
        if _matches(name, TEMPLATE_DELETE_PATTERNS):
            try:
                code.remove(tpl)
            except ValueError:
                pass
            continue
        if _matches(name, TEMPLATE_EXPAND_PATTERNS):
            lines = [f"【{name}】"]
            for p in tpl.params:
                key = str(p.name).strip()
                val = str(p.value).strip()
                if val:
                    lines.append(f"{key}: {val}")
            replacement = "\n".join(lines) + "\n"
            try:
                code.replace(tpl, replacement)
            except ValueError:
                pass

    text = str(code)
    text = _RE_REF.sub('', text)
    text = _RE_REF_SELF.sub('', text)
    text = _RE_HTML.sub('', text)
    text = _RE_LINK_ALT.sub(r'\2', text)
    text = _RE_LINK.sub(r'\1', text)
    text = _RE_EMPTY_LINES.sub('\n\n', text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════
# 页面跳过判断（取代分类路由）
# ══════════════════════════════════════════════════════════════════════
def is_skip_page(wikitext: str, title: str) -> bool:
    """判断此页是否为纯列表/导航/消歧义页（不值得抽取）。任一条件命中即跳过。"""
    t = title or ''

    # 1. 标题关键词（列表/年表/索引/目录/一览/消歧义）
    for kw in _SKIP_TITLE_KEYWORDS:
        if kw in t:
            return True

    # 2. 纯数字标题（"293"、"161" 等编号页）
    if _RE_TITLE_NUM.match(t.strip()):
        return True

    # 3. 模板命中纯列表白名单
    try:
        code = mwparserfromhell.parse(wikitext)
        for tpl in code.filter_templates(recursive=False):
            if _matches(_template_name(tpl), TEMPLATE_LIST_PATTERNS):
                return True
    except Exception:
        pass

    # 4. 结构信号：表格行数 > 50 且正文（非表格）< 500 字符
    table_rows = wikitext.count('\n|-')
    non_table = re.sub(r'\{\|[\s\S]*?\|\}', '', wikitext)
    if table_rows > 50 and len(non_table.strip()) < 500:
        return True

    return False


# ══════════════════════════════════════════════════════════════════════
# 实体解析
# ══════════════════════════════════════════════════════════════════════
def split_by_sections(text: str) -> List[str]:
    """按 == 小节标题 == 拆成 sections（fallback 用）"""
    parts = _H2_RE.split(text)
    if len(parts) <= 1:
        return [text]
    sections = []
    if parts[0].strip():
        sections.append(parts[0])
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ''
        sections.append(f"== {heading} ==\n{body}")
    return sections


def get_top_entities_for_page(graph: GraphDB, page_id: int,
                              limit: int = TOP_ENTITIES) -> List[Tuple[str, str]]:
    """返回该页面 page_mentions 前 N 个实体 (name_zh, node_id)"""
    page_node = f"wiki_page:{page_id}"
    rows = graph.conn.execute("""
        SELECT n.node_id, n.name_zh,
               COALESCE(json_extract(e.properties, '$.match_count'), 1) AS cnt
        FROM graph_edges e
        JOIN graph_nodes n ON n.node_id = e.target_id
        WHERE e.source_id = ? AND e.edge_type = 'page_mentions'
          AND n.node_type NOT IN ('wiki_page','wiki_section','generation','game')
        ORDER BY cnt DESC
        LIMIT ?
    """, (page_node, limit)).fetchall()
    return [(r[1], r[0]) for r in rows if r[1]]


def resolve_entity(graph: GraphDB, name: str,
                   preferred_ids: Optional[set] = None) -> Optional[str]:
    """实体名 → node_id。顺序：preferred → 别名精确 → name_zh 精确 → LIKE 模糊"""
    if not name or not name.strip():
        return None
    name = name.strip()

    if preferred_ids:
        rows = graph.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE name_zh = ? AND node_id IN (%s)"
            % ",".join("?" * len(preferred_ids)),
            [name] + list(preferred_ids)
        ).fetchall()
        if rows:
            return rows[0][0]

    rows = graph.conn.execute("""
        SELECT a.node_id FROM graph_entity_aliases a
        JOIN graph_nodes n ON n.node_id = a.node_id
        WHERE a.alias = ?
          AND n.node_type NOT IN ('wiki_page','wiki_section','generation','game')
        ORDER BY a.confidence DESC LIMIT 1
    """, (name,)).fetchall()
    if rows:
        return rows[0][0]

    rows = graph.conn.execute("""
        SELECT node_id FROM graph_nodes
        WHERE name_zh = ?
          AND node_type NOT IN ('wiki_page','wiki_section','generation','game')
        LIMIT 1
    """, (name,)).fetchall()
    if rows:
        return rows[0][0]

    if len(name) >= 3:
        rows = graph.conn.execute("""
            SELECT node_id FROM graph_nodes
            WHERE name_zh LIKE ?
              AND node_type NOT IN ('wiki_page','wiki_section','generation','game')
            LIMIT 1
        """, (f"%{name}%",)).fetchall()
        if rows:
            return rows[0][0]

    return None


def get_or_create_wiki_entity(graph: GraphDB, name: str, source_page_id: int) -> str:
    """匹配不到则创建 wiki_entity 节点（Step 6 再做对齐）"""
    node_id = f"wiki_entity:{name}"
    graph.add_node(
        node_id, "wiki_entity", name_zh=name,
        source="llm_extracted",
        source_page=f"wiki_page:{source_page_id}",
    )
    return node_id


# ══════════════════════════════════════════════════════════════════════
# 关系名校验（开放集，只做格式检查）
# ══════════════════════════════════════════════════════════════════════
_RE_VALID_RELATION = re.compile(r'^[a-z][a-z0-9_]{1,30}$')


def _sanitize_relation(rel: str) -> Optional[str]:
    """校验关系名格式：snake_case、小写开头、2-31 字符。不合规返回 None。"""
    rel = (rel or '').strip()
    if _RE_VALID_RELATION.match(rel):
        return rel
    # 尝试小写转换（LLM 有时输出 CamelCase 或大写）
    lower = rel.lower().replace('-', '_').replace(' ', '_')
    if _RE_VALID_RELATION.match(lower):
        return lower
    return None


# ══════════════════════════════════════════════════════════════════════
# LLM 调用
# ══════════════════════════════════════════════════════════════════════
_JSON_ARRAY_RE = re.compile(r'\[[\s\S]*\]')
_CODE_FENCE_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)


def parse_llm_json(text: str) -> List[dict]:
    """宽松解析 LLM 返回的 JSON 数组，支持 max_tokens 截断。"""
    if not text:
        return []
    t = _CODE_FENCE_RE.sub('', text).strip()

    # 直接 parse
    try:
        data = json.loads(t)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # 从文本中抠出完整的 [...]
    m = _JSON_ARRAY_RE.search(t)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 截断修复：文本以 [ 开头但没有匹配的 ]（max_tokens 截断）
    if t.startswith('['):
        # 尝试补全截断的 JSON：依次尝试 "]", "}]"
        for suffix in [']', '}\n]', '}\n]\n]']:
            try:
                data = json.loads(t + suffix)
                if isinstance(data, list):
                    return data
            except Exception:
                continue
        # 最后手段：逐行扫描，把每个完整的 {...} 提取出来
        objects = []
        depth = 0
        start = -1
        for i, ch in enumerate(t):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        obj = json.loads(t[start:i+1])
                        if isinstance(obj, dict):
                            objects.append(obj)
                    except Exception:
                        pass
                    start = -1
        if objects:
            return objects

    return []


def call_llm(client: OpenAI, model: str, prompt: str,
             max_tokens: int = 4000,
             temperature: float = 0.1) -> Tuple[str, int, int]:
    # 关闭思考模式（MiMo 等推理模型默认开思考，关掉可大幅加速）
    extra = {}
    if any(model.lower().startswith(p) for p in ("mimo", "deepseek-r", "qwq")):
        extra["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        **extra,
    )
    msg = resp.choices[0].message.content or ""
    in_toks = getattr(resp.usage, 'prompt_tokens', 0) if resp.usage else 0
    out_toks = getattr(resp.usage, 'completion_tokens', 0) if resp.usage else 0
    return msg, in_toks, out_toks


def call_llm_with_retry(client: OpenAI, model: str, prompt: str,
                        max_tokens: int = 4000) -> Tuple[List[dict], int, int, Optional[str]]:
    """重试：① 原样 ② 加强指令 ③ 退避+降温"""
    last_err: Optional[str] = None
    total_in = 0
    total_out = 0
    for attempt in range(LLM_MAX_RETRIES):
        try:
            if attempt == 0:
                p, temp = prompt, 0.1
            elif attempt == 1:
                p = prompt + "\n\n【再次强调】只输出 JSON 数组，不要任何 markdown 代码块或解释文本。"
                temp = 0.1
            else:
                p = prompt + "\n\n【再次强调】只输出 JSON 数组，不要任何 markdown 代码块或解释文本。"
                temp = 0.05
                time.sleep(2 ** attempt)

            msg, in_toks, out_toks = call_llm(client, model, p, max_tokens, temp)
            total_in += in_toks
            total_out += out_toks
            relations = parse_llm_json(msg)
            if relations:
                return relations, total_in, total_out, None
            if msg.strip() in ('[]', '[ ]'):
                return [], total_in, total_out, None
            last_err = f"attempt {attempt}: parse empty, raw={msg[:200]}"
        except Exception as e:
            last_err = f"attempt {attempt}: {type(e).__name__}: {e}"
            if attempt < LLM_MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return [], total_in, total_out, last_err


# ══════════════════════════════════════════════════════════════════════
# 入库
# ══════════════════════════════════════════════════════════════════════
def _dedupe_triples(rels: List[dict]) -> List[dict]:
    """同一页按 (source, target, relation) 三元组去重，保留第一个"""
    seen = set()
    out = []
    for r in rels:
        key = (r.get('source', ''), r.get('target', ''), r.get('relation', ''))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def write_relations(graph: GraphDB, page_id: int,
                    relations: List[dict],
                    top_entity_ids: set) -> Dict[str, int]:
    """把 LLM 返回的关系写入 graph_edges。关系名开放，只校验格式。"""
    stats = {'written': 0, 'skipped_invalid': 0, 'new_wiki_entity': 0}
    for r in relations:
        src = (r.get('source') or '').strip()
        tgt = (r.get('target') or '').strip()
        rel_raw = (r.get('relation') or '').strip()
        ctx = (r.get('context') or '').strip()[:200]

        # 校验：实体名非空、关系名格式合规、source ≠ target
        rel = _sanitize_relation(rel_raw)
        if not src or not tgt or not rel or src == tgt:
            stats['skipped_invalid'] += 1
            continue

        src_id = resolve_entity(graph, src, top_entity_ids)
        tgt_id = resolve_entity(graph, tgt, top_entity_ids)

        if not src_id:
            src_id = get_or_create_wiki_entity(graph, src, page_id)
            stats['new_wiki_entity'] += 1
        if not tgt_id:
            tgt_id = get_or_create_wiki_entity(graph, tgt, page_id)
            stats['new_wiki_entity'] += 1
        if src_id == tgt_id:
            stats['skipped_invalid'] += 1
            continue

        graph.upsert_edge(
            src_id, tgt_id, rel,
            context=ctx,
            properties={"source_page_id": page_id},
            source='llm_extracted',
        )
        stats['written'] += 1
    return stats


def log_extraction(graph: GraphDB, page_id: int, status: str,
                   model: str, input_tokens: int, output_tokens: int,
                   error_msg: Optional[str] = None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    graph.conn.execute("""
        INSERT INTO graph_extraction_log
        (page_id, section_id, status, model, input_tokens, output_tokens,
         error_msg, created_at)
        VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
    """, (page_id, status, model, input_tokens, output_tokens,
          (error_msg or '')[:1000], now))


# ══════════════════════════════════════════════════════════════════════
# 单页抽取
# ══════════════════════════════════════════════════════════════════════
class WikiExtractor:
    def __init__(self, graph_db_path: str = GRAPH_DB_PATH,
                 wiki_meta_path: str = WIKI_META_DB,
                 dry_run: bool = False,
                 require_llm: bool = True):
        self.graph_db_path = graph_db_path
        self.wiki_meta_path = wiki_meta_path
        self.dry_run = dry_run
        self.client, self.model = _make_client(require_key=require_llm)
        self.prompt_template = load_prompt()
        self.graph = GraphDB(graph_db_path)
        # 已有关系类型缓存（每批查询一次）
        self._cached_relations = get_existing_relations(self.graph)
        self._cached_relations_count = 0
        # dry-run 输出文件
        self._dry_run_file = None
        if dry_run:
            os.makedirs(os.path.dirname(DRY_RUN_OUTPUT), exist_ok=True)
            self._dry_run_file = open(DRY_RUN_OUTPUT, 'w', encoding='utf-8')

    def build_page_queue(self, retry_errors: bool = False,
                         limit: Optional[int] = None) -> List[Tuple[int, str, str]]:
        """返回 [(page_id, title, file_path), ...]，排除已完成页。"""
        wiki_db = sqlite3.connect(self.wiki_meta_path)
        done_ids = set()
        if not retry_errors:
            for row in self.graph.conn.execute(
                "SELECT DISTINCT page_id FROM graph_extraction_log WHERE status='done'"
            ):
                done_ids.add(row[0])
        else:
            for row in self.graph.conn.execute(
                "SELECT DISTINCT page_id FROM graph_extraction_log WHERE status='done'"
            ):
                done_ids.add(row[0])

        queue: List[Tuple[int, str, str]] = []
        rows = wiki_db.execute(
            "SELECT page_id, title, file_path FROM wiki_pages WHERE status='done'"
        ).fetchall()

        if retry_errors:
            error_ids = {r[0] for r in self.graph.conn.execute(
                "SELECT DISTINCT page_id FROM graph_extraction_log WHERE status='error'"
            )}
            rows = [r for r in rows if r[0] in error_ids]

        for page_id, title, file_path in rows:
            if page_id in done_ids:
                continue
            queue.append((page_id, title, file_path))
            if limit and len(queue) >= limit * 5:
                break

        wiki_db.close()
        return queue

    def _read_wikitext(self, file_path: str) -> Optional[str]:
        if not os.path.isabs(file_path):
            file_path = os.path.join(_PROJECT_ROOT, file_path)
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None

    def extract_page(self, page_id: int, title: str, file_path: str) -> Dict[str, Any]:
        """返回 {status, relations_count, input_tokens, output_tokens, error, ...}"""
        result = {
            'page_id': page_id, 'title': title,
            'status': 'skipped',
            'relations_count': 0, 'input_tokens': 0, 'output_tokens': 0,
            'error': None, 'written': 0, 'new_wiki_entity': 0,
            'skipped_invalid': 0,
        }

        raw = self._read_wikitext(file_path)
        if raw is None:
            result['error'] = 'file_missing'
            return result

        # 跳过：纯列表/导航/消歧义页
        if is_skip_page(raw, title):
            result['status'] = 'skipped_list'
            return result

        cleaned = preprocess_wikitext(raw)
        if not cleaned or len(cleaned) < MIN_CLEANED_LEN:
            result['status'] = 'skipped_empty'
            return result

        # 取该页 top 50 实体
        top_entities = get_top_entities_for_page(self.graph, page_id)
        top_ids = {nid for _, nid in top_entities}

        # 调 LLM（正常 vs fallback 按 section 拆）
        all_relations: List[dict] = []
        total_in = 0
        total_out = 0
        last_err: Optional[str] = None

        # 每 100 页刷新关系类型缓存
        self._cached_relations_count += 1
        if self._cached_relations_count >= 100:
            self._cached_relations = get_existing_relations(self.graph)
            self._cached_relations_count = 0

        if len(cleaned) <= MAX_CONTENT_CHARS:
            prompt = build_prompt(self.prompt_template, cleaned, top_entities,
                                  self._cached_relations)
            rels, in_t, out_t, err = call_llm_with_retry(
                self.client, self.model, prompt, max_tokens=4000)
            all_relations.extend(rels)
            total_in += in_t
            total_out += out_t
            last_err = err
        else:
            sections = split_by_sections(cleaned)
            for sec in sections:
                if len(sec) < MIN_CLEANED_LEN:
                    continue
                if len(sec) > SECTION_MAX_CHARS:
                    sec = sec[:SECTION_MAX_CHARS]
                prompt = build_prompt(self.prompt_template, sec, top_entities,
                                      self._cached_relations)
                rels, in_t, out_t, err = call_llm_with_retry(
                    self.client, self.model, prompt, max_tokens=2000)
                all_relations.extend(rels)
                total_in += in_t
                total_out += out_t
                if err and not last_err:
                    last_err = err
            all_relations = _dedupe_triples(all_relations)

        result['input_tokens'] = total_in
        result['output_tokens'] = total_out
        result['relations_count'] = len(all_relations)
        result['relations'] = all_relations

        if not all_relations and last_err:
            result['status'] = 'error'
            result['error'] = last_err
            return result

        if not self.dry_run:
            stats = write_relations(self.graph, page_id, all_relations, top_ids)
            result['written'] = stats['written']
            result['new_wiki_entity'] = stats['new_wiki_entity']
            result['skipped_invalid'] = stats['skipped_invalid']

        result['status'] = 'done'
        return result

    def run_batch(self, concurrency: int = 1,
                  retry_errors: bool = False,
                  limit: Optional[int] = None,
                  shuffle_queue: bool = False,
                  verbose: bool = True):
        queue = self.build_page_queue(retry_errors=retry_errors, limit=limit)
        if shuffle_queue:
            random.shuffle(queue)
        if limit:
            queue = queue[:limit]
        total = len(queue)

        if verbose:
            mode = 'DRY-RUN' if self.dry_run else 'LIVE'
            print(f"[{mode}] 模型: {self.model}, 待抽取: {total} 页, 并发: {concurrency}")

        if not queue:
            return {'total': 0}

        t0 = time.time()
        stats_agg = {
            'done': 0, 'error': 0, 'skipped_list': 0, 'skipped_empty': 0,
            'skipped_other': 0,
            'written': 0, 'new_wiki_entity': 0, 'relations_count': 0,
            'input_tokens': 0, 'output_tokens': 0,
        }

        if concurrency <= 1:
            for i, (pid, title, fp) in enumerate(queue):
                if verbose:
                    t1 = time.time()
                    print(f"  [{i+1}/{total}] {title[:30]!r} ...", end='', flush=True)
                res = self._process_one(pid, title, fp)
                self._aggregate(stats_agg, res)
                if verbose:
                    dt = time.time() - t1
                    status = res.get('status', '?')
                    n = res.get('relations_count', 0)
                    print(f" {status} ({n} rels, {dt:.1f}s)")
                if not self.dry_run and (i + 1) % 20 == 0:
                    self.graph.commit()
            if not self.dry_run:
                self.graph.commit()
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {
                    pool.submit(self._process_one_threadsafe,
                                pid, title, fp): pid
                    for pid, title, fp in queue
                }
                dc = 0
                for fut in as_completed(futures):
                    dc += 1
                    try:
                        res = fut.result()
                    except Exception as e:
                        res = {'status': 'error', 'error': f'future: {e}',
                               'page_id': futures[fut], 'title': '',
                               'relations_count': 0,
                               'input_tokens': 0, 'output_tokens': 0,
                               'written': 0, 'new_wiki_entity': 0,
                               'skipped_invalid': 0}
                    self._aggregate(stats_agg, res)
                    if verbose and dc % 10 == 0:
                        self._print_progress(dc, total, t0, stats_agg)

        elapsed = time.time() - t0
        if verbose:
            print("\n" + "=" * 60)
            print(f"完成 {total} 页，耗时 {elapsed:.1f}s")
            for k, v in stats_agg.items():
                print(f"  {k}: {v}")
            if self.dry_run:
                print(f"  结果已写入: {DRY_RUN_OUTPUT}")
        return stats_agg

    def _process_one(self, pid, title, fp):
        try:
            res = self.extract_page(pid, title, fp)
        except Exception as e:
            res = {
                'page_id': pid, 'title': title, 'status': 'error',
                'relations_count': 0,
                'input_tokens': 0, 'output_tokens': 0,
                'error': f'{type(e).__name__}: {e}',
                'written': 0, 'new_wiki_entity': 0, 'skipped_invalid': 0,
            }
        # dry-run: 写 JSONL
        if self.dry_run and self._dry_run_file:
            self._write_dry_run(res)
        if not self.dry_run:
            log_extraction(
                self.graph, pid,
                status=res['status'] if res['status'] in ('done', 'error') else 'skipped',
                model=self.model,
                input_tokens=res['input_tokens'],
                output_tokens=res['output_tokens'],
                error_msg=res.get('error'),
            )
        return res

    def _process_one_threadsafe(self, pid, title, fp):
        local_graph = GraphDB(self.graph_db_path)
        try:
            orig_graph = self.graph
            self.graph = local_graph
            try:
                res = self.extract_page(pid, title, fp)
            finally:
                self.graph = orig_graph

            if not self.dry_run:
                log_extraction(
                    local_graph, pid,
                    status=res['status'] if res['status'] in ('done', 'error') else 'skipped',
                    model=self.model,
                    input_tokens=res['input_tokens'],
                    output_tokens=res['output_tokens'],
                    error_msg=res.get('error'),
                )
                local_graph.commit()
            else:
                self._write_dry_run(res)
            return res
        except Exception as e:
            return {
                'page_id': pid, 'title': title, 'status': 'error',
                'relations_count': 0,
                'input_tokens': 0, 'output_tokens': 0,
                'error': f'{type(e).__name__}: {e}',
                'written': 0, 'new_wiki_entity': 0, 'skipped_invalid': 0,
            }
        finally:
            local_graph.close()

    @staticmethod
    def _aggregate(agg: Dict[str, int], res: Dict[str, Any]):
        status = res.get('status', 'skipped_other')
        if status in agg:
            agg[status] += 1
        else:
            agg['skipped_other'] += 1
        for k in ('written', 'new_wiki_entity', 'relations_count',
                  'input_tokens', 'output_tokens'):
            agg[k] = agg.get(k, 0) + res.get(k, 0)

    @staticmethod
    def _print_progress(done, total, t0, stats):
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"  [{done}/{total}] done={stats['done']} err={stats['error']} "
              f"skip={stats['skipped_list'] + stats['skipped_empty']} "
              f"edges={stats['written']} rate={rate:.1f}/s eta={eta:.0f}s")

    def close(self):
        self.graph.close()
        if self._dry_run_file:
            self._dry_run_file.close()

    def _write_dry_run(self, res: Dict[str, Any]):
        """dry-run 模式：把单页结果写入 JSONL 文件"""
        row = {
            'page_id': res['page_id'],
            'title': res['title'],
            'status': res['status'],
            'relations_count': res.get('relations_count', 0),
            'relations': res.get('relations', []),
        }
        if res.get('error'):
            row['error'] = res['error']
        self._dry_run_file.write(json.dumps(row, ensure_ascii=False) + '\n')
        self._dry_run_file.flush()


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None,
                    help='最多处理 N 页')
    ap.add_argument('--concurrency', type=int, default=1,
                    help='并发数，默认 1（串行）')
    ap.add_argument('--dry-run', action='store_true',
                    help='只调 LLM 不写库')
    ap.add_argument('--retry-errors', action='store_true',
                    help='只重试 status=error 的页面')
    ap.add_argument('--shuffle', action='store_true',
                    help='打乱队列顺序（推荐第一轮试跑使用）')
    args = ap.parse_args()

    extractor = WikiExtractor(dry_run=args.dry_run)
    try:
        extractor.run_batch(
            concurrency=args.concurrency,
            retry_errors=args.retry_errors,
            limit=args.limit,
            shuffle_queue=args.shuffle,
        )
    finally:
        extractor.close()


if __name__ == "__main__":
    main()
