"""
Step 1: 补全 pokemons 表的 9 列
- 形态无关：species, egg_group1, egg_group2, gender_ratio, catch_rate, color, ev_yield
- 形态相关：height_m, weight_kg, base_exp

数据源：52poke Wiki 的 寶可夢信息框 模板
"""

import sqlite3
import re
import os
import sys
import json
import httpx
import functools

print = functools.partial(print, flush=True)

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_CACHE = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wikitext_cache')
WIKI_META_DB = os.path.join(BASE_DIR, '..', '..', '..', 'wiki', 'wiki_meta.db')
POKEMON_DB = os.path.join(BASE_DIR, '..', '..', '..', 'pokemonData.db')
ENV_FILE = os.path.join(BASE_DIR, '..', '..', '..', '..', 'api', '.env')

# ── 加载 wiki 数据 ──

def load_wiki_index():
    """从 wiki_meta.db 构建匹配索引"""
    conn = sqlite3.connect(WIKI_META_DB)
    cur = conn.cursor()

    # wiki_pages: title -> file_path
    cur.execute('SELECT title, file_path FROM wiki_pages WHERE file_path IS NOT NULL')
    wiki_pages = {}
    for title, fpath in cur.fetchall():
        if title and fpath:
            wiki_pages[title] = fpath

    # wiki_redirects
    cur.execute('SELECT source_title, target_page_id, target_title FROM wiki_redirects')
    zh_redirects = {}      # 中文名 -> 中文名（页面跳转）
    en_to_zh = {}           # 英文名 -> 中文名
    form_alias_map = {}     # DB name_zh -> wiki 形态名（反向查 target_title）

    for src, page_id, tgt in cur.fetchall():
        if not src or not tgt:
            continue
        if all(c.isascii() for c in src):
            en_to_zh[src.lower()] = tgt
        else:
            zh_redirects[src] = tgt
            # form alias: target_page_id 为 0 且 target_title 包含（ 的是形态别名
            if page_id == 0 and '（' in tgt:
                form_alias_map[tgt] = src

    conn.close()
    return wiki_pages, zh_redirects, en_to_zh, form_alias_map


def find_wiki_file(name_en, name_zh, wiki_pages, zh_redirects, en_to_zh):
    """匹配 wiki 文件，返回 file_path"""
    # 1. name_zh 精确
    if name_zh in wiki_pages:
        return wiki_pages[name_zh]
    # 2. 去掉（...）后缀
    zh_base = re.sub(r'[（(].*?[）)]$', '', name_zh)
    if zh_base in wiki_pages:
        return wiki_pages[zh_base]
    # 3. zh redirect
    redir = zh_redirects.get(name_zh)
    if redir and redir in wiki_pages:
        return wiki_pages[redir]
    # 4. en redirect
    redir = en_to_zh.get(name_en.lower())
    if redir and redir in wiki_pages:
        return wiki_pages[redir]
    return None


# ── 模板解析 ──

