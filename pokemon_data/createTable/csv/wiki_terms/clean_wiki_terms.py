"""
清洗 wiki_terms.json，输出 wiki_terms_clean.json。

处理：
1. 合并同一页面的多个"概述" section
2. 清理消歧义/重定向提示文本
3. 去掉杂页（Template、talk、User）
4. 去掉纯链接列表的 section（相关条目等）
5. 去掉极短无意义 section
6. 为每个页面生成 summary（第一段有效文本）

用法：
    python clean_wiki_terms.py
    python clean_wiki_terms.py --stats
"""

from __future__ import annotations

import os
import re
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "wiki_terms.json")
INDEX_FILE = os.path.join(SCRIPT_DIR, "page_index.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "wiki_terms_clean.json")

JUNK_TITLE_PATTERNS = ["Template:", "User:", "talk:"]

SKIP_SECTIONS = {"相关条目", "相关链接", "外部链接", "另请参阅", "参考"}

DISAMBIG_PATTERNS = [
    re.compile(r"^.*?重定向至此。.*?(?:请移步|参见).*?[。\n]", re.MULTILINE),
    re.compile(r"^这篇文章讲述的是.*?(?:请移步|参见).*?[。\n]", re.MULTILINE),
    re.compile(r"^如果您在寻找.*?(?:请移步|参见).*?[。\n]", re.MULTILINE),
    re.compile(r"^关于.*?(?:请移步|参见).*?[。\n]", re.MULTILINE),
]


def clean_text(text: str) -> str:
    for pat in DISAMBIG_PATTERNS:
        text = pat.sub("", text)
    text = text.strip()
    return text


def merge_overview_sections(sections: list[dict]) -> list[dict]:
    """合并连续的概述 section。"""
    result = []
    overview_buf = []

    for s in sections:
        if s["heading"] == "概述":
            overview_buf.append(s.get("text", ""))
        else:
            if overview_buf:
                merged_text = "\n".join(t for t in overview_buf if t)
                result.append({
                    "heading": "概述",
                    "level": 2,
                    "text": merged_text,
                })
                overview_buf = []
            result.append(s)

    if overview_buf:
        merged_text = "\n".join(t for t in overview_buf if t)
        result.append({
            "heading": "概述",
            "level": 2,
            "text": merged_text,
        })

    return result


def extract_summary(sections: list[dict]) -> str:
    """从第一个有效 section 提取摘要（第一句或前 200 字）。"""
    for s in sections:
        text = s.get("text", "").strip()
        if len(text) < 10:
            continue
        # 取第一个句号或前 200 字
        end = text.find("。")
        if end != -1 and end < 300:
            return text[:end + 1]
        return text[:200]
    return ""


def clean_page(page: dict) -> dict | None:
    # 跳过杂页
    for pat in JUNK_TITLE_PATTERNS:
        if pat in page["title"]:
            return None

    sections = page.get("sections", [])

    # 合并概述
    sections = merge_overview_sections(sections)

    # 清洗每个 section
    cleaned_sections = []
    for s in sections:
        if s["heading"] in SKIP_SECTIONS:
            continue

        text = clean_text(s.get("text", ""))

        if len(text) < 5:
            continue

        cleaned_sections.append({
            "heading": s["heading"],
            "level": s["level"],
            "text": text,
        })

    if not cleaned_sections:
        return None

    summary = extract_summary(cleaned_sections)

    return {
        "title": page["title"],
        "url": page["url"],
        "summary": summary,
        "sections": cleaned_sections,
        "internal_links": page.get("internal_links", []),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 加载分类信息
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        idx = json.load(f)
    title_to_cat = {x["title"]: x.get("category", "?") for x in idx}

    results = []
    removed = 0
    for page in data:
        cleaned = clean_page(page)
        if cleaned:
            cleaned["category"] = title_to_cat.get(page["title"], "未分类")
            results.append(cleaned)
        else:
            removed += 1

    if args.stats:
        from collections import Counter
        print(f"输入: {len(data)} 页")
        print(f"输出: {len(results)} 页 (去掉 {removed})")
        total_sections = sum(len(x["sections"]) for x in results)
        print(f"段落: {total_sections}")

        # 概述重复检查
        dup = sum(1 for x in results if sum(1 for s in x["sections"] if s["heading"] == "概述") > 1)
        print(f"仍有多个概述: {dup} 页")

        # 分类统计
        cat_count = Counter(x["category"] for x in results)
        print("\n按分类:")
        for c, n in cat_count.most_common():
            print(f"  {c}: {n}")

        # summary 质量
        no_summary = sum(1 for x in results if not x["summary"])
        print(f"\n无摘要: {no_summary} 页")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"已保存 {len(results)} 条到 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
