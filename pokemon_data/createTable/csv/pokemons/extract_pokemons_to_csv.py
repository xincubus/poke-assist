"""
从 pokemon_data/pokemon/ 目录下的 JSON 文件提取宝可梦数据，生成 pokemons.csv
输出字段：pokedex_id, pokeapi_id, name_en, name_zh, name_ja, is_default_form,
          type1, type2, ability1_name, ability2_name, hidden_ability_name,
          weight_kg, hp, attack, defense, sp_attack, sp_defense, speed, total_stats,
          description_zh, description_en, description_ja
"""

import json
import csv
import os
from pathlib import Path

POKEMON_DIR = Path(__file__).parent.parent.parent.parent / 'pokemon'
OUTPUT_CSV  = Path(__file__).parent / 'pokemons.csv'

REGIONAL_FORMS = {
    'alola': ['sun', 'moon', 'ultra-sun', 'ultra-moon'],
    'galar': ['sword', 'shield', 'isle-of-armor', 'crown-tundra'],
    'hisui': ['legends-arceus'],
    'paldea': ['scarlet', 'violet', 'the-teal-mask', 'the-indigo-disk'],
}

FIELDNAMES = [
    'pokedex_id', 'pokeapi_id', 'name_en', 'name_zh', 'name_ja', 'is_default_form',
    'type1', 'type2', 'ability1_name', 'ability2_name', 'hidden_ability_name',
    'weight_kg', 'hp', 'attack', 'defense', 'sp_attack', 'sp_defense', 'speed', 'total_stats',
    'image_official_artwork',
    'description_zh', 'description_en', 'description_ja',
]

# 形态后缀翻译（中文、日文）
FORM_TRANSLATIONS = {
    '-alola':       {'zh': '（阿罗拉的样子）', 'ja': '（アローラのすがた）'},
    '-galar':       {'zh': '（伽勒尔的样子）', 'ja': '（ガラルのすがた）'},
    '-hisui':       {'zh': '（洗翠的样子）',   'ja': '（ヒスイのすがた）'},
    '-paldea':      {'zh': '（帕底亚的样子）', 'ja': '（パルデアのすがた）'},
    '-mega-x':      {'zh': '（超级进化X）',    'ja': '（メガシンカX）'},
    '-mega-y':      {'zh': '（超级进化Y）',    'ja': '（メガシンカY）'},
    '-mega':        {'zh': '（超级进化）',     'ja': '（メガシンカ）'},
    '-gigantamax':  {'zh': '（超极巨化）',     'ja': '（キョダイマックス）'},
    '-gmax':        {'zh': '（超极巨化）',     'ja': '（キョダイマックス）'},
    '-incarnate':   {'zh': '（化身形态）',     'ja': '（けしんフォルム）'},
    '-therian':     {'zh': '（灵兽形态）',     'ja': '（れいじゅうフォルム）'},
    '-crowned':     {'zh': '（加冕形态）',     'ja': '（かんむりのすがた）'},
}

FORM_OVERRIDES = {
    'eiscue-ice':      {'zh': '（结冻头）',   'ja': '（アイスフェイス）'},
    'zacian-crowned':  {'zh': '（剑之王）',   'ja': '（けんのおう）'},
    'zamazenta-crowned': {'zh': '（盾之王）', 'ja': '（たてのおう）'},
}

DEFAULT_FORM_OVERRIDES = {
    'zacian':    {'zh': '（百战勇者）', 'ja': '（れきせんのゆうしゃ）'},
    'zamazenta': {'zh': '（百战勇者）', 'ja': '（れきせんのゆうしゃ）'},
}

