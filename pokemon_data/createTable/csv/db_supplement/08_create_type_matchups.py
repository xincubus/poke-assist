"""
Step 8: 新建 type_matchups_by_gen 表（按世代区分属性克制）
- 从 18 个属性页面的 "==属性相克==" section 解析 {{属性相克}} 模板
- 按世代分组，生成 18×18 属性克制矩阵
- 数据源：wiki wikitext_cache 中的 X（属性）.wiki 文件

策略：
- 只解析防御方字段（weakto=2x, resist=0.5x, unaffected/noeffect=0x）
- 攻击方倍率通过反向推导：若 A 被 B 打 2x → B 攻击 A = 2x
- 验证：和现有 type_effectiveness 表（当前世代）对比
"""

import sqlite3
import re
import os
import functools

print = functools.partial(print, flush=True)

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POKEMON_DB = os.path.join(BASE_DIR, '..', '..', '..', 'pokemonData.db')
WIKI_CACHE = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wikitext_cache')

# ── 18 种标准属性 ──
ALL_TYPES = [
    '一般', '火', '水', '草', '电', '冰',
    '格斗', '毒', '地面', '飞行', '超能力', '虫',
    '岩石', '幽灵', '龙', '恶', '钢', '妖精',
]

# ── 属性页面文件名映射 ──
TYPE_FILES = {
    '一般': '2202_一般（属性）.wiki',
    '火':   '2211_火（属性）.wiki',
    '水':   '2188_水（属性）.wiki',
    '草':   '2197_草（属性）.wiki',
    '电':   '2196_电（属性）.wiki',
    '冰':   '2198_冰（属性）.wiki',
    '格斗': '2203_格斗（属性）.wiki',
    '毒':   '2206_毒（属性）.wiki',
    '地面': '2207_地面（属性）.wiki',
    '飞行': '2204_飞行（属性）.wiki',
    '超能力': '2199_超能力（属性）.wiki',
    '虫':   '2205_虫（属性）.wiki',
    '岩石': '2208_岩石（属性）.wiki',
    '幽灵': '2210_幽灵（属性）.wiki',
    '龙':   '2200_龙（属性）.wiki',
    '恶':   '2201_恶（属性）.wiki',
    '钢':   '2209_钢（属性）.wiki',
    '妖精': '55681_妖精（属性）.wiki',
}

# ── 世代存在的属性 ──
# Gen 1: 15 种（无钢/恶/妖精）
# Gen 2-5: 17 种（无妖精）
# Gen 6+: 18 种（全）
TYPES_BY_GEN = {}
for g in range(1, 2 + 1):
    TYPES_BY_GEN[g] = [t for t in ALL_TYPES if t not in ('钢', '恶', '妖精')]
for g in range(2, 5 + 1):
    TYPES_BY_GEN[g] = [t for t in ALL_TYPES if t != '妖精']
for g in range(6, 10 + 1):
    TYPES_BY_GEN[g] = ALL_TYPES[:]


def find_wiki_file(type_name):
    """查找属性页面的 wiki 文件"""
    # 先用预定义文件名
    fname = TYPE_FILES.get(type_name)
    if fname:
        fpath = os.path.join(WIKI_CACHE, fname)
        if os.path.exists(fpath):
            return fpath

    # fallback: 搜索文件名包含 "X（属性）" 的文件
    target = f'{type_name}（属性）'
    for f in os.listdir(WIKI_CACHE):
        if target in f and f.endswith('.wiki'):
            return os.path.join(WIKI_CACHE, f)
    return None


def extract_type_section(content):
    """提取 ==属性相克== 到下一个 == 之间的内容"""
    m = re.search(r'==属性相克==(.*?)(?=\n==[^=])', content, re.DOTALL)
    return m.group(1) if m else None


