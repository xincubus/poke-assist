"""
Wiki 工具 Mixin：Wiki 页面查找、读取、模板展开、搜索
"""
import os
import sqlite3
from typing import Dict, Any, Optional, List

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WIKI_META_DB = os.path.join(_BASE_DIR, "pokemon_data", "wiki", "wiki_meta.db")
WIKITEXT_CACHE_DIR = os.path.join(_BASE_DIR, "pokemon_data", "wiki", "wikitext_cache")


class WikiToolsMixin:
    """Wiki 页面查找、读取、模板展开、搜索"""

    def _resolve_wiki_page(self, title: str) -> Optional[Dict[str, str]]:
        """查找 wiki 页面，返回 {title, file_path} 或 None。
        顺序：精确匹配 → redirects → LIKE 模糊匹配（返回候选）。"""
        conn = sqlite3.connect(WIKI_META_DB)
        conn.row_factory = sqlite3.Row
        try:
            # 1. 精确匹配
            row = conn.execute(
                "SELECT title, file_path FROM wiki_pages WHERE title = ? AND status = 'done'",
                (title,)
            ).fetchone()
            if row and row["file_path"]:
                return {"title": row["title"], "file_path": row["file_path"]}

            # 2. 通过 redirects 找目标
            row = conn.execute("""
                SELECT r.target_title, wp.file_path
                FROM wiki_redirects r
                JOIN wiki_pages wp ON wp.page_id = r.target_page_id
                WHERE r.source_title = ? AND wp.status = 'done'
            """, (title,)).fetchone()
            if row and row["file_path"]:
                return {"title": row["target_title"], "file_path": row["file_path"]}

            # 3. LIKE 模糊匹配 — 返回候选列表
            candidates = conn.execute(
                "SELECT title FROM wiki_pages WHERE title LIKE ? AND status = 'done' AND namespace = 0 LIMIT 10",
                (f"%{title}%",)
            ).fetchall()
            if candidates:
                titles = [c["title"] for c in candidates]
                return {"candidates": titles}
            return None
        finally:
            conn.close()

    def _read_and_expand_wiki(self, file_path: str) -> str:
        """读取 wikitext 文件并展开模板。"""
        path = file_path
        if not os.path.isabs(path):
            path = os.path.join(WIKITEXT_CACHE_DIR, os.path.basename(path))
        with open(path, "r", encoding="utf-8") as f:
            wikitext = f.read()
        import sys
        wiki_dir = os.path.join(_BASE_DIR, "pokemon_data", "wiki")
        if wiki_dir not in sys.path:
            sys.path.insert(0, wiki_dir)
        from template_expander import expand
        return expand(wikitext)

    def _extract_and_expand_wiki(self, rows: List[Dict[str, Any]]) -> str:
        """从查询结果中提取 wiki_file_path，读取并展开 wiki 全文。
        多条结果时只取第一条的 wiki（精确查询通常只有 1 条命中）。"""
        for row in rows:
            file_path = row.get("wiki_file_path")
            if file_path:
                try:
                    return self._read_and_expand_wiki(file_path)
                except Exception as e:
                    print(f"读取 wiki 失败 ({file_path}): {e}")
                    return ""
        return ""

    def _fetch_wiki_page(self, title: str) -> str:
        """fetch_wiki_page 工具：查找并返回 wiki 页面全文（模板已展开）。"""
        if not title:
            return "请提供页面标题"

        try:
            result = self._resolve_wiki_page(title)
            if result is None:
                return f"未找到与「{title}」相关的 wiki 页面"

            # 模糊匹配返回候选
            if "candidates" in result:
                candidates = result["candidates"]
                return f"未精确匹配「{title}」，以下为候选页面，请选择正确的标题重试：\n" + "\n".join(f"  - {t}" for t in candidates)

            page_title = result["title"]
            expanded = self._read_and_expand_wiki(result["file_path"])

            if not expanded.strip():
                return f"页面「{page_title}」内容为空"

            return f"【{page_title}】\n\n{expanded}"
        except Exception as e:
            print(f"fetch_wiki_page 失败: {e}")
            return f"获取 wiki 页面失败: {str(e)}"

    def _search_wiki(self, keywords: List[str]) -> str:
        """search_wiki 工具：FTS5 搜索 wiki 页面标题和摘要 + redirect 反查，返回 top 10。"""
        if not keywords:
            return "请提供搜索关键词"

        try:
            conn = sqlite3.connect(WIKI_META_DB)
            conn.row_factory = sqlite3.Row

            # ① FTS5 搜索：任一关键词匹配标题/摘要
            fts_query = " OR ".join(f'"{kw}"' for kw in keywords)
            rows = conn.execute("""
                SELECT wp.page_id, wp.title, wp.summary
                FROM wiki_pages_fts fts
                JOIN wiki_pages wp ON wp.page_id = fts.rowid
                WHERE wiki_pages_fts MATCH ?
                LIMIT 10
            """, (fts_query,)).fetchall()

            seen_ids = {row["page_id"] for row in rows}
            results = [(row["title"], row["summary"] or "") for row in rows]

            # ② redirect 反查：用关键词模糊匹配 redirect 源标题，找到目标页面
            if len(results) < 10:
                remaining = 10 - len(results)
                like_conditions = " OR ".join("source_title LIKE ?" for _ in keywords)
                like_params = [f"%{kw}%" for kw in keywords]
                redirect_rows = conn.execute(f"""
                    SELECT DISTINCT r.target_page_id, r.target_title
                    FROM wiki_redirects r
                    WHERE ({like_conditions})
                    AND r.target_page_id NOT IN ({','.join('?' for _ in seen_ids)})
                    LIMIT ?
                """, like_params + list(seen_ids) + [remaining * 2]).fetchall()

                # 查目标页面的 summary
                for rrow in redirect_rows:
                    if len(results) >= remaining:
                        break
                    pid = rrow["target_page_id"]
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    page = conn.execute(
                        "SELECT title, summary FROM wiki_pages WHERE page_id = ?", (pid,)
                    ).fetchone()
                    if page:
                        results.append((page["title"], page["summary"] or ""))

            conn.close()

            if not results:
                return f"wiki 搜索未找到与 {', '.join(keywords)} 相关的页面"

            lines = []
            for title, summary in results:
                lines.append(f"- **{title}**：{summary}")

            return f"搜索「{' '.join(keywords)}」结果（{len(results)} 条）：\n\n" + "\n".join(lines)
        except Exception as e:
            print(f"search_wiki 失败: {e}")
            return f"wiki 搜索失败: {str(e)}"