BASE_SUFFIXES = sorted([
    '-mega-x', '-mega-y', '-mega', '-alola', '-galar', '-hisui', '-paldea',
    '-gigantamax', '-gmax', '-male', '-female', '-standard', '-altered',
    '-incarnate', '-aria', '-shield', '-average', '-midday', '-ordinary',
    '-land', '-red-striped', '-disguised', '-solo', '-full-belly', '-ice',
    '-blade', '-normal', '-red-meteor', '-baile', '-zero', '-plant', '-50',
    '-single-strike', '-curly', '-green-plumage', '-amped', '-two-segment',
    '-family-of-four', '-rapid-strike', '-shadow', '-bloodmoon',
], key=len, reverse=True)


def get_name(names, lang):
    for entry in names:
        if entry['language']['name'] == lang:
            return entry['name']
    return ''


def get_flavor_text(entries, lang, regional_form=None):
    versions = REGIONAL_FORMS.get(regional_form, []) if regional_form else []
    if versions:
        for entry in entries:
            if entry['language']['name'] == lang and entry['version']['name'] in versions:
                return entry['flavor_text'].replace('\n', ' ').replace('\f', ' ')
    result = ''
    for entry in entries:
        if entry['language']['name'] == lang:
            result = entry['flavor_text'].replace('\n', ' ').replace('\f', ' ')
    return result


def get_base_name(pokemon_name):
    name = pokemon_name.lower()
    for suffix in BASE_SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def get_regional_form(pokemon_name):
    name = pokemon_name.lower()
    for region in ('alola', 'galar', 'hisui', 'paldea'):
        if f'-{region}' in name:
            return region
    return None


def resolve_form_suffix(suffix, full_name):
    if full_name in FORM_OVERRIDES:
        return FORM_OVERRIDES[full_name]
    sorted_keys = sorted(FORM_TRANSLATIONS.keys(), key=len, reverse=True)
    remaining = suffix
    zh_parts, ja_parts = [], []
    while remaining:
        matched = False
        for k in sorted_keys:
            if remaining.endswith(k):
                zh_parts.insert(0, FORM_TRANSLATIONS[k]['zh'].strip('（）'))
                ja_parts.insert(0, FORM_TRANSLATIONS[k]['ja'].strip('（）'))
                remaining = remaining[:-len(k)]
                matched = True
                break
        if not matched:
            break
    if zh_parts and not remaining:
        return {'zh': f'（{" ".join(zh_parts)}）', 'ja': f'（{" ".join(ja_parts)}）'}
    return {'zh': suffix, 'ja': suffix}


