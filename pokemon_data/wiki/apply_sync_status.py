"""Apply status sync changes from report to pokemonData.db"""
import json, sqlite3, sys, os, glob

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'pokemonData.db')
SYNC_REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'sync_reports')


def find_latest_report():
    """找到最新的 status 同步报告"""
    pattern = os.path.join(SYNC_REPORTS_DIR, 'sync_report_status_*.json')
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


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

        cur.execute('SELECT id FROM status WHERE name_en = ?', (name_en,))
        row = cur.fetchone()
        if not row:
            print(f'  SKIP (not found): {name_zh} ({name_en})')
            skipped += 1
            continue

        status_id = row[0]

        for change in entry['changes']:
            field = change['field']
            new_val = change['new_value']
            cur.execute(f'UPDATE status SET {field} = ? WHERE id = ?', (new_val, status_id))
            print(f'  UPDATED: {name_zh} ({name_en}) SET {field} = {new_val!r}')

        updated += 1

    conn.commit()
    conn.close()
    print(f'\nCommitted {updated} status ({skipped} skipped)')


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    report_path = None
    for arg in sys.argv[1:]:
        if arg != '--dry-run':
            report_path = arg
            break

    if not report_path:
        report_path = find_latest_report()
        if not report_path:
            print('未找到报告文件，请指定路径：python apply_sync_status.py <report.json>')
            sys.exit(1)
        print(f'使用最新报告: {os.path.basename(report_path)}')

    if not os.path.isabs(report_path):
        report_path = os.path.join(SYNC_REPORTS_DIR, report_path)

    apply_changes(report_path, dry_run=dry_run)
