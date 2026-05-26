"""
Step 7: 扩展 status 表
- ALTER TABLE 新增 12 列（category / type_zh / duration / is_field / affects_pokemon /
  batonpass / removable_by_defog / removable_by_spin / blocked_by_safeguard /
  blocked_by_magicguard / blocked_by_substitute / note）
- 从 wiki_meta.db 读 124 条状态变化页面，解析 {{状态信息框}} 模板
- 分类 + UPSERT 到 status 表

数据源：wiki_meta.db → wiki_pages (title LIKE '%（状态）', status='done')
"""

import sqlite3
import re
import os
import functools

print = functools.partial(print, flush=True)

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POKEMON_DB = os.path.join(BASE_DIR, '..', '..', '..', 'pokemonData.db')
WIKI_META_DB = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wiki_meta.db')

# ── 天气/场地表（用于分类） ──
WEATHER_ZH = {'下雨', '大晴天', '沙暴', '冰雹', '下雪', '大日照', '大雨', '乱流'}
TERRAIN_ZH = {'精神场地', '电气场地', '薄雾场地', '青草场地'}

# ── 新增 12 列 ──
NEW_COLUMNS = [
    ('category',              'TEXT'),
    ('type_zh',               'TEXT'),
    ('duration',              'TEXT'),
    ('is_field',              'INTEGER'),
    ('affects_pokemon',       'INTEGER'),
    ('batonpass',             'INTEGER'),
    ('removable_by_defog',    'INTEGER'),
    ('removable_by_spin',     'INTEGER'),
    ('blocked_by_safeguard',  'INTEGER'),
    ('blocked_by_magicguard', 'INTEGER'),
    ('blocked_by_substitute', 'INTEGER'),
    ('note',                  'TEXT'),
]

# ── 布尔字段 → DB 列名 ──
BOOL_FIELDS = {
    'pokemon':    'affects_pokemon',
    'batonpass':  'batonpass',
    'defog':      'removable_by_defog',
    'spin':       'removable_by_spin',
    'safeguard':  'blocked_by_safeguard',
    'magicguard': 'blocked_by_magicguard',
    'substitute': 'blocked_by_substitute',
}

# ── 能力变化关键字 ──
STAT_CHANGE_KEYWORDS = ['能力', '充电', '易中要害', '进攻', '防守', '减速', '加倍']


def parse_yn(value, default=0):
    """yes/y → 1，no/空/缺失 → 0（默认 0）"""
    if value is None or value.strip() == '':
        return default
    v = value.strip().lower()
    return 1 if v in ('yes', 'y') else 0


def parse_infobox_fields(tpl):
    """解析 {{状态信息框|...}} 中的 |key=value 字段，处理嵌套 {{}}"""
    fields = {}
    for line in tpl.split('\n'):
        line = line.strip()
        if not line.startswith('|') or '=' not in line:
            continue
        eq_idx = line.index('=')
        key = line[1:eq_idx].strip()
        val = line[eq_idx+1:].strip()
        # 检查 val 中是否有未闭合的 {{，说明字段值跨越到下一行
        # （状态信息框中不常见，但保险起见）
        fields[key] = val
    return fields


def extract_field(fields, key):
    """从已解析的字段字典中获取值"""
    return fields.get(key)


def clean_templates(text):
    """清理 wiki 模板：{{tt|显示文本|提示}} → 显示文本，其他 {{}} 移除"""
    if not text:
        return text
    def _tt_replace(m):
        parts = m.group(1).split('|')
        return parts[1] if len(parts) >= 2 else ''
    text = re.sub(r'\{\{tt\|(.*?)\}\}', _tt_replace, text)
    text = re.sub(r'\{\{sup[^}]*\}\}', '', text)
    text = re.sub(r'\{\{gen\|(\d+)[^}]*\}\}', r'第\1世代', text)
    text = re.sub(r'\{\{[^}]*\}\}', '', text)
    return text.strip()


def clean_desc(raw_desc):
    """从 desc 字段提取 zh-hans 部分，清理模板"""
    if not raw_desc:
        return None
    m = re.search(r'zh-hans:(.*?);', raw_desc)
    text = m.group(1) if m else raw_desc
    text = clean_templates(text)
    return text if text else None


