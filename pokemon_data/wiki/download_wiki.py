"""
52poke Wiki 全量 wikitext 下载脚本

功能：
1. 通过 MediaWiki API 枚举所有内容页（namespace=0）
2. 下载每页的 wikitext 源码
3. 用 SQLite 记录元数据（页面标题、page_id、wiki更新时间、本地下载时间）
4. 支持断点续传：已下载且未更新的页面自动跳过
5. 支持增量更新：只下载 wiki 上有更新的页面

用法：
    python download_wiki.py                # 下载/更新所有页面
    python download_wiki.py --limit 100    # 只处理前100页（测试用）
    python download_wiki.py --stats        # 查看下载统计
    python download_wiki.py --refresh-list # 只刷新页面列表，不下载内容
"""

import io
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Windows 终端 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 日志配置：同时输出到终端和文件
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "download.log")

logger = logging.getLogger("wiki_download")
logger.setLevel(logging.DEBUG)

# 文件 handler：详细日志（每页都记录）
fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(fh)

# 终端 handler：只显示 INFO 及以上（100 页汇总）
sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(sh)


# ============================================================
# 配置
# ============================================================
WIKI_API = "https://wiki.52poke.com/api.php"
WIKITEXT_DIR = os.path.join(SCRIPT_DIR, "wikitext_cache")
DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")
PAGES_JSON = os.path.join(SCRIPT_DIR, "all_pages.json")

REQUEST_DELAY = 0.5  # 每次请求间隔（秒），避免被封
USER_AGENT = "PokemonGraphRAG/1.0 (contact: pokemon-bot@example.com)"
REQUEST_TIMEOUT = 20
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "download_progress.txt")


# Ctrl+C 优雅退出
def _sigint_handler(sig, frame):
    print("\n\n收到 Ctrl+C，正在安全退出...（已下载的页面会自动续传）")
    sys.exit(0)


signal.signal(signal.SIGINT, _sigint_handler)


# ============================================================
# 时间格式化
# ============================================================
def format_duration(seconds):
    """秒数格式化为可读时间"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds/60:.1f}分钟"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}小时{m}分钟"


# ============================================================
# 数据库初始化
# ============================================================
def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wiki_pages (
            page_id     INTEGER PRIMARY KEY,
            title       TEXT NOT NULL UNIQUE,
            namespace   INTEGER DEFAULT 0,
            wiki_updated TEXT,
            local_downloaded TEXT,
            file_path   TEXT,
            char_count  INTEGER,
            status      TEXT DEFAULT 'pending'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wp_title ON wiki_pages(title)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wp_status ON wiki_pages(status)")
    # 重定向别名表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wiki_redirects (
            source_title TEXT NOT NULL,
            target_page_id INTEGER NOT NULL,
            target_title TEXT,
            PRIMARY KEY (source_title, target_page_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS download_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_time    TEXT,
            pages_total INTEGER,
            pages_new   INTEGER,
            pages_updated INTEGER,
            pages_skipped INTEGER,
            pages_error INTEGER,
            duration_sec REAL
        )
    """)
    conn.commit()


# ============================================================
# API 请求封装
# ============================================================
def api_request(params, retries=3):
    """发送 MediaWiki API 请求，返回 JSON"""
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return None


# ============================================================
# 步骤1：枚举所有页面
# ============================================================
def refresh_page_list(conn, limit=None, namespace=0, prefix=None, json_path=None):
    """从 wiki 枚举指定 namespace 的页面，写入数据库。

    Args:
        namespace: MediaWiki 命名空间 ID（0=内容页、10=Template 等）
        prefix: 仅枚举前缀匹配的页面（不含 namespace 前缀，如 "招式效果/"）
        json_path: 标题列表输出路径；默认按 namespace 自动命名
    """
    scope = f"ns={namespace}" + (f", prefix={prefix!r}" if prefix else "")
    logger.info(f"[1/2] 枚举页面列表（{scope}）...")
    os.makedirs(WIKITEXT_DIR, exist_ok=True)

    all_pages = []
    apcontinue = None
    batch = 0

    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "aplimit": "500",
            "apnamespace": str(namespace),
            "format": "json",
        }
        if prefix:
            params["apprefix"] = prefix
        if apcontinue:
            params["apcontinue"] = apcontinue

        data = api_request(params)
        pages = data.get("query", {}).get("allpages", [])
        all_pages.extend(pages)
        batch += 1

        if batch % 10 == 0:
            logger.info(f"  已枚举 {len(all_pages)} 页...")

        if limit and len(all_pages) >= limit:
            all_pages = all_pages[:limit]
            break

        if "continue" in data:
            apcontinue = data["continue"]["apcontinue"]
            time.sleep(0.2)
        else:
            break

    logger.info(f"  枚举完成，共 {len(all_pages)} 页")

    # 写入数据库（allpages 不返回时间戳，时间戳在下载时从 revisions 获取）
    new_count = 0
    for p in all_pages:
        pid = p["pageid"]
        title = p["title"]
        cur = conn.execute("SELECT page_id FROM wiki_pages WHERE title = ?", (title,)).fetchone()
        if cur is None:
            conn.execute(
                "INSERT OR IGNORE INTO wiki_pages (page_id, title, namespace, status) VALUES (?, ?, ?, 'pending')",
                (pid, title, namespace),
            )
            new_count += 1
    conn.commit()

    # 保存标题列表到 JSON（按 namespace 区分，避免覆盖内容页列表）
    if json_path is None:
        json_path = PAGES_JSON if namespace == 0 else os.path.join(
            SCRIPT_DIR, f"all_pages_ns{namespace}.json"
        )
    titles = [p["title"] for p in all_pages]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)

    logger.info(f"  新增 {new_count} 页，已保存到 {json_path}")
    return len(all_pages)


