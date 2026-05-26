"""
template_expander 单元测试（分类表驱动版）

覆盖：
- normalize_template_body / substitute_params
- inline 分类：$1 / $2 / $last / $name / 空 param_fmt
- infobox 分类：key_value / title_only
- semantic 分类：展开 body + 参数替换 + 嵌套
- drop 分类：整个删掉
- unknown 分类：默认 drop / keep
- 循环守卫 / depth_limit
- 集成测试：构造临时 wiki_meta.db + wiki_templates 表，展开血月招式片段，
  验证只保留语义文本，信息框和布局表被清理
"""

import os
import sys
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from template_expander import (
    ClassifierTable,
    TemplateExpander,
    normalize_template_body,
    normalize_template_name,
    substitute_params,
    render_inline,
    render_infobox,
    expand,
    CAT_SEMANTIC, CAT_INFOBOX, CAT_INLINE, CAT_DROP, CAT_UNKNOWN,
)


# ════════════════════════════════════════════════════════════════
# 测试脚手架：内存版 Classifier，不用真的 DB
# ════════════════════════════════════════════════════════════════
class FakeClassifier(ClassifierTable):
    """用 dict 构造，不读 DB。key 经过 first-letter 归一化以匹配真实表行为。"""

    def __init__(self, mapping: dict):
        # mapping: name -> (category, param_fmt)
        super().__init__(db_path=":memory:")
        self._rows = {
            normalize_template_name(k): (v[0], v[1] if len(v) > 1 else "", "")
            for k, v in mapping.items()
        }
        self._loaded = True


def build_expander(classifier_map: dict, templates: dict = None, unknown_behavior: str = "drop"):
    """构造一个独立 Expander。

    classifier_map: {模板名: (category, param_fmt)}
    templates:      {模板名: body_wikitext}   —— 仅 semantic 需要
    """
    templates = templates or {}
    normalized = {k: normalize_template_body(v) for k, v in templates.items()}

    def _load(name):
        return normalized.get(name)

    return TemplateExpander(
        loader=_load,
        classifier=FakeClassifier(classifier_map),
        unknown_behavior=unknown_behavior,
    )


# ════════════════════════════════════════════════════════════════
# 低层函数
# ════════════════════════════════════════════════════════════════
class TestNormalizeTemplateName(unittest.TestCase):
    """MediaWiki Template namespace 是 first-letter case —— ASCII 首字母自动大写。"""

    def test_lowercase_ascii_gets_uppercased(self):
        self.assertEqual(normalize_template_name("m"), "M")
        self.assertEqual(normalize_template_name("lang"), "Lang")

    def test_already_uppercase(self):
        self.assertEqual(normalize_template_name("M"), "M")
        self.assertEqual(normalize_template_name("Movelist/foo"), "Movelist/foo")

    def test_chinese_unchanged(self):
        self.assertEqual(normalize_template_name("招式信息框"), "招式信息框")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_template_name("  m  "), "M")

    def test_empty(self):
        self.assertEqual(normalize_template_name(""), "")
        self.assertEqual(normalize_template_name("  "), "")