def parse_gen_range(header_text):
    """
    解析世代范围标题，返回 (gen_start, gen_end)。
    示例：
      "={{gen|1}}===" → (1, 1)
      "={{gen|2}}至{{gen|5}}===" → (2, 5)
      "={{gen|6}}起===" → (6, 10)
      "第二世代起" → (2, 10)
    """
    # Pattern: {{gen|N}}起  or  {{gen|N}}至{{gen|M}}
    m = re.search(r'\{\{gen\|(\d+)\}\}(?:至\{\{gen\|(\d+)\}\})?(起)?', header_text)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else (10 if m.group(3) else start)
        return (start, end)

    # Fallback: 中文数字（支持 "第X世代至第Y世代" 和 "第X世代起"）
    cn_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
               '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    m = re.search(r'第([一二三四五六七八九十]+)世代(?:至第([一二三四五六七八九十]+)世代)?', header_text)
    if m:
        start = cn_nums.get(m.group(1), 0)
        if m.group(2):
            end = cn_nums.get(m.group(2), start)
        elif '起' in header_text:
            end = 10
        else:
            end = start
        return (start, end)

    return None


def parse_template_values(tpl_text):
    """
    解析 {{属性相克 ... }} 模板中的字段值。
    返回 dict: { 'weakto': [...], 'resist': [...], 'unaffected': [...], 'noeffect': [...] }
    """
    result = {'weakto': [], 'resist': [], 'unaffected': [], 'noeffect': []}

    for line in tpl_text.split('\n'):
        line = line.strip()
        if not line.startswith('|') or '=' not in line:
            continue
        eq_idx = line.index('=')
        key = line[1:eq_idx].strip()
        val = line[eq_idx + 1:].strip()

        # 提取 key 的前缀（去掉数字后缀）
        prefix = re.match(r'([a-z]+)', key)
        if not prefix:
            continue
        prefix = prefix.group(1)

        if prefix in result and val:
            result[prefix].append(val)

    return result


def split_gen_sections(section_text):
    """
    按世代标题切分 section，返回 [(gen_start, gen_end, template_text), ...]
    """
    # 找所有世代标题和对应的模板
    parts = re.split(r'(===.*?===)', section_text)

    sections = []
    current_header = None

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # 检查是否是世代标题（包含 {{gen| 或 第X世代 或 起/至）
        if part.startswith('===') and ('gen|' in part or '世代' in part or '起===' in part or '至' in part):
            gen_range = parse_gen_range(part)
            if gen_range:
                current_header = gen_range
        elif current_header and '{{属性相克' in part:
            # 这是模板内容
            sections.append((current_header[0], current_header[1], part))
            current_header = None

    return sections


def parse_type_page(fpath):
    """
    解析一个属性页面，返回 [(gen_start, gen_end, defense_map, attack_map, unaffected_types), ...]
    - defense_map: {attacker_type: eff} — 该属性被攻击时的倍率（不含 unaffected）
    - attack_map: {defender_type: eff} — 该属性攻击时的倍率（仅 noeffect）
    - unaffected_types: set — 防御方免疫的属性集合（不能反向推导攻击方）
    """
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    section = extract_type_section(content)
    if not section:
        return []

    gen_sections = split_gen_sections(section)
    results = []

    for gen_start, gen_end, tpl_text in gen_sections:
        vals = parse_template_values(tpl_text)

        # 防御方倍率：该属性被 X 打多少（不含 unaffected）
        defense_map = {}
        for t in vals['weakto']:
            defense_map[t] = 2.0
        for t in vals['resist']:
            defense_map[t] = 0.5

        # unaffected：防御方免疫，单独记录
        unaffected_types = set(vals['unaffected'])

        # 攻击方倍率：该属性打 X 多少（仅 noeffect）
        attack_map = {}
        for t in vals['noeffect']:
            attack_map[t] = 0.0

        results.append((gen_start, gen_end, defense_map, attack_map, unaffected_types))

    return results