def classify(base_zh, wiki_category, defog_yes=False):
    """分类规则（优先级从高到低）"""
    # 1. 天气
    if base_zh in WEATHER_ZH:
        return 'weather'
    # 2. 场地
    if base_zh in TERRAIN_ZH:
        return 'terrain'
    # 3. 异常
    if wiki_category == '异常':
        return 'abnormal'
    # 4. 场地效果：defog=yes 且未归入 weather/terrain
    if defog_yes:
        return 'field'
    # 5. 能力变化
    if any(kw in base_zh for kw in STAT_CHANGE_KEYWORDS):
        return 'stat_change'
    # 6. 其余
    return 'special'


def extract_template(content, template_name):
    """用括号深度计数提取模板内容（处理嵌套 {{}}）"""
    marker = '{{' + template_name
    start = content.find(marker)
    if start < 0:
        return None
    depth = 0
    i = start
    while i < len(content) - 1:
        if content[i] == '{' and content[i+1] == '{':
            depth += 1
            i += 2
        elif content[i] == '}' and content[i+1] == '}':
            depth -= 1
            i += 2
            if depth == 0:
                return content[start:i]
        else:
            i += 1
    return None


def parse_status_wikitext(fpath):
    """解析状态信息框，返回字典或 None"""
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    full_tpl = extract_template(content, '状态信息框')
    if not full_tpl:
        return None

    # 去掉外层 {{ 和 }}
    tpl = full_tpl[2:-2]
    fields = parse_infobox_fields(tpl)

    name_zh  = extract_field(fields, 'name')
    name_en  = extract_field(fields, 'enname')
    name_ja  = extract_field(fields, 'janame')
    type_zh  = extract_field(fields, 'type')
    duration = clean_templates(extract_field(fields, 'time'))
    note     = extract_field(fields, 'note')
    raw_desc = extract_field(fields, 'desc')
    desc_zh  = clean_desc(raw_desc)
    wiki_cat = extract_field(fields, 'category')  # 异常 / 变化

    # 布尔字段（默认 0）
    bools = {}
    for wiki_key, db_col in BOOL_FIELDS.items():
        val = extract_field(fields, wiki_key)
        bools[db_col] = parse_yn(val)

    # defog=yes 标记（用于分类）
    defog_yes = parse_yn(extract_field(fields, 'defog')) == 1

    return {
        'name_zh':         name_zh,
        'name_en':         name_en,
        'name_ja':         name_ja,
        'description_zh':  desc_zh,
        'wiki_category':   wiki_cat,
        'type_zh':         type_zh,
        'duration':        duration,
        'note':            note,
        'bools':           bools,
        'defog_yes':       defog_yes,
    }


