"""批量运行 moves 同步检测（mimo-v2.5 thinking）

用法：
  python run_sync_moves.py --since 2026-04-01
  python run_sync_moves.py --file pokemon_data/wiki/wikitext_cache/109235_First Impression.wiki
"""
import sys, os, json, argparse, sqlite3
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', 'api', '.env'))

from sync_detector import load_wiki_index, detect_stale_entries, detect_new_entries, llm_extract_changes, llm_extract_entity_info, generate_summary_md, WIKI_META_DB, POKEMON_DB

def find_stale_by_file(file_path):
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

    conn = sqlite3.connect(POKEMON_DB)
    conn.row_factory = sqlite3.Row
    # 招式表：通过 name_zh 或 wiki_file_path 匹配
    db_row = conn.execute(
        "SELECT * FROM moves WHERE name_zh = ? OR name_zh = ?",
        (wiki_title, wiki_title.replace('（招式）', ''))
    ).fetchone()
    if not db_row:
        # 尝试用 wiki_file_path 匹配
        db_row = conn.execute(
            "SELECT * FROM moves WHERE wiki_file_path LIKE ?", (f'%{basename}',)
        ).fetchone()
    if not db_row:
        # 从 wiki 页面提取 name 字段匹配
        import re
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()[:2000]
            m = re.search(r'\|name=([^|\n]+)', text)
            if m:
                name = m.group(1).strip()
                db_row = conn.execute("SELECT * FROM moves WHERE name_zh = ?", (name,)).fetchone()
    if not db_row:
        conn.close()
        return None

    columns = [c[1] for c in conn.execute("PRAGMA table_info(moves)")]
    entry = {col: db_row[col] for col in columns}
    conn.close()
    return {
        "entity_type": "moves",
        "name_zh": entry.get("name_zh", ""),
        "name_en": entry.get("name_en", ""),
        "wiki_title": wiki_title,
        "wiki_updated": wiki_updated,
        "wiki_url": f"https://wiki.52poke.com/wiki/{wiki_title}",
        "summary": "",
        "db_entry": entry,
        "file_path": file_path,
    }

