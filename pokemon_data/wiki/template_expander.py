"""
MediaWiki 模板递归展开引擎（分类表驱动）

四种分类来自 `wiki_templates` 表的 `category` 字段：

- semantic —— 展开 body（如 `招式效果/不能连续使用`、`招式说明/一般`）
- infobox  —— 不展开 body，只把调用参数压平成 `key: value` 行
- inline   —— 按 `param_fmt` 输出单个参数（如 `{{m|挣扎}}` → 挣扎）
- drop     —— 整个删掉（工程模板、分类链接、parser function 等）
- unknown  —— 新模板默认值，保留原始 wikitext 调用

`param_fmt` 约定：
- inline:  "$1" / "$2" / "$last" / "$name" / 模板字符串（如 "$1($2)"）
- infobox: "key_value"（默认）/ "title_only" / "drop_body"
- semantic/drop 不读这个字段

典型用法：
    from template_expander import expand
    with open('.../253994_血月（招式）.wiki', encoding='utf-8') as f:
        text = expand(f.read())
"""

import os
import re
import sqlite3
from typing import Callable, Optional

import mwparserfromhell


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(SCRIPT_DIR, "wiki_meta.db")
DEFAULT_CACHE_DIR = os.path.join(SCRIPT_DIR, "wikitext_cache")

TEMPLATE_NS_PREFIX = "Template:"
MAX_PARAM_SUB_PASSES = 5

# 分类默认值
CAT_SEMANTIC = "semantic"
CAT_INFOBOX = "infobox"
CAT_INLINE = "inline"
CAT_DROP = "drop"
CAT_UNKNOWN = "unknown"


# ============================================================
# noinclude / includeonly / onlyinclude 处理（MediaWiki 规则）
# ============================================================
_RE_ONLYINCLUDE = re.compile(r"<onlyinclude>(.*?)</onlyinclude>", re.DOTALL | re.IGNORECASE)
_RE_NOINCLUDE = re.compile(r"<noinclude>.*?</noinclude>", re.DOTALL | re.IGNORECASE)
_RE_INCLUDEONLY_OPEN = re.compile(r"<includeonly>", re.IGNORECASE)
_RE_INCLUDEONLY_CLOSE = re.compile(r"</includeonly>", re.IGNORECASE)


def normalize_template_body(body: str) -> str:
    """按 MediaWiki 模板转译规则处理原始模板 wikitext。"""
    matches = _RE_ONLYINCLUDE.findall(body)
    if matches:
        body = "".join(matches)
    else:
        body = _RE_NOINCLUDE.sub("", body)
    body = _RE_INCLUDEONLY_OPEN.sub("", body)
    body = _RE_INCLUDEONLY_CLOSE.sub("", body)
    return body


# ============================================================
# 参数替换：{{{1}}} / {{{key}}} / {{{key|default}}}
# ============================================================
_RE_PARAM = re.compile(r"\{\{\{([^{}]+?)\}\}\}")


def substitute_params(body: str, args: dict) -> str:
    def _sub(m: re.Match) -> str:
        content = m.group(1)
        if "|" in content:
            key, default = content.split("|", 1)
        else:
            key, default = content, ""
        return args.get(key.strip(), default)

    prev = None
    cur = body
    passes = MAX_PARAM_SUB_PASSES
    while prev != cur and passes > 0:
        prev = cur
        cur = _RE_PARAM.sub(_sub, cur)
        passes -= 1
    return cur


# ============================================================
# 模板名归一化（MediaWiki first-letter case）
# ============================================================
def normalize_template_name(name: str) -> str:
    """MediaWiki Template namespace 是 first-letter case —— ASCII 首字母自动大写。
    中文等非 ASCII 字符保留原样。"""
    n = name.strip()
    if not n:
        return n
    first = n[0]
    if first.isascii() and first.isalpha():
        return first.upper() + n[1:]
    return n