def main():
    print('=== Step 7: 扩展 status 表 ===\n')

    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    # Phase 1: ALTER TABLE
    print('Phase 1: ALTER TABLE 新增 12 列...')
    cur.execute('PRAGMA table_info(status)')
    existing_cols = {r[1] for r in cur.fetchall()}

    for col_name, col_type in NEW_COLUMNS:
        if col_name not in existing_cols:
            cur.execute(f'ALTER TABLE status ADD COLUMN {col_name} {col_type}')
            print(f'  + {col_name} {col_type}')
        else:
            print(f'  = {col_name} 已存在')
    conn.commit()

    # Phase 2: 加载 wiki_meta 状态页面 + 构建文件索引
    print('\nPhase 2: 加载 wiki_meta.db 状态页面...')
    wiki_conn = sqlite3.connect(WIKI_META_DB)
    wiki_rows = wiki_conn.execute(
        "SELECT page_id, title FROM wiki_pages "
        "WHERE title LIKE '%（状态）' AND status='done'"
    ).fetchall()
    wiki_conn.close()
    print(f'  总条目: {len(wiki_rows)}')

    # 用 title 构建文件索引（file_path 字段不可靠，指向错误的缓存文件）
    cache_dir = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wikitext_cache')
    title_index = {}
    for fname in os.listdir(cache_dir):
        if not fname.endswith('.wiki'):
            continue
        m_fname = re.match(r'\d+_(.+)\.wiki$', fname)
        if m_fname:
            title_index[m_fname.group(1)] = os.path.join(cache_dir, fname)
    print(f'  文件索引条目: {len(title_index)}')

    # Phase 3: 解析 + 分类 + UPSERT
    print('\nPhase 3: 解析信息框 + 分类 + UPSERT...')
    cur.execute('SELECT id, name_en, name_zh FROM status')
    existing = {(r[1] or '').lower(): r[0] for r in cur.fetchall()}  # name_en → id

    insert_count = 0
    update_count = 0
    skip_count = 0
    category_counts = {}

    for page_id, title in wiki_rows:
        fpath = title_index.get(title)
        # fallback：着迷/瞌睡等页面缓存文件名不含（状态）后缀
        if not fpath:
            base = title.replace('（状态）', '')
            fpath = title_index.get(base)
        if not fpath:
            skip_count += 1
            print(f'  [SKIP] 文件不存在: {title}')
            continue

        info = parse_status_wikitext(fpath)
        if not info:
            skip_count += 1
            print(f'  [SKIP] 无信息框: {title}')
            continue

        name_en = info['name_en']
        if not name_en:
            skip_count += 1
            print(f'  [SKIP] 无英文名: {title}')
            continue

        # 分类
        base_zh = (info['name_zh'] or title).replace('（状态）', '')
        category = classify(base_zh, info['wiki_category'], info['defog_yes'])
        category_counts[category] = category_counts.get(category, 0) + 1

        # is_field：field 类/terrain/weather 标记为场地效果
        is_field = 1 if category in ('field', 'terrain', 'weather') else 0

        b = info['bools']

        # 判断 UPSERT
        row_id = existing.get(name_en.lower())
        if row_id:
            # UPDATE：已有记录
            cur.execute('''UPDATE status SET
                category=?, type_zh=?, duration=?,
                is_field=?, affects_pokemon=?, batonpass=?,
                removable_by_defog=?, removable_by_spin=?,
                blocked_by_safeguard=?, blocked_by_magicguard=?,
                blocked_by_substitute=?, note=?
                WHERE id=?''', (
                category, info['type_zh'], info['duration'],
                is_field, b['affects_pokemon'], b['batonpass'],
                b['removable_by_defog'], b['removable_by_spin'],
                b['blocked_by_safeguard'], b['blocked_by_magicguard'],
                b['blocked_by_substitute'], info['note'],
                row_id))
            update_count += 1
        else:
            # INSERT：新记录
            cur.execute('''INSERT INTO status
                (name_en, name_ja, name_zh, description_zh,
                 category, type_zh, duration,
                 is_field, affects_pokemon, batonpass,
                 removable_by_defog, removable_by_spin,
                 blocked_by_safeguard, blocked_by_magicguard,
                 blocked_by_substitute, note)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                name_en, info['name_ja'],
                info['name_zh'] or base_zh, info['description_zh'],
                category, info['type_zh'], info['duration'],
                is_field, b['affects_pokemon'], b['batonpass'],
                b['removable_by_defog'], b['removable_by_spin'],
                b['blocked_by_safeguard'], b['blocked_by_magicguard'],
                b['blocked_by_substitute'], info['note']))
            insert_count += 1

    conn.commit()

    print(f'\n  插入: {insert_count}')
    print(f'  更新: {update_count}')
    print(f'  跳过: {skip_count}')
    print(f'  分类分布: {category_counts}')

    # Phase 4: 验证
    print('\n=== 验证 ===')
    cur.execute('SELECT category, count(*) FROM status GROUP BY category ORDER BY count(*) DESC')
    print('\ncategory 分布:')
    for r in cur.fetchall():
        print(f'  {r[0] or "NULL"}: {r[1]}')

    cur.execute('SELECT name_zh, duration FROM status WHERE duration IS NOT NULL AND duration != ""')
    dur_rows = cur.fetchall()
    print(f'\nduration 非空 ({len(dur_rows)} 条):')
    for r in dur_rows[:15]:
        print(f'  {r[0]}: {r[1]}')

    cur.execute('SELECT name_zh FROM status WHERE is_field=1 ORDER BY name_zh')
    field_rows = cur.fetchall()
    print(f'\nis_field=1 ({len(field_rows)} 条):')
    for r in field_rows:
        print(f'  {r[0]}')

    cur.execute('SELECT count(*) FROM status')
    print(f'\nstatus 表总行数: {cur.fetchone()[0]}')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
