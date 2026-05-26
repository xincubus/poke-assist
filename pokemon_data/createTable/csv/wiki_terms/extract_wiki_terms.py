"""
从缓存的 52poke HTML 中提取结构化术语数据。

输出 wiki_terms.json，每条记录包含：
  title, url, sections (按 h2/h3 分段的正文), internal_links (内链术语)

用法：
    python extract_wiki_terms.py
    python extract_wiki_terms.py --stats   # 只输出统计
"""

import os
import re
import json
import argparse
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "html_cache")
INDEX_FILE = os.path.join(SCRIPT_DIR, "page_index.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "wiki_terms.json")

SKIP_SECTIONS = {"目录", "名字", "各语言名字", "参见", "參見", "外部链接", "细节", "注释", "参考资料", "漫画中", "动画中", "旁支系列中", "卡牌游戏中"}
SKIP_PREFIXES = ("卡牌游戏中", "在《", "漫画中", "动画中", "旁支系列", "Pokémon GO中")

# PLACEHOLDER_NEXT_CHUNK

class ContentExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []
        self.internal_links = []
        self.in_content = False
        self.in_heading = False
        self.heading_tag = ""
        self.heading_text = ""
        self.current_section = None
        self.text_buf = []
        self.in_table = 0
        self.in_ref = False
        self.skip_section = False
        self._seen_links = set()

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "div" and "mw-parser-output" in attrs_dict.get("class", ""):
            self.in_content = True
            self.current_section = {"heading": "概述", "level": 2}
            self.text_buf = []
            return

        if not self.in_content:
            return

        if tag in ("h2", "h3"):
            self.in_heading = True
            self.heading_tag = tag
            self.heading_text = ""
            return

        if tag == "table":
            self.in_table += 1

        if tag == "ref" or (tag == "sup" and "reference" in attrs_dict.get("class", "")):
            self.in_ref = True

        if tag == "a" and not self.skip_section:
            href = attrs_dict.get("href", "")
            if href.startswith("/wiki/") and ":" not in href[6:] and "#" not in href:
                from urllib.parse import unquote
                link_title = unquote(href[6:])
                if link_title not in self._seen_links:
                    self._seen_links.add(link_title)
                    self.internal_links.append(link_title)

    def handle_endtag(self, tag):
        if tag in ("h2", "h3") and self.in_heading:
            self.in_heading = False
            title = self.heading_text.strip()

            if self.current_section and not self.skip_section:
                text = self._flush_text()
                if text:
                    self.current_section["text"] = text
                self.sections.append(self.current_section)

            self.skip_section = (
                title in SKIP_SECTIONS
                or any(title.startswith(p) for p in SKIP_PREFIXES)
            )

            self.current_section = {
                "heading": title,
                "level": 2 if self.heading_tag == "h2" else 3,
            }
            self.text_buf = []
            return

        if tag == "table":
            self.in_table = max(0, self.in_table - 1)

        if tag in ("ref", "sup"):
            self.in_ref = False

    def handle_data(self, data):
        if self.in_heading:
            if data.strip() not in ("[", "]", "编辑"):
                self.heading_text += data
            return

        if (
            self.in_content
            and not self.skip_section
            and not self.in_ref
            and self.in_table == 0
            and self.current_section is not None
        ):
            self.text_buf.append(data)

    def _flush_text(self) -> str:
        raw = "".join(self.text_buf).strip()
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        lines = [l.strip() for l in raw.split("\n")]
        return "\n".join(l for l in lines if l)

    def finalize(self):
        if self.current_section and not self.skip_section:
            text = self._flush_text()
            if text:
                self.current_section["text"] = text
            self.sections.append(self.current_section)


def extract_page(html: str) -> dict:
    extractor = ContentExtractor()
    extractor.feed(html)
    extractor.finalize()

    sections = [s for s in extractor.sections if s.get("text")]
    return {
        "sections": sections,
        "internal_links": extractor.internal_links,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    results = []
    errors = []

    for item in index:
        cache_file = item.get("cache_file")
        if not cache_file or "error" in item:
            continue

        filepath = os.path.join(CACHE_DIR, cache_file)
        if not os.path.exists(filepath):
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()
            data = extract_page(html)
            data["title"] = item["title"]
            data["url"] = item["url"]
            if data["sections"]:
                results.append(data)
        except Exception as e:
            errors.append({"title": item["title"], "error": str(e)})

    if args.stats:
        total_sections = sum(len(r["sections"]) for r in results)
        total_links = sum(len(r["internal_links"]) for r in results)
        print(f"页面: {len(results)}")
        print(f"段落: {total_sections}")
        print(f"内链: {total_links}")
        if errors:
            print(f"错误: {len(errors)}")
            for e in errors:
                print(f"  {e['title']}: {e['error']}")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(results)} 条到 {OUTPUT_FILE}")
    if errors:
        print(f"错误 {len(errors)} 条:")
        for e in errors:
            print(f"  {e['title']}: {e['error']}")


if __name__ == "__main__":
    main()