def build_type_chart():
    """
    构建完整的 type_matchups_by_gen 数据。
    返回 [(generation, attacker_type, defender_type, effectiveness), ...]

    策略：
    1. weakto/resist → 防御方数据，可反向推导攻击方（2x↔2x, 0.5x↔0.5x）
    2. unaffected → 只设防御方 0x，不反向（单向免疫）
    3. noeffect → 只设攻击方 0x，不反向（单向无效）
    4. 剩余空白通过防御方反向推导
    """
    page_data_map = {}

    for type_name in ALL_TYPES:
        fpath = find_wiki_file(type_name)
        if not fpath:
            print(f'  [WARN] 文件不存在: {type_name}')
            continue

        page_data = parse_type_page(fpath)
        if not page_data:
            print(f'  [WARN] 无属性相克数据: {type_name}')
            continue

        print(f'  {type_name}: {len(page_data)} 个世代段')
        page_data_map[type_name] = page_data

    # (gen, attacker, defender) → effectiveness
    chart = {}
    # 记录所有 0x 来源，反向推导时跳过（单向关系不能反向）
    zero_entries = set()

    for type_name, page_data in page_data_map.items():
        for gen_start, gen_end, defense_map, attack_map, unaffected_types in page_data:
            for gen in range(gen_start, gen_end + 1):
                valid_types = TYPES_BY_GEN.get(gen, ALL_TYPES)

                # 防御方：type_name 被 att_type 打多少（weakto/resist）
                for att_type in valid_types:
                    eff = defense_map.get(att_type, None)
                    if eff is not None:
                        chart[(gen, att_type, type_name)] = eff

                # unaffected：防御方免疫（type_name 被 att_type 打 = 0x）
                for att_type in unaffected_types:
                    if att_type in valid_types:
                        chart[(gen, att_type, type_name)] = 0.0
                        zero_entries.add((gen, att_type, type_name))

                # noeffect：攻击方无效（type_name 打 def_type = 0x）
                for def_type in valid_types:
                    eff = attack_map.get(def_type, None)
                    if eff is not None:
                        chart[(gen, type_name, def_type)] = 0.0
                        zero_entries.add((gen, type_name, def_type))

    # 反向推导：用防御方数据填充攻击方空白
    # 若 A 被 B 打 2x → B 攻击 A = 2x
    # 若 A 被 B 打 0.5x → B 攻击 A = 0.5x
    # 跳过 0x 来源（unaffected/noeffect 是单向关系）
    for gen in range(1, 10 + 1):
        valid_types = TYPES_BY_GEN.get(gen, ALL_TYPES)
        for att in valid_types:
            for defe in valid_types:
                key = (gen, att, defe)
                if key in chart:
                    continue
                # 反向推导：att 攻击 defe = defe 被 att 打
                # "defe 被 att 打" 存储为 chart[(gen, att, defe)]
                # 但 key = (gen, att, defe) 已经不在 chart 中（上面 continue 检查过）
                # 所以需要从 defe 的防御方数据中找：defe 被 att 打多少
                # 这个数据在构建时已存为 chart[(gen, att, defe)]
                # 由于 key 不在 chart，说明这个关系未被显式设置
                # 只能从对称关系推导：若 att 被 defe 打 X，则 defe 被 att 打 X（2x/0.5x 对称）
                # 查 chart[(gen, defe, att)] = defe 攻击 att = att 被 defe 打
                rev_key = (gen, defe, att)
                rev_eff = chart.get(rev_key)
                if rev_eff is not None and rev_key not in zero_entries:
                    # 2x/0.5x 对称：若 att 被 defe 打 X，则 defe 被 att 打 X
                    chart[key] = rev_eff

    # 填充剩余空白为 1.0
    all_records = []
    for gen in range(1, 10 + 1):
        valid_types = TYPES_BY_GEN.get(gen, ALL_TYPES)
        for att in valid_types:
            for defe in valid_types:
                eff = chart.get((gen, att, defe), 1.0)
                all_records.append((gen, att, defe, eff))

    return all_records


