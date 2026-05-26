"""
Step 2: 补全 moves 表的 6 列
- makes_contact: 是否接触招式 (0/1)
- can_protect: 能否被守住 (0/1)
- can_magic_coat: 能否被魔法反射 (0/1)
- can_snatch: 能否被抢夺 (0/1)
- can_mirror_move: 能否被模仿 (0/1)
- target: 目标范围代码 (1-16)

数据源：52poke Wiki 的 招式信息框 模板
"""

import sqlite3
import re
import os
import functools

print = functools.partial(print, flush=True)

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_META_DB = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wiki_meta.db')
POKEMON_DB = os.path.join(BASE_DIR, '..', '..', '..', 'pokemonData.db')

# ── 特例映射（DB name_zh → wiki 用名）──
SPECIAL_MAP = {
    '究极无敌大冲撞': '全力無雙激烈拳',
    '毁天灭地巨岩坠': '極速俯衝轟烈撞',
    '冲岩':          '衝岩',
}


def load_wiki_index():
    """从 wiki_meta.db 加载 pages 和 redirects 索引"""
    conn = sqlite3.connect(WIKI_META_DB)
    cur = conn.cursor()

    cur.execute('SELECT title, file_path FROM wiki_pages WHERE file_path IS NOT NULL')
    pages_map = {}
    for title, fpath in cur.fetchall():
        if title and fpath:
            pages_map[title] = fpath

    cur.execute('SELECT source_title, target_title FROM wiki_redirects')
    redir_map = {}
    for src, tgt in cur.fetchall():
        if src and tgt:
            redir_map[src] = tgt

    conn.close()
    return pages_map, redir_map


def match_move(name_zh, pages_map, redir_map, cc):
    """6 轮匹配 + 特例，返回 file_path 或 None"""
    if not name_zh:
        return None

    # 特例替换
    lookup_zh = SPECIAL_MAP.get(name_zh, name_zh)

    # Round 1: name_zh（招式）→ pages_map
    key = f'{lookup_zh}（招式）'
    fpath = pages_map.get(key)
    if fpath and os.path.exists(fpath):
        return fpath

    # Round 2: name_zh → pages_map
    fpath = pages_map.get(lookup_zh)
    if fpath and os.path.exists(fpath):
        return fpath

    # Round 3: redirect → pages_map
    for k in [key, lookup_zh]:
        if k in redir_map:
            tgt = redir_map[k]
            fpath = pages_map.get(tgt)
            if fpath and os.path.exists(fpath):
                return fpath

    # Round 4: redirect → pages_map（带后缀）
    for k in [key, lookup_zh]:
        if k in redir_map:
            tgt = redir_map[k]
            for suffix in ['（招式）', '']:
                fpath = pages_map.get(f'{tgt}{suffix}')
                if fpath and os.path.exists(fpath):
                    return fpath

    # Round 5: 繁体（招式）→ pages_map
    trad = cc.convert(lookup_zh)
    if trad != lookup_zh:
        fpath = pages_map.get(f'{trad}（招式）')
        if fpath and os.path.exists(fpath):
            return fpath

    # Round 6: 繁体 → pages_map
    if trad != lookup_zh:
        fpath = pages_map.get(trad)
        if fpath and os.path.exists(fpath):
            return fpath

    return None


def extract_move_fields(content):
    """从招式 wikitext 提取 6 个字段"""
    def yn(key):
        m = re.search(r'\|' + key + r'=(\w+)', content)
        if m:
            return 1 if m.group(1).strip().lower() == 'yes' else 0
        return None

    m = re.search(r'\|target=(\d+)', content)
    target = int(m.group(1)) if m else None

    return {
        'makes_contact': yn('touches'),
        'can_protect': yn('protect'),
        'can_magic_coat': yn('magiccoat'),
        'can_snatch': yn('snatch'),
        'can_mirror_move': yn('mirrormove'),
        'target': target,
    }


def main():
    print('=== Step 2: moves 补 6 列 ===\n')

    from opencc import OpenCC
    cc = OpenCC('s2t')

    # Phase 1: ALTER TABLE
    print('Phase 1: ALTER TABLE 新增 6 列...')
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    new_cols = [
        ('makes_contact', 'INTEGER'),
        ('can_protect', 'INTEGER'),
        ('can_magic_coat', 'INTEGER'),
        ('can_snatch', 'INTEGER'),
        ('can_mirror_move', 'INTEGER'),
        ('target', 'INTEGER'),
    ]
    cur.execute('PRAGMA table_info(moves)')
    existing_cols = {r[1] for r in cur.fetchall()}

    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cur.execute(f'ALTER TABLE moves ADD COLUMN {col_name} {col_type}')
            print(f'  + {col_name} {col_type}')
        else:
            print(f'  = {col_name} 已存在')
    conn.commit()

    # Phase 2: 加载索引
    print('\nPhase 2: 加载 wiki 索引...')
    pages_map, redir_map = load_wiki_index()
    print(f'  pages_map: {len(pages_map)}, redir_map: {len(redir_map)}')

    # Phase 3: 匹配
    print('\nPhase 3: 匹配招式文件...')
    cur.execute('SELECT id, name_en, name_zh FROM moves')
    all_moves = cur.fetchall()

    matched = {}   # id -> file_path
    unmatched = []

    for mid, name_en, name_zh in all_moves:
        fpath = match_move(name_zh, pages_map, redir_map, cc)
        if fpath:
            matched[mid] = fpath
        else:
            unmatched.append((mid, name_en, name_zh))

    print(f'  匹配成功: {len(matched)}/{len(all_moves)} ({len(matched)/len(all_moves)*100:.1f}%)')
    print(f'  未匹配: {len(unmatched)}')

    if unmatched:
        print('\n  未匹配列表:')
        for mid, ne, nz in unmatched:
            print(f'    {mid}\t{ne}\t{nz}')

    # Phase 4: 提取 + UPDATE
    print('\nPhase 4: 提取模板字段 + UPDATE...')
    update_count = 0
    skip_count = 0

    for mid, fpath in matched.items():
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        fields = extract_move_fields(content)

        # 跳过全为 None 的记录
        if all(v is None for v in fields.values()):
            skip_count += 1
            continue

        cur.execute('''UPDATE moves SET
            makes_contact=?, can_protect=?, can_magic_coat=?,
            can_snatch=?, can_mirror_move=?, target=?
            WHERE id=?''', (
            fields['makes_contact'], fields['can_protect'],
            fields['can_magic_coat'], fields['can_snatch'],
            fields['can_mirror_move'], fields['target'], mid))
        update_count += 1

    conn.commit()
    print(f'  更新: {update_count}, 跳过(无数据): {skip_count}')

    # Phase 5: 验证
    print('\n=== 验证 ===')
    for col in ['makes_contact', 'can_protect', 'can_magic_coat',
                'can_snatch', 'can_mirror_move', 'target']:
        cur.execute(f'SELECT count(*) FROM moves WHERE {col} IS NOT NULL')
        print(f'  {col}: {cur.fetchone()[0]} / {len(all_moves)}')

    print('\n  target 分布:')
    cur.execute('SELECT target, count(*) FROM moves WHERE target IS NOT NULL GROUP BY target ORDER BY count(*) DESC')
    for t, cnt in cur.fetchall():
        print(f'    target={t}: {cnt}')

    print('\n  makes_contact 分布:')
    cur.execute('SELECT makes_contact, count(*) FROM moves WHERE makes_contact IS NOT NULL GROUP BY makes_contact')
    for v, cnt in cur.fetchall():
        print(f'    {v}: {cnt}')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