# ============================================================
# 分类表加载
# ============================================================
class ClassifierTable:
    """从 wiki_templates 表加载模板分类。

    表结构（由 seed_wiki_templates.py 建）：
        name TEXT PRIMARY KEY, page_id INT, file_path TEXT,
        category TEXT, param_fmt TEXT, note TEXT, updated_at TEXT
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._rows: dict = {}   # name (已 normalize) -> (category, param_fmt, file_path)
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("""
                SELECT name, COALESCE(category, ''), COALESCE(param_fmt, ''), COALESCE(file_path, '')
                FROM wiki_templates
            """)
            for name, cat, fmt, path in cur:
                self._rows[normalize_template_name(name)] = (cat or CAT_UNKNOWN, fmt, path)
            conn.close()
        except sqlite3.OperationalError:
            # 表不存在：当作全空，所有模板走 unknown 分支
            pass
        self._loaded = True

    def lookup(self, name: str) -> tuple:
        """返回 (category, param_fmt, file_path)。未命中返回 (unknown, '', '')。"""
        self._ensure_loaded()
        return self._rows.get(normalize_template_name(name), (CAT_UNKNOWN, "", ""))


# ============================================================
# inline 渲染：param_fmt 解释器
# ============================================================
_RE_POS = re.compile(r"\$(\d+|last|name)")


def render_inline(name: str, args: dict, positional_count: int, fmt: str) -> str:
    """按 param_fmt 渲染 inline 模板。

    支持 token：
        $1..$9 —— 对应位置参数
        $last —— 最后一个位置参数
        $name —— 模板名自身
    fmt 为空或不含任何 token 时，回退到"末位参数，否则模板名"。
    """
    if not fmt:
        return args.get(str(positional_count), name) if positional_count > 0 else name

    def _sub(m: re.Match) -> str:
        token = m.group(1)
        if token == "name":
            return name
        if token == "last":
            return args.get(str(positional_count), "") if positional_count > 0 else ""
        return args.get(token, "")

    return _RE_POS.sub(_sub, fmt)


# ============================================================
# infobox 渲染：参数压平成 key: value 行
# ============================================================
def render_infobox(name: str, params: list, fmt: str) -> str:
    """把 {{招式信息框|威力=140|命中=100|...}} 压成纯文本块。

    fmt 可选：
        "key_value" (默认) —— 【模板名】\n key: value 每行一条
        "title_only"      —— 只输出 【模板名】
        "drop_body"       —— 输出空串（配合外层的 drop 效果，但保留层级可读性）
    """
    if fmt == "title_only":
        return f"【{name}】\n"
    if fmt == "drop_body":
        return ""
    # key_value / 空 —— 默认
    lines = [f"【{name}】"]
    for key, value in params:
        value = value.strip()
        if not value:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


# ============================================================
# 结构化模板渲染函数
# ============================================================

def render_pokemon_infobox(name: str, params: list) -> str:
    """渲染寶可夢信息框/形態，提取关键字段输出成简洁文本。

    关键字段：名称、属性、特性、图鉴编号、身高体重、蛋组、颜色、捕获率
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    lines = []

    # 基本信息
    zh_name = args.get("name", "")
    jname = args.get("jname", "")
    enname = args.get("enname", "")
    if zh_name:
        lines.append(f"【{zh_name}】")
    if jname:
        lines.append(f"日文名: {jname}")
    if enname:
        lines.append(f"英文名: {enname}")

    # 种类
    species = args.get("species", "")
    if species:
        lines.append(f"种类: {species}")

    # 属性
    type1 = args.get("type1", "")
    type2 = args.get("type2", "")
    if type1:
        if type2 and type2 != type1:
            lines.append(f"属性: {type1}/{type2}")
        else:
            lines.append(f"属性: {type1}")

    # 特性
    ability1 = args.get("ability1", "")
    abilityd = args.get("abilityd", "")
    if ability1:
        if abilityd and abilityd != ability1:
            lines.append(f"特性: {ability1} / 隐藏特性: {abilityd}")
        else:
            lines.append(f"特性: {ability1}")

    # 图鉴编号
    ndex = args.get("ndex", "")
    if ndex:
        lines.append(f"全国图鉴: #{ndex}")

    # 身高体重
    height = args.get("height", "")
    weight = args.get("weight", "")
    if height:
        lines.append(f"身高: {height}m")
    if weight:
        lines.append(f"体重: {weight}kg")

    # 蛋组
    egggroup1 = args.get("egggroup1", "")
    egggroup2 = args.get("egggroup2", "")
    if egggroup1:
        if egggroup2:
            lines.append(f"蛋组: {egggroup1}/{egggroup2}")
        else:
            lines.append(f"蛋组: {egggroup1}")

    # 颜色
    color = args.get("color", "")
    if color:
        lines.append(f"颜色: {color}")

    # 捕获率
    catchrate = args.get("catchrate", "")
    if catchrate:
        lines.append(f"捕获率: {catchrate}")

    # 形态
    forms = []
    for i in range(1, 10):
        form = args.get(f"form{i}", "")
        if form:
            forms.append(form)
    if forms and len(forms) > 1:
        lines.append(f"形态: {', '.join(forms)}")

    return "\n".join(lines) + "\n"