def validate_against_existing(cur, records):
    """和现有 type_effectiveness 表（当前世代）对比验证"""
    # 读取现有表
    cur.execute('''
        SELECT t_a.name_zh, t_d.name_zh, e.effectiveness
        FROM type_effectiveness e
        JOIN types t_a ON e.attacker_type_id = t_a.id
        JOIN types t_d ON e.defender_type_id = t_d.id
    ''')
    existing = {(r[0], r[1]): r[2] for r in cur.fetchall()}

    # 对比 Gen 9（SV 当前世代）
    mismatches = []
    gen9_records = {(r[1], r[2]): r[3] for r in records if r[0] == 9}

    for (att, defe), eff in existing.items():
        gen9_eff = gen9_records.get((att, defe))
        if gen9_eff is not None and abs(gen9_eff - eff) > 0.01:
            mismatches.append((att, defe, eff, gen9_eff))

    return mismatches


def main():
    print('=== Step 8: 新建 type_matchups_by_gen 表 ===\n')

    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    # Phase 1: 建表
    print('Phase 1: 建表...')
    cur.execute('DROP TABLE IF EXISTS type_matchups_by_gen')
    cur.execute('''
        CREATE TABLE type_matchups_by_gen (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            generation      INTEGER NOT NULL,
            attacker_type   TEXT NOT NULL,
            defender_type   TEXT NOT NULL,
            effectiveness   REAL NOT NULL,
            UNIQUE(generation, attacker_type, defender_type)
        )
    ''')
    conn.commit()
    print('  表已创建')

    # Phase 2: 解析 wiki 模板 + 构建完整矩阵
    print('\nPhase 2: 解析属性页面...')
    complete_records = build_type_chart()
    print(f'  总记录数: {len(complete_records)}')

    # Phase 3: 验证
    print('\nPhase 3: 验证...')
    mismatches = validate_against_existing(cur, complete_records)
    if mismatches:
        print(f'  [WARN] 发现 {len(mismatches)} 处不匹配:')
        for att, defe, expected, actual in mismatches:
            print(f'    {att} → {defe}: 期望 {expected}, 实际 {actual}')
    else:
        print('  全部匹配!')

    # Phase 5: 写入数据库
    print('\nPhase 5: 写入数据库...')
    cur.executemany(
        'INSERT OR IGNORE INTO type_matchups_by_gen (generation, attacker_type, defender_type, effectiveness) VALUES (?,?,?,?)',
        [(r[0], r[1], r[2], r[3]) for r in complete_records]
    )
    conn.commit()

    # Phase 6: 统计
    print('\n=== 统计 ===')
    cur.execute('SELECT generation, count(*) FROM type_matchups_by_gen GROUP BY generation ORDER BY generation')
    for r in cur.fetchall():
        print(f'  Gen {r[0]}: {r[1]} 条')

    cur.execute('SELECT count(*) FROM type_matchups_by_gen')
    print(f'  总计: {cur.fetchone()[0]} 条')

    # 抽查
    print('\n=== 抽查 ===')
    checks = [
        (9, '火', '草', 2.0),
        (9, '水', '火', 2.0),
        (9, '一般', '幽灵', 0.0),
        (9, '格斗', '幽灵', 0.0),
        (9, '电', '地面', 0.0),
        (9, '钢', '毒', 1.0),  # 钢攻击毒 = 1x（unaffected 是防御方免疫，不影响攻击方）
        (1, '超能力', '幽灵', 1.0),  # Gen1 超能力打幽灵 = 1x
        (1, '幽灵', '超能力', 0.0),  # Gen1 幽灵打超能力 = 0x（wiki 记录的 bug）
        (1, '火', '钢', None),  # Gen1 无钢，应无记录
        (1, '钢', '火', None),  # Gen1 无钢，应无记录
    ]
    for gen, att, defe, expected in checks:
        cur.execute(
            'SELECT effectiveness FROM type_matchups_by_gen WHERE generation=? AND attacker_type=? AND defender_type=?',
            (gen, att, defe)
        )
        row = cur.fetchone()
        if expected is None:
            status = 'OK (无记录)' if row is None else f'FAIL (有记录: {row[0]})'
        else:
            actual = row[0] if row else None
            status = 'OK' if actual == expected else f'FAIL (实际: {actual})'
        print(f'  Gen{gen} {att}→{defe}: {status}')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