def extract():
    json_files = [f for f in os.listdir(POKEMON_DIR)
                  if f.endswith('.json') and not f.endswith('_species.json')]
    print(f'找到 {len(json_files)} 个宝可梦 JSON 文件')

    rows = []
    skipped = 0

    for filename in json_files:
        pokemon_name = filename[:-5]  # strip .json
        pokemon_path = POKEMON_DIR / filename
        species_path = POKEMON_DIR / f'{pokemon_name}_species.json'

        if not species_path.exists():
            base = get_base_name(pokemon_name)
            species_path = POKEMON_DIR / f'{base}_species.json'
            if not species_path.exists():
                print(f'  跳过 {pokemon_name}：找不到 species 文件')
                skipped += 1
                continue

        with open(pokemon_path, encoding='utf-8') as f:
            poke = json.load(f)
        with open(species_path, encoding='utf-8') as f:
            species = json.load(f)

        pokeapi_id  = poke.get('id', '')
        is_default  = poke.get('is_default', False)

        # 图鉴编号
        pokedex_id = ''
        for entry in species.get('pokedex_numbers', []):
            if entry['pokedex']['name'] == 'national':
                pokedex_id = entry['entry_number']
                break

        # 名称
        names_list = species.get('names', [])
        name_en = poke.get('name', get_name(names_list, 'en'))
        name_zh = get_name(names_list, 'zh-hans')
        name_ja = get_name(names_list, 'ja')

        # 形态后缀处理
        species_name = species.get('name', '')
        varieties = species.get('varieties', [])
        default_variety = next((v['pokemon']['name'] for v in varieties if v.get('is_default')), '')

        if pokemon_name == species_name == default_variety:
            # 默认形态，检查是否需要 override
            if pokemon_name in DEFAULT_FORM_OVERRIDES:
                ov = DEFAULT_FORM_OVERRIDES[pokemon_name]
                name_zh += ov['zh']
                name_ja += ov['ja']
        else:
            # 特殊形态，提取后缀
            if pokemon_name != species_name and pokemon_name.startswith(species_name + '-'):
                suffix = pokemon_name[len(species_name):]
            elif pokemon_name == species_name and default_variety.startswith(species_name + '-'):
                suffix = default_variety[len(species_name):]
            else:
                suffix = None
            if suffix:
                trans = resolve_form_suffix(suffix, pokemon_name)
                name_zh += trans['zh']
                name_ja += trans['ja']

        # 属性
        types = poke.get('types', [])
        type1 = types[0]['type']['name'] if types else ''
        type2 = types[1]['type']['name'] if len(types) > 1 else ''

        # 特性
        ability1 = ability2 = hidden_ability = ''
        for ab in poke.get('abilities', []):
            if ab['is_hidden']:
                hidden_ability = ab['ability']['name']
            elif ab['slot'] == 1:
                ability1 = ab['ability']['name']
            elif ab['slot'] == 2:
                ability2 = ab['ability']['name']

        # 体重
        weight_kg = poke.get('weight', 0) / 10

        # 种族值
        stat_dict = {s['stat']['name']: s['base_stat'] for s in poke.get('stats', [])}
        hp         = stat_dict.get('hp', 0)
        attack     = stat_dict.get('attack', 0)
        defense    = stat_dict.get('defense', 0)
        sp_attack  = stat_dict.get('special-attack', 0)
        sp_defense = stat_dict.get('special-defense', 0)
        speed      = stat_dict.get('speed', 0)
        total      = hp + attack + defense + sp_attack + sp_defense + speed

        # 图鉴说明
        regional_form = get_regional_form(pokemon_name)
        flavor = species.get('flavor_text_entries', [])
        desc_zh = get_flavor_text(flavor, 'zh-hans', regional_form)
        desc_en = get_flavor_text(flavor, 'en', regional_form)
        desc_ja = get_flavor_text(flavor, 'ja', regional_form)

        rows.append({
            'pokedex_id':      pokedex_id,
            'pokeapi_id':      pokeapi_id,
            'name_en':         name_en,
            'name_zh':         name_zh,
            'name_ja':         name_ja,
            'is_default_form': 1 if is_default else 0,
            'type1':           type1,
            'type2':           type2,
            'ability1_name':   ability1,
            'ability2_name':   ability2,
            'hidden_ability_name': hidden_ability,
            'weight_kg':       weight_kg,
            'hp':              hp,
            'attack':          attack,
            'defense':         defense,
            'sp_attack':       sp_attack,
            'sp_defense':      sp_defense,
            'speed':           speed,
            'total_stats':     total,
            'description_zh':  desc_zh,
            'description_en':  desc_en,
            'description_ja':  desc_ja,
            'image_official_artwork': (
                f"pokemonImage/{pokeapi_id:03d}-{name_en}-officialArtwork.png"
                if pokeapi_id < 1000 else
                f"pokemonImage/{pokeapi_id}-{name_en}-officialArtwork.png"
            ),
        })

    # 按图鉴编号排序
    rows.sort(key=lambda r: (int(r['pokedex_id']) if r['pokedex_id'] else 9999, int(r['pokeapi_id'])))

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f'已导出 {len(rows)} 条（跳过 {skipped} 条）到 {OUTPUT_CSV}')
    missing_zh   = sum(1 for r in rows if not r['name_zh'])
    missing_ja   = sum(1 for r in rows if not r['name_ja'])
    missing_desc = sum(1 for r in rows if not r['description_zh'])
    print(f'name_zh 缺失：{missing_zh} 条')
    print(f'name_ja 缺失：{missing_ja} 条')
    print(f'description_zh 缺失：{missing_desc} 条')


if __name__ == '__main__':
    extract()