def render_toggle_header(name: str, params: list) -> str:
    """渲染 Toggle/Header，只保留形态/选项名称。

    参数结构：set=分组名, [1]=选项1, [2]=选项2, ...
    注意：mwparserfromhell 把位置参数从 1 开始编号
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    set_name = args.get("set", "")
    options = []
    # 尝试从 1 开始（mwparserfromhell 的默认行为）
    for i in range(1, 20):
        opt = args.get(str(i), "")
        if opt:
            options.append(opt)

    if set_name and options:
        return f"【{set_name}: {', '.join(options)}】"
    elif set_name:
        return f"【{set_name}】"
    return ""


def render_toggle_content(name: str, params: list) -> str:
    """渲染 Toggle/Content，保留实际内容（去掉图片路径）。

    参数结构：set=分组名, [1]=内容1, [2]=内容2, ...
    注意：mwparserfromhell 把位置参数从 1 开始编号
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    set_name = args.get("set", "")

    # 提取内容（跳过图片标记）
    contents = []
    # 尝试从 1 开始（mwparserfromhell 的默认行为）
    for i in range(1, 20):
        val = args.get(str(i), "")
        if val and not val.startswith("[[File:") and not val.startswith("[[Image:"):
            contents.append(val)

    if contents:
        # 多个内容用换行分隔（如多个种族值）
        return "\n".join(contents) + "\n"
    return ""