# ============================================================
# 步骤2：下载 wikitext
# ============================================================
def download_wikitexts(conn, limit=None, force=False, namespace=None):
    """下载所有 pending 状态的页面。

    Args:
        namespace: 若指定（如 10 表示 Template），只下载该 namespace 的页面；None 表示不筛选
    """
    cols = "page_id, title, namespace, local_downloaded"
    where_ns = ""
    if namespace is not None:
        where_ns = f" AND namespace = {int(namespace)}"

    if force:
        query = f"SELECT page_id, title, namespace, NULL as local_downloaded FROM wiki_pages WHERE 1=1{where_ns}"
    else:
        query = f"SELECT {cols} FROM wiki_pages WHERE status = 'pending'{where_ns}"
    if limit:
        query += f" LIMIT {limit}"
    rows = conn.execute(query).fetchall()

    if not rows:
        logger.info("[2/2] 没有需要下载的页面")
        return 0, 0, 0

    total = len(rows)
    scope = f"ns={namespace}" if namespace is not None else "all namespaces"
    logger.info(f"[2/2] 开始下载 {total} 页（{scope}）...")
    logger.info(f"  日志文件: {LOG_PATH}")
    os.makedirs(WIKITEXT_DIR, exist_ok=True)

    new_count = 0
    updated_count = 0
    error_count = 0
    skipped_count = 0
    start_time = time.time()

    # 预加载已有文件列表（page_id → 文件名），用于快速跳过
    existing_files_map = {}
    if os.path.exists(WIKITEXT_DIR):
        for fname in os.listdir(WIKITEXT_DIR):
            if fname.endswith('.wiki') and '_' in fname:
                pid = fname.split('_')[0]
                existing_files_map[pid] = fname

    BATCH_SIZE = 5  # 每次 API 请求查 5 页

    # 先跳过已有文件的页面，收集需要下载的页面
    to_download = []
    for page_id, title, ns, local_downloaded in rows:
        if str(page_id) in existing_files_map and not local_downloaded:
            file_path = os.path.join(WIKITEXT_DIR, existing_files_map[str(page_id)])
            char_count = os.path.getsize(file_path)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute("""
                UPDATE wiki_pages SET status = 'done', local_downloaded = ?,
                file_path = ?, char_count = ? WHERE page_id = ?
            """, (now, file_path, char_count, page_id))
            skipped_count += 1
        else:
            to_download.append((page_id, title, ns, local_downloaded))
    conn.commit()
    initial_skipped = skipped_count
    if initial_skipped:
        logger.info(f"  跳过已有文件: {initial_skipped} 页，待下载: {len(to_download)} 页")

    # 批量下载
    total_to_dl = len(to_download)
    for batch_start in range(0, total_to_dl, BATCH_SIZE):
        batch = to_download[batch_start:batch_start + BATCH_SIZE]
        batch_ids = [str(pid) for pid, _, _, _ in batch]
        batch_map = {pid: (pid, title, ns, ld) for pid, title, ns, ld in batch}

        try:
            params = {
                "action": "query",
                "pageids": "|".join(batch_ids),
                "prop": "revisions",
                "rvprop": "content|timestamp",
                "rvslots": "main",
                "format": "json",
            }

            data = api_request(params)
            pages = data.get("query", {}).get("pages", {})

            for pid_str, pdata in pages.items():
                orig_pid = int(pid_str)
                orig_info = batch_map.get(orig_pid)
                if not orig_info:
                    continue
                _, title, ns, local_downloaded = orig_info

                if pid_str == "-1":
                    error_count += 1
                    conn.execute("UPDATE wiki_pages SET status = 'error' WHERE page_id = ?", (orig_pid,))
                    logger.debug(f"[NOT FOUND] {title}")
                    continue

                revisions = pdata.get("revisions", [])
                if not revisions:
                    continue

                rev_ts = revisions[0].get("timestamp", "")
                wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")

                # 判断是否为重定向页
                is_redirect = wikitext.startswith("#REDIRECT") or wikitext.startswith("#重定向")
                if is_redirect:
                    m = re.search(r'\[\[(.+?)(?:\|.*?)?\]\]', wikitext)
                    target_title = m.group(1).strip() if m else ""
                    target_page_id = None
                    if target_title:
                        row = conn.execute(
                            "SELECT page_id FROM wiki_pages WHERE title = ?", (target_title,)
                        ).fetchone()
                        if row:
                            target_page_id = row[0]
                    conn.execute("""
                        INSERT OR IGNORE INTO wiki_redirects
                        (source_title, target_page_id, target_title)
                        VALUES (?, ?, ?)
                    """, (title, target_page_id, target_title))
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    conn.execute("""
                        UPDATE wiki_pages SET status = 'redirect', wiki_updated = ?,
                        local_downloaded = ?, char_count = 0 WHERE page_id = ?
                    """, (rev_ts, now, orig_pid))
                    skipped_count += 1
                    logger.debug(f"[REDIRECT] {title} -> {target_title}")
                    continue

                # 非重定向：比较时间戳
                if local_downloaded and rev_ts and local_downloaded >= rev_ts:
                    conn.execute("UPDATE wiki_pages SET status = 'done' WHERE page_id = ?", (orig_pid,))
                    skipped_count += 1
                    continue

                # 保存文件
                actual_pid = pdata.get("pageid", orig_pid)
                actual_title = pdata.get("title", title)
                actual_ns = pdata.get("ns", ns if ns is not None else 0)
                safe_name = actual_title.replace("/", "_").replace(":", "_").replace("?", "？").replace("\\", "_")
                file_path = os.path.join(WIKITEXT_DIR, f"{actual_pid}_{safe_name}.wiki")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(wikitext)

                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if actual_pid != orig_pid:
                    conn.execute("DELETE FROM wiki_pages WHERE page_id = ?", (orig_pid,))
                    conn.execute("""
                        INSERT OR REPLACE INTO wiki_pages
                        (page_id, title, namespace, wiki_updated, local_downloaded, file_path, char_count, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'done')
                    """, (actual_pid, actual_title, actual_ns, rev_ts, now, file_path, len(wikitext)))
                else:
                    conn.execute("""
                        UPDATE wiki_pages SET title = ?, namespace = ?, wiki_updated = ?,
                        local_downloaded = ?, file_path = ?, char_count = ?, status = 'done'
                        WHERE page_id = ?
                    """, (actual_title, actual_ns, rev_ts, now, file_path, len(wikitext), orig_pid))

                new_count += 1
                logger.debug(f"[NEW] {actual_title} ({len(wikitext)} chars)")

        except Exception as e:
            for pid, _, _, _ in batch:
                error_count += 1
                conn.execute("UPDATE wiki_pages SET status = 'error' WHERE page_id = ?", (pid,))
            logger.debug(f"[BATCH ERROR] batch {batch_ids}: {e}")

        # 进度 + 提交
        try:
            done_count = batch_start + len(batch) + initial_skipped
            if (batch_start + len(batch)) % (BATCH_SIZE * 20) == 0 or batch_start + len(batch) >= total_to_dl:
                elapsed = time.time() - start_time
                processed = batch_start + len(batch)
                speed = processed / max(elapsed, 1)
                eta = (total_to_dl - processed) / max(speed, 0.01)
                logger.info(
                    f"[{done_count}/{total}] {done_count*100//total}% | "
                    f"{speed:.1f}/s ETA {format_duration(eta)} | "
                    f"新:{new_count} 更:{updated_count} 跳:{skipped_count} 错:{error_count}"
                )
                with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
                    pf.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    pf.write(f"done={done_count}/{total}\n")
                    pf.write(f"new={new_count} updated={updated_count} skipped={skipped_count} error={error_count}\n")
                    pf.write(f"speed={speed:.1f}/s elapsed={format_duration(elapsed)}\n")

            conn.commit()
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.debug(f"[FATAL] 循环异常: {e}")
            logger.info(f"\n!!! 脚本异常退出: {e}")
            raise

    # 记录本次运行日志
    elapsed = time.time() - start_time
    conn.execute("""
        INSERT INTO download_log (run_time, pages_total, pages_new, pages_updated, pages_skipped, pages_error, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total, new_count, updated_count, skipped_count, error_count, elapsed))
    conn.commit()

    logger.info(f"  下载完成，耗时 {format_duration(elapsed)}")
    return new_count, updated_count, error_count


# ============================================================
# 统计
# ============================================================
def show_stats(conn):
    """显示下载统计"""
    total = conn.execute("SELECT count(*) FROM wiki_pages").fetchone()[0]
    done = conn.execute("SELECT count(*) FROM wiki_pages WHERE status = 'done'").fetchone()[0]
    pending = conn.execute("SELECT count(*) FROM wiki_pages WHERE status = 'pending'").fetchone()[0]
    redirect = conn.execute("SELECT count(*) FROM wiki_pages WHERE status = 'redirect'").fetchone()[0]
    error = conn.execute("SELECT count(*) FROM wiki_pages WHERE status = 'error'").fetchone()[0]
    redirect_count = conn.execute("SELECT count(*) FROM wiki_redirects").fetchone()[0]

    logger.info("=== 52poke Wiki 下载统计 ===")
    logger.info(f"  总页面数:     {total}")
    logger.info(f"  已下载:       {done}")
    logger.info(f"  重定向页:     {redirect}（指向 {redirect_count} 条重定向关系）")
    logger.info(f"  待下载:       {pending}")
    logger.info(f"  错误:         {error}")

    # 按 namespace 拆分
    ns_rows = conn.execute("""
        SELECT namespace, COUNT(*),
               SUM(CASE WHEN status='done' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END)
        FROM wiki_pages GROUP BY namespace ORDER BY namespace
    """).fetchall()
    if len(ns_rows) > 1:
        logger.info("  按 namespace 拆分:")
        ns_name = {0: "内容页", 10: "Template"}
        for ns, n_total, n_done, n_pending in ns_rows:
            label = ns_name.get(ns, f"ns={ns}")
            logger.info(f"    {label:<10} 总:{n_total}  已下:{n_done}  待下:{n_pending}")

    # 最近一次运行日志
    last = conn.execute(
        "SELECT * FROM download_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if last:
        logger.info(f"\n  最近一次运行: {last[1]}")
        logger.info(f"    总计:{last[2]} 新增:{last[3]} 更新:{last[4]} 跳过:{last[5]} 错误:{last[6]} 耗时:{format_duration(last[7])}")


# ============================================================
# 主入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="52poke Wiki wikitext 下载脚本")
    parser.add_argument("--limit", type=int, help="最多处理N页（测试用）")
    parser.add_argument("--stats", action="store_true", help="只显示统计")
    parser.add_argument("--refresh-list", action="store_true", help="只刷新页面列表，不下载")
    parser.add_argument("--force", action="store_true", help="强制重新下载所有页面（忽略时间戳）")
    parser.add_argument("--auto-restart", action="store_true", help="分批自动重启（规避系统超时）")
    parser.add_argument("--batch-size", type=int, default=1000, help="每批处理页数（默认1000，配合--auto-restart）")
    parser.add_argument("--namespace", type=int, default=0,
                        help="MediaWiki 命名空间 ID（0=内容页、10=Template，默认 0）")
    parser.add_argument("--prefix", help="仅枚举前缀匹配的页面标题（配合 --namespace 使用）")
    parser.add_argument("--skip-enumerate", action="store_true",
                        help="跳过枚举步骤，直接下载已在数据库中 status=pending 的页面")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if args.stats:
        show_stats(conn)
        conn.close()
        return

    # 步骤1：刷新页面列表
    if not args.skip_enumerate:
        refresh_page_list(conn, limit=args.limit, namespace=args.namespace, prefix=args.prefix)

    if args.refresh_list:
        logger.info("页面列表已刷新，未下载内容")
        conn.close()
        return

    # 步骤2：下载 wikitext
    if args.auto_restart:
        # 分批模式：每批 batch_size 页，自动循环直到全部完成
        batch = 0
        while True:
            batch += 1
            pending = conn.execute(
                "SELECT count(*) FROM wiki_pages WHERE status = 'pending' AND namespace = ?",
                (args.namespace,),
            ).fetchone()[0]
            if pending == 0:
                logger.info(f"\n所有页面下载完成！共 {batch-1} 批")
                break
            logger.info(f"\n===== 第 {batch} 批（剩余 {pending} 页，每批 {args.batch_size} 页）=====")
            new, updated, errors = download_wikitexts(
                conn, limit=args.batch_size, force=args.force, namespace=args.namespace
            )
            if new == 0 and updated == 0 and errors == 0:
                logger.info("本批无新页面需要下载，结束")
                break
            # 重新打开连接，避免长时间连接积累问题
            conn.close()
            conn = sqlite3.connect(DB_PATH)
            logger.info(f"  第 {batch} 批完成：新增 {new} 更新 {updated} 错误 {errors}")
    else:
        new, updated, errors = download_wikitexts(
            conn, limit=args.limit, force=args.force, namespace=args.namespace
        )

    # 显示统计
    logger.info("")
    show_stats(conn)
    conn.close()


if __name__ == "__main__":
    main()
