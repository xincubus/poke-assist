"""
Step 4: 补全 abilities 表的对战中/对战外效果列
- effect_battle: 对战中效果
- effect_overworld: 对战外效果

数据源：52poke Wiki 的 特性效果 section
匹配策略：中文名两轮匹配（同 03_supplement_abilities.py）
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


def build_wiki_index(cache_dir):
    """扫描 wikitext_cache，构建 {中文名: 文件路径} 索引"""
    index = {}
    if not os.path.isdir(cache_dir):
        print(f'[ERROR] wiki cache 目录不存在: {cache_dir}')
        return index
    for fname in os.listdir(cache_dir):
        if not fname.endswith('.wiki'):
            continue
        m = re.match(r'\d+_(.+)\.wiki$', fname)
        if m:
            index[m.group(1)] = os.path.join(cache_dir, fname)
    return index


def match_ability(name_zh, wiki_index):
    """两轮匹配：先 {name_zh}（特性），再 {name_zh}"""
    if not name_zh:
        return None
    for key in [f'{name_zh}（特性）', name_zh]:
        fpath = wiki_index.get(key)
        if fpath and os.path.exists(fpath):
            return fpath
    return None


def clean_wikitext(text):
    """将 wikitext 标记转为纯文本"""
    # 移除 HTML 注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # {{frac|1|4}} → 1/4
    text = re.sub(r'\{\{frac\|(\d+)\|(\d+)\}\}', r'\1/\2', text)
    # {{特性效果/...}} / {{Template:特性效果/...}} → 展开参数
    def expand_effect(m):
        parts = m.group(0)[2:-2].split('|')  # 去掉 {{ }}, 按 | 分割
        name = parts[0].split('/')[-1]  # 取 / 后最后一段
        if len(parts) >= 2:
            params = '、'.join(p for p in parts[1:] if p)
            return f'{name}（{params}）'
        return name
    text = re.sub(r'\{\{(?:Template:)?特性效果/[^}]+\}\}', expand_effect, text)
    # [[link|text]] → text
    text = re.sub(r'\[\[[^\]|]+\|([^\]]+)\]\]', r'\1', text)
    # [[link]] → link
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    # {{gen|七}} → 第七世代
    text = re.sub(r'\{\{gen\|([^}]+)\}\}', r'第\1世代', text)
    # {{game|RS}} → RS
    text = re.sub(r'\{\{game\|([^}]+)\}\}', r'\1', text)
    # {{MSP|id|name|...}} → 移除（精灵图模板，纯装饰）
    text = re.sub(r'\{\{MSP\|[^}]+\}\}', '', text)
    # {{prefix|text}} → text（通用模板处理）
    text = re.sub(r'\{\{[^}|]+\|([^}]+)\}\}', r'\1', text)
    # {{text}} → text（无参数模板）
    text = re.sub(r'\{\{([^}]+)\}\}', r'\1', text)
    # 表格行：|- / ! / | 开头的行，提取纯文本
    lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped in ('{|', '|}', '|-', ''):
            continue
        m = re.match(r'^[|!]\s*(.+)', stripped)
        if m:
            lines.append(m.group(1).strip())
        else:
            lines.append(stripped)
    text = '\n'.join(lines)
    # 移除残留的 wiki 标记
    text = re.sub(r"'''", '', text)
    text = re.sub(r"''", '', text)
    # 合并多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_effects(content):
    """从特性 wikitext 提取对战中/对战外效果"""
    # 找到 特性效果 section
    m = re.search(r'==\s*特性效果\s*==\s*(.*?)(?=\n==[^=]|\Z)', content, re.DOTALL)
    if not m:
        return None, None

    section = m.group(1)

    # 拆分对战中 / 对战外
    # 对战中：从 ===对战中=== 到 ===对战外=== 或下一个 == 或 EOF
    # 对战外：从 ===对战外=== 到下一个 == 或 EOF

    battle_text = None
    overworld_text = None

    # 尝试按 === 子标题分段（section 可能以 === 开头，不需要前导换行）
    parts = re.split(r'\n?===\s*(对战中|對戰中|对战外|對戰外|对战外效果)\s*===\s*\n', section)

    if len(parts) >= 3:
        # 有子标题
        for i in range(1, len(parts), 2):
            header = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ''
            if header in ('对战中', '對戰中'):
                battle_text = body
            elif header in ('对战外', '對戰外', '对战外效果'):
                overworld_text = body
    else:
        # 无子标题，整个 section 作为对战中效果
        battle_text = section.strip()

    # 清理
    if battle_text:
        # 截断到子标题（====）之前
        battle_text = re.split(r'\n={4,}', battle_text)[0]
        battle_text = clean_wikitext(battle_text)
        if not battle_text:
            battle_text = None
    if overworld_text:
        # 截断到子标题（====）之前，避免道具列表等大段内容
        overworld_text = re.split(r'\n={4,}', overworld_text)[0]
        overworld_text = clean_wikitext(overworld_text)
        if not overworld_text:
            overworld_text = None

    return battle_text, overworld_text


def main():
    print('=== Step 4: abilities 补对战中/对战外效果 ===\n')

    # Phase 1: ALTER TABLE
    print('Phase 1: ALTER TABLE 新增 2 列...')
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    cur.execute('PRAGMA table_info(abilities)')
    existing_cols = {r[1] for r in cur.fetchall()}

    for col_name, col_type in [('effect_battle', 'TEXT'), ('effect_overworld', 'TEXT')]:
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
    print('\nPhase 3: 匹配特性文件 + 提取效果...')
    cur.execute('SELECT id, name_en, name_zh FROM abilities WHERE id < 10000')
    all_abilities = cur.fetchall()

    matched = 0
    unmatched = []
    updated = 0
    battle_count = 0
    overworld_count = 0

    for aid, name_en, name_zh in all_abilities:
        fpath = match_ability(name_zh, wiki_index)
        if not fpath:
            unmatched.append((aid, name_en, name_zh))
            continue

        matched += 1

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        battle, overworld = extract_effects(content)

        if battle or overworld:
            cur.execute('UPDATE abilities SET effect_battle=?, effect_overworld=? WHERE id=?',
                        (battle, overworld, aid))
            updated += 1
            if battle:
                battle_count += 1
            if overworld:
                overworld_count += 1

    conn.commit()
    print(f'  匹配成功: {matched}/{len(all_abilities)} ({matched/len(all_abilities)*100:.1f}%)')
    print(f'  更新: {updated}')
    print(f'  有对战中效果: {battle_count}')
    print(f'  有对战外效果: {overworld_count}')
    print(f'  未匹配: {len(unmatched)}')

    if unmatched:
        print('\n  未匹配列表:')
        for aid, ne, nz in unmatched:
            print(f'    {aid}\t{ne}\t{nz}')

    # Phase 4: 验证
    print('\n=== 验证 ===')
    cur.execute('SELECT COUNT(*) FROM abilities WHERE effect_battle IS NOT NULL AND id < 10000')
    print(f'  effect_battle 非空: {cur.fetchone()[0]}')
    cur.execute('SELECT COUNT(*) FROM abilities WHERE effect_overworld IS NOT NULL AND id < 10000')
    print(f'  effect_overworld 非空: {cur.fetchone()[0]}')
    cur.execute('SELECT COUNT(*) FROM abilities WHERE id >= 10000 AND effect_battle IS NULL')
    print(f'  GO 特性 effect_battle NULL: {cur.fetchone()[0]}')

    # 抽样展示
    print('\n=== 抽样 ===')
    cur.execute('''SELECT id, name_zh, effect_battle, effect_overworld
        FROM abilities WHERE effect_overworld IS NOT NULL AND id < 10000 LIMIT 5''')
    for row in cur.fetchall():
        b = (row[2] or '无')[:60]
        o = (row[3] or '无')[:60]
        print(f'  [{row[0]}] {row[1]}')
        print(f'    对战中: {b}')
        print(f'    对战外: {o}')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
