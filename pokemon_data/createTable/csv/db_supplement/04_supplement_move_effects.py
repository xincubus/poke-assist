"""
Step 4: 补全 moves 表的 effect_zh（101 条）
从 wiki wikitext 的 ==招式附加效果== section 提取，展开模板语法为纯中文文本。

匹配策略：复用 Step 2 的 6 轮匹配 + 3 条特例。
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

# ── 特例映射 ──
SPECIAL_MAP = {
    '究极无敌大冲撞': '全力無雙激烈拳',
    '毁天灭地巨岩坠': '極速俯衝轟烈撞',
    '冲岩':          '衝岩',
}


def load_wiki_index():
    conn = sqlite3.connect(WIKI_META_DB)
    cur = conn.cursor()
    cur.execute('SELECT title, file_path FROM wiki_pages WHERE file_path IS NOT NULL')
    pages_map = {t: f for t, f in cur.fetchall() if t and f}
    cur.execute('SELECT source_title, target_title FROM wiki_redirects')
    redir_map = {s: t for s, t in cur.fetchall() if s and t}
    conn.close()
    return pages_map, redir_map


def match_move(name_zh, pages_map, redir_map, cc):
    if not name_zh:
        return None
    lookup = SPECIAL_MAP.get(name_zh, name_zh)

    key = f'{lookup}（招式）'
    fpath = pages_map.get(key)
    if fpath and os.path.exists(fpath):
        return fpath

    fpath = pages_map.get(lookup)
    if fpath and os.path.exists(fpath):
        return fpath

    for k in [key, lookup]:
        if k in redir_map:
            fpath = pages_map.get(redir_map[k])
            if fpath and os.path.exists(fpath):
                return fpath

    for k in [key, lookup]:
        if k in redir_map:
            tgt = redir_map[k]
            for suffix in ['（招式）', '']:
                fpath = pages_map.get(f'{tgt}{suffix}')
                if fpath and os.path.exists(fpath):
                    return fpath

    trad = cc.convert(lookup)
    if trad != lookup:
        fpath = pages_map.get(f'{trad}（招式）')
        if fpath and os.path.exists(fpath):
            return fpath
        fpath = pages_map.get(trad)
        if fpath and os.path.exists(fpath):
            return fpath

    return None


# ── 模板展开 ──

def expand_templates(text):
    """展开 wikitext 模板为纯中文文本"""

    # 招式效果/中毒: {{招式效果/中毒|30}} 或 {{招式效果/中毒||剧毒}}
    def _中毒(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if len(args) > 0 and args[0].strip() else ''
        variant = args[1].strip() if len(args) > 1 and args[1].strip() else ''
        if variant:
            return f'使目标陷入{variant}状态'
        return f'有{pct}%几率使目标陷入中毒状态' if pct else '使目标陷入中毒状态'

    # 招式效果/灼伤
    def _灼伤(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args and args[0].strip() else ''
        return f'有{pct}%几率使目标陷入灼伤状态' if pct else '使目标陷入灼伤状态'

    # 招式效果/麻痹
    def _麻痹(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args and args[0].strip() else ''
        return f'有{pct}%几率使目标陷入麻痹状态' if pct else '使目标陷入麻痹状态'

    # 招式效果/睡眠
    def _睡眠(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args and args[0].strip() else ''
        return f'有{pct}%几率使目标陷入睡眠状态' if pct else '使目标陷入睡眠状态'

    # 招式效果/混乱
    def _混乱(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args and args[0].strip() else ''
        return f'有{pct}%几率使目标陷入混乱状态' if pct else '使目标陷入混乱状态'

    # 招式效果/畏缩
    def _畏缩(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args and args[0].strip() else ''
        return f'有{pct}%几率使目标畏缩' if pct else '使目标畏缩'

    # 招式效果/能力提升: {{招式效果/能力提升|攻击}} 或 {{招式效果/能力提升|速度|2}}
    def _能力提升(m):
        args = m.group(1).split('|') if m.group(1) else []
        stat = args[0].strip() if args else ''
        lvl = args[1].strip() if len(args) > 1 and args[1].strip() else '1'
        return f'提升使用者的{stat}{lvl}级'

    # 招式效果/能力降低: {{招式效果/能力降低|攻擊|1|30}} 或 {{招式效果/能力降低|防御|1||使用者}}
    def _能力降低(m):
        args = m.group(1).split('|') if m.group(1) else []
        stat = args[0].strip() if args else ''
        lvl = args[1].strip() if len(args) > 1 and args[1].strip() else '1'
        pct = args[2].strip() if len(args) > 2 and args[2].strip() else ''
        target = args[3].strip() if len(args) > 3 and args[3].strip() else '目标'
        if pct:
            return f'有{pct}%几率降低{target}的{stat}{lvl}级'
        return f'降低{target}的{stat}{lvl}级'

    # 招式效果/保护
    def _保护(m):
        args = m.group(1).split('|') if m.group(1) else []
        variant = args[0].strip() if args and args[0].strip() else ''
        if variant:
            return f'进入守住状态，保护自己不受到{variant}招式的伤害'
        return '进入守住状态'

    # 招式效果/必中
    def _必中(m):
        return '该招式必定命中'

    # 招式效果/天气影响: {{招式效果/天气影响|大晴天|炽热岩石}}
    def _天气影响(m):
        args = m.group(1).split('|') if m.group(1) else []
        weather = args[0].strip() if args else ''
        rock = args[1].strip() if len(args) > 1 and args[1].strip() else ''
        text = f'召唤{weather}天气，持续5回合'
        if rock:
            text += f'；携带{rock}时持续8回合'
        return text

    # 招式效果/回复ＨＰ: {{招式效果/回复ＨＰ|50}} 或 {{招式效果/回复ＨＰ|25|使用者和同伴|异常=y}}
    def _回复HP(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args else ''
        who = args[1].strip() if len(args) > 1 and args[1].strip() else '使用者'
        cure = '异常=y' in (m.group(1) or '')
        text = f'回复{who}最大ＨＰ的{pct}%'
        if cure:
            text += '，并治愈异常状态'
        return text

    # 招式效果/吸取: {{招式效果/吸取|50}}
    def _吸取(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args else '50'
        return f'回复造成伤害{pct}%的ＨＰ'

    # 招式效果/击中要害
    def _击中要害(m):
        args = m.group(1).split('|') if m.group(1) else []
        lvl = args[0].strip() if args and args[0].strip() else ''
        if lvl:
            return f'更容易击中要害（+{lvl}级）'
        return '容易击中要害'

    # 招式效果/连续: {{招式效果/连续|2～5|物理||15}}
    def _连续(m):
        args = m.group(1).split('|') if m.group(1) else []
        times = args[0].strip() if args else ''
        return f'连续攻击{times}次'

    # 招式效果/不能连续使用
    def _不能连续使用(m):
        args = m.group(1).split('|') if m.group(1) else []
        name = args[0].strip() if args else ''
        return f'连续使用{ name}会失败' if name else '连续使用会失败'

    # 招式效果/多种异常: {{招式效果/多种异常|50|中毒|麻痹|睡眠}}
    def _多种异常(m):
        args = m.group(1).split('|') if m.group(1) else []
        pct = args[0].strip() if args else ''
        statuses = [a.strip() for a in args[1:] if a.strip()]
        status_str = '、'.join(statuses)
        return f'有{pct}%几率使目标陷入{status_str}之一' if pct else f'使目标陷入{status_str}之一'

    # 招式效果/属性变更
    def _属性变更(m):
        args = m.group(1).split('|') if m.group(1) else []
        typ = args[0].strip() if args else ''
        return f'将目标的属性变为{typ}属性'

    # 招式效果/固定伤害
    def _固定伤害(m):
        desc = m.group(1).strip() if m.group(1) else ''
        return f'造成固定伤害：{desc}'

    # 招式效果/蓄力
    def _蓄力(m):
        args = m.group(1).split('|') if m.group(1) else []
        # 取第2个参数作为描述（第1个是内部标识）
        desc = args[1].strip() if len(args) > 1 and args[1].strip() else '需要蓄力一回合'
        return desc

    # 招式效果/反作用力伤害
    def _反作用力伤害(m):
        args = m.group(1).split('|') if m.group(1) else []
        denom = args[0].strip() if args else ''
        return f'使用者受到最大ＨＰ的1/{denom}的反作用力伤害'

    # 招式效果/飞膝踢
    def _飞膝踢(m):
        return '如果未命中，使用者受到最大ＨＰ的1/2的反作用力伤害'

    # 招式效果/盐腌
    def _盐腌(m):
        return '使目标陷入盐腌状态，每回合受到伤害'

    # 招式效果/解冻
    def _解冻(m):
        return '解除使用者的冰冻状态'

    # 招式效果/威力翻倍
    def _威力翻倍(m):
        cond = m.group(1).strip() if m.group(1) else ''
        return f'在{cond}时威力翻倍' if cond else '威力翻倍'

    # 招式效果/多回合攻击
    def _多回合攻击(m):
        args = m.group(1).split('|') if m.group(1) else []
        times = args[0].strip() if args else ''
        return f'连续攻击{times}回合'

    # 按模板名分发
    handlers = {
        '中毒': _中毒,
        '灼伤': _灼伤,
        '麻痹': _麻痹,
        '睡眠': _睡眠,
        '混乱': _混乱,
        '畏缩': _畏缩,
        '能力提升': _能力提升,
        '能力降低': _能力降低,
        '保护': _保护,
        '必中': _必中,
        '天气影响': _天气影响,
        '回复ＨＰ': _回复HP,
        '吸取': _吸取,
        '击中要害': _击中要害,
        '连续': _连续,
        '不能连续使用': _不能连续使用,
        '多种异常': _多种异常,
        '属性变更': _属性变更,
        '固定伤害': _固定伤害,
        '蓄力': _蓄力,
        '反作用力伤害': _反作用力伤害,
        '飞膝踢': _飞膝踢,
        '盐腌': _盐腌,
        '解冻': _解冻,
        '威力翻倍': _威力翻倍,
        '多回合攻击': _多回合攻击,
    }

    # 展开 {{招式效果/xxx|args}}
    def replace_effect_tpl(m):
        tpl_name = m.group(1)
        args = m.group(2) or ''
        handler = handlers.get(tpl_name)
        if handler:
            # 用一个假的 match 对象传 args
            class FakeMatch:
                def __init__(self, s): self._s = s
                def group(self, n): return self._s if n == 1 else None
            return handler(FakeMatch(args))
        # 未知模板，保留原文
        return m.group(0)

    text = re.sub(r'\{\{招式效果/([^|}]+)(?:\|([^}]*))?\}\}', replace_effect_tpl, text)

    # 通用模板清理
    text = re.sub(r'\{\{main\|([^}]*)\}\}', r'\1', text)          # {{main|xxx}} → xxx
    text = re.sub(r'\{\{m\|([^}]*)\}\}', r'\1', text)             # {{m|招式名}} → 招式名
    text = re.sub(r'\{\{a\|([^}]*)\}\}', r'\1', text)             # {{a|特性名}} → 特性名
    text = re.sub(r'\{\{s\|([^}]*)\}\}', r'\1', text)             # {{s|状态名}} → 状态名
    text = re.sub(r'\{\{i\|([^}]*)\}\}', r'\1', text)             # {{i|道具名}} → 道具名
    text = re.sub(r'\{\{type\|([^}]*)\}\}', r'\1属性', text)      # {{type|火}} → 火属性
    text = re.sub(r'\{\{frac\|([^}]*)\|([^}]*)\}\}', r'\1/\2', text)  # {{frac|1|8}} → 1/8
    text = re.sub(r'\{\{tt\|([^}]*)\|([^}]*)\}\}', r'\1', text)   # {{tt|显示|提示}} → 显示
    text = re.sub(r'\{\{sup/[^}]*\}\}', '', text)                 # {{sup/3|RSEFRLG}} → 删除
    text = re.sub(r'\{\{S\}\}', '', text)                          # {{S}} → 删除
    text = re.sub(r'\{\{MSP[^}]*\}\}', '', text)                  # {{MSP|...}} → 删除
    text = re.sub(r'\{\{NBPAGENAME\}\}', '', text)                # {{NBPAGENAME}} → 删除
    text = re.sub(r'\{\{形态变化\}\}', '形态变化', text)           # {{形态变化}} → 形态变化
    text = re.sub(r'\{\{\$\}\}', '$', text)                        # {{$}} → $

    # 链接清理
    text = re.sub(r'\[\[([^\]]*?\|)?([^\]]*?)\]\]', r'\2', text)  # [[a|b]] → b

    # 标记清理
    text = re.sub(r"'''?", '', text)

    # 参考文献
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r'<ref[^>]*/>', '', text)

    # HTML 注释
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # 清理残留的 {{}}（未知模板）
    text = re.sub(r'\{\{[^}]*\}\}', '', text)

    # 压缩空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def extract_effect(content):
    """从 wikitext 提取 ==招式附加效果== section 并展开模板"""
    m = re.search(r'==\s*招式附加效果\s*==\s*\n(.*?)(?:\n==|\Z)', content, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    return expand_templates(raw)


# ── 主流程 ──

def main():
    print('=== Step 4: moves 补 effect_zh ===\n')

    from opencc import OpenCC
    cc = OpenCC('s2t')

    # Phase 1: 加载索引
    print('Phase 1: 加载 wiki 索引...')
    pages_map, redir_map = load_wiki_index()
    print(f'  pages_map: {len(pages_map)}, redir_map: {len(redir_map)}')

    # Phase 2: 读 effect_zh 为空的招式
    conn = sqlite3.connect(POKEMON_DB)
    cur = conn.cursor()
    cur.execute('SELECT id, name_en, name_zh FROM moves WHERE effect_zh IS NULL OR effect_zh = \"\"')
    null_moves = cur.fetchall()
    print(f'\nPhase 2: effect_zh 为空: {len(null_moves)}')

    # Phase 3 + 4: 匹配 + 提取
    print('\nPhase 3: 匹配 + 提取...')
    updated = 0
    no_match = 0
    no_effect = 0
    examples = []

    for mid, name_en, name_zh in null_moves:
        fpath = match_move(name_zh, pages_map, redir_map, cc)
        if not fpath:
            no_match += 1
            continue

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        effect = extract_effect(content)
        if not effect:
            no_effect += 1
            continue

        cur.execute('UPDATE moves SET effect_zh = ? WHERE id = ?', (effect, mid))
        updated += 1

        if len(examples) < 10:
            examples.append((mid, name_zh, effect[:100]))

    conn.commit()

    print(f'  更新: {updated}')
    print(f'  未匹配: {no_match}')
    print(f'  无效果 section: {no_effect}')

    print('\n=== 更新样例 ===')
    for mid, nz, eff in examples:
        print(f'  {mid} {nz}: {eff}')

    # Phase 5: 验证
    print('\n=== 验证 ===')
    cur.execute('SELECT count(*) FROM moves WHERE effect_zh IS NULL OR effect_zh = \"\"')
    remaining = cur.fetchone()[0]
    print(f'  effect_zh 为空: {remaining} (应为 18 暗影招式)')

    cur.execute('SELECT count(*) FROM moves WHERE effect_zh IS NOT NULL AND effect_zh != \"\"')
    filled = cur.fetchone()[0]
    print(f'  effect_zh 有值: {filled}/937')

    conn.close()
    print('\n完成!')


if __name__ == '__main__':
    main()