class TestClassifierTableCasing(unittest.TestCase):
    """ClassifierTable 必须做 first-letter 归一化，否则 {{m|...}} 命中不了 Template:M。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="classifier_case_")
        self.db = os.path.join(self.tmp, "wiki_meta.db")
        conn = sqlite3.connect(self.db)
        conn.execute("""
            CREATE TABLE wiki_templates (
                name TEXT PRIMARY KEY, page_id INT, file_path TEXT,
                category TEXT, param_fmt TEXT, note TEXT, updated_at TEXT
            )
        """)
        # 表里存的是大写 "M"（MediaWiki 的实际存储形式）
        conn.execute("INSERT INTO wiki_templates (name, category, param_fmt) VALUES ('M', 'inline', '$last')")
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lowercase_call_hits_uppercase_row(self):
        c = ClassifierTable(db_path=self.db)
        # 不管页面里写 {{m|...}} 还是 {{M|...}}，都应命中同一条
        self.assertEqual(c.lookup("m"), ("inline", "$last", ""))
        self.assertEqual(c.lookup("M"), ("inline", "$last", ""))


class TestNormalizeTemplateBody(unittest.TestCase):
    def test_noinclude_stripped(self):
        self.assertEqual(normalize_template_body("body<noinclude>doc</noinclude>tail"), "bodytail")

    def test_includeonly_kept_content(self):
        self.assertEqual(normalize_template_body("keep<includeonly>this</includeonly>"), "keepthis")

    def test_onlyinclude_wins(self):
        self.assertEqual(normalize_template_body("outer<onlyinclude>inner</onlyinclude>more"), "inner")

    def test_case_insensitive_tags(self):
        self.assertEqual(normalize_template_body("A<NOINCLUDE>x</NoInclude>B"), "AB")


class TestSubstituteParams(unittest.TestCase):
    def test_positional(self):
        self.assertEqual(substitute_params("hi {{{1}}}!", {"1": "world"}), "hi world!")

    def test_named(self):
        self.assertEqual(substitute_params("x={{{name}}}", {"name": "Ash"}), "x=Ash")

    def test_default_value(self):
        self.assertEqual(substitute_params("{{{1|d}}}", {}), "d")
        self.assertEqual(substitute_params("{{{1|d}}}", {"1": "given"}), "given")

    def test_missing_no_default(self):
        self.assertEqual(substitute_params("{{{missing}}}", {}), "")


class TestRenderInline(unittest.TestCase):
    def test_last(self):
        self.assertEqual(render_inline("m", {"1": "挣扎"}, 1, "$last"), "挣扎")

    def test_pos_n(self):
        self.assertEqual(render_inline("m2", {"1": "招式", "2": "显示"}, 2, "$2"), "显示")

    def test_name(self):
        self.assertEqual(render_inline("PAGENAME", {}, 0, "$name"), "PAGENAME")

    def test_empty_fmt_fallback(self):
        # 无 fmt 时：末位参数，否则模板名
        self.assertEqual(render_inline("m", {"1": "挣扎"}, 1, ""), "挣扎")
        self.assertEqual(render_inline("NoArgs", {}, 0, ""), "NoArgs")

    def test_template_fmt(self):
        self.assertEqual(render_inline("link", {"1": "Link", "2": "Text"}, 2, "$1($2)"), "Link(Text)")


class TestRenderInfobox(unittest.TestCase):
    def test_key_value(self):
        params = [("威力", "140"), ("命中", "100"), ("empty", "")]
        out = render_infobox("招式信息框", params, "key_value")
        self.assertIn("【招式信息框】", out)
        self.assertIn("威力: 140", out)
        self.assertIn("命中: 100", out)
        self.assertNotIn("empty", out)

    def test_title_only(self):
        out = render_infobox("名字/entry", [("1", "ja"), ("2", "x")], "title_only")
        self.assertEqual(out.strip(), "【名字/entry】")

    def test_drop_body(self):
        out = render_infobox("X", [("a", "b")], "drop_body")
        self.assertEqual(out, "")

    def test_default_is_key_value(self):
        out = render_infobox("T", [("k", "v")], "")
        self.assertIn("k: v", out)


# ════════════════════════════════════════════════════════════════
# 分类行为
# ════════════════════════════════════════════════════════════════
class TestInlineCategory(unittest.TestCase):
    def test_m_takes_last_param(self):
        exp = build_expander({"m": (CAT_INLINE, "$last")})
        self.assertEqual(exp.expand("走 {{m|挣扎}} 路"), "走 挣扎 路")

    def test_lang_keeps_content(self):
        exp = build_expander({"lang": (CAT_INLINE, "$last")})
        out = exp.expand("{{lang|ja|ブラッドムーン}}")
        self.assertEqual(out, "ブラッドムーン")

    def test_fallback_when_no_fmt(self):
        exp = build_expander({"m": (CAT_INLINE, "")})
        self.assertEqual(exp.expand("{{m|挣扎}}"), "挣扎")


class TestInfoboxCategory(unittest.TestCase):
    def test_key_value_flattens_params(self):
        exp = build_expander({"招式信息框": (CAT_INFOBOX, "key_value")})
        src = "{{招式信息框|name=血月|威力=140|命中=100}}"
        out = exp.expand(src)
        self.assertIn("【招式信息框】", out)
        self.assertIn("威力: 140", out)
        self.assertIn("命中: 100", out)
        # 模板正文被丢弃，无 MediaWiki 表格标记
        self.assertNotIn("{|", out)

    def test_title_only_drops_params(self):
        exp = build_expander({"名字/entry": (CAT_INFOBOX, "title_only")})
        src = "{{名字/entry|ja|ブラッドムーン|roma=Blood Moon}}"
        out = exp.expand(src)
        self.assertIn("【名字/entry】", out)
        self.assertNotIn("Blood Moon", out)
        self.assertNotIn("ブラッドムーン", out)


class TestSemanticCategory(unittest.TestCase):
    def test_expands_and_substitutes(self):
        exp = build_expander(
            {"招式效果/X": (CAT_SEMANTIC, "")},
            templates={"招式效果/X": "规则：使用{{{1|该招式}}}后……"},
        )
        self.assertEqual(exp.expand("{{招式效果/X|血月}}"), "规则：使用血月后……")

    def test_nested_semantic(self):
        exp = build_expander(
            {
                "Outer": (CAT_SEMANTIC, ""),
                "Inner": (CAT_SEMANTIC, ""),
            },
            templates={
                "Outer": "OUT[{{Inner|{{{1}}}}}]",
                "Inner": "in-{{{1}}}-in",
            },
        )
        self.assertEqual(exp.expand("{{Outer|X}}"), "OUT[in-X-in]")

    def test_semantic_with_inline_inside(self):
        """semantic 正文里嵌了 inline 模板，应同步被 inline 规则处理。"""
        exp = build_expander(
            {
                "招式效果/连用": (CAT_SEMANTIC, ""),
                "m": (CAT_INLINE, "$last"),
                "s": (CAT_INLINE, "$last"),
            },
            templates={
                "招式效果/连用":
                "若处于{{s|再来一次}}状态，只能使出{{m|挣扎}}。",
            },
        )
        out = exp.expand("{{招式效果/连用|血月}}")
        self.assertIn("再来一次", out)
        self.assertIn("挣扎", out)
        self.assertNotIn("{{s", out)
        self.assertNotIn("{{m", out)


class TestDropCategory(unittest.TestCase):
    def test_drop_removes_entirely(self):
        exp = build_expander({"模板文档": (CAT_DROP, "")})
        out = exp.expand("正文前。{{模板文档}}正文后。")
        self.assertEqual(out, "正文前。正文后。")


class TestUnknownCategory(unittest.TestCase):
    def test_unknown_drop_by_default(self):
        exp = build_expander({}, unknown_behavior="drop")
        self.assertEqual(exp.expand("A{{NeverSeen|x}}B"), "AB")

    def test_unknown_keep_mode(self):
        exp = build_expander({}, unknown_behavior="keep")
        out = exp.expand("A{{NeverSeen|x}}B")
        self.assertIn("{{NeverSeen", out)


class TestSafety(unittest.TestCase):
    def test_parser_function_preserved(self):
        exp = build_expander({})
        out = exp.expand("{{#if:yes|A|B}}")
        self.assertIn("#if", out)

    def test_cycle_guard(self):
        exp = build_expander(
            {"A": (CAT_SEMANTIC, ""), "B": (CAT_SEMANTIC, "")},
            templates={"A": "a[{{B}}]", "B": "b[{{A}}]"},
        )
        out = exp.expand("{{A}}")
        # 不死循环，进入循环时栈守卫拦截
        self.assertIn("a[b[", out)

    def test_depth_limit(self):
        exp = build_expander(
            {"Loop": (CAT_SEMANTIC, "")},
            templates={"Loop": "x{{Loop}}"},
        )
        out = TemplateExpander(
            loader=exp.loader, classifier=exp.classifier, depth_limit=3
        ).expand("{{Loop}}")
        self.assertTrue(out.startswith("x"))


# ════════════════════════════════════════════════════════════════
# 集成：真实 wiki_meta.db + wiki_templates 表
# ════════════════════════════════════════════════════════════════
class TestIntegrationBloodMoon(unittest.TestCase):
    """构造临时 wiki_meta.db + wikitext_cache + wiki_templates 表，
    展开「血月招式」片段，验证：
      1. semantic 规则文本保留（再来一次 / 号令 / 梦话）
      2. infobox 被压平成 key: value，没有表格 markup
      3. inline 模板被替换为单词，<nowiki>{{m|…}}</nowiki> 不出现
      4. drop 模板整个消失（模板文档 / 神奇宝贝百科招式工程）
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wiki_expander_it_")
        self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.cache)
        self.db = os.path.join(self.tmp, "wiki_meta.db")
        conn = sqlite3.connect(self.db)
        conn.execute("""
            CREATE TABLE wiki_pages (
                page_id INTEGER PRIMARY KEY,
                title TEXT UNIQUE,
                namespace INTEGER,
                file_path TEXT,
                status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE wiki_templates (
                name TEXT PRIMARY KEY,
                page_id INTEGER,
                file_path TEXT,
                category TEXT,
                param_fmt TEXT,
                note TEXT,
                updated_at TEXT
            )
        """)
        self.conn = conn

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add_template(self, page_id, name, body, category, param_fmt=None):
        title = "Template:" + name
        safe = name.replace("/", "_")
        path = os.path.join(self.cache, f"{page_id}_{safe}.wiki")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        self.conn.execute(
            "INSERT INTO wiki_pages (page_id, title, namespace, file_path, status) "
            "VALUES (?, ?, 10, ?, 'done')",
            (page_id, title, path),
        )
        self.conn.execute(
            "INSERT INTO wiki_templates (name, page_id, file_path, category, param_fmt) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, page_id, path, category, param_fmt),
        )
        self.conn.commit()

    def test_blood_moon_page_fragment(self):
        # Semantic 模板：保留文本，带内嵌 inline
        self._add_template(
            1001, "招式效果/不能连续使用",
            "攻击目标造成伤害。若上个回合成功使用{{{1|这个招式}}}，则这个回合不能选择{{{1|这个招式}}}。\n"
            "若下一回合该宝可梦已处于{{s|再来一次}}状态，只能使出{{m|挣扎}}。\n"
            "以下情况可以实现连续２次使用{{{1|这个招式}}}：通过{{m|号令}}、{{m|梦话}}。",
            "semantic",
        )
        # Infobox 模板：不展开 body，只保留参数
        self._add_template(
            2001, "招式信息框",
            "{|...大量 MediaWiki 表格...{{#switch:{{{type}}}|...}}|}",
            "infobox", "key_value",
        )
        # Inline 模板：输出末位参数
        self._add_template(3001, "m", "[[{{{1}}}]]", "inline", "$last")
        self._add_template(3002, "s", "[[{{{1}}}]]", "inline", "$last")
        self._add_template(3003, "lang", "<span>{{{2}}}</span>", "inline", "$last")
        # Drop 模板：工程/版权声明
        self._add_template(4001, "模板文档", "TEMPLATE DOC DON'T SHOW", "drop")
        self._add_template(4002, "神奇宝贝百科招式工程", "PROJECT BANNER", "drop")

        src = """{{招式信息框|name=血月|威力=140|命中=100|分类=特殊|属性=一般|gen=9}}

==招式附加效果==
{{招式效果/不能连续使用|血月}}

==名字==
日文：{{lang|ja|ブラッドムーン}}

==细节==
* 血月是月月熊的专用招式。

{{模板文档}}
{{神奇宝贝百科招式工程}}"""

        # 覆盖默认 loader/classifier 指向临时 DB
        from template_expander import SqliteTemplateLoader, ClassifierTable
        loader = SqliteTemplateLoader(db_path=self.db, cache_dir=self.cache)
        classifier = ClassifierTable(db_path=self.db)
        out = expand(src, loader=loader, classifier=classifier)
        loader.close()

        # 1. semantic 文本保留
        self.assertIn("再来一次", out)
        self.assertIn("号令", out)
        self.assertIn("梦话", out)
        self.assertIn("血月", out)
        # 2. infobox 被压平
        self.assertIn("威力: 140", out)
        self.assertIn("命中: 100", out)
        self.assertNotIn("{|", out)
        self.assertNotIn("#switch", out)
        # 3. inline 被替换成单词
        self.assertIn("ブラッドムーン", out)
        self.assertNotIn("{{m|", out)
        self.assertNotIn("{{s|", out)
        self.assertNotIn("{{lang", out)
        # 4. drop 模板消失
        self.assertNotIn("TEMPLATE DOC", out)
        self.assertNotIn("PROJECT BANNER", out)
        # 5. 总行数合理（原 src 不到 15 行，展开后不该膨胀 10 倍）
        self.assertLess(len(out.splitlines()), 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
