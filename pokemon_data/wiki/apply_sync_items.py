"""Apply items sync changes from report to pokemonData.db

用法：
  python apply_sync_items.py                          # 自动找最新报告
  python apply_sync_items.py report.json              # 指定报告
  python apply_sync_items.py --dry-run                # 预览不写入
  python apply_sync_items.py --new-only report.json   # 只插入新增条目
"""
import json, sqlite3, sys, os, glob

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pokemonData.db')
SYNC_REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'sync_reports')


def find_latest_report():
    """找到最新的 items 同步报告"""
    pattern = os.path.join(SYNC_REPORTS_DIR, 'sync_report_items_*.json')
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def parse_value(field, raw):
    """Convert report value to DB-compatible value."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ('—', '-', 'null', 'None', ''):
        return None
    if field == 'fling_power':
        return int(s)
    return s


def apply_changes(report_path, dry_run=False):
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    changes = report.get('changes', [])
    if not changes:
        print('没有需要更新的条目')
        return

    # 预览变更
    print(f'报告: {os.path.basename(report_path)}')
    print(f'共 {len(changes)} 个条目：')
    for entry in changes:
        name_zh = entry['name_zh']
        name_en = entry['name_en']
        for c in entry['changes']:
            print(f'  {name_zh} ({name_en}): {c["field"]}: {c["current_value"]} -> {c["new_value"]}')

    if dry_run:
        print('\n=== DRY RUN (no changes written) ===')
        return

    # 交互确认
    confirm = input('\n确认执行更新？(yes/no): ').strip().lower()
    if confirm not in ('yes', 'y'):
        print('已取消')
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    updated = 0
    skipped = 0

    for entry in changes:
        name_en = entry['name_en']
        name_zh = entry['name_zh']

        cur.execute('SELECT id FROM items WHERE name_en = ?', (name_en,))
        row = cur.fetchone()
        if not row:
            print(f'  SKIP (not found): {name_zh} ({name_en})')
            skipped += 1
            continue

        item_id = row[0]

        for change in entry['changes']:
            field = change['field']
            new_val = parse_value(field, change['new_value'])
            cur.execute(f'UPDATE items SET {field} = ? WHERE id = ?', (new_val, item_id))
            print(f'  UPDATED: {name_zh} ({name_en}) SET {field} = {new_val!r}')

        updated += 1

    conn.commit()
    conn.close()
    print(f'\nCommitted {updated} items ({skipped} skipped)')


def apply_new_entries(report_path, dry_run=False):
    """将报告中的 new_entries 插入 items 表"""
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    new_entries = report.get('new_entries', [])
    if not new_entries:
        print('没有新增条目')
        return

    print(f'报告: {os.path.basename(report_path)}')
    print(f'共 {len(new_entries)} 个新增条目')

    if dry_run:
        for entry in new_entries[:20]:
            wi = entry['wiki_info']
            print(f'  {entry["name_zh"]} ({wi.get("name_en", "")}) cat={wi.get("category")}')
        if len(new_entries) > 20:
            print(f'  ... +{len(new_entries) - 20}')
        print('\n=== DRY RUN (no changes written) ===')
        return

    confirm = input(f'\n确认插入 {len(new_entries)} 条新道具？(yes/no): ').strip().lower()
    if confirm not in ('yes', 'y'):
        print('已取消')
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for entry in new_entries:
        wi = entry['wiki_info']
        name_en = wi.get('name_en', '')
        name_zh = entry.get('name_zh', wi.get('name_zh', ''))

        # 跳过 name_en 为空的
        if not name_en:
            print(f'  SKIP (no name_en): {name_zh}')
            skipped += 1
            continue

        # 检查是否已存在
        cur.execute('SELECT id FROM items WHERE name_en = ?', (name_en,))
        if cur.fetchone():
            print(f'  SKIP (exists): {name_zh} ({name_en})')
            skipped += 1
            continue

        # 构建插入数据
        wiki_file_path = wi.get('file_path', '')
        fling_power = wi.get('fling_power')
        if fling_power is not None:
            try:
                fling_power = int(fling_power)
            except (ValueError, TypeError):
                fling_power = None

        cur.execute(
            '''INSERT INTO items (name_zh, name_en, name_ja, category, fling_power, fling_effect, wiki_file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                name_zh,
                name_en,
                wi.get('name_ja'),
                wi.get('category'),
                fling_power,
                wi.get('fling_effect'),
                wiki_file_path,
            )
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f'\nInserted {inserted} items ({skipped} skipped)')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:]]
    dry_run = '--dry-run' in args
    new_only = '--new-only' in args
    args = [a for a in args if a not in ('--dry-run', '--new-only')]

    report_path = args[0] if args else None
    if not report_path:
        report_path = find_latest_report()
        if not report_path:
            print('未找到报告文件，请指定路径：python apply_sync_items.py <report.json>')
            sys.exit(1)
        print(f'使用最新报告: {os.path.basename(report_path)}')

    if not os.path.isabs(report_path):
        report_path = os.path.join(SYNC_REPORTS_DIR, report_path)

    if new_only:
        apply_new_entries(report_path, dry_run=dry_run)
    else:
        apply_changes(report_path, dry_run=dry_run)