def render_race_value(name: str, params: list) -> str:
    """渲染种族值模板，输出成简洁文本。

    参数结构：type=属性, type2=属性2, HP=xx, 攻击=xx, 防御=xx, 特攻=xx, 特防=xx, 速度=xx
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    type1 = args.get("type", "")
    type2 = args.get("type2", "")
    hp = args.get("HP", "0")
    atk = args.get("攻击", "0")
    defe = args.get("防御", "0")
    spa = args.get("特攻", "0")
    spd = args.get("特防", "0")
    spe = args.get("速度", "0")
    # 第一世代有"特殊"字段
    spc = args.get("特殊", "")

    lines = []
    if type1:
        if type2:
            lines.append(f"【种族值】属性: {type1}/{type2}")
        else:
            lines.append(f"【种族值】属性: {type1}")
    else:
        lines.append("【种族值】")

    # 计算总和
    try:
        total = int(hp) + int(atk) + int(defe) + int(spa) + int(spd) + int(spe)
        if spc:
            total += int(spc)
    except ValueError:
        total = 0

    if spc:
        # 第一世代：HP | 攻击 | 防御 | 特殊 | 速度
        lines.append(f"HP: {hp} | 攻击: {atk} | 防御: {defe} | 特殊: {spc} | 速度: {spe}")
    else:
        lines.append(f"HP: {hp} | 攻击: {atk} | 防御: {defe} | 特攻: {spa} | 特防: {spd} | 速度: {spe}")
    if total > 0:
        lines.append(f"总和: {total}")

    return "\n".join(lines) + "\n"


def render_type_effectiveness_header(name: str, params: list) -> str:
    """渲染属性相性/header，输出属性类型。"""
    args = {}
    for key, value in params:
        args[key] = value.strip()

    type1 = args.get("type", "")
    if type1:
        return f"【属性相性】{type1}"
    return "【属性相性】"


def render_type_effectiveness_entry(name: str, params: list) -> str:
    """渲染属性相性/entry，输出各属性的倍率。

    参数结构：type=属性, sp=特性, 各属性=倍率
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    type1 = args.get("type", "")
    sp = args.get("sp", "")

    # 18 个属性
    types = ["一般", "格斗", "飞行", "毒", "地面", "岩石", "虫", "幽灵",
             "钢", "火", "水", "草", "电", "超能力", "冰", "龙", "恶", "妖精"]

    # 按倍率分组
    weak = []      # 2x 或 4x
    resist = []    # 0.5x 或 0.25x
    immune = []    # 0x

    for t in types:
        mult = args.get(t, "1")
        try:
            m = float(mult)
        except ValueError:
            m = 1.0

        if m == 0:
            immune.append(t)
        elif m >= 2:
            weak.append(f"{t}({mult}x)")
        elif m <= 0.5:
            resist.append(f"{t}({mult}x)")

    lines = []
    if sp and sp != "none" and sp != "yes":
        lines.append(f"特性: {sp}")
    if weak:
        lines.append(f"弱点: {', '.join(weak)}")
    if resist:
        lines.append(f"抗性: {', '.join(resist)}")
    if immune:
        lines.append(f"免疫: {', '.join(immune)}")

    return " | ".join(lines) + "\n" if lines else ""


def render_obtain_header(name: str, params: list) -> str:
    """渲染获得方式/header。"""
    args = {}
    for i, (key, value) in enumerate(params):
        args[str(i + 1)] = value.strip()

    type1 = args.get("1", "")
    type2 = args.get("2", "")
    gen = args.get("3", "")

    if type1:
        return f"【获得方式】属性: {type1}/{type2} 世代: {gen}\n"
    return "【获得方式】\n"


def render_obtain_main(name: str, params: list) -> str:
    """渲染获得方式/main。

    参数结构：[1]=图鉴编号, [2]=版本, [3]=世代, [4]=版本缩写, [5]=出现方式, [6]=地点, [7]=备注
    """
    args = {}
    for i, (key, value) in enumerate(params):
        args[str(i + 1)] = value.strip()
        args[key] = value.strip()

    ndex = args.get("1", "")
    version = args.get("4", "")
    method = args.get("5", "")
    location = args.get("6", "")
    note = args.get("7", "")

    # 清理 location 中的 wiki 链接标记
    location = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', location)
    location = re.sub(r'\[\[([^\]]+)\]\]', r'\1', location)

    parts = []
    if version:
        parts.append(version)
    if location:
        parts.append(location)
    if method:
        parts.append(method)
    if note:
        parts.append(note)

    return f"  {' | '.join(parts)}\n"


def render_obtain_end(name: str, params: list) -> str:
    """渲染获得方式/end。"""
    return ""


def render_evolution_box(name: str, params: list) -> str:
    """渲染进化框。

    参数结构：[1]=图鉴编号+名称, [2]=名称, [3]=属性1, [4]=属性2, ...
    对于复杂模板（如 进化框/月月熊），提取关键信息。
    """
    # 如果没有参数，可能是引用模板（如 {{进化框/月月熊}}）
    if not params:
        return f"【进化】{name.split('/')[-1]}\n"

    args = {}
    for i, (key, value) in enumerate(params):
        args[str(i + 1)] = value.strip()

    # 第一个参数通常是 图鉴编号+名称 格式
    first = args.get("1", "")
    name_from_first = re.sub(r'^\d+', '', first).strip()

    type1 = args.get("3", "")
    type2 = args.get("4", "")

    if name_from_first:
        if type1:
            return f"【进化】{name_from_first} ({type1}/{type2})\n" if type2 else f"【进化】{name_from_first} ({type1})\n"
        return f"【进化】{name_from_first}\n"
    return ""


