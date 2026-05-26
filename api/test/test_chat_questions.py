"""
对话测试脚本 - 测试 100 个问题并生成报告
用法: python -m api.test.test_chat_questions [--url URL] [--range 1-10] [--timeout 120]
  或: cd api/test && python test_chat_questions.py [...]
"""
import requests
import json
import time
import argparse
import sys
import os
from datetime import datetime

# 输出目录：api/test/responses/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESPONSES_DIR = os.path.join(SCRIPT_DIR, "responses")
QUESTIONS_MD = os.path.join(SCRIPT_DIR, "test_questions.md")


def load_questions(md_path=QUESTIONS_MD):
    """从 test_questions.md 解析问题列表，返回与原 QUESTIONS 格式相同的列表。

    md 格式：
        N. 问题文本
           > type:xxx | kw:关键词1,关键词2
    category 从最近的 ## 标题推断。
    """
    import re
    questions = []
    current_category = "综合"
    last_question = None  # (qid, category, text)

    section_map = {
        "一": "伤害计算", "二": "招式查询", "三": "宝可梦查询",
        "四": "属性克制", "五": "道具查询", "六": "术语查询", "七": "综合",
    }

    with open(md_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()

            # 识别 ## 章节标题，推断分类
            m = re.match(r"^## [一二三四五六七]", line)
            if m:
                for key, val in section_map.items():
                    if key in line:
                        current_category = val
                        break
                continue

            # 识别题目行：以数字+点开头
            m = re.match(r"^\s*(\d+)\.\s+(.+)", line)
            if m:
                # 先把上一题（无元数据）存入
                if last_question:
                    qid, cat, text = last_question
                    questions.append((qid, cat, text, {"type": None, "keywords": []}))
                last_question = (int(m.group(1)), current_category, m.group(2).strip())
                continue

            # 识别元数据行：> type:xxx | kw:...
            m = re.match(r"^\s*>\s*(.+)", line)
            if m and last_question:
                meta_str = m.group(1)
                expect = {"type": None, "keywords": []}
                for part in meta_str.split("|"):
                    part = part.strip()
                    if part.startswith("type:"):
                        val = part[5:].strip()
                        expect["type"] = val if val else None
                    elif part.startswith("kw:"):
                        kws = [k.strip() for k in part[3:].split(",") if k.strip()]
                        expect["keywords"] = kws
                qid, cat, text = last_question
                questions.append((qid, cat, text, expect))
                last_question = None
                continue

        # 最后一题没有元数据行
        if last_question:
            qid, cat, text = last_question
            questions.append((qid, cat, text, {"type": None, "keywords": []}))

    questions.sort(key=lambda x: x[0])
    return questions


QUESTIONS = load_questions()


# ==================== 判定逻辑 ====================

class TestResult:
    """单条测试结果"""
    def __init__(self, qid, category, question):
        self.qid = qid
        self.category = category
        self.question = question
        self.status = "SKIP"      # PASS / FAIL / ERROR / SKIP
        self.http_code = None
        self.resp_type = None     # 实际返回的 type
        self.response = ""        # 完整回复文本
        self.raw_json = None      # 完整 JSON 响应
        self.fail_reasons = []
        self.elapsed = 0.0

    def to_dict(self):
        return {
            "id": self.qid,
            "category": self.category,
            "question": self.question,
            "status": self.status,
            "http_code": self.http_code,
            "resp_type": self.resp_type,
            "response": self.response,
            "fail_reasons": self.fail_reasons,
            "elapsed_s": round(self.elapsed, 2),
        }


def judge(result_obj: TestResult, resp_json: dict, expect: dict):
    """根据返回结果判定通过/失败"""
    reasons = []

    success = resp_json.get("success", False)
    if not success:
        reasons.append(f"success=False, error={resp_json.get('error', resp_json.get('detail', ''))}")

    actual_type = resp_json.get("type", "")
    result_obj.resp_type = actual_type
    if expect.get("type") and actual_type not in expect["type"].split("/"):
        reasons.append(f"期望type={expect['type']}, 实际type={actual_type}")

    response_text = resp_json.get("response", "")
    result_obj.response = response_text
    result_obj.raw_json = resp_json
    if not response_text or len(response_text.strip()) < 5:
        reasons.append("response 为空或过短")

    if expect.get("keywords"):
        missing = []
        for kw in expect["keywords"]:
            if "/" in kw:
                # 用 / 分隔的关键词，命中任意一个即可
                if not any(alt in response_text for alt in kw.split("/")):
                    missing.append(kw)
            else:
                if kw not in response_text:
                    missing.append(kw)
        if missing:
            reasons.append(f"缺少关键词: {missing}")

    error_phrases = ["出错", "抱歉", "error", "找不到"]
    has_error = any(p in response_text[:50] for p in error_phrases)
    if has_error and success:
        reasons.append("回复疑似包含错误信息")

    result_obj.fail_reasons = reasons
    result_obj.status = "PASS" if not reasons else "FAIL"


# ==================== 测试执行 ====================

def run_tests(base_url, q_range=None, timeout=120, verbose=False):
    """执行测试"""
    questions = QUESTIONS
    if q_range:
        start, end = q_range
        questions = [q for q in QUESTIONS if start <= q[0] <= end]

    results = []
    total = len(questions)

    print(f"\n{'='*60}")
    print(f"  对话测试 - 共 {total} 题")
    print(f"  服务器: {base_url}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for i, (qid, category, question, expect) in enumerate(questions):
        result = TestResult(qid, category, question)
        prefix = f"[{i+1}/{total}] Q{qid:03d}"

        try:
            t0 = time.time()
            resp = requests.post(
                f"{base_url}/api/chat",
                json={"message": question, "debug": True},
                timeout=timeout,
            )
            result.elapsed = time.time() - t0
            result.http_code = resp.status_code

            if resp.status_code != 200:
                result.status = "ERROR"
                result.fail_reasons = [f"HTTP {resp.status_code}: {resp.text[:200]}"]
                result.response = resp.text[:500]
            else:
                resp_json = resp.json()
                judge(result, resp_json, expect)

        except requests.exceptions.Timeout:
            result.status = "ERROR"
            result.fail_reasons = [f"请求超时 (>{timeout}s)"]
        except requests.exceptions.ConnectionError:
            result.status = "ERROR"
            result.fail_reasons = ["无法连接服务器"]
        except Exception as e:
            result.status = "ERROR"
            result.fail_reasons = [str(e)]

        result.finished_at = datetime.now().strftime("%H:%M:%S")
        icon = {"PASS": "+", "FAIL": "-", "ERROR": "!", "SKIP": "?"}[result.status]
        line = f"  {prefix} [{icon}] ({result.elapsed:.1f}s) [{result.finished_at}] {question[:40]}"
        if result.status != "PASS":
            line += f"  << {'; '.join(result.fail_reasons)[:60]}"
        print(line)

        # 打印各阶段耗时
        resp_timings = result.raw_json.get("timings") if result.raw_json else None
        if resp_timings:
            parts = []
            for k, v in resp_timings.items():
                parts.append(f"{k}={v}s")
            print(f"         耗时明细: {' | '.join(parts)}")

        if verbose and result.response:
            print(f"         回复: {result.response[:120]}...")

        results.append(result)

    return results


def print_report(results):
    """打印汇总报告"""
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")

    print(f"\n{'='*60}")
    print(f"  测试报告")
    print(f"{'='*60}")
    print(f"  总计: {total}  通过: {passed}  失败: {failed}  错误: {errors}")
    print(f"  通过率: {passed/total*100:.1f}%")

    # 按分类统计
    categories = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total": 0, "pass": 0, "fail": 0, "error": 0}
        categories[cat]["total"] += 1
        if r.status == "PASS":
            categories[cat]["pass"] += 1
        elif r.status == "FAIL":
            categories[cat]["fail"] += 1
        else:
            categories[cat]["error"] += 1

    print(f"\n  分类统计:")
    print(f"  {'分类':<12} {'总数':>4} {'通过':>4} {'失败':>4} {'错误':>4} {'通过率':>8}")
    print(f"  {'-'*44}")
    for cat, stats in categories.items():
        rate = stats["pass"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  {cat:<12} {stats['total']:>4} {stats['pass']:>4} {stats['fail']:>4} {stats['error']:>4} {rate:>7.1f}%")

    # 列出失败/错误的题目
    failures = [r for r in results if r.status in ("FAIL", "ERROR")]
    if failures:
        print(f"\n  失败/错误详情 ({len(failures)} 题):")
        print(f"  {'-'*56}")
        for r in failures:
            print(f"  Q{r.qid:03d} [{r.status}] {r.question[:35]}")
            for reason in r.fail_reasons:
                print(f"        -> {reason[:70]}")

    # 耗时统计
    times = [r.elapsed for r in results if r.elapsed > 0]
    if times:
        print(f"\n  耗时统计:")
        print(f"    平均: {sum(times)/len(times):.1f}s  "
              f"最快: {min(times):.1f}s  最慢: {max(times):.1f}s  "
              f"总计: {sum(times):.0f}s")

    print(f"{'='*60}\n")


def save_responses(results, run_dir):
    """保存每题的完整回复文本到 responses/ 子目录"""
    os.makedirs(run_dir, exist_ok=True)

    # 1. 保存每题的完整回复为单独 txt
    for r in results:
        filepath = os.path.join(run_dir, f"Q{r.qid:03d}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"问题: {r.question}\n")
            f.write(f"分类: {r.category}\n")
            f.write(f"状态: {r.status}\n")
            f.write(f"耗时: {r.elapsed:.2f}s\n")
            f.write(f"完成时间: {getattr(r, 'finished_at', 'N/A')}\n")
            f.write(f"意图: {r.resp_type}\n")
            # 写入各阶段耗时
            timings = r.raw_json.get("timings") if r.raw_json else None
            if timings:
                f.write(f"\n各阶段耗时:\n")
                label_map = {
                    "rag_s1": "RAG检索(Step1)",
                    "llm1": "LLM#1(意图识别)",
                    "rag_s2": "RAG检索(Step2)",
                    "llm2": "LLM#2(参数提取)",
                    "calc": "计算器执行",
                    "llm3": "LLM#3(结果总结)",
                    "llm_chat": "LLM(聊天回答)",
                    "llm_query": "LLM(查询工具)",
                }
                for key, val in timings.items():
                    label = label_map.get(key, key)
                    f.write(f"  {label}: {val}s\n")
            if r.fail_reasons:
                f.write(f"失败原因: {'; '.join(r.fail_reasons)}\n")
            f.write(f"\n{'='*40}\n回复内容:\n{'='*40}\n\n")
            f.write(r.response if r.response else "(无回复)")

            # 写入 LLM 调用记录
            llm_calls = r.raw_json.get("llm_calls") if r.raw_json else None
            if llm_calls:
                f.write(f"\n\n{'='*40}\nLLM 调用记录\n{'='*40}\n")
                for entry in llm_calls:
                    f.write(f"\n--- Call #{entry['call']} {entry['purpose']} ---\n")
                    for msg in entry.get("messages", []):
                        role = msg.get("role", "?")
                        content = msg.get("content", "")
                        tool_calls = msg.get("tool_calls")
                        tool_call_id = msg.get("tool_call_id")
                        if role == "assistant" and tool_calls:
                            tc_desc = ", ".join(f"{tc['name']}({tc.get('args', '')[:200]})" for tc in tool_calls)
                            f.write(f"[assistant] → 调用工具: {tc_desc}\n")
                        elif role == "tool":
                            result_preview = content
                            f.write(f"[tool] {result_preview}\n")
                        else:
                            f.write(f"[{role}] {content}\n")
                    if "reasoning" in entry:
                        f.write(f"\n[LLM思考] {entry['reasoning']}\n")
                    if "reply" in entry:
                        f.write(f"\n[LLM回复] {entry['reply']}\n")

    # 2. 保存汇总 JSON 报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.status == "PASS"),
            "failed": sum(1 for r in results if r.status == "FAIL"),
            "errors": sum(1 for r in results if r.status == "ERROR"),
        },
        "results": [r.to_dict() for r in results],
    }
    report_path = os.path.join(run_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  回复已保存到: {run_dir}/")
    print(f"    - Q001.txt ~ Q100.txt (每题完整回复)")
    print(f"    - report.json (汇总报告)")


# ==================== 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="对话测试脚本")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="API 地址 (默认 http://localhost:8000)")
    parser.add_argument("--range", type=str, default=None,
                        help="测试范围，如 1-25 或 26-45")
    parser.add_argument("--timeout", type=int, default=120,
                        help="单题超时秒数 (默认 120)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="显示回复内容预览")
    args = parser.parse_args()

    # 解析范围
    q_range = None
    if args.range:
        parts = args.range.split("-")
        q_range = (int(parts[0]), int(parts[1]))

    # 先检查服务器连通性
    try:
        r = requests.get(f"{args.url}/", timeout=5)
        if r.status_code != 200:
            print(f"服务器返回异常: HTTP {r.status_code}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"无法连接服务器: {args.url}")
        print("请先启动服务: cd api && python main.py")
        sys.exit(1)

    results = run_tests(args.url, q_range, args.timeout, args.verbose)
    print_report(results)

    # 保存到 api/test/responses/<timestamp>/
    run_dir = os.path.join(RESPONSES_DIR, datetime.now().strftime("%Y%m%d_%H%M%S"))
    save_responses(results, run_dir)


if __name__ == "__main__":
    main()
