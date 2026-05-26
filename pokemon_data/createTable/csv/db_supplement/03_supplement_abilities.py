"""
Step 3: 补全 abilities 表的 7 个机制属性列
- affected_by_mold_breaker: 受不受破格等无视特性效果影响 (0/1)
- affected_by_no_ability: 受不受无特性状态影响 (0/1)
- triggers_on_entry: 入场时发动 (0/1)
- can_be_traced: 能不能被追踪复制 (0/1)
- works_when_transformed: 变身时有没有效果 (0/1)
- can_be_swapped: 能不能被特性交换 (0/1)
- can_be_overridden: 能不能被其他特性覆盖 (0/1)

数据源：52poke Wiki 的 特性信息框 模板
匹配策略：中文名两轮匹配（先带（特性）后缀，再不带）
"""

import sqlite3
import re
import os
import functools

print = functools.partial(print, flush=True)

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_CACHE = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wikitext_cache')
POKEMON_DB = os.path.join(BASE_DIR, '..', '..', '..', 'pokemonData.db')

# ── 机制参数 → DB 列名映射 ──
MECHANIC_PARAMS = {
    'Moldbreaker': 'affected_by_mold_breaker',
    'Noability':   'affected_by_no_ability',
    'Entry':       'triggers_on_entry',
    'Trace':       'can_be_traced',
    'Transform':   'works_when_transformed',
    'Skillswap':   'can_be_swapped',
    'Change':      'can_be_overridden',
}


def parse_yn(value):
    """将 wiki 参数值转为 0/1，缺失默认为 1"""
    if value is None:
        return 1
    v = value.strip().lower()
    return 0 if v == 'no' else 1


def build_wiki_index(cache_dir):
    """扫描 wikitext_cache，构建 {中文名: 文件路径} 索引"""
    index = {}
    if not os.path.isdir(cache_dir):
        print(f'[ERROR] wiki cache 目录不存在: {cache_dir}')
        return index

    for fname in os.listdir(cache_dir):
        if not fname.endswith('.wiki'):
            continue
        # 提取中文名：去掉 {id}_ 前缀和 .wiki 后缀
        m = re.match(r'\d+_(.+)\.wiki$', fname)
        if m:
            title = m.group(1)
            index[title] = os.path.join(cache_dir, fname)

    return index


def match_ability(name_zh, wiki_index):
    """两轮匹配：先 {name_zh}（特性），再 {name_zh}"""
    if not name_zh:
        return None

    # Round 1: 带后缀
    key = f'{name_zh}（特性）'
    fpath = wiki_index.get(key)
    if fpath and os.path.exists(fpath):
        return fpath

    # Round 2: 不带后缀
    fpath = wiki_index.get(name_zh)
    if fpath and os.path.exists(fpath):
        return fpath

    return None


def extract_mechanic_fields(content):
    """从特性 wikitext 的 特性信息框 模板提取 7 个机制字段"""
    # 提取模板内容
    m = re.search(r'\{\{特性信息框(.*?)\}\}', content, re.DOTALL)
    if not m:
        return None

    tpl = m.group(0)
    result = {}

    for wiki_key, db_col in MECHANIC_PARAMS.items():
        # 匹配 |Key=value，value 可能是 y/yes/no
        param_match = re.search(r'\|' + wiki_key + r'\s*=\s*(\S+)', tpl, re.IGNORECASE)
        result[db_col] = parse_yn(param_match.group(1) if param_match else None)

    return result


def main():
    print('=== Step 3: abilities 补 7 个机制属性列 ===\n')

    # Phase 1: ALTER TABLE
    print('Phase 1: ALTER TABLE 新增 7 列...')
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    new_cols = [
        ('affected_by_mold_breaker', 'INTEGER'),
        ('affected_by_no_ability',   'INTEGER'),
        ('triggers_on_entry',        'INTEGER'),
        ('can_be_traced',            'INTEGER'),
        ('works_when_transformed',   'INTEGER'),
        ('can_be_swapped',           'INTEGER'),
        ('can_be_overridden',        'INTEGER'),
    ]
    cur.execute('PRAGMA table_info(abilities)')
    existing_cols = {r[1] for r in cur.fetchall()}

    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cur.execute(f'ALTER TABLE abilities ADD COLUMN {col_name} {col_type}')
            print(f'  + {col_name} {col_type}')
        else:
            print(f'  = {col_name} 已存在')
    conn.commit()

    # Phase 2: 构建 wiki 索引
    print('\nPhase 2: 构建 wiki 文件索引...')
    wiki_index = build_wiki_index(WIKI_CACHE)
    print(f'  索引条目: {len(wiki_index)}')

    # Phase 3: 匹配 + 提取 + UPDATE
    print('\nPhase 3: 匹配特性文件 + 提取机制参数...')
    cur.execute('SELECT id, name_en, name_zh FROM abilities WHERE id < 10000')
    all_abilities = cur.fetchall()

    matched = 0
    unmatched = []
    update_count = 0

    for aid, name_en, name_zh in all_abilities:
        fpath = match_ability(name_zh, wiki_index)
        if not fpath:
            unmatched.append((aid, name_en, name_zh))
            continue

        matched += 1

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        fields = extract_mechanic_fields(content)
        if not fields:
            continue

        cur.execute('''UPDATE abilities SET
            affected_by_mold_breaker=?, affected_by_no_ability=?,
            triggers_on_entry=?, can_be_traced=?,
            works_when_transformed=?, can_be_swapped=?,
            can_be_overridden=?
            WHERE id=?''', (
            fields['affected_by_mold_breaker'], fields['affected_by_no_ability'],
            fields['triggers_on_entry'], fields['can_be_traced'],
            fields['works_when_transformed'], fields['can_be_swapped'],
            fields['can_be_overridden'], aid))
        update_count += 1

    conn.commit()
    print(f'  匹配成功: {matched}/{len(all_abilities)} ({matched/len(all_abilities)*100:.1f}%)')
    print(f'  更新: {update_count}')
    print(f'  未匹配: {len(unmatched)}')

    if unmatched:
        print('\n  未匹配列表:')
        for aid, ne, nz in unmatched:
            print(f'    {aid}\t{ne}\t{nz}')

    # Phase 4: 验证
    print('\n=== 验证 ===')
    for col in ['affected_by_mold_breaker', 'affected_by_no_ability',
                'triggers_on_entry', 'can_be_traced',
                'works_when_transformed', 'can_be_swapped',
                'can_be_overridden']:
        cur.execute(f'SELECT COUNT(*) FROM abilities WHERE {col} IS NOT NULL AND id < 10000')
        non_null = cur.fetchone()[0]
        cur.execute(f'SELECT SUM({col}) FROM abilities WHERE {col} IS NOT NULL AND id < 10000')
        yes_count = cur.fetchone()[0] or 0
        no_count = non_null - yes_count
        print(f'  {col}: yes={yes_count}, no={no_count}, NULL={len(all_abilities)-non_null}')

    # 检查 GO 特性是否为 NULL
    cur.execute('SELECT COUNT(*) FROM abilities WHERE id >= 10000 AND affected_by_mold_breaker IS NULL')
    go_null = cur.fetchone()[0]
    print(f'\n  GO 特性 NULL 数: {go_null} / 60')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