def render_status_infobox(name: str, params: list) -> str:
    """渲染状态信息框，提取关键字段。

    参数结构：type=属性, name=名称, janame=日文名, enname=英文名, desc=描述, ...
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    zh_name = args.get("name", "")
    janame = args.get("janame", "")
    enname = args.get("enname", "")
    type1 = args.get("type", "")
    desc = args.get("desc", "")
    category = args.get("category", "")
    time = args.get("time", "")

    lines = []
    if zh_name:
        lines.append(f"【{zh_name}】")
    if janame:
        lines.append(f"日文名: {janame}")
    if enname:
        lines.append(f"英文名: {enname}")
    if type1:
        lines.append(f"属性: {type1}")
    if category:
        lines.append(f"分类: {category}")
    if time:
        lines.append(f"持续时间: {time}回合")

    # 清理描述中的 wiki 标记
    if desc:
        # 移除 -{zh-hans:...;zh-hant:...}- 格式，只保留简体中文
        desc = re.sub(r'-\{zh-hans:(.*?);zh-hant:.*?\}-', r'\1', desc)
        # 移除 [[链接|显示文本]] 格式
        desc = re.sub(r'\[\[([^|\]]+)\|([^\]]+)\]\]', r'\2', desc)
        # 移除 [[链接]] 格式
        desc = re.sub(r'\[\[([^\]]+)\]\]', r'\1', desc)
        lines.append(f"描述: {desc}")

    return "\n".join(lines) + "\n"


def render_weather_infobox(name: str, params: list) -> str:
    """渲染天气信息框，提取关键字段。

    参数结构：type=属性, name=名称, janame=日文名, enname=英文名, ...
    """
    args = {}
    for key, value in params:
        args[key] = value.strip()

    zh_name = args.get("name", "")
    janame = args.get("janame", "")
    enname = args.get("enname", "")
    type1 = args.get("type", "")

    lines = []
    if zh_name:
        lines.append(f"【{zh_name}】")
    if janame:
        lines.append(f"日文名: {janame}")
    if enname:
        lines.append(f"英文名: {enname}")
    if type1:
        lines.append(f"属性: {type1}")

    return "\n".join(lines) + "\n"


def render_field_effect(name: str, params: list) -> str:
    """渲染场地影响/天气影响模板。

    参数结构：[1]=场地/天气名称
    """
    args = {}
    for i, (key, value) in enumerate(params):
        args[str(i + 1)] = value.strip()

    effect_name = args.get("1", "")
    if effect_name:
        return f"【{name}】{effect_name}\n"
    return f"【{name}】\n"


# 结构化模板渲染函数映射
_STRUCTURED_RENDERERS = {
    # 宝可梦信息框
    "寶可夢信息框": render_pokemon_infobox,
    "寶可夢信息框/形態": render_pokemon_infobox,
    "宝可梦信息框": render_pokemon_infobox,

    # Toggle 折叠面板
    "Toggle/Header": render_toggle_header,
    "Toggle/Content": render_toggle_content,

    # 种族值
    "种族值": render_race_value,
    "種族值": render_race_value,

    # 属性相性
    "属性相性/header": render_type_effectiveness_header,
    "属性相性/entry": render_type_effectiveness_entry,

    # 获得方式
    "获得方式/header": render_obtain_header,
    "获得方式/main": render_obtain_main,
    "获得方式/end": render_obtain_end,

    # 进化框
    "进化框": render_evolution_box,
    "進化框": render_evolution_box,

    # 状态信息框
    "状态信息框": render_status_infobox,

    # 天气信息框
    "天气信息框": render_weather_infobox,

    # 场地影响/天气影响
    "招式/场地影响": render_field_effect,
    "招式/天气影响": render_field_effect,
}

# 前缀匹配的模板（变体模板，如 进化框/月月熊、进化框/形态 等）
_STRUCTURED_PREFIXES = [
    "进化框/",
    "進化框/",
]


def render_structured(name: str, params: list) -> str:
    """根据模板名调用对应的结构化渲染函数。"""
    # normalize 模板名（首字母大写）
    normalized = normalize_template_name(name)

    # 尝试精确匹配
    renderer = _STRUCTURED_RENDERERS.get(name) or _STRUCTURED_RENDERERS.get(normalized)
    if renderer:
        return renderer(name, params)

    # 模糊匹配（处理 /doc 等变体）
    base_name = name.split("/")[0]
    renderer = _STRUCTURED_RENDERERS.get(base_name)
    if renderer:
        return renderer(name, params)

    # 前缀匹配（处理 进化框/月月熊 等变体）
    for prefix in _STRUCTURED_PREFIXES:
        if name.startswith(prefix):
            renderer = _STRUCTURED_RENDERERS.get(prefix.rstrip("/"))
            if renderer:
                return renderer(name, params)

    # 兜底：返回空串
    return ""


# ============================================================
# parser function 识别与求值
# ============================================================
def _is_parser_function(name: str) -> bool:
    if not name:
        return True
    if name.startswith("#"):
        return True
    low = name.lower()
    if low.startswith("subst:") or low.startswith("safesubst:"):
        return True
    return False


def _eval_parser_function(name: str, params_list: list) -> str:
    """求值 MediaWiki parser function，返回结果文本。

    支持：#if:、#ifeq:、#expr:、#switch:、#ifexpr:
    params_list: mwparserfromhell 的 tpl.params 列表（Parameter 对象）
    """
    # mwparserfromhell 把 {{#if:10|a|b}} 解析为 name="#if:10"，params=[a, b]
    # 需要把 name 中 : 后的部分当作第一个参数
    if ":" in name:
        func, first_arg = name.split(":", 1)
    else:
        func, first_arg = name, ""

    func = func.strip().lower()
    # 把 name 中提取的第一个参数放到参数列表前面（字符串形式）
    all_args = ([first_arg] if first_arg else []) + [str(p.value) for p in params_list]

    def _arg(i: int) -> str:
        return all_args[i] if i < len(all_args) else ""

    if func == "#if":
        # {{#if:condition|then|else}} — condition 非空且非"0" → then
        cond = _arg(0)
        if cond and cond.strip() != "0":
            return _arg(1)
        return _arg(2)

    if func == "#ifeq":
        # {{#ifeq:string1|string2|then|else}}
        s1, s2 = _arg(0), _arg(1)
        return _arg(2) if s1.strip() == s2.strip() else _arg(3)

    if func == "#ifexpr":
        # {{#ifexpr:expr|then|else}}
        try:
            result = _safe_eval_expr(_arg(0))
            return _arg(1) if result else _arg(2)
        except Exception:
            return _arg(2)

    if func == "#expr":
        # {{#expr:expr}}
        try:
            return _safe_eval_expr(_arg(0))
        except Exception:
            return all_args[0] if all_args else ""

    if func == "#switch":
        # {{#switch:value|case1|case2=result|default}}
        # mwparserfromhell 解析：positional 是 case/fall-through，named 是 case=result
        value = _arg(0).strip()
        default = ""
        pending_cases = []  # fall-through case 累积
        for p in params_list:
            val = str(p.value).strip()
            if p.showkey:
                # named: case=result
                case_name = str(p.name).strip()
                pending_cases.append(case_name)
                if value in pending_cases:
                    return val
                pending_cases = []
            else:
                # positional: 可能是 case（fall-through）或 default
                pending_cases.append(val)
                default = val
        return default

    return ""


def _safe_eval_expr(expr: str) -> str:
    """安全求值数学表达式，只允许数字和基本运算符。"""
    expr = expr.strip()
    if not expr:
        return "0"
    # 只允许数字、小数点、运算符、括号、空格
    if not re.match(r'^[\d\.\+\-\*\/\(\)\s%]+$', expr):
        raise ValueError(f"不安全的表达式: {expr}")
    result = eval(expr, {"__builtins__": {}}, {})
    # 整数结果不带小数点
    if isinstance(result, float) and result == int(result):
        return str(int(result))
    return str(result)


# ============================================================
# 魔术词替换
# ============================================================
_MAGIC_WORDS = {
    "PAGENAME", "NBPAGENAME", "NOBRACKETPAGENAME", "BASEPAGENAME", "SUBPAGENAME",
    "FULLPAGENAME", "SUBJECTPAGENAME", "ARTICLEPAGENAME",
}


# ============================================================
# 模板正文加载器（只给 semantic 用）
# ============================================================
class SqliteTemplateLoader:
    """按模板名从 wiki_meta.db + wikitext_cache 加载模板正文。"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH, cache_dir: str = DEFAULT_CACHE_DIR):
        self.db_path = db_path
        self.cache_dir = cache_dir
        self._conn = None
        self._hit_cache: dict = {}
        self._miss_cache: set = set()

    def _conn_ready(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def __call__(self, name: str) -> Optional[str]:
        if name in self._hit_cache:
            return self._hit_cache[name]
        if name in self._miss_cache:
            return None

        title = TEMPLATE_NS_PREFIX + name
        conn = self._conn_ready()
        row = conn.execute(
            "SELECT file_path FROM wiki_pages WHERE title = ? AND status = 'done'",
            (title,),
        ).fetchone()
        if row is None or not row[0]:
            self._miss_cache.add(name)
            return None

        path = row[0]
        if not os.path.isabs(path):
            path = os.path.join(self.cache_dir, os.path.basename(path))
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            self._miss_cache.add(name)
            return None

        body = normalize_template_body(raw)
        self._hit_cache[name] = body
        return body

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ============================================================
# 展开器主体
# ============================================================
class TemplateExpander:
    """分类表驱动的模板递归展开器。"""

    def __init__(
        self,
        loader: Callable[[str], Optional[str]],
        classifier: Optional[ClassifierTable] = None,
        depth_limit: int = 5,
        unknown_behavior: str = "keep",  # drop / keep
        page_title: str = "",
    ):
        self.loader = loader
        self.classifier = classifier if classifier is not None else ClassifierTable()
        self.depth_limit = depth_limit
        self.unknown_behavior = unknown_behavior
        self.page_title = page_title

    def expand(self, wikitext: str, page_title: str = "") -> str:
        if page_title:
            self.page_title = page_title
        # 魔术词替换（在模板展开之前）
        if self.page_title:
            wikitext = self._replace_magic_words(wikitext, self.page_title)
        return self._expand(wikitext, self.depth_limit, frozenset())

    @staticmethod
    def _replace_magic_words(wikitext: str, page_title: str) -> str:
        """替换 {{PAGENAME}} 等魔术词为页面标题。"""
        for mw in _MAGIC_WORDS:
            wikitext = wikitext.replace("{{" + mw + "}}", page_title)
            wikitext = wikitext.replace("{{" + mw.lower() + "}}", page_title)
        return wikitext

    def _expand(self, wikitext: str, depth: int, stack: frozenset) -> str:
        if depth <= 0 or not wikitext:
            return wikitext
        # 魔术词替换（每次递归展开时都执行，处理模板正文中的魔术词）
        if self.page_title:
            wikitext = self._replace_magic_words(wikitext, self.page_title)

        prev = None
        cur = wikitext
        # 循环展开直到稳定（处理 parser function 求值后产生的新模板）
        while prev != cur and depth > 0:
            prev = cur
            cur = self._expand_pass(cur, depth, stack)
            depth -= 1
        return cur

    def _expand_pass(self, wikitext: str, depth: int, stack: frozenset) -> str:
        """单轮展开。"""
        try:
            code = mwparserfromhell.parse(wikitext)
        except Exception:
            return wikitext

        for tpl in list(code.filter_templates(recursive=True)):
            name = str(tpl.name).strip()
            if _is_parser_function(name):
                # parser function：求值替换
                try:
                    result = _eval_parser_function(name, tpl.params)
                    code.replace(tpl, result)
                except Exception:
                    pass  # 求值失败保留原样
                continue
            if name in stack:
                continue  # 循环守卫

            category, param_fmt, _ = self.classifier.lookup(name)

            # 收集参数
            args: dict = {}
            params: list = []   # [(key_or_pos, value)]
            pos = 0
            for p in tpl.params:
                val = str(p.value)
                if p.showkey:
                    key = str(p.name).strip()
                    args[key] = val
                    params.append((key, val))
                else:
                    pos += 1
                    args[str(pos)] = val
                    params.append((str(pos), val))
            positional_count = pos

            replacement = self._render(name, category, param_fmt, args, params, positional_count, depth, stack)
            try:
                code.replace(tpl, replacement)
            except ValueError:
                pass

        return str(code)

    def _render(
        self,
        name: str,
        category: str,
        param_fmt: str,
        args: dict,
        params: list,
        positional_count: int,
        depth: int,
        stack: frozenset,
    ) -> str:
        if category == CAT_DROP:
            return ""

        if category == CAT_INLINE:
            rendered = render_inline(name, args, positional_count, param_fmt)
            return self._expand(rendered, depth - 1, stack | {name})

        if category == CAT_INFOBOX:
            rendered = render_infobox(name, params, param_fmt)
            return self._expand(rendered, depth - 1, stack | {name})

        if category == CAT_SEMANTIC:
            body = self.loader(name)
            if body is None:
                # 分类说要展开但找不到模板正文 —— 保留调用体
                return "{{" + name + "|" + "|".join(v for _, v in params) + "}}" if params else "{{" + name + "}}"
            substituted = substitute_params(body, args)
            return self._expand(substituted, depth - 1, stack | {name})

        # structured —— 结构化模板，使用专门的渲染函数
        if category == "structured":
            rendered = render_structured(name, params)
            return self._expand(rendered, depth - 1, stack | {name})

        # unknown / 未识别分类
        if self.unknown_behavior == "keep":
            # 先展开参数中的内部模板
            expanded_params = []
            for key, value in params:
                expanded_value = self._expand(value, depth - 1, stack | {name})
                expanded_params.append((key, expanded_value))
            return "{{" + name + "|" + "|".join(v for _, v in expanded_params) + "}}" if expanded_params else "{{" + name + "}}"
        return ""


# ============================================================
# 便捷入口
# ============================================================
_default_loader: Optional[SqliteTemplateLoader] = None
_default_classifier: Optional[ClassifierTable] = None


def _get_default_loader() -> SqliteTemplateLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = SqliteTemplateLoader()
    return _default_loader


def _get_default_classifier() -> ClassifierTable:
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = ClassifierTable()
    return _default_classifier


def expand(
    wikitext: str,
    loader: Optional[Callable[[str], Optional[str]]] = None,
    classifier: Optional[ClassifierTable] = None,
    depth_limit: int = 5,
    unknown_behavior: str = "keep",
    page_title: str = "",
) -> str:
    if loader is None:
        loader = _get_default_loader()
    if classifier is None:
        classifier = _get_default_classifier()
    return TemplateExpander(
        loader, classifier=classifier, depth_limit=depth_limit, unknown_behavior=unknown_behavior
    ).expand(wikitext, page_title=page_title)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="展开 wiki 页面里的模板调用（分类表驱动）")
    parser.add_argument("file", help="要展开的 .wiki 文件路径")
    parser.add_argument("--depth", type=int, default=5, help="最大递归深度（默认 5）")
    parser.add_argument("--unknown", choices=["drop", "keep"], default="drop",
                        help="未分类模板处理：drop=删掉（默认）/ keep=保留原样")
    parser.add_argument("--page-title", default="",
                        help="页面标题（用于替换 PAGENAME/NBPAGENAME 等魔术词）")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        src = f.read()
    out = expand(src, depth_limit=args.depth, unknown_behavior=args.unknown, page_title=args.page_title)
    sys.stdout.write(out)