def main():
    parser = argparse.ArgumentParser(description="运行 moves 同步检测")
    parser.add_argument('--since', default='2026-05-01', help='只检查此日期后更新的页面 (YYYY-MM-DD)')
    parser.add_argument('--until', default=None, help='只检查此日期前更新的页面 (YYYY-MM-DD，默认不限)')
    parser.add_argument('--file', help='只分析指定的 wikitext 文件路径（跳过全量扫描）')
    parser.add_argument('--new-only', action='store_true', help='只检测新增条目，跳过过期条目分析')
    args = parser.parse_args()

    # 单文件模式：短路，不加载 wiki 索引
    if args.file:
        file_path = args.file
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.path.dirname(__file__), '..', '..', file_path)
            file_path = os.path.normpath(file_path)
        print(f'Single file mode: {os.path.basename(file_path)}', flush=True)
        stale = find_stale_by_file(file_path)
        if not stale:
            print(f'  未找到匹配的条目', flush=True)
            return
        print(f'  匹配: {stale["name_zh"]} (wiki: {stale["wiki_title"]})', flush=True)
        print('LLM analysis...', flush=True)
        suggestions = llm_extract_changes([stale], 'moves', POKEMON_DB)
        for s in suggestions:
            for c in s.get('changes', []):
                print(f'  {s["name_zh"]}: {c["field"]}: {c["current_value"]} -> {c["new_value"]}', flush=True)
        if not suggestions:
            print('  无变化', flush=True)

        report = {
            'generated_at': datetime.now().isoformat(),
            'entity_type': 'moves',
            'since': args.since,
            'model': os.getenv('LLM_MODEL_SYNC', 'mimo-v2.5'),
            'total_stale': 1,
            'total_changes': len(suggestions),
            'changes': suggestions,
        }
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = os.path.join(os.path.dirname(__file__), 'sync_reports', f'sync_report_moves_{timestamp}.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        md_path = generate_summary_md(report, out)
        print(f'\nSaved to {out}', flush=True)
        print(f'Summary: {md_path}', flush=True)
        return

    # 批量模式
    print('Loading wiki index...', flush=True)
    pages, redirects, reverse_redirects = load_wiki_index(WIKI_META_DB)
    print(f'  {len(pages)} pages loaded', flush=True)

    # Phase 1: 新条目检测
    print(f'Detecting new moves...', flush=True)
    new_entries, renamed_entries = detect_new_entries('moves', pages, redirects, reverse_redirects, POKEMON_DB)
    print(f'  {len(new_entries)} new entries, {len(renamed_entries)} renamed', flush=True)

    if args.since:
        new_entries = [e for e in new_entries if pages.get(e.get('wiki_title', ''), {}).get('wiki_updated', '9999') >= args.since]
    if args.until:
        new_entries = [e for e in new_entries if pages.get(e.get('wiki_title', ''), {}).get('wiki_updated', '0000') <= args.until]
    print(f'  {len(new_entries)} new entries after date filter', flush=True)

    new_items_info = []
    if new_entries:
        print(f'LLM extracting new moves info...', flush=True)
        for i, entry in enumerate(new_entries):
            wiki_title = entry.get('wiki_title', '')
            print(f'  [{i+1}/{len(new_entries)}] {entry["name_zh"]}...', flush=True)
            info = llm_extract_entity_info(wiki_title, 'moves')
            if info:
                new_items_info.append({
                    'entity_type': 'moves',
                    'name_zh': entry['name_zh'],
                    'wiki_title': wiki_title,
                    'wiki_url': entry.get('wiki_url', ''),
                    'change_type': 'new',
                    'wiki_info': info,
                })

    # Phase 2: 过期条目检测（--new-only 时跳过）
    stale = []
    suggestions = []
    if not args.new_only:
        print(f'Detecting stale moves (since {args.since}, until {args.until or "now"})...', flush=True)
        stale = detect_stale_entries('moves', pages, redirects, POKEMON_DB, args.since, args.until)
        print(f'  {len(stale)} stale entries', flush=True)

        print('LLM analysis...', flush=True)
        suggestions = llm_extract_changes(stale, 'moves', POKEMON_DB)
    else:
        print('Skipping stale detection (--new-only)', flush=True)

    report = {
        'generated_at': datetime.now().isoformat(),
        'entity_type': 'moves',
        'since': args.since,
        'until': args.until,
        'model': os.getenv('LLM_MODEL_SYNC', 'mimo-v2.5'),
        'total_stale': len(stale),
        'total_changes': len(suggestions),
        'total_new': len(new_items_info),
        'total_renamed': len(renamed_entries),
        'changes': suggestions,
        'new_entries': new_items_info,
        'renamed_entries': renamed_entries,
    }
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = os.path.join(os.path.dirname(__file__), 'sync_reports', f'sync_report_moves_{timestamp}.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    md_path = generate_summary_md(report, out)

    print(f'\n=== Results ===', flush=True)
    print(f'Stale: {len(stale)}, Changes: {len(suggestions)}', flush=True)
    print(f'New: {len(new_items_info)}, Renamed: {len(renamed_entries)}', flush=True)
    if new_items_info:
        print(f'\nNew entries:', flush=True)
        for e in new_items_info:
            info = e.get('wiki_info', {})
            print(f'  {e["name_zh"]} ({info.get("name_en", "")}) - {e["wiki_url"]}', flush=True)
    if suggestions:
        print(f'\nChanges:', flush=True)
        for s in suggestions:
            for c in s.get('changes', []):
                print(f'  {s["name_zh"]}: {c["field"]}: {c["current_value"]} -> {c["new_value"]}', flush=True)
    print(f'\nSaved to {out}', flush=True)
    print(f'Summary: {md_path}', flush=True)

if __name__ == '__main__':
    main()