def extract_template(content):
    """提取 寶可夢信息框 或 寶可夢信息框/形態 模板块"""
    # 匹配 {{寶可夢信息框/形態 或 {{寶可夢信息框/形态 或 {{寶可夢信息框
    match = re.search(r'\{\{寶可夢信息框(?:/形[態态])?\s*\n(.*?)\n\}\}', content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def parse_field(tpl, key):
    """从模板中提取 |key=value"""
    m = re.search(r'\|' + re.escape(key) + r'=(.+)', tpl)
    return m.group(1).strip() if m else None


def parse_int(val):
    if val is None:
        return None
    m = re.search(r'(\d+)', val.replace(',', ''))
    return int(m.group(1)) if m else None


def parse_float(val):
    if val is None:
        return None
    m = re.search(r'(\d+\.?\d*)', val)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def extract_form_independent(tpl):
    """提取形态无关字段"""
    species = parse_field(tpl, 'species')

    egg1 = parse_field(tpl, 'egggroup1')
    egg2 = parse_field(tpl, 'egggroup2')
    # 空值视为 None
    egg1 = egg1 if egg1 else None
    egg2 = egg2 if egg2 else None

    gender = parse_int(parse_field(tpl, 'gendercode'))
    catch = parse_int(parse_field(tpl, 'catchrate'))
    color = parse_field(tpl, 'color')

    # ev_yield: 拼接非零项
    ev_parts = []
    for stat, key in [('hp', 'evhp'), ('at', 'evat'), ('de', 'evde'),
                       ('sa', 'evsa'), ('sd', 'evsd'), ('sp', 'evsp')]:
        val = parse_int(parse_field(tpl, key))
        if val and val > 0:
            ev_parts.append(f'{stat}+{val}')
    ev_yield = '/'.join(ev_parts) if ev_parts else None

    return {
        'species': species,
        'egg_group1': egg1,
        'egg_group2': egg2,
        'gender_ratio': gender,
        'catch_rate': catch,
        'color': color,
        'ev_yield': ev_yield,
    }


def extract_form_dependent(tpl, form_id=None):
    """提取形态相关字段。form_id=None 表示取无后缀（base form）"""
    suffix = '' if form_id is None else str(form_id)
    height = parse_float(parse_field(tpl, f'height{suffix}'))
    weight = parse_float(parse_field(tpl, f'weight{suffix}'))
    exp_raw = parse_field(tpl, f'expyield{suffix}')
    base_exp = parse_int(exp_raw) if exp_raw and exp_raw != '&mdash;' else None
    return {'height_m': height, 'weight_kg': weight, 'base_exp': base_exp}


def find_form_id_by_name(tpl, wiki_form_name):
    """在模板中找 formN=wiki_form_name，返回 N"""
    for m in re.finditer(r'\|form(\d+)=(.+)', tpl):
        if m.group(2).strip() == wiki_form_name:
            return int(m.group(1))
    return None


def find_form_id_by_keyword(tpl, keyword):
    """在模板 formN 值中搜索关键词，返回第一个匹配的 N"""
    for m in re.finditer(r'\|form(\d+)=(.+)', tpl):
        if keyword in m.group(2):
            return int(m.group(1))
    return None


# ── 后缀规则 ──

SUFFIX_RULES = [
    ('-mega-x', '超级', 'Ｘ'),
    ('-mega-y', '超级', 'Ｙ'),
    ('-mega-z', '超级', 'Ｚ'),
    ('-mega', '超级', None),
    ('-primal', '原始', None),
    ('-alola', '阿罗拉', None),
    ('-galar', '伽勒尔', None),
    ('-hisui', '洗翠', None),
    ('-paldea', '帕底亚', None),
    ('-gmax', '超极巨化', None),
]


def match_by_suffix(name_en, tpl):
    """从 name_en 后缀推断 wiki 形态名关键词，匹配 formN"""
    for suffix, keyword, extra in SUFFIX_RULES:
        if name_en.endswith(suffix):
            if extra:
                # 如 -mega-x → 找包含 "超级" 和 "Ｘ" 的 form
                for m in re.finditer(r'\|form(\d+)=(.+)', tpl):
                    val = m.group(2)
                    if keyword in val and extra in val:
                        return int(m.group(1))
            else:
                fid = find_form_id_by_keyword(tpl, keyword)
                if fid is not None:
                    return fid
    return None


# ── LLM 调用 ──

def load_llm_config():
    """从 api/.env 加载 DeepSeek 配置"""
    env_vars = {}
    env_path = os.path.normpath(ENV_FILE)
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                env_vars[k.strip()] = v.strip()

    def get(key, default=None):
        return os.getenv(key) or env_vars.get(key) or default

    api_key = get('LLM_TOOL_USE_API_KEY') or get('LLM_API_KEY') or get('DEEPSEEK_API_KEY')
    base_url = get('LLM_TOOL_USE_BASE_URL') or get('LLM_BASE_URL') or 'https://api.deepseek.com'
    model = get('LLM_MODEL_TOOL_USE') or get('LLM_MODEL') or 'deepseek-chat'

    return api_key, base_url, model


def call_llm(api_key, base_url, model, name_zh, name_en, tpl):
    """调用 LLM 解析形态名和形态相关字段"""
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(60, connect=10),
    )

    # 只提取 form/height/weight/expyield 相关行，减少 token
    tpl_lines = []
    for line in tpl.split('\n'):
        if re.match(r'\|(form\d+|height\d*|weight\d*|expyield\d*)=', line):
            tpl_lines.append(line.strip())
    tpl_short = '\n'.join(tpl_lines)

    prompt = f"""Wiki模板（form定义+数据）：
{tpl_short}

DB形态「{name_zh}」（{name_en}）在模板中对应哪个formN？返回该形态的身高(米)、体重(公斤)、基础经验值。
只返回JSON：{{"wiki_form_name":"xxx","form_id":0,"height":0.0,"weight":0.0,"base_exp":null}}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "system", "content": "你是宝可梦数据提取助手。只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()
        # 提取 JSON
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f'  LLM 调用失败: {e}')
    return None


# ── 主流程 ──

def main():
    print('=== Step 1: pokemons 补列 ===\n')

    # Phase 0: 加载数据
    print('加载 wiki 索引...')
    wiki_pages, zh_redirects, en_to_zh, form_alias_map = load_wiki_index()
    print(f'  wiki_pages: {len(wiki_pages)}, zh_redirects: {len(zh_redirects)}, '
          f'en_to_zh: {len(en_to_zh)}, form_alias_map: {len(form_alias_map)}')

    # 连接 DB
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()

    # Phase 1: ALTER TABLE
    print('\nPhase 1: ALTER TABLE 新增 9 列...')
    new_cols = [
        ('species', 'TEXT'),
        ('egg_group1', 'TEXT'),
        ('egg_group2', 'TEXT'),
        ('gender_ratio', 'INTEGER'),
        ('catch_rate', 'INTEGER'),
        ('base_exp', 'INTEGER'),
        ('color', 'TEXT'),
        ('ev_yield', 'TEXT'),
        ('height_m', 'REAL'),
        ('weight_kg', 'REAL'),
    ]
    # 获取已有列
    cur.execute('PRAGMA table_info(pokemons)')
    existing_cols = {r[1] for r in cur.fetchall()}

    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cur.execute(f'ALTER TABLE pokemons ADD COLUMN {col_name} {col_type}')
            print(f'  + {col_name} {col_type}')
        else:
            print(f'  = {col_name} 已存在')
    conn.commit()

    # Phase 1: 提取形态无关字段
    print('\nPhase 1: 提取形态无关字段...')
    cur.execute('SELECT id, name_en, name_zh, pokedex_id, is_default_form FROM pokemons')
    all_pokemon = cur.fetchall()

    # 按 pokedex_id 分组
    pokedex_groups = {}
    for pid, name_en, name_zh, pdex, is_default in all_pokemon:
        pokedex_groups.setdefault(pdex, []).append((pid, name_en, name_zh, is_default))

    # 读 wiki 并提取
    content_cache = {}
    form_indep_data = {}  # pokedex_id -> form_independent fields
    default_form_info = {}  # pokedex_id -> (fpath, tpl)

    matched_files = 0
    for pid, name_en, name_zh, pdex, is_default in all_pokemon:
        if not is_default:
            continue
        fpath = find_wiki_file(name_en, name_zh, wiki_pages, zh_redirects, en_to_zh)
        if not fpath:
            print(f'  未匹配: {name_en} ({name_zh})')
            continue
        matched_files += 1

        if fpath not in content_cache:
            with open(fpath, 'r', encoding='utf-8') as f:
                content_cache[fpath] = f.read()
        content = content_cache[fpath]
        tpl = extract_template(content)
        if not tpl:
            print(f'  无模板: {name_en} ({fpath})')
            continue

        fields = extract_form_independent(tpl)
        form_indep_data[pdex] = fields
        default_form_info[pdex] = (fpath, tpl)

    print(f'  匹配到文件: {matched_files}')
    print(f'  提取到数据: {len(form_indep_data)} 个 pokedex_id')

    # 写入形态无关字段（所有形态共享）
    update_count = 0
    for pdex, fields in form_indep_data.items():
        for pid, name_en, name_zh, is_default in pokedex_groups[pdex]:
            cur.execute('''UPDATE pokemons SET
                species=?, egg_group1=?, egg_group2=?, gender_ratio=?,
                catch_rate=?, color=?, ev_yield=?
                WHERE id=?''',
                (fields['species'], fields['egg_group1'], fields['egg_group2'],
                 fields['gender_ratio'], fields['catch_rate'], fields['color'],
                 fields['ev_yield'], pid))
            update_count += 1
    conn.commit()
    print(f'  更新 {update_count} 条记录')

    # Phase 2: 形态相关字段
    print('\nPhase 2: 形态相关字段...')
    llm_needed = []  # 需要 LLM 处理的形态

    default_updated = 0
    form_matched = 0

    for pid, name_en, name_zh, pdex, is_default in all_pokemon:
        if pdex not in default_form_info:
            continue
        fpath, tpl = default_form_info[pdex]

        if is_default:
            # base form: 取无后缀字段
            dep = extract_form_dependent(tpl, form_id=None)
            cur.execute('UPDATE pokemons SET height_m=?, weight_kg=?, base_exp=? WHERE id=?',
                        (dep['height_m'], dep['weight_kg'], dep['base_exp'], pid))
            default_updated += 1
        else:
            form_id = None

            # 1. 查 form_alias_map（wiki_redirects 中的形态别名）
            wiki_form_name = form_alias_map.get(name_zh)
            if wiki_form_name:
                form_id = find_form_id_by_name(tpl, wiki_form_name)

            # 2. 后缀规则匹配
            if form_id is None:
                form_id = match_by_suffix(name_en, tpl)

            if form_id is not None:
                dep = extract_form_dependent(tpl, form_id)
                cur.execute('UPDATE pokemons SET height_m=?, weight_kg=?, base_exp=? WHERE id=?',
                            (dep['height_m'], dep['weight_kg'], dep['base_exp'], pid))
                form_matched += 1
            else:
                llm_needed.append((pid, name_en, name_zh, pdex, tpl))

    conn.commit()
    print(f'  default form 更新: {default_updated}')
    print(f'  非 default 规则匹配: {form_matched}')
    print(f'  需要 LLM 处理: {len(llm_needed)}')

    # Phase 3: LLM 兜底
    if llm_needed:
        print(f'\nPhase 3: LLM 处理 {len(llm_needed)} 个形态...')
        api_key, base_url, model = load_llm_config()
        if not api_key:
            print('  错误: 未找到 LLM API Key，跳过 LLM 处理')
        else:
            print(f'  使用模型: {model} @ {base_url}')
            llm_success = 0
            llm_fail = 0

            # 连接 wiki_meta.db 用于写回 form alias
            wiki_conn = sqlite3.connect(WIKI_META_DB)
            wiki_cur = wiki_conn.cursor()

            for i, (pid, name_en, name_zh, pdex, tpl) in enumerate(llm_needed):
                print(f'  [{i+1}/{len(llm_needed)}] {name_zh} ({name_en})...', end=' ')

                result = call_llm(api_key, base_url, model, name_zh, name_en, tpl)
                if result and result.get('form_id'):
                    form_id = result['form_id']
                    wiki_form_name = result.get('wiki_form_name', '')

                    # 从模板提取该 form 的值作为 fallback
                    dep = extract_form_dependent(tpl, form_id)
                    height = result.get('height') or dep['height_m']
                    weight = result.get('weight') or dep['weight_kg']
                    base_exp = result.get('base_exp') if result.get('base_exp') is not None else dep['base_exp']

                    cur.execute('UPDATE pokemons SET height_m=?, weight_kg=?, base_exp=? WHERE id=?',
                                (height, weight, base_exp, pid))

                    # 写回 wiki_redirects（target_page_id=0 表示形态别名）
                    if wiki_form_name:
                        wiki_cur.execute(
                            "INSERT OR REPLACE INTO wiki_redirects (source_title, target_page_id, target_title) VALUES (?, 0, ?)",
                            (wiki_form_name, name_zh))
                        form_alias_map[name_zh] = wiki_form_name

                    llm_success += 1
                    print(f'OK → {wiki_form_name} (f{form_id})')
                else:
                    llm_fail += 1
                    print(f'LLM 未返回有效结果: {result}')

            wiki_conn.commit()
            wiki_conn.close()
            conn.commit()

            print(f'  LLM 成功: {llm_success}, 失败: {llm_fail}')

    conn.commit()
    conn.close()

    # 验证
    print('\n=== 验证 ===')
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()
    for col in ['species', 'egg_group1', 'gender_ratio', 'catch_rate', 'color', 'ev_yield', 'height_m', 'weight_kg', 'base_exp']:
        cur.execute(f'SELECT count(*) FROM pokemons WHERE {col} IS NOT NULL')
        print(f'  {col}: {cur.fetchone()[0]} / 1350')
    conn.close()

    print('\n完成!')


if __name__ == '__main__':
    main()
